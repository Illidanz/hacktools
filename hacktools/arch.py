import os
from hacktools import common


class ARCHArchive:
    filenum = 0
    tableoff = 0
    fatoff = 0
    nameindexoff = 0
    dataoff = 0
    files = []


class ARCHFile:
    name = ""
    length = 0
    declength = 0
    offset = 0
    nameoffset = 0
    encoded = False


def read(f):
    f.seek(4)  # Magic: ARCH
    archive = ARCHArchive()
    archive.files = []
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


def repack(fin, f, archive, infolder):
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
            # Set the file as not encoded and copy it
            size = os.path.getsize(filepath)
            size += size % 16
            f.seek(archive.fatoff + i * 16)
            f.writeUInt(size)
            f.writeUInt(size)
            f.writeUInt(dataoff)
            f.seek(2, 1)
            f.writeUShort(0)
            f.seek(archive.dataoff + dataoff)
            with common.Stream(filepath, "rb") as subf:
                f.write(subf.read())
        # Align with 0s
        if f.tell() % 16 > 0:
            f.writeZero(16 - (f.tell() % 16))
        dataoff = f.tell() - archive.dataoff


def extract(f, archive, outfolder):
    for subfile in archive.files:
        with common.Stream(outfolder + subfile.name, "wb") as fout:
            f.seek(archive.dataoff + subfile.offset)
            if not subfile.encoded:
                fout.write(f.read(subfile.length))
            else:
                # Based on Tinke's ARCH implementation
                startpos = f.tell()
                buffer1 = []
                buffer2 = []
                for i in range(0x100):
                    buffer1.append(0)
                    buffer2.append(0)
                while f.tell() - startpos < subfile.length:
                    # InitBuffer
                    for i in range(0x100):
                        buffer2[i] = i
                    # FillBuffer
                    index = 0
                    while index != 0x100:
                        id = f.readByte()
                        numloops = id
                        if id > 0x7F:
                            numloops = 0
                            index += id - 0x7F
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
                    nextsamples = []
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
