import codecs
from enum import IntFlag
import os
import struct
from hacktools import common, compression, cmp_lzss, cmp_misc


def extractRom(romfile, extractfolder, workfolder=""):
    try:
        import ndspy.rom
    except ImportError:
        common.logError("ndspy not found")
        return
    common.logMessage("Extracting ROM", romfile, "...")
    common.makeFolder(extractfolder)
    datafolder = extractfolder + "data/"
    rom = ndspy.rom.NintendoDSRom.fromFile(romfile)
    common.makeFolder(datafolder)
    for i,file in enumerate(rom.files):
        filepath = rom.filenames.filenameOf(i)
        if filepath is not None:
            common.makeFolders(datafolder + os.path.dirname(filepath))
            with common.Stream(datafolder + filepath, "wb") as f:
                f.write(file)
    with common.Stream(extractfolder + "banner.bin", "wb") as f:
        f.write(rom.iconBanner)
    with common.Stream(extractfolder + "header.bin", "wb") as f:
        with common.Stream(romfile, "rb") as fin:
            f.write(fin.read(0x200))
    with common.Stream(extractfolder + "arm7.bin", "wb") as f:
        f.write(rom.arm7)
    with common.Stream(extractfolder + "arm9.bin", "wb") as f:
        f.write(rom.arm9)
    with common.Stream(extractfolder + "y7.bin", "wb") as f:
        f.write(rom.arm7OverlayTable)
    with common.Stream(extractfolder + "y9.bin", "wb") as f:
        f.write(rom.arm9OverlayTable)
    if len(rom.arm9OverlayTable) > 0:
        with common.Stream(extractfolder + "y9.bin", "rb") as f:
            common.makeFolder(extractfolder + "overlay/")
            for i in range(len(rom.arm9OverlayTable) // 0x20):
                f.seek(i * 0x20)
                fileid = f.readUInt()
                with common.Stream(extractfolder + "overlay/overlay_" + str(i).zfill(4) + ".bin", "wb") as overlayf:
                    overlayf.write(rom.files[fileid])
    if workfolder != "":
        common.logMessage("Copying data to", workfolder, "...")
        common.copyFolder(extractfolder, workfolder)
    common.logMessage("Done!")


def repackRom(romfile, rompatch, workfolder, patchfile=""):
    try:
        import ndspy.rom
    except ImportError:
        common.logError("ndspy not found")
        return
    common.logMessage("Repacking ROM", rompatch, "...")
    rom = ndspy.rom.NintendoDSRom.fromFile(romfile)
    datafolder = workfolder + "data/"
    for i,_ in enumerate(rom.files):
        filepath = rom.filenames.filenameOf(i)
        if filepath is not None and os.path.isfile(datafolder + filepath):
            with common.Stream(datafolder + filepath, "rb") as f:
                rom.files[i] = f.read()
    with common.Stream(workfolder + "banner.bin", "rb") as f:
        rom.iconBanner = f.read()
    with common.Stream(workfolder + "arm7.bin", "rb") as f:
        rom.arm7 = f.read()
    with common.Stream(workfolder + "arm9.bin", "rb") as f:
        rom.arm9 = f.read()
    with common.Stream(workfolder + "y7.bin", "rb") as f:
        rom.arm7OverlayTable = f.read()
    with common.Stream(workfolder + "y9.bin", "rb") as f:
        rom.arm9OverlayTable = f.read()
        for i in range(len(rom.arm9OverlayTable) // 0x20):
            f.seek(i * 0x20)
            fileid = f.readUInt()
            overlayname = workfolder + "overlay/overlay_" + str(i).zfill(4) + ".bin"
            if os.path.isfile(overlayname):
                with common.Stream(overlayname, "rb") as overlayf:
                    rom.files[fileid] = overlayf.read()
    rom.saveToFile(rompatch)
    common.logMessage("Done!")
    # Create xdelta patch
    if patchfile != "":
        common.xdeltaPatch(patchfile, romfile, rompatch)


def editBannerTitle(file, title):
    with common.Stream(file, "r+b") as f:
        for i in range(6):
            # Write new text for all languages
            f.seek(576 + 256 * i)
            for char in title:
                f.writeByte(ord(char))
                f.writeByte(0x00)
            # Compute CRC
            f.seek(32)
            crc = common.crc16(f.read(2080))
            f.seek(2)
            f.writeUShort(crc)


def getHeaderID(file):
    with common.Stream(file, "rb") as f:
        f.seek(12)
        return f.readString(6)


# Binary-related functions
def extractBIN(binrange, readfunc=common.detectEncodedString, encoding="shift_jis", binin="data/extract/arm9.bin", binfile="data/bin_output.txt", writepos=False, writedupes=False, sectionname="bin"):
    common.logMessage("Extracting BIN to", binfile, "...")
    if type(binrange) == tuple:
        binrange = [binrange]
    strings, positions = common.extractBinaryStrings(binin, binrange, readfunc, encoding)
    if binfile.endswith(".txt"):
        with codecs.open(binfile, "w", "utf-8") as out:
            for i in range(len(strings)):
                if writepos:
                    allpositions = []
                    for strpos in positions[i]:
                        allpositions.append(common.toHex(strpos))
                    out.write(str(allpositions) + "!")
                for j in range(1 if writedupes is False else len(positions[i])):
                    out.write(strings[i] + "=\n")
    else:
        t = common.TranslationFile()
        for i in range(len(strings)):
            for j in range(1 if writedupes is False else len(positions[i])):
                t.addEntry(strings[i], sectionname, positions[i][j])
        t.save(binfile, True)
    common.logMessage("Done! Extracted", len(strings), "lines")


def repackBIN(binrange, freeranges=[], readfunc=common.detectEncodedString, writefunc=common.writeEncodedString, encoding="shift_jis", comments="#",
              binin="data/extract/arm9.bin", binout="data/repack/arm9.bin", binfile="data/bin_input.txt", fixchars=[], pointerstart=0x02000000, injectstart=0x02000000, fallbackf=None, injectfallback=0, nocopy=False, sectionname="bin"):
    if not os.path.isfile(binfile):
        common.logError("Input file", binfile, "not found")
        return False

    if not nocopy:
        common.copyFile(binin, binout)
    common.logMessage("Repacking BIN from", binfile, "...")
    section = {}
    if binfile.endswith(".txt"):
        with codecs.open(binfile, "r", "utf-8") as bin:
            section = common.getSection(bin, "", comments, fixchars=fixchars)
            chartot, transtot = common.getSectionPercentage(section)
    else:
        section = common.TranslationFile(binfile)
        section.preloadLookup()
    if type(binrange) == tuple:
        binrange = [binrange]
    notfound = common.repackBinaryStrings(section, binin, binout, binrange, freeranges, readfunc, writefunc, encoding, pointerstart, injectstart, fallbackf, injectfallback, sectionname)
    for pointer in notfound:
        common.logError("Pointer", common.toHex(pointer.old), "->", common.toHex(pointer.new), "not found for string", pointer.str)
    if binfile.endswith(".txt"):
        common.logMessage("Done! Translation is at {0:.2f}%".format((100 * transtot) / chartot))
    else:
        common.logMessage("Done! Translation is at {0:.2f}%".format(section.getProgress()))
    return True


class BINSection:
    def __init__(self, f, ramaddr, ramlen, fileoff, bsssize, real = True):
        self.offset = fileoff
        self.length = ramlen
        self.ramaddr = ramaddr
        self.bsssize = bsssize
        self.real = real
        if f is not None:
            f.seek(self.offset)
            self.data = f.read(ramlen)
        else:
            self.data = bytearray(ramlen)


def expandBIN(binin, binout, headerin, headerout, newlength, injectpos):
    if not os.path.isfile(binin):
        common.logError("Input file", binin, "not found")
        return False
    if not os.path.isfile(headerin):
        common.logError("Header file", headerin, "not found")
        return False
    codesettings = -1
    with common.Stream(headerin, "rb") as fin:
        fin.seek(0x20)
        arm9offset = fin.readUInt()
        arm9entry = fin.readUInt()
        arm9ramaddr = fin.readUInt()
        arm9len = fin.readUInt()
        fin.seek(0x50)
        arm9ovaddr = fin.readUInt()
        arm9ovlen = fin.readUInt()
        fin.seek(0x70)
        armcodesettings = fin.readUInt()
        common.logDebug("arm9offset", common.toHex(arm9offset), "arm9entry", common.toHex(arm9entry), "arm9ramaddr", common.toHex(arm9ramaddr), "arm9len", common.toHex(arm9len), "arm9ovaddr", common.toHex(arm9ovaddr), "arm9ovlen", common.toHex(arm9ovlen), "codesettings", common.toHex(armcodesettings))
    with common.Stream(binin, "rb") as fin:
        # Get code settings position if it wasn't in the header
        if armcodesettings > 0:
            codesettings = fin.readUIntAt(armcodesettings - arm9ramaddr - 4) - arm9ramaddr
            common.logDebug("codesettings", common.toHex(codesettings))
        if codesettings <= 0:
            for i in range(0, 0x8000, 4):
                if fin.readUIntAt(i) == 0xdec00621 and fin.readUIntAt(i + 4) == 0x2106c0de:
                    codesettings = i - 0x1c
                    common.logDebug("codesettings heuristic", common.toHex(codesettings))
        if codesettings <= 0:
            common.logError("Code settings offset not found")
            return False
        # Read the current sections
        copytablestart = fin.readUIntAt(codesettings) - arm9ramaddr
        copytableend = fin.readUIntAt(codesettings + 4) - arm9ramaddr
        datastart = fin.readUIntAt(codesettings + 8) - arm9ramaddr
        common.logDebug("copytablestart", common.toHex(copytablestart), "copytableend", common.toHex(copytableend), "datastart", common.toHex(datastart))
        sections = []
        sections.append(BINSection(fin, arm9ramaddr, datastart, 0, 0, False))
        while copytablestart < copytableend:
            start = fin.readUIntAt(copytablestart)
            size = fin.readUIntAt(copytablestart + 4)
            bsssize = fin.readUIntAt(copytablestart + 8)
            copytablestart += 12
            common.logDebug("  start", common.toHex(start), "size", common.toHex(size), "bsssize", common.toHex(bsssize))
            sections.append(BINSection(fin, start, size, datastart, bsssize))
            datastart += size
    # Write the new extended arm9.bin
    sections.append(BINSection(None, injectpos, newlength, 0, 0))
    with common.Stream(binout, "wb") as f:
        # Write the section data first
        f.write(sections[0].data)
        datastart = f.tell()
        for i in range(1, len(sections)):
            sections[i].offset = f.tell()
            f.write(sections[i].data)
        # Write the new copytable
        copytablestart = f.tell()
        for section in sections:
            if not section.real:
                continue
            f.writeUInt(section.ramaddr)
            f.writeUInt(section.length)
            f.writeUInt(section.bsssize)
        copytableend = f.tell()
        arm9len = f.tell()
        f.seek(codesettings)
        f.writeUInt(copytablestart + arm9ramaddr)
        f.writeUInt(copytableend + arm9ramaddr)
        f.writeUInt(datastart + arm9ramaddr)
    # Write the new length in the header
    common.copyFile(headerin, headerout)
    with common.Stream(headerout, "rb+") as f:
        f.seek(0x2c)
        f.writeUInt(arm9len - 0xc)
        # Update the checksum
        f.seek(0)
        crc = common.crc16(f.read(0x15e))
        f.writeUShort(crc)
    return sections[len(sections) - 1].offset


# Compression-related functions
class CompressionType(IntFlag):
    LZ10 = 0x10,
    LZ11 = 0x11,
    Huff4 = 0x24,
    Huff8 = 0x28,
    RLE = 0x30,
    LZ40 = 0x40,
    LZ60 = 0x60


def decompress(f, complength):
    header = f.readUInt()
    type = header & 0xff
    decomplength = ((header & 0xffffff00) >> 8)
    common.logDebug("Compression header:", common.toHex(header), "type:", common.toHex(type), "length:", decomplength)
    data = f.read(complength)
    if type == CompressionType.LZ10:
        return cmp_lzss.decompressLZ10(data, decomplength, 1)
    elif type == CompressionType.LZ11:
        return cmp_lzss.decompressLZ11(data, decomplength, 1)
    elif type == CompressionType.Huff4:
        return compression.decompressHuffman(data, decomplength, 4)
    elif type == CompressionType.Huff8:
        return compression.decompressHuffman(data, decomplength, 8)
    elif type == CompressionType.RLE:
        return cmp_misc.decompressRLE(data, decomplength)
    else:
        common.logError("Unsupported decompression type", common.toHex(type))
        return data


def compress(data, type):
    with common.Stream() as out:
        length = len(data)
        out.writeByte(type.value)
        out.writeByte(length & 0xff)
        out.writeByte((length >> 8) & 0xff)
        out.writeByte((length >> 16) & 0xff)
        if type == CompressionType.LZ10:
            out.write(cmp_lzss.compressLZ10(data, 1))
        elif type == CompressionType.LZ11:
            out.write(cmp_lzss.compressLZ11(data, 1))
        elif type == CompressionType.Huff4:
            out.write(compression.compressHuffman(data, 4))
        elif type == CompressionType.Huff8:
            out.write(compression.compressHuffman(data, 8))
        else:
            common.logError("Unsupported compression type", common.toHex(type))
            out.write(data)
        out.seek(0)
        return out.read()


def decompressFile(infile, outfile):
    insize = os.path.getsize(infile)
    with common.Stream(infile, "rb") as fin:
        with common.Stream(outfile, "wb") as fout:
            fout.write(decompress(fin, insize - 4))


def compressFile(infile, outfile, type):
    with common.Stream(infile, "rb") as fin:
        data = fin.read()
        with common.Stream(outfile, "wb") as fout:
            fout.write(compress(data, type))


def decompressBinary(infile, outfile):
    try:
        import ndspy.codeCompression
    except ImportError:
        common.logError("ndspy not found")
        return
    with common.Stream(infile, "rb") as fin:
        data = fin.read()
    uncdata = ndspy.codeCompression.decompress(data)
    with common.Stream(outfile, "wb") as f:
        f.write(uncdata)


def compressBinary(infile, outfile, arm9=True):
    try:
        import ndspy.codeCompression
    except ImportError:
        common.logError("ndspy not found")
        return
    with common.Stream(infile, "rb") as fin:
        data = bytearray(fin.read())
    compdata = bytearray(ndspy.codeCompression.compress(data, arm9))
    if arm9:
        codeoffset = 0
        for i in range(0, 0x8000, 4):
            if compdata[i:i+8] == b'\x21\x06\xC0\xDE\xDE\xC0\x06\x21':
                codeoffset = i - 0x1c
                break
        if codeoffset > 0:
            struct.pack_into("<I", compdata, codeoffset + 0x14, 0x02000000 + len(compdata))
    with common.Stream(outfile, "wb") as f:
        f.write(compdata)
