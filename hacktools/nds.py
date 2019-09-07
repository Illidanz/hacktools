import os
import struct
import crcmod
from hacktools import common


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


# Compression
def decompress(f, size):
    header = f.readUInt()
    length = header >> 8
    type = 0x10 if ((header >> 4) & 0xF == 1) else 0x11
    common.logDebug("  Header:", common.toHex(header), "length:", length, "type:", type)
    if type == 0x10:
        return bytes(decompressRawLZSS10(f.read(), length))
    elif type == 0x11:
        return bytes(decompressRawLZSS11(f.read(), length))


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
        uncdata = decompressRawLZSS10(data, decsize, True)
        uncdata.reverse()
        # Write uncompressed bin with header
        with common.Stream(outfile, "wb") as f:
            fin.seek(0)
            f.write(fin.read(headerlen))
            f.write(uncdata)
    return headerlen, footer


# https://github.com/magical/nlzss/blob/master/lzss3.py
def bits(b):
    return ((b >> 7) & 1, (b >> 6) & 1, (b >> 5) & 1, (b >> 4) & 1, (b >> 3) & 1, (b >> 2) & 1, (b >> 1) & 1, (b) & 1)


def decompressRawLZSS10(indata, decompressed_size, binary=False):
    data = bytearray()
    it = iter(indata)
    disp_extra = 3 if binary else 1

    while len(data) < decompressed_size:
        b = next(it)
        flags = bits(b)
        for flag in flags:
            if flag == 0:
                data.append(next(it))
            elif flag == 1:
                sha = next(it)
                shb = next(it)
                sh = (sha << 8) | shb
                count = (sh >> 0xc) + 3
                disp = (sh & 0xfff) + disp_extra

                for _ in range(count):
                    data.append(data[-disp])
            else:
                raise ValueError(flag)

            if decompressed_size <= len(data):
                break

    if len(data) != decompressed_size:
        common.logError("Decompressed size", len(data), "does not match the expected size", decompressed_size)

    return data


def decompressRawLZSS11(indata, decompressed_size):
    data = bytearray()
    it = iter(indata)

    while len(data) < decompressed_size:
        b = next(it)
        flags = bits(b)
        for flag in flags:
            if flag == 0:
                data.append(next(it))
            elif flag == 1:
                b = next(it)
                indicator = b >> 4

                if indicator == 0:
                    # 8 bit count, 12 bit disp
                    # indicator is 0, don't need to mask b
                    count = (b << 4)
                    b = next(it)
                    count += b >> 4
                    count += 0x11
                elif indicator == 1:
                    # 16 bit count, 12 bit disp
                    count = ((b & 0xf) << 12) + (next(it) << 4)
                    b = next(it)
                    count += b >> 4
                    count += 0x111
                else:
                    # indicator is count (4 bits), 12 bit disp
                    count = indicator
                    count += 1

                disp = ((b & 0xf) << 8) + next(it)
                disp += 1

                try:
                    for _ in range(count):
                        data.append(data[-disp])
                except IndexError:
                    raise Exception(count, disp, len(data), sum(1 for x in it))
            else:
                raise ValueError(flag)

            if decompressed_size <= len(data):
                break

    if len(data) != decompressed_size:
        common.logError("Decompressed size", len(data), "does not match the expected size", decompressed_size)

    return data
