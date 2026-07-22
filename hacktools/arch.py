"""Support for ARCH archives, including compression and decompression.

An ARCH archive starts with an "ARCH" magic followed by a header, a name
table, a file allocation table and the file data. Files can optionally be
compressed with a byte-pair encoding scheme, based on Tinke's implementation.
"""
import os
from collections import Counter
from hacktools import common


class ARCHArchive:
    """Structure of an ARCH archive header.

    Attributes:
        filenum: Number of files in the archive.
        tableoff: Offset of the name table.
        fatoff: Offset of the file allocation table.
        nameindexoff: Offset of the name index.
        dataoff: Offset of the file data.
        files: List of files in the archive.
    """
    def __init__(self):
        self.filenum: int = 0
        self.tableoff: int = 0
        self.fatoff: int = 0
        self.nameindexoff: int = 0
        self.dataoff: int = 0
        self.files: list[ARCHFile] = []


class ARCHFile:
    """Structure of a single file entry in an ARCH archive.

    Attributes:
        name: File name, read from the archive name table.
        length: Length of the file data as stored in the archive.
        declength: Decompressed length, equal to length if not encoded.
        offset: Offset of the file data, relative to the archive dataoff.
        nameoffset: Offset of the file name, relative to the archive tableoff.
        encoded: Whether the file data is compressed.
    """
    def __init__(self):
        self.name: str = ""
        self.length: int = 0
        self.declength: int = 0
        self.offset: int = 0
        self.nameoffset: int = 0
        self.encoded: bool = False


def read(f: common.Stream) -> ARCHArchive:
    """Read the header and file table of an ARCH archive.

    Args:
        f: Stream opened on the archive file.

    Returns:
        The parsed archive structure.
    """
    f.seek(4)  # Magic: ARCH
    archive = ARCHArchive()
    archive.filenum = f.readUInt()
    archive.tableoff = f.readUInt()
    archive.fatoff = f.readUInt()
    archive.nameindexoff = f.readUInt()
    archive.dataoff = f.readUInt()
    common.logDebug("Archive:", vars(archive))
    for i in range(archive.filenum):
        f.seek(archive.fatoff + i * 16)
        subfile = ARCHFile()
        subfile.length = f.readUInt()
        subfile.declength = f.readUInt()
        subfile.offset = f.readUInt()
        subfile.nameoffset = f.readUShort()
        subfile.encoded = f.readUShort() == 1
        f.seek(archive.tableoff + subfile.nameoffset)
        subfile.name = f.readNullString()
        common.logDebug("File", i, vars(subfile))
        archive.files.append(subfile)
    return archive


def repack(fin: common.Stream, f: common.Stream, archive: ARCHArchive, infolder: str) -> None:
    """Repack an ARCH archive, replacing the files found in a folder.

    Files that exist in infolder are read from there, compressing the ones
    marked as encoded in the archive, while the others are copied from fin.
    File data is aligned to 16 bytes with zeros.

    Args:
        fin: Stream opened on the original archive file.
        f: Stream opened on the output archive file.
        archive: Archive structure returned by :func:`read`.
        infolder: Path of the folder containing the replacement files.
    """
    # Copy everything up to dataoff
    fin.seek(0)
    f.seek(0)
    f.write(fin.read(archive.dataoff))
    # Loop the files
    dataoff = 0
    for i in range(archive.filenum):
        subfile = archive.files[i]
        filepath = infolder + subfile.name
        if not os.path.isfile(filepath):
            # Just update the offset and copy the file
            f.seek(archive.fatoff + i * 16)
            f.seek(8, 1)
            f.writeUInt(dataoff)
            fin.seek(archive.dataoff + subfile.offset)
            f.seek(archive.dataoff + dataoff)
            f.write(fin.read(subfile.length))
        else:
            size = os.path.getsize(filepath)
            f.seek(archive.fatoff + i * 16)
            # If the file was not compressed, just copy it
            if not subfile.encoded:
                f.writeUInt(size)
                f.writeUInt(size)
                f.writeUInt(dataoff)
                f.seek(2, 1)
                f.writeUShort(0)
                f.seek(archive.dataoff + dataoff)
                with common.Stream(filepath, "rb") as subf:
                    f.write(subf.read())
            else:
                common.logDebug("Compressing", subfile.name)
                with common.Stream(filepath, "rb") as subf:
                    filedata = subf.read()
                    compdata = compress(filedata)
                f.writeUInt(len(compdata))
                f.writeUInt(size)
                f.writeUInt(dataoff)
                f.seek(2, 1)
                f.writeUShort(1)
                f.seek(archive.dataoff + dataoff)
                f.write(compdata)
        # Align with 0s
        if f.tell() % 16 > 0:
            f.writeZero(16 - (f.tell() % 16))
        dataoff = f.tell() - archive.dataoff


def extract(f: common.Stream, archive: ARCHArchive, outfolder: str) -> None:
    """Extract all the files of an ARCH archive to a folder.

    Files marked as encoded are decompressed.

    Args:
        f: Stream opened on the archive file.
        archive: Archive structure returned by :func:`read`.
        outfolder: Path of the folder to extract the files to.
    """
    for subfile in archive.files:
        with common.Stream(outfolder + subfile.name, "wb") as fout:
            f.seek(archive.dataoff + subfile.offset)
            if not subfile.encoded:
                fout.write(f.read(subfile.length))
            else:
                fout.write(decompress(f.read(subfile.length), subfile.declength))


def compress(data: bytes) -> bytes:
    """Compress data with the byte-pair encoding used by ARCH archives.

    The most common byte pairs are recursively replaced with single bytes
    that don't occur in the data, and a dictionary of these replacements is
    written before the encoded content.

    Args:
        data: Data to compress.

    Returns:
        The compressed data.
    """
    # Find unused bytes in the data
    dictkeys = []
    for i in range(1, 0x100):
        dictkeys.append(i)
    for b in data:
        if b in dictkeys:
            dictkeys.remove(b)
    dictvalues = {}
    # Recursively find the most used pair and replace it in the copied data
    content = bytearray(data)
    while True:
        if len(dictkeys) == 0:
            break
        # Write all the pairs in a list, for simplicity will just stick to halfwords
        allpairs = []
        for i in range(len(content) // 2):
            allpairs.append((content[i], content[i+1]))
        # Find the most common one
        c = Counter(allpairs).most_common(1)
        if len(c) < 1:
            break
        pair = c[0]
        if pair[1] < 4:
            break
        dictkey = dictkeys.pop()
        common.logDebug("setting pair", common.toHex(pair[0][0]), common.toHex(pair[0][1]), "with", pair[1], "occurrences as dict key", common.toHex(dictkey))
        dictvalues[dictkey] = pair[0]
        content = content.replace(bytes(pair[0]), bytes([dictkey]))
    with common.Stream() as f:
        # Write the dictionary values
        currentkey = 0
        ordkeys = list(dictvalues.keys())
        ordkeys.sort()
        isconsecutive = False
        # Special case where there are no dict keys
        if len(ordkeys) == 0:
            f.writeByte(0x7f + 0x7f)
            f.writeByte(0x7f)
            f.writeByte(0x7f + 0x7f)
            f.writeByte(0xff)
            currentkey = 0x100
        else:
            for i in range(len(ordkeys)):
                dictkey = ordkeys[i]
                common.logDebug("Writing key", common.toHex(dictkey))
                # If the key is not consecutive, we need to skip places
                if dictkey > currentkey:
                    keydiff = dictkey - currentkey
                    # Since we can only skip 0x7f bytes, we need to do an additional skip if it's bigger
                    while keydiff > 0x7f:
                        f.writeByte(0x7f + 0x7f)
                        # Also write a byte equal to the index
                        f.writeByte(0x7f)
                        keydiff -= 0x80
                    f.writeByte(keydiff + 0x7f)
                    currentkey = dictkey
                    isconsecutive = False
                elif not isconsecutive:
                    # If this is the first time we're writing a key, we need to check how many consecutive ones there are
                    consecutive = 1
                    for j in range(i+1, len(ordkeys)):
                        if ordkeys[j] == dictkey + consecutive:
                            consecutive += 1
                    f.writeByte(consecutive - 1)
                    isconsecutive = True
                common.logDebug("Writing key pairs", common.toHex(dictvalues[dictkey][0]), common.toHex(dictvalues[dictkey][1]))
                f.writeByte(dictvalues[dictkey][0])
                # Don't write the 2nd byte if it's the same as the index (shouldn't happen)
                if dictvalues[dictkey][1] != dictkey:
                    f.writeByte(dictvalues[dictkey][1])
                currentkey += 1
        # We're forced to write all indexes even if they aren't used
        if currentkey < 0x100:
            f.writeByte(0x100 - currentkey - 1)
            while currentkey < 0x100:
                f.writeByte(currentkey)
                currentkey += 1
        # Write the actual content
        numloopspos = f.tell()
        f.writeByte(0)
        f.writeByte(0)
        numloops = 0
        for b in content:
            f.writeByte(b)
            numloops += 1
        f.seek(numloopspos)
        f.writeByte(numloops >> 8)
        f.writeByte(numloops & 0xff)
        f.seek(0)
        return f.read()


def decompress(data: bytes, declen: int) -> bytes:
    """Decompress byte-pair encoded data from an ARCH archive.

    Args:
        data: Data to decompress.
        declen: Expected length of the decompressed data, currently unused.

    Returns:
        The decompressed data.
    """
    with common.Stream() as f:
        with common.Stream() as fout:
            f.write(data)
            f.seek(0)
            # Based on Tinke's ARCH implementation
            buffer1 = []
            buffer2 = []
            for i in range(0x100):
                buffer1.append(0)
                buffer2.append(0)
            while f.tell() < len(data):
                # InitBuffer
                for i in range(0x100):
                    buffer2[i] = i
                # FillBuffer
                index = 0
                while index != 0x100:
                    bufid = f.readByte()
                    numloops = bufid
                    if bufid > 0x7f:
                        numloops = 0
                        index += bufid - 0x7f
                    if index == 0x100:
                        break
                    if numloops < 0:
                        continue
                    for i in range(numloops + 1):
                        byte = f.readByte()
                        buffer2[index] = byte
                        if byte != index:
                            buffer1[index] = f.readByte()
                        index += 1
                # Process
                numloops = (f.readByte() << 8) + f.readByte()
                common.logDebug("Decompressing with", common.toHex(numloops), "loops starting at", common.toHex(f.tell()))
                nextsamples: list[int] = []
                while True:
                    if len(nextsamples) == 0:
                        if numloops == 0:
                            break
                        numloops -= 1
                        index = f.readByte()
                    else:
                        index = nextsamples.pop()
                    if buffer2[index] == index:
                        fout.writeByte(index)
                    else:
                        nextsamples.append(buffer1[index])
                        nextsamples.append(buffer2[index])
                        index = len(nextsamples)
                common.logDebug("Finished at", common.toHex(f.tell()), "with numloops", common.toHex(numloops))
            fout.seek(0)
            return fout.read()