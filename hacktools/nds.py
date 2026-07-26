"""Support for NDS ROMs, based on ndspy.

Includes ROM extraction and repacking, banner editing, string extraction
and repacking for binary files, arm9.bin expansion and the BIOS
compression formats.
"""
from enum import IntFlag
import os
import struct
from hacktools import common, cmp_huff, cmp_lzss, cmp_misc


def extractRom(romfile: str, extractfolder: str, workfolder: str = "") -> None:
    """Extract a NDS ROM with ndspy.

    The filesystem is extracted to a data subfolder, along with the header,
    banner, arm7/arm9 binaries, overlay tables (y7/y9) and arm9 overlays.

    Args:
        romfile: Path of the ROM file.
        extractfolder: Path of the folder to extract to.
        workfolder: Optional path of a work folder the extracted files are
            copied to.
    """
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


def repackRom(romfile: str, rompatch: str, workfolder: str, patchfile: str = "") -> None:
    """Repack a NDS ROM, replacing the files found in a folder.

    Args:
        romfile: Path of the original ROM file.
        rompatch: Path of the output ROM file.
        workfolder: Path of the folder with the files to replace, as
            extracted by :func:`extractRom`.
        patchfile: Path of the xdelta patch to create, or empty to skip
            patch creation.
    """
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


def editBannerTitle(file: str, title: str) -> None:
    """Write a new game title in a banner file and update its CRC.

    The title is written for all the 6 languages.

    Args:
        file: Path of the banner file.
        title: Title to write.
    """
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


def getHeaderID(file: str) -> str:
    """Read the 6 character game ID from a header file.

    Args:
        file: Path of the header or ROM file.

    Returns:
        The game and maker codes as a single string.
    """
    with common.Stream(file, "rb") as f:
        f.seek(12)
        return f.readString(6)


# Binary-related functions
def extractBIN(binrange, readfunc=common.detectEncodedString, encoding: str = "shift_jis", binin: str = "data/extract/arm9.bin", binfile: str = "data/bin_output.txt", writepos: bool = False, writedupes: bool = False, sectionname: str = "bin") -> None:
    """Extract strings from ranges of a binary file.

    The strings are written to a text file, or to an xliff translation
    file if binfile doesn't have a .txt extension.

    Args:
        binrange: A (start, end) range, or a list of them.
        readfunc: Function used to detect strings, called with
            (stream, encoding).
        encoding: Encoding passed to readfunc.
        binin: Path of the binary file.
        binfile: Path of the output text or xliff file.
        writepos: Whether to write the positions of each string before it,
            for text file outputs.
        writedupes: Whether to write one entry for every position a string
            is found at, instead of just the first one.
        sectionname: File entry name for xliff outputs.
    """
    common.logMessage("Extracting BIN to", binfile, "...")
    if isinstance(binrange, tuple):
        binrange = [binrange]
    strings, positions = common.extractBinaryStrings(binin, binrange, readfunc, encoding)
    if binfile.endswith(".txt"):
        with open(binfile, "w", encoding="utf-8", newline="") as out:
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


def repackBIN(binrange, freeranges: list = [], readfunc=common.detectEncodedString, writefunc=common.writeEncodedString, encoding: str = "shift_jis", comments: str = "#",
              binin: str = "data/extract/arm9.bin", binout: str = "data/repack/arm9.bin", binfile: str = "data/bin_input.txt", fixchars: list = [], pointerstart: int = 0x02000000, injectstart: int = 0x02000000, fallbackf: common.Stream | None = None, injectfallback: int = 0, nocopy: bool = False, sectionname: str = "bin", preformat=None, postformat=None):
    """Repack translated strings into a binary file.

    The strings are read from a text file, or from an xliff translation
    file if binfile doesn't have a .txt extension, and repacked with
    common.repackBinaryStrings.

    Args:
        binrange: A (start, end) range, or a list of them.
        freeranges: List of (start, end) ranges that can hold relocated
            strings.
        readfunc: Function used to detect strings, called with
            (stream, encoding).
        writefunc: Function used to write strings, called with
            (stream, string, maxlen, encoding).
        encoding: Encoding passed to readfunc and writefunc.
        comments: Comment marker used in the text file.
        binin: Path of the original binary file.
        binout: Path of the output binary file.
        binfile: Path of the input text or xliff file.
        fixchars: List of (old, new) character replacements to apply.
        pointerstart: Value added to file offsets to form pointers, usually
            the load address of the binary.
        injectstart: Pointer start for free ranges marked with a boolean.
        fallbackf: Stream to write strings to when no free range has room.
        injectfallback: Pointer start of the fallback stream.
        nocopy: Whether to skip copying binin to binout first.
        sectionname: File entry name for xliff inputs.
        preformat: Function called on each detected string, returning
            (string, pre, post) data passed to postformat.
        postformat: Function called with (translation, pre, post), returning
            the final string to write.

    Returns:
        The updated free ranges, or False if the input file is missing.
    """
    if not os.path.isfile(binfile):
        common.logError("Input file", binfile, "not found")
        return False

    if not nocopy:
        common.copyFile(binin, binout)
    common.logMessage("Repacking BIN from", binfile, "...")
    section = {}
    if binfile.endswith(".txt"):
        with open(binfile, "r", encoding="utf-8", newline="") as bin:
            section = common.getSection(bin, "", comments, fixchars=fixchars)
            chartot, transtot = common.getSectionPercentage(section)
    else:
        section = common.TranslationFile(binfile)
        section.preloadLookup(comments)
    if isinstance(binrange, tuple):
        binrange = [binrange]
    notfound, freeranges = common.repackBinaryStrings(section, binin, binout, binrange, freeranges, readfunc, writefunc, encoding, pointerstart, injectstart, fallbackf, injectfallback, sectionname, preformat, postformat)
    for pointer in notfound:
        common.logError("Pointer", common.toHex(pointer.old), "->", common.toHex(pointer.new), "not found for string", pointer.str)
    if binfile.endswith(".txt"):
        common.logMessage("Done! Translation is at {0:.2f}%".format((100 * transtot) / chartot))
    else:
        common.logMessage("Done! Translation is at {0:.2f}%".format(section.getProgress()))
    return freeranges


class BINSection:
    """Section of an arm9.bin binary, as listed in its copytable.

    Args:
        f: Stream to read the section data from, or None to create a
            zero-filled section.
        ramaddr: RAM address the section is copied to.
        ramlen: Length of the section.
        fileoff: Offset of the section data in the file.
        bsssize: Size of the section bss.
        real: Whether the section is listed in the copytable.

    Attributes:
        offset: Offset of the section data in the file.
        length: Length of the section.
        ramaddr: RAM address the section is copied to.
        bsssize: Size of the section bss.
        real: Whether the section is listed in the copytable.
        data: Data of the section.
    """
    def __init__(self, f: common.Stream, ramaddr: int, ramlen: int, fileoff: int, bsssize: int, real: bool = True):
        self.offset: int = fileoff
        self.length: int = ramlen
        self.ramaddr: int = ramaddr
        self.bsssize: int = bsssize
        self.real: bool = real
        if f is not None:
            f.seek(self.offset)
            self.data = f.read(ramlen)
        else:
            self.data = bytearray(ramlen)


def expandBIN(binin: str, binout: str, headerin: str, headerout: str, newlengths, injectpos):
    """Expand arm9.bin, adding new sections to its copytable.

    The code settings offset is read from the header, or searched with a
    heuristic if it's not there. A new section is added for each of the
    given lengths, the copytable is rebuilt, and the new arm9 length is
    written in the header along with its updated checksum.

    Args:
        binin: Path of the original arm9.bin file.
        binout: Path of the output arm9.bin file.
        headerin: Path of the original header file.
        headerout: Path of the output header file.
        newlengths: Length of the new section, or a list of lengths.
        injectpos: RAM address of the new section, or a list of addresses.

    Returns:
        The file offset of the last added section, or False on error.
    """
    if not os.path.isfile(binin):
        common.logError("Input file", binin, "not found")
        return False
    if not os.path.isfile(headerin):
        common.logError("Header file", headerin, "not found")
        return False
    if not isinstance(newlengths, list):
        newlengths = [newlengths]
    if not isinstance(injectpos, list):
        injectpos = [injectpos]
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
    for i in range(len(newlengths)):
        sections.append(BINSection(None, injectpos[i], newlengths[i], 0, 0))
    with common.Stream(binout, "wb") as f:
        # Write the section data first
        f.write(sections[0].data)
        datastart = f.tell()
        for i in range(1, len(sections)):
            sections[i].offset = f.tell()
            common.logDebug("Section", i, "offset:", common.toHex(f.tell()))
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
    """Compression types supported by :func:`decompress` and :func:`compress`."""
    LZ10 = 0x10,
    LZ11 = 0x11,
    Huff4 = 0x24,
    Huff8 = 0x28,
    RLE = 0x30,
    LZ40 = 0x40,
    LZ60 = 0x60


def decompress(f: common.Stream, complength: int) -> bytes:
    """Decompress BIOS-compressed data from the current stream position.

    The compression type and decompressed length are read from the 4-byte
    header before the data.

    Args:
        f: Stream to read from.
        complength: Length of the compressed data.

    Returns:
        The decompressed data, or the raw data if the compression type is
        not supported.
    """
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
        return cmp_huff.decompressHuffman(data, decomplength, 4)
    elif type == CompressionType.Huff8:
        return cmp_huff.decompressHuffman(data, decomplength, 8)
    elif type == CompressionType.RLE:
        return cmp_misc.decompressRLE(data, decomplength)
    else:
        common.logError("Unsupported decompression type", common.toHex(type))
        return data


def compress(data: bytes, type: CompressionType) -> bytes:
    """Compress data with the given BIOS compression type.

    The output starts with the 4-byte header holding the compression type
    and the decompressed length.

    Args:
        data: Data to compress.
        type: Compression type to use.

    Returns:
        The compressed data, or the raw data if the compression type is
        not supported.
    """
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
            out.write(cmp_huff.compressHuffman(data, 4))
        elif type == CompressionType.Huff8:
            out.write(cmp_huff.compressHuffman(data, 8))
        elif type == CompressionType.RLE:
            out.write(cmp_misc.compressRLE(data))
        else:
            common.logError("Unsupported compression type", common.toHex(type))
            out.write(data)
        out.seek(0)
        return out.read()


def decompressFile(infile: str, outfile: str) -> None:
    """Decompress a BIOS-compressed file.

    Args:
        infile: Path of the compressed file.
        outfile: Path of the output file.
    """
    insize = os.path.getsize(infile)
    with common.Stream(infile, "rb") as fin:
        with common.Stream(outfile, "wb") as fout:
            fout.write(decompress(fin, insize - 4))


def compressFile(infile: str, outfile: str, type: CompressionType) -> None:
    """Compress a file with the given BIOS compression type.

    Args:
        infile: Path of the file to compress.
        outfile: Path of the output file.
        type: Compression type to use.
    """
    with common.Stream(infile, "rb") as fin:
        data = fin.read()
        with common.Stream(outfile, "wb") as fout:
            fout.write(compress(data, type))


def decompressBinary(infile: str, outfile: str) -> None:
    """Decompress an arm9.bin or overlay file with ndspy.

    Args:
        infile: Path of the compressed file.
        outfile: Path of the output file.
    """
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


def compressBinary(infile: str, outfile: str, arm9: bool = True) -> None:
    """Compress an arm9.bin or overlay file with ndspy.

    For arm9 files, the compressed size in the code settings is updated.

    Args:
        infile: Path of the file to compress.
        outfile: Path of the output file.
        arm9: Whether the file is an arm9.bin, instead of an overlay.
    """
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
