
class ti_files(object):

    @staticmethod
    def isProgram(bytes):
        return ti_files.flags(bytes) & 0x01

    @staticmethod
    def isInternal(bytes):
        return ti_files.flags(bytes) & 0x02

    @staticmethod
    def isProtected(bytes):
        return ti_files.flags(bytes) & 0x04

    @staticmethod
    def isVariable(bytes):
        return ti_files.flags(bytes) & 0x80

    @staticmethod
    def isValid(bytes):
        return bytes[0] == 0x07 and str(bytes[1:8]) == "TIFILES"
        
    @staticmethod
    def getSectors(bytes):
        return bytes[9] + (bytes[8] << 8)

    @staticmethod
    def flags(bytes):
        return bytes[10]

    @staticmethod
    def recordsPerSector(bytes):
        return bytes[11]

    @staticmethod
    def eofOffset(bytes):
        return bytes[12]

    @staticmethod
    def recordLength(bytes):
        return bytes[13]

    @staticmethod
    def recordCount(bytes):
        return bytes[15] + (bytes[14] << 8)

    @staticmethod
    def tiName(bytes):
        return str(bytes[0x10:0x1A])

    @staticmethod
    def byteLength(bytes):
        return ((ti_files.getSectors(bytes)-1) * 256) + ti_files.eofOffset(bytes)

    @staticmethod
    def flagsToString(bytes):
        if ti_files.isInternal(bytes):
            type = "INT/"
        else:
            type = "DIS/"
        if ti_files.isVariable(bytes):
            type += "VAR"
        else:
            type += "FIX"
        
        if ti_files.isProgram(bytes):
            type = "PROGRAM"

        if ti_files.isProtected(bytes):
            type += " Protected"

        return type

    @staticmethod
    def showHeader(bytes):
        print "TIFILES Header: "
        print "  name: " + str(ti_files.tiName(bytes))
        print "  type: " + str(ti_files.flagsToString(bytes))
        print "  sectors: " + str(ti_files.getSectors(bytes))
        print "  records: " + str(ti_files.recordsPerSector(bytes))
        print "  eof: " + str(ti_files.eofOffset(bytes))
        print "  record length: " + str(ti_files.recordLength(bytes))
        print "  record count: " + str(ti_files.recordCount(bytes))

