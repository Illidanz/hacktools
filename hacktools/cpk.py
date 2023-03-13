import os
from enum import IntEnum
from hacktools import common, cmp_cri


class CPK:
    def __init__(self):
        self.filetable = []
        self.data = {}
        self.align = 0

    def getFileEntry(self, filename, filetype="", tocname=""):
        for i in range(len(self.filetable)):
            if self.filetable[i].filename == filename and (filetype == "" or self.filetable[i].filetype == filetype) and (tocname == "" or self.filetable[i].tocname == tocname):
                return self.filetable[i]
        return None

    def getIDEntry(self, id, filetype="", tocname=""):
        for i in range(len(self.filetable)):
            if self.filetable[i].id == id and (filetype == "" or self.filetable[i].filetype == filetype) and (tocname == "" or self.filetable[i].tocname == tocname):
                return self.filetable[i]
        return None

    def getEntries(self, filetype):
        ret = []
        for i in range(len(self.filetable)):
            if self.filetable[i].filetype == filetype:
                ret.append(self.filetable[i])
        return ret


class CPKFileEntry:
    def __init__(self):
        self.dirname = ""
        self.filename = ""
        self.filesize = 0
        self.filesizepos = 0
        self.filesizetype = UTFStructTypes.DATA_TYPE_NONE
        self.fileoffset = 0
        self.fileoffsetpos = 0
        self.fileoffsettype = UTFStructTypes.DATA_TYPE_NONE
        self.extractsize = 0
        self.extractsizepos = 0
        self.extractsizetype = UTFStructTypes.DATA_TYPE_NONE
        self.offset = 0
        self.id = 0
        self.userstring = ""
        self.updatetime = 0
        self.localdir = ""
        self.tocname = ""
        self.encrypted = False
        self.filetype = ""
        self.utf = None

    @classmethod
    def createEntry(cls, filename, fileoffset, fileoffsettype, fileoffsetpos, tocname, filetype, encrypted):
        entry = cls()
        entry.filename = filename
        entry.fileoffset = fileoffset
        entry.fileoffsettype = fileoffsettype
        entry.fileoffsetpos = fileoffsetpos
        entry.tocname = tocname
        entry.filetype = filetype
        entry.encrypted = encrypted
        return entry

    def getFolderFile(self, basefolder):
        folder = basefolder
        if self.dirname is not None and self.dirname != "" and self.dirname != "<NULL>":
            folder = basefolder + self.dirname + "/"
        filename = ""
        if self.filename is not None and self.filename != "" and self.filename != "<NULL>":
            filename = self.filename
        if filename == "":
            filename = "ID" + str(self.id).zfill(5)
        return folder, filename


class UTFStructTypes(IntEnum):
    DATA_TYPE_UINT8 = 0
    DATA_TYPE_INT8 = 1
    DATA_TYPE_UINT16 = 2
    DATA_TYPE_INT16 = 3
    DATA_TYPE_UINT32 = 4
    DATA_TYPE_INT32 = 5
    DATA_TYPE_UINT64 = 6
    DATA_TYPE_INT64 = 7
    DATA_TYPE_FLOAT = 8
    DATA_TYPE_STRING = 0xa
    DATA_TYPE_BYTEARRAY = 0xb
    DATA_TYPE_MASK = 0xf
    DATA_TYPE_NONE = -1


class UTF:
    def __init__(self):
        self.columns = []
        self.rows = []
        self.tablesize = 0
        self.rowsoffset = 0
        self.stringsoffset = 0
        self.dataoffset = 0
        self.tablename = 0
        self.numcolumns = 0
        self.rowlength = 0
        self.numrows = 0
        self.columnlookup = {}
        self.baseoffset = 0
        self.rawpacket = None
        self.datalpos = 0
        self.datahpos = 0
        self.utfdatal = None
        self.utfdatah = None

    def getColumnData(self, row, name, type):
        data, pos, _ = self.getColumnDataType(row, name)
        if data is None:
            if type == UTFStructTypes.DATA_TYPE_UINT8 or type == UTFStructTypes.DATA_TYPE_INT8:
                data = 0xff
            elif type == UTFStructTypes.DATA_TYPE_UINT16 or type == UTFStructTypes.DATA_TYPE_INT16:
                data = 0xffff
            elif type == UTFStructTypes.DATA_TYPE_UINT32 or type == UTFStructTypes.DATA_TYPE_INT32:
                data = 0xffffffff
            elif type == UTFStructTypes.DATA_TYPE_UINT64 or type == UTFStructTypes.DATA_TYPE_INT64:
                data = 0xffffffffffffffff
            else:
                data = 0
        return data, pos

    def getColumnDataType(self, row, name):
        if name not in self.columnlookup:
            return None, 0, UTFStructTypes.DATA_TYPE_NONE
        columnid = self.columnlookup[name]
        column = self.columns[columnid]
        data = None
        pos = 0
        type = column.type
        if column.type != UTFStructTypes.DATA_TYPE_NONE:
            data = column.data
            pos = column.position
        elif column.storagetype != UTFColumnFlags.STORAGE_NONE and column.storagetype != UTFColumnFlags.STORAGE_ZERO:
            data = self.rows[row][columnid].data
            pos = self.rows[row][columnid].position
            type = self.rows[row][columnid].type
        return data, pos, type

    def updateColumnDataType(self, data, pos, type):
        self.rawpacket.seek(pos)
        if type == UTFStructTypes.DATA_TYPE_UINT8:
            self.rawpacket.writeByte(data)
        elif type == UTFStructTypes.DATA_TYPE_INT8:
            self.rawpacket.writeSByte(data)
        elif type == UTFStructTypes.DATA_TYPE_UINT16:
            self.rawpacket.writeUShort(data)
        elif type == UTFStructTypes.DATA_TYPE_INT16:
            self.rawpacket.writeShort(data)
        elif type == UTFStructTypes.DATA_TYPE_UINT32:
            self.rawpacket.writeUInt(data)
        elif type == UTFStructTypes.DATA_TYPE_INT32:
            self.rawpacket.writeInt(data)
        elif type == UTFStructTypes.DATA_TYPE_UINT64:
            self.rawpacket.writeULong(data)
        elif type == UTFStructTypes.DATA_TYPE_INT64:
            self.rawpacket.writeLong(data)
        else:
            common.logError("Unsupported type for updateColumnDataType", type)


class UTFColumnFlags(IntEnum):
    STORAGE_NONE = 0x0
    STORAGE_MASK = 0xf0
    STORAGE_ZERO = 0x10
    STORAGE_CONSTANT = 0x30
    STORAGE_PERROW = 0x50
    TYPE_MASK = 0xf


class UTFColumn:
    def __init__(self):
        self.flags = 0
        self.name = ""
        self.data = None
        self.storagetype = UTFColumnFlags.STORAGE_NONE
        self.type = UTFStructTypes.DATA_TYPE_NONE
        self.position = 0


class UTFRow:
    def __init__(self):
        self.data = None
        self.type = UTFStructTypes.DATA_TYPE_NONE
        self.position = 0


def extract(file, outfolder, guessextension=None):
    common.logDebug("Processing", file, "...")
    common.makeFolder(outfolder)
    cpk = readCPK(file)
    if cpk is None:
        common.logError("Error reading CPK")
        return
    if len(cpk.filetable) == 0:
        common.logError("No files in CPK filetable")
        return
    with common.Stream(file, "rb") as f:
        for entry in cpk.filetable:
            if entry.filetype != "FILE":
                continue
            folder, filename = entry.getFolderFile(outfolder)
            f.seek(entry.fileoffset)
            data = f.read(entry.filesize)
            f.seek(entry.fileoffset)
            checkcomp = f.readString(8)
            if checkcomp == "CRILAYLA":
                extractsize = entry.extractsize if entry.extractsize != 0 else entry.filesize
                if extractsize != 0:
                    data = cmp_cri.decompressCRILAYLA(data)
            if guessextension is not None:
                filename = guessextension(data, entry, filename)
            if not os.path.isdir(folder):
                common.makeFolders(folder)
            with common.Stream(folder + filename, "wb") as fout:
                fout.write(data)


def repack(file, outfile, infolder, outfolder, nocmp=False):
    common.logDebug("Processing", file, "...")
    cpk = readCPK(file)
    if cpk is None:
        common.logError("Error reading CPK")
        return
    if len(cpk.filetable) == 0:
        common.logError("No files in CPK filetable")
        return
    # Get all the file with the custom extensions
    idtoext = {}
    for subfile in common.getFiles(infolder):
        nameext = os.path.splitext(subfile)
        idtoext[nameext[0]] = nameext[1]
    with common.Stream(outfile, "wb") as fout:
        with common.Stream(file, "rb") as fin:
            idnewdata = {}
            # Copy the file up to the ContentOffset
            contentoffsetentry = cpk.getFileEntry("CONTENT_OFFSET")
            contentoffset = contentoffsetentry.fileoffset
            fout.write(fin.read(contentoffset))
            # Sort the list by original offset, to keep the file order the same
            sortedfiletable = sorted(cpk.filetable, key=lambda e: e.fileoffset)
            for i in common.showProgress(range(len(sortedfiletable))):
                entry = sortedfiletable[i]
                if entry.filetype != "FILE":
                    continue
                folder, filename = entry.getFolderFile(infolder)
                folder2, _ = entry.getFolderFile(outfolder)
                if not os.path.isfile(folder + filename):
                    filename += idtoext[filename]
                if not os.path.isfile(folder + filename):
                    common.logError("Input file", folder + filename, "not found")
                    continue
                if not os.path.isfile(folder2 + filename):
                    # Read this directly from the CPK so we avoid compressing it again
                    fin.seek(entry.fileoffset)
                    filedata = fin.read(entry.filesize)
                    uncdatalen = entry.extractsize
                    cdatalen = entry.filesize
                else:
                    with common.Stream(folder2 + filename, "rb") as subf:
                        filedata = subf.read()
                    if entry.extractsize == entry.filesize:
                        uncdatalen = cdatalen = len(filedata)
                    else:
                        uncdatalen = len(filedata)
                        crc = common.crcFile(folder2 + filename)
                        cachename = folder2 + filename + "_" + str(crc) + ".cache"
                        if os.path.isfile(cachename):
                            common.logDebug("Using cached", cachename)
                            with common.Stream(cachename, "rb") as cachef:
                                filedata = cachef.read()
                            cdatalen = len(filedata)
                        elif nocmp:
                            uncdatalen = cdatalen = len(filedata)
                        else:
                            common.logDebug("Compressing", entry.extractsize, entry.filesize)
                            filedata = cmp_cri.compressCRILAYLA(filedata)
                            cdatalen = len(filedata)
                            common.logDebug("Compressed", uncdatalen, cdatalen)
                            with common.Stream(cachename, "wb") as cachef:
                                cachef.write(filedata)
                # Write the file data and align
                fileoffset = fout.tell() - entry.offset
                fout.write(filedata)
                # If this is the last file, we don't align
                if i + 1 < len(sortedfiletable) and cdatalen % cpk.align > 0:
                    fout.writeZero(cpk.align - (cdatalen % cpk.align))
                idnewdata[entry.id] = (fileoffset, uncdatalen, cdatalen)
            # Update TOC
            tocentry = cpk.getFileEntry("TOC_HDR")
            itocentry = cpk.getFileEntry("ITOC_HDR")
            updatetoc = False
            updateitoc = False
            for id in idnewdata:
                newoffset, newuncdatalen, newcdatalen = idnewdata[id]
                if tocentry is not None:
                    idtocentry = cpk.getIDEntry(id, tocname="TOC")
                    if idtocentry is None:
                        common.logError("TOC entry not found for id", id)
                    else:
                        tocentry.utf.updateColumnDataType(newoffset, idtocentry.fileoffsetpos, idtocentry.fileoffsettype)
                        tocentry.utf.updateColumnDataType(newuncdatalen, idtocentry.extractsizepos, idtocentry.extractsizetype)
                        tocentry.utf.updateColumnDataType(newcdatalen, idtocentry.filesizepos, idtocentry.filesizetype)
                        updatetoc = True
                if itocentry is not None:
                    iditocentry = cpk.getIDEntry(id, tocname="ITOC")
                    if iditocentry is not None:
                        # TODO: Not sure if only updating the datah here is correct in all cases, also might need to check the offset
                        itocentry.utf.utfdatah.updateColumnDataType(newuncdatalen, iditocentry.extractsizepos, iditocentry.extractsizetype)
                        itocentry.utf.utfdatah.updateColumnDataType(newcdatalen, iditocentry.filesizepos, iditocentry.filesizetype)
                        updateitoc = True
            # Write the new packets
            if updatetoc:
                fout.seek(tocentry.fileoffset + 0x10)
                tocentry.utf.rawpacket.seek(0)
                utfpacket = tocentry.utf.rawpacket.read()
                if tocentry.encrypted:
                    utfpacket = decryptUTF(utfpacket)
                fout.write(utfpacket)
            if updateitoc:
                # TODO: check if this works whern the ITOC is encrypted
                itocentry.utf.utfdatah.rawpacket.seek(0)
                utfpacket = itocentry.utf.utfdatah.rawpacket.read()
                itocentry.utf.rawpacket.seek(itocentry.utf.datahpos)
                datapos = itocentry.utf.rawpacket.readInt() + itocentry.utf.dataoffset
                fout.seek(itocentry.fileoffset + 0x10 + datapos)
                fout.write(utfpacket)


def readCPK(file):
    with common.Stream(file, "rb") as f:
        magic = f.readString(4)
        if magic != "CPK ":
            common.logError("Wrong magic:", magic)
            return None
        cpk = CPK()
        utfoffset = f.tell()
        utfpacket, utfsize, encrypted = readUTFData(f)
        cpak = CPKFileEntry()
        cpak.filename = "CPK_HDR"
        cpak.fileoffsetpos = f.tell() + 0x10
        cpak.filesize = utfsize
        cpak.encrypted = encrypted
        cpak.filetype = "CPK"
        utf = readUTF(utfpacket, utfoffset, True)
        if utf is None:
            common.logError("Error reading first UTF")
            return None
        cpak.utf = utf
        cpk.filetable.append(cpak)
        tocoffset, tocoffsetpos = utf.getColumnData(0, "TocOffset", UTFStructTypes.DATA_TYPE_UINT64)
        etocoffset, etocoffsetpos = utf.getColumnData(0, "EtocOffset", UTFStructTypes.DATA_TYPE_UINT64)
        itocoffset, itocoffsetpos = utf.getColumnData(0, "ItocOffset", UTFStructTypes.DATA_TYPE_UINT64)
        gtocoffset, gtocoffsetpos = utf.getColumnData(0, "GtocOffset", UTFStructTypes.DATA_TYPE_UINT64)
        contentoffset, contentoffsetpos = utf.getColumnData(0, "ContentOffset", UTFStructTypes.DATA_TYPE_UINT64)
        cpk.filetable.append(CPKFileEntry.createEntry("CONTENT_OFFSET", contentoffset, UTFStructTypes.DATA_TYPE_UINT64, contentoffsetpos, "CPK", "CONTENT", False))
        files, _ = utf.getColumnData(0, "Files", UTFStructTypes.DATA_TYPE_UINT32)
        cpk.align, _ = utf.getColumnData(0, "Align", UTFStructTypes.DATA_TYPE_UINT16)
        common.logDebug("tocoffset", common.toHex(tocoffset), "tocoffsetpos", common.toHex(tocoffsetpos))
        common.logDebug("etocoffset", common.toHex(etocoffset), "etocoffsetpos", common.toHex(etocoffsetpos))
        common.logDebug("itocoffset", common.toHex(itocoffset), "itocoffsetpos", common.toHex(itocoffsetpos))
        common.logDebug("gtocoffset", common.toHex(gtocoffset), "gtocoffsetpos", common.toHex(gtocoffsetpos))
        common.logDebug("contentoffset", common.toHex(contentoffset), "contentoffsetpos", common.toHex(contentoffsetpos))
        common.logDebug("files", common.toHex(files), "align", common.toHex(cpk.align))
        if tocoffset != 0xffffffffffffffff:
            cpk.filetable.append(CPKFileEntry.createEntry("TOC_HDR", tocoffset, UTFStructTypes.DATA_TYPE_UINT64, tocoffsetpos, "CPK", "HDR", False))
            readTOC(f, cpk, tocoffset, contentoffset)
        if etocoffset != 0xffffffffffffffff:
            cpk.filetable.append(CPKFileEntry.createEntry("ETOC_HDR", etocoffset, UTFStructTypes.DATA_TYPE_UINT64, etocoffsetpos, "CPK", "HDR", False))
            readETOC(f, cpk, etocoffset)
        if itocoffset != 0xffffffffffffffff:
            cpk.filetable.append(CPKFileEntry.createEntry("ITOC_HDR", itocoffset, UTFStructTypes.DATA_TYPE_UINT64, itocoffsetpos, "CPK", "HDR", False))
            readITOC(f, cpk, itocoffset, contentoffset, cpk.align)
        if gtocoffset != 0xffffffffffffffff:
            cpk.filetable.append(CPKFileEntry.createEntry("GTOC_HDR", gtocoffset, UTFStructTypes.DATA_TYPE_UINT64, gtocoffsetpos, "CPK", "HDR", False))
            readGTOC(f, cpk, gtocoffset)
        return cpk


def readTOC(f, cpk, tocoffset, contentoffset):
    addoffset = 0
    if tocoffset > 0x800:
        tocoffset = 0x800
    if contentoffset < 0:
        addoffset = tocoffset
    else:
        if tocoffset < 0:
            addoffset = contentoffset
        else:
            if contentoffset < tocoffset:
                addoffset = contentoffset
            else:
                addoffset = tocoffset
    f.seek(tocoffset)
    headercheck = f.readString(4)
    if headercheck != "TOC ":
        common.logError("Wrong TOC header", headercheck)
        return
    utfoffset = f.tell()
    utfpacket, utfsize, encrypted = readUTFData(f)
    tocentry = cpk.getFileEntry("TOC_HDR")
    tocentry.encrypted = encrypted
    tocentry.filesize = utfsize
    files = readUTF(utfpacket, utfoffset, True)
    tocentry.utf = files
    for i in range(files.numrows):
        entry = CPKFileEntry()
        entry.tocname = "TOC"
        entry.dirname, _, _ = files.getColumnDataType(i, "DirName")
        entry.filename, _, _ = files.getColumnDataType(i, "FileName")
        entry.filesize, entry.filesizepos, entry.filesizetype = files.getColumnDataType(i, "FileSize")
        entry.extractsize, entry.extractsizepos, entry.extractsizetype = files.getColumnDataType(i, "ExtractSize")
        entry.fileoffset, entry.fileoffsetpos, entry.fileoffsettype = files.getColumnDataType(i, "FileOffset")
        entry.fileoffset += addoffset
        entry.filetype = "FILE"
        entry.offset = addoffset
        entry.id, _, _ = files.getColumnDataType(i, "ID")
        entry.userstring, _, _ = files.getColumnDataType(i, "UserString")
        cpk.filetable.append(entry)
        common.logDebug("TOC", i, vars(entry))



def readETOC(f, cpk, tocoffset):
    f.seek(tocoffset)
    headercheck = f.readString(4)
    if headercheck != "ETOC":
        common.logError("Wrong ETOC header", headercheck)
        return
    utfoffset = f.tell()
    utfpacket, utfsize, encrypted = readUTFData(f)
    tocentry = cpk.getFileEntry("ETOC_HDR")
    tocentry.encrypted = encrypted
    tocentry.filesize = utfsize
    files = readUTF(utfpacket, utfoffset)
    entries = cpk.getEntries("FILE")
    for i in range(len(entries)):
        entries[i].localdir, _, _ = files.getColumnDataType(i, "LocalDir")
        updatetime, _, _ = files.getColumnDataType(i, "UpdateDateTime")
        if updatetime is None:
            updatetime = 0
        entries[i].updatetime = updatetime


def readITOC(f, cpk, tocoffset, contentoffset, align):
    f.seek(tocoffset)
    headercheck = f.readString(4)
    if headercheck != "ITOC":
        common.logError("Wrong ITOC header", headercheck)
        return
    utfoffset = f.tell()
    utfpacket, utfsize, encrypted = readUTFData(f)
    tocentry = cpk.getFileEntry("ITOC_HDR")
    tocentry.encrypted = encrypted
    tocentry.filesize = utfsize
    files = readUTF(utfpacket, utfoffset, True)
    tocentry.utf = files
    datal, files.datalpos, _ = files.getColumnDataType(0, "DataL")
    datah, files.datahpos, _ = files.getColumnDataType(0, "DataH")
    ids = []
    sizetable = {}
    csizetable = {}
    if datal is not None:
        data = common.Stream(little=False).__enter__()
        data.write(datal)
        data.seek(0)
        files.utfdatal = readUTF(data, -1, True)
        for i in range(files.utfdatal.numrows):
            id, _, _ = files.utfdatal.getColumnDataType(i, "ID")
            size, sizepos, sizetype = files.utfdatal.getColumnDataType(i, "FileSize")
            csize, csizepos, csizetype = files.utfdatal.getColumnDataType(i, "ExtractSize")
            ids.append(id)
            sizetable[id] = (size, sizepos, sizetype)
            if csize is not None:
                csizetable[id] = (csize, csizepos, csizetype)
    if datah is not None:
        data = common.Stream(little=False).__enter__()
        data.write(datah)
        data.seek(0)
        files.utfdatah = readUTF(data, -1, True)
        for i in range(files.utfdatah.numrows):
            id, _, _ = files.utfdatah.getColumnDataType(i, "ID")
            size, sizepos, sizetype = files.utfdatah.getColumnDataType(i, "FileSize")
            csize, csizepos, csizetype = files.utfdatah.getColumnDataType(i, "ExtractSize")
            ids.append(id)
            sizetable[id] = (size, sizepos, sizetype)
            if csize is not None:
                csizetable[id] = (csize, csizepos, csizetype)
    if len(ids) == 0:
        entries = cpk.getEntries("FILE")
        for i in range(len(entries)):
            id, _, _ = files.getColumnDataType(i, "ID")
            tocindex, _, _ = files.getColumnDataType(i, "TocIndex")
            entries[tocindex].id = id
    else:
        baseoffset = contentoffset
        for id in ids:
            entry = CPKFileEntry()
            entry.tocname = "ITOC"
            entry.filesize, entry.filesizepos, entry.filesizetype = sizetable[id]
            if id in csizetable:
                entry.extractsize, entry.extractsizepos, entry.extractsizetype = csizetable[id]
            entry.filetype = "FILE"
            entry.fileoffset = baseoffset
            entry.id = id
            cpk.filetable.append(entry)
            common.logDebug("ITOC", i, vars(entry))
            baseoffset += entry.filesize
            if entry.filesize % align > 0:
                baseoffset += (align - (entry.filesize % align))


def readGTOC(f, cpk, tocoffset):
    f.seek(tocoffset)
    headercheck = f.readString(4)
    if headercheck != "GTOC":
        common.logError("Wrong GTOC header", headercheck)
        return
    utfpacket, utfsize, encrypted = readUTFData(f)
    tocentry = cpk.getFileEntry("GTOC_HDR")
    tocentry.encrypted = encrypted
    tocentry.filesize = utfsize
    files = readUTF(utfpacket, tocoffset)


def readUTFData(f):
    f.setEndian(True)
    unk1 = f.readInt()
    utfsize = f.readLong()
    # common.logDebug("readUTFData unk1", common.toHex(unk1), "size", common.toHex(utfsize))
    utfpacket = f.read(utfsize)
    encrypted = False
    if utfpacket[:4].decode("ascii", "ignore") != "@UTF":
        utfpacket = decryptUTF(utfpacket)
        encrypted = True
    f.setEndian(False)
    packetstream = common.Stream(little=False).__enter__()
    packetstream.write(utfpacket)
    packetstream.seek(0)
    return packetstream, utfsize, encrypted


def decryptUTF(input):
    ret = bytearray(input)
    m = 0x0000655f
    t = 0x00004115
    for i in range(len(ret)):
        d = ret[i]
        d = (d ^ (m & 0xff))
        ret[i] = d
        m *= t
    return bytes(ret)


def readUTF(f, baseoffset, storeraw=False):
    offset = f.tell()
    headercheck = f.readString(4)
    if headercheck != "@UTF":
        common.logError("Wrong UTF header", headercheck)
        return None
    utf = UTF()
    utf.tablesize = f.readInt()
    utf.rowsoffset = f.readInt() + offset + 8
    utf.stringsoffset = f.readInt() + offset + 8
    utf.dataoffset = f.readInt() + offset + 8
    utf.tablename = f.readInt()
    utf.numcolumns = f.readShort()
    utf.rowlength = f.readShort()
    utf.numrows = f.readInt()
    utf.baseoffset = baseoffset
    if storeraw:
        utf.rawpacket = f
    # common.logDebug("UTF", vars(utf))
    for i in range(utf.numcolumns):
        column = UTFColumn()
        column.flags = f.readByte()
        if column.flags == 0:
            common.logDebug("Column flag is 0, skipping 3 bytes")
            f.seek(3, 1)
            column.flags = f.readByte()
        column.storagetype = column.flags & UTFColumnFlags.STORAGE_MASK
        nameoffset = f.readInt() + utf.stringsoffset
        # Assume ASCII, might be better to assume UTF8?
        column.name = f.readNullStringAt(nameoffset)
        if column.flags & UTFColumnFlags.STORAGE_MASK == UTFColumnFlags.STORAGE_CONSTANT:
            column.position = f.tell()
            column.data, column.type = readUTFTypedData(f, utf, column.flags)
        utf.columns.append(column)
        utf.columnlookup[column.name] = i
        common.logDebug("UTFColumn", i, vars(column))
    for j in range(utf.numrows):
        f.seek(utf.rowsoffset + (j * utf.rowlength))
        rows = []
        for i in range(utf.numcolumns):
            column = utf.columns[i]
            row = UTFRow()
            if column.storagetype == UTFColumnFlags.STORAGE_ZERO:
                row.data = 0
            elif column.storagetype == UTFColumnFlags.STORAGE_CONSTANT:
                row.data = column.data
            elif column.storagetype == UTFColumnFlags.STORAGE_PERROW:
                row.position = f.tell()
                row.data, row.type = readUTFTypedData(f, utf, column.flags)
            rows.append(row)
            # common.logDebug("UTFRow", j, i, column.name, vars(row))
        utf.rows.append(rows)
    return utf


def readUTFTypedData(f, utf, flags):
    type = flags & UTFColumnFlags.TYPE_MASK
    if type == UTFStructTypes.DATA_TYPE_UINT8:
        return f.readByte(), type
    if type == UTFStructTypes.DATA_TYPE_INT8:
        return f.readSByte(), type
    if type == UTFStructTypes.DATA_TYPE_UINT16:
        return f.readUShort(), type
    if type == UTFStructTypes.DATA_TYPE_INT16:
        return f.readShort(), type
    if type == UTFStructTypes.DATA_TYPE_UINT32:
        return f.readUInt(), type
    if type == UTFStructTypes.DATA_TYPE_INT32:
        return f.readInt(), type
    if type == UTFStructTypes.DATA_TYPE_UINT64:
        return f.readULong(), type
    if type == UTFStructTypes.DATA_TYPE_INT64:
        return f.readLong(), type
    if type == UTFStructTypes.DATA_TYPE_FLOAT:
        return f.readFloat(), type
    if type == UTFStructTypes.DATA_TYPE_STRING:
        strpos = f.readInt() + utf.stringsoffset
        return f.readNullStringAt(strpos), type
    if type == UTFStructTypes.DATA_TYPE_BYTEARRAY:
        datapos = f.readInt() + utf.dataoffset
        datasize = f.readInt()
        return f.readAt(datapos, datasize), type
