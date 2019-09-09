from enum import IntFlag
import os
import struct
import crcmod
from hacktools import common, compression


def extractRom(romfile, extractfolder, workfolder=""):
    common.logMessage("Extracting ROM", romfile, "...")
    ndstool = common.bundledExecutable("ndstool.exe")
    if not os.path.isfile(ndstool):
        common.logError("ndstool not found")
    else:
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
    else:
        common.execute(ndstool + " -c {rom} -9 {folder}arm9.bin -7 {folder}arm7.bin -y9 {folder}y9.bin -y7 {folder}y7.bin -t {folder}banner.bin -h {folder}header.bin -d {folder}data -y {folder}overlay".
                       format(rom=rompatch, folder=workfolder), False)
        common.logMessage("Done!")
        # Create xdelta patch
        if patchfile != "":
            common.logMessage("Creating xdelta patch", patchfile, "...")
            xdelta = common.bundledExecutable("xdelta.exe")
            if not os.path.isfile(xdelta):
                common.logError("xdelta not found")
            else:
                common.execute(xdelta + " -f -e -s {rom} {rompatch} {patch}".format(rom=romfile, rompatch=rompatch, patch=patchfile), False)
                common.logMessage("Done!")


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
        data.write(f.read(complength - 4))
        data.seek(0)
        if type == CompressionType.LZ10:
            return compression.decompressLZ10(data, complength, decomplength)
        elif type == CompressionType.LZ11:
            return compression.decompressLZ11(data, complength, decomplength)
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
    filelen = os.path.getsize(infile)
    footer = bytes()
    if infile.endswith("arm9.bin"):
        filelen -= 0x0C
    with common.Stream(infile, "rb") as fin:
        # Read footer
        if infile.endswith("arm9.bin"):
            fin.seek(filelen)
            footer = fin.read(0x0C)
        # Read compression info
        fin.seek(filelen - 8)
        header = fin.read(8)
        enddelta, startdelta = struct.unpack("<LL", header)
        padding = enddelta >> 0x18
        enddelta &= 0xFFFFFF
        decsize = startdelta + enddelta
        headerlen = filelen - enddelta
        # Read compressed data and reverse it
        fin.seek(headerlen)
        data = bytearray()
        data.extend(fin.read(enddelta - padding))
        data.reverse()
        # Decompress and reverse again
        uncdata = compression.decompressLZ10(data, len(data), decsize, 3)
        uncdata.reverse()
        # Write uncompressed bin with header
        with common.Stream(outfile, "wb") as f:
            fin.seek(0)
            f.write(fin.read(headerlen))
            f.write(uncdata)
    return headerlen, footer
