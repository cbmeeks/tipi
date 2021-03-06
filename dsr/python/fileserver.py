#!/usr/bin/env python2
import sys
import traceback
import logging
import logging.handlers
import time
import os
import errno
import RPi.GPIO as GPIO 
from array import array
import re
from ti_files import ti_files
from tipi.TipiMessage import TipiMessage
from tifloat import tifloat
from tinames import tinames
from SpecialFiles import SpecialFiles
from Pab import *
from RawExtensions import RawExtensions
from ResetHandler import createResetListener

#
# Setup logging
#
logpath = "/var/log/tipi"
try:
    os.makedirs(logpath)
except OSError as exc:
    if exc.errno == errno.EEXIST and os.path.isdir(logpath):
        pass
    else: raise

LOG_FILENAME = "/var/log/tipi/tipi.log"
logging.getLogger('').setLevel(logging.DEBUG)
loghandler = logging.handlers.RotatingFileHandler(
                 LOG_FILENAME, maxBytes=(5000 * 1024), backupCount=5)
logformatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
loghandler.setFormatter(logformatter)
logging.getLogger('').addHandler(loghandler)

logger = logging.getLogger('tipi')
oled = logging.getLogger('oled')

#
# Utils
#

def handleNotSupported(pab, devname):
    logger.warn("Opcode not supported: " + str(opcode(pab)))
    sendErrorCode(EILLOP)

def sendErrorCode(code):
    logger.error("responding with error: " + str(code))
    sendSingleByte(code)

def sendSuccess():
    logger.debug("responding with success!")
    sendSingleByte(SUCCESS)

def sendSingleByte(byte):
    msg = bytearray(1)
    msg[0] = byte
    tipi_io.send(msg)

openRecord = { }

def handleOpen(pab, devname):
    global openRecord
    logger.debug("Opcode 0 Open - %s", devname)
    logPab(pab)
    localPath = tinames.devnameToLocal(devname)
    logger.debug("  local file: " + localPath)
    if mode(pab) == INPUT and not os.path.exists(localPath):
        sendErrorCode(EFILERR)
        return

    if os.path.isdir(localPath) and mode(pab) == INPUT and dataType(pab) == INTERNAL and recordType(pab) == FIXED:
        sendSuccess()
        # since it is a directory the recordlength is 38, often it is opened with no value.
        # TODO: if they specify the longer filename record length, and recordType, then this will be different
        #       for implementation of long file name handling
        tipi_io.send([38])
        openRecord[localPath] = 0
        return

    if os.path.exists(localPath):
        fh = None
        try:
            fh = open(localPath, 'rb')
            bytes = bytearray(fh.read())
            if not ti_files.isValid(bytes):
                raise Exception("not tifiles format")
            if dataType(pab) == DISPLAY and ti_files.isInternal(bytes):
                raise Exception("cannot open as DISPLAY")
            if dataType(pab) == INTERNAL and not ti_files.isInternal(bytes):
                raise Exception("cannot open as INTERNAL")
            if recordType(pab) == FIXED and ti_files.isVariable(bytes):
                raise Exception("cannot open as FIXED")
            if recordType(pab) == VARIABLE and not ti_files.isVariable(bytes):
                raise Exception("cannot open as VARIABLE")
            if recordLength(pab) != 0 and (ti_files.recordLength(bytes) != recordLength(pab)):
                raise Exception("record length mismatch")
            fillInRecordLen = ti_files.recordLength(bytes)

            sendSuccess()
            tipi_io.send([fillInRecordLen])
            openRecord[localPath] = 0
            return

        except Exception as e:
            sendErrorCode(EOPATTR)
            logger.exception("failed to open file - %s", devname)
            return
        finally:
            if fh != None:
                fh.close()

    else:
        pass
        # TODO: check that any parent directory specified does exist. 

    sendErrorCode(EFILERR)

def handleClose(pab, devname):
    logger.debug("Opcode 1 Close - %s", devname)
    logPab(pab)
    sendSuccess()
    try:
        del openRecord[tinames.devnameToLocal(devname)]
    except Exception as e:
        # I don't care if close is called while file is not open
        pass

def handleRead(pab, devname):
    logger.debug("Opcode 2 Read - %s", devname)
    logPab(pab)
    localPath = tinames.devnameToLocal(devname)

    if not os.path.exists(localPath):
       sendErrorCode(EFILERR)
       return


    recNum = recordNumber(pab)
    # UNSPEC'ED
    # TI software is too lazy to increment record number because TIFDC didn't require it.
    if recNum == 0:
	recNum = openRecord[localPath]

    if os.path.isdir(localPath) and mode(pab) == INPUT and dataType(pab) == INTERNAL and recordType(pab) == FIXED:
        logger.debug("  local file: %s", localPath)

	try:
	    if recNum == 0:
		sendSuccess()
		vdata = createVolumeData(localPath)
		tipi_io.send(vdata)
		return
	    else:
		fdata = createFileCatRecord(localPath,recNum)
		if len(fdata) == 0:
		    sendErrorCode(EEOF)
		else:
		    sendSuccess()
		    tipi_io.send(fdata)
		return
	except:
	    pass
	finally:
	    openRecord[localPath] += 1

    if os.path.exists(localPath):
        fdata = createFileReadRecord(localPath,recNum)
        if fdata == None:
            sendErrorCode(EEOF)
        else:
            sendSuccess()
            tipi_io.send(fdata)
	openRecord[localPath] += 1
        return

    sendErrorCode(EFILERR)

def handleWrite(pab, devname):
    logger.info("Opcode 3 Write - %s", devname)
    logPab(pab)
    sendErrorCode(EDEVERR)

def handleRestore(pab, devname):
    logger.info("Opcode 4 Restore - %s", devname)
    logPab(pab)
    sendErrorCode(EDEVERR)

def handleLoad(pab, devname):
    logger.info("Opcode 5 LOAD - %s", devname)
    logPab(pab)
    maxsize = recordNumber(pab)
    unix_name = tinames.devnameToLocal(devname)
    fh = None
    try:
        fh = open(unix_name, 'rb')
        bytes = bytearray(fh.read())
        # TODO: check that it fits in maxsize
        ti_files.showHeader(bytes)
        if not ti_files.isValid(bytes):
            raise Exception("not tifiles format")
        if not ti_files.isProgram(bytes):
            raise Exception("not PROGRAM image file")
        filesize = ti_files.byteLength(bytes)
        sendSuccess()

        # Just cause DSR doesn't have a global SYN for reading.
        filesizemsb = (filesize & 0xFF00) >> 8
        filesizelsb = (filesize & 0xFF)

        tipi_io.send((bytes[128:])[:filesize])

    except Exception as e:
        # I don't think this will work. we need to check for as many errors as possible up front.
        sendErrorCode(EFILERR)
        logger.exception("failed to load file - %s", devname)
    finally:
        if fh != None:
            fh.close()
    
def handleSave(pab, devname):
    logger.info("Opcode 6 Save - %s", devname)
    logPab(pab)
    sendErrorCode(EDEVERR)

def handleDelete(pab, devname):
    logger.info("Opcode 7 Delete - %s", devname)
    logPab(pab)
    sendErrorCode(EDEVERR)

def handleScratch(pab, devname):
    logger.info("Opcode 8 Scratch - %s", devname)
    logPab(pab)
    sendErrorCode(EDEVERR)

def handleStatus(pab, devname):
    logger.info("Opcode 9 Status - %s", devname)
    logPab(pab)
    sendErrorCode(EDEVERR)

def createVolumeData(path):
    return encodeDirRecord("TIPI", 0, 1440, 1438)

def createFileCatRecord(path,recordNumber):
    files = sorted(list(filter(lambda x : os.path.isdir(os.path.join(path,x)) or ti_files.isTiFile(str(os.path.join(path,x))), os.listdir(path))))
    fh = None
    try:
        f = files[recordNumber - 1]

        if os.path.isdir(os.path.join(path,f)):
            return encodeDirRecord(f, 6, 2, 0)
      
        fh = open(os.path.join(path, f), 'rb')

        header = bytearray(fh.read()[:128])

        ft = ti_files.dsrFileType(header)
        sectors = ti_files.getSectors(header) + 1
        recordlen = ti_files.recordLength(header)
        return encodeDirRecord(f, ft, sectors, recordlen)


    except Exception as e:
        return encodeDirRecord("",0,0,0)
        
    finally:
        if fh != None:
            fh.close()

def encodeDirRecord(name, ftype, sectors, recordLength):
    bytes = bytearray(38)

    shortname = tinames.asTiShortName(name)

    bytes[0] = len(shortname)
    i = 1
    for c in shortname:
        bytes[i] = c
        i += 1
    ft = tifloat.asFloat(ftype)
    for b in ft:
        bytes[i] = b
        i += 1
    sc = tifloat.asFloat(sectors)
    for b in sc:
        bytes[i] = b
        i += 1
    rl = tifloat.asFloat(recordLength)
    for b in rl:
        bytes[i] = b
        i += 1
    for i in range(i,38):
        bytes[i] = 0

    return bytes

def createFileReadRecord(path,recordNumber):
    fh = None
    try:
        fh = open(path, 'rb')
        bytes = bytearray(fh.read())
        return ti_files.readRecord(bytes, recordNumber)
    except:
        raise
    finally:
        if fh != None:
            fh.close()
    return None
        

## 
## MAIN
##

oled.info("TIPI Init")

createResetListener()

tipi_io = TipiMessage()
specialFiles = SpecialFiles(tipi_io)
rawExtensions = RawExtensions(tipi_io)

oled.info("TIPI Ready")

while True:
    logger.info("waiting for PAB request...")

    pab = tipi_io.receive()
    if rawExtensions.handle(pab):
        continue

    logger.debug("PAB received.")

    logger.debug("waiting for devicename...")
    devicename = tipi_io.receive()

    # Special file name requests to force different errors
    filename = str(devicename)
    if filename == "TIPI.EDVNAME":
        sendErrorCode(EDVNAME)
    elif filename == "TIPI.EWPROT":
        sendErrorCode(EWPROT)
    elif filename == "TIPI.EOPATTR":
        sendErrorCode(EOPATTR)
    elif filename == "TIPI.EILLOP":
        sendErrorCode(EILLOP)
    elif filename == "TIPI.ENOSPAC":
        sendErrorCode(ENOSPAC)
    elif filename == "TIPI.EEOF":
        sendErrorCode(EEOF)
    elif filename == "TIPI.EDEVERR":
        sendErrorCode(EDEVERR)
    elif filename == "TIPI.EFILERR":
        sendErrorCode(EFILERR)
    else:
        if specialFiles.handle(pab, filename):
            continue

        switcher = {
            0: handleOpen,
            1: handleClose,
            2: handleRead,
            3: handleWrite,
            4: handleRestore,
            5: handleLoad,
            6: handleSave,
            7: handleDelete,
            8: handleScratch,
            9: handleStatus
        }
        handler = switcher.get(opcode(pab), handleNotSupported)
        handler(pab, filename)

    logger.info("Request completed.")


