import codecs
from enum import IntFlag
import os
import struct
import crcmod
from ndspy import codeCompression
from hacktools import common, compression


def extractRom(romfile, extractfolder, workfolder=""):
    common.logMessage("Extracting ROM", romfile, "...")
    ndstool = common.bundledExecutable("ndstool.exe")
    if not os.path.isfile(ndstool):
        common.logError("ndstool not found")
        return
    common.makeFolder(extractfolder)
    common.execute(ndstool + " -x {rom} -9 {folder}arm9.bin -7 {folder}arm7.bin -y9 {folder}y9.bin -y7 {folder}y7.bin -t {folder}banner.bin -h {folder}header.bin -d {folder}data -y {folder}overlay".
                   format(rom=romfile, folder=extractfolder), False)
    if workfolder != "":
        common.copyFolder(extractfolder, workfolder)
    common.logMessage("Done!")


def repackRom(romfile, rompatch, workfolder, patchfile=""):
    common.logMessage("Repacking ROM", rompatch, "...")
    ndstool = common.bundledExecutable("ndstool.exe")
    if not os.path.isfile(ndstool):
        common.logError("ndstool not found")
        return
    common.execute(ndstool + " -c {rom} -9 {folder}arm9.bin -7 {folder}arm7.bin -y9 {folder}y9.bin -y7 {folder}y7.bin -t {folder}banner.bin -h {folder}header.bin -d {folder}data -y {folder}overlay".
                   format(rom=rompatch, folder=workfolder), False)
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
            crc = crcmod.predefined.mkCrcFun("modbus")(f.read(2080))
            f.seek(2)
            f.writeUShort(crc)


def getHeaderID(file):
    with common.Stream(file, "rb") as f:
        f.seek(12)
        return f.readString(6)


# Binary-related functions
def extractBIN(binrange, readfunc=common.detectEncodedString, encoding="shift_jis", binin="data/extract/arm9.bin", binfile="data/bin_output.txt", writepos=False, writedupes=False):
    common.logMessage("Extracting BIN to", binfile, "...")
    if type(binrange) == tuple:
        binrange = [binrange]
    strings, positions = common.extractBinaryStrings(binin, binrange, readfunc, encoding)
    with codecs.open(binfile, "w", "utf-8") as out:
        for i in range(len(strings)):
            if writepos:
                allpositions = []
                for strpos in positions[i]:
                    allpositions.append(common.toHex(strpos))
                out.write(str(allpositions) + "!")
            for j in range(1 if writedupes is False else len(positions[i])):
                out.write(strings[i] + "=\n")
    common.logMessage("Done! Extracted", len(strings), "lines")


def repackBIN(binrange, freeranges=[], readfunc=common.detectEncodedString, writefunc=common.writeEncodedString, encoding="shift_jis", comments="#",
              binin="data/extract/arm9.bin", binout="data/repack/arm9.bin", binfile="data/bin_input.txt", fixchars=[], pointerstart=0x02000000, injectstart=0x02000000, fallbackf=None, injectfallback=0, nocopy=False):
    if not os.path.isfile(binfile):
        common.logError("Input file", binfile, "not found")
        return False

    if not nocopy:
        common.copyFile(binin, binout)
    common.logMessage("Repacking BIN from", binfile, "...")
    section = {}
    with codecs.open(binfile, "r", "utf-8") as bin:
        section = common.getSection(bin, "", comments, fixchars=fixchars)
        chartot, transtot = common.getSectionPercentage(section)
    if type(binrange) == tuple:
        binrange = [binrange]
    notfound = common.repackBinaryStrings(section, binin, binout, binrange, freeranges, readfunc, writefunc, encoding, pointerstart, injectstart, fallbackf, injectfallback)
    for pointer in notfound:
        common.logError("Pointer", common.toHex(pointer.old), "->", common.toHex(pointer.new), "not found for string", pointer.str)
    common.logMessage("Done! Translation is at {0:.2f}%".format((100 * transtot) / chartot))
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
        crc = crcmod.predefined.mkCrcFun("modbus")(f.read(0x15e))
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
    type = header & 0xFF
    decomplength = ((header & 0xFFFFFF00) >> 8)
    common.logDebug("Compression header:", common.toHex(header), "type:", common.toHex(type), "length:", decomplength)
    with common.Stream() as data:
        data.write(f.read(complength))
        data.seek(0)
        if type == CompressionType.LZ10:
            return compression.decompressLZ10(data, complength, decomplength)
        elif type == CompressionType.LZ11:
            return compression.decompressLZ11(data, complength, decomplength)
        elif type == CompressionType.Huff4:
            return compression.decompressHuffman(data, complength, decomplength, 4)
        elif type == CompressionType.Huff8:
            return compression.decompressHuffman(data, complength, decomplength, 8)
        elif type == CompressionType.RLE:
            return compression.decompressRLE(data, complength, decomplength)
        else:
            common.logError("Unsupported compression type", common.toHex(type))
            return data.read()


def compress(data, type):
    with common.Stream() as out:
        length = len(data)
        out.writeByte(type.value)
        out.writeByte(length & 0xFF)
        out.writeByte(length >> 8 & 0xFF)
        out.writeByte(length >> 16 & 0xFF)
        if type == CompressionType.LZ10:
            out.write(compression.compressLZ10(data))
        elif type == CompressionType.LZ11:
            out.write(compression.compressLZ11(data))
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
    with common.Stream(infile, "rb") as fin:
        data = fin.read()
    uncdata = codeCompression.decompress(data)
    with common.Stream(outfile, "wb") as f:
        f.write(uncdata)


def compressBinary(infile, outfile, arm9=True):
    with common.Stream(infile, "rb") as fin:
        data = bytearray(fin.read())
    compdata = bytearray(codeCompression.compress(data, arm9))
    if arm9:
        codeoffset = 0
        for i in range(0, 0x8000, 4):
            if compdata[i:i+8] == b'\x21\x06\xC0\xDE\xDE\xC0\x06\x21':
                codeoffset = i - 0x1C
                break
        if codeoffset > 0:
            struct.pack_into("<I", compdata, codeoffset + 0x14, 0x02000000 + len(compdata))
    with common.Stream(outfile, "wb") as f:
        f.write(compdata)
