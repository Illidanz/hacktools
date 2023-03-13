import ctypes
import codecs
import json
import math
import os
import struct
from hacktools import common


def extractIso(isofile, extractfolder, workfolder=""):
    try:
        import pycdlib
    except ImportError:
        common.logError("pycdlib not found")
        return
    common.logMessage("Extracting ISO", isofile, "...")
    common.makeFolder(extractfolder)
    iso = pycdlib.PyCdlib()
    iso.open(isofile)
    for dirname, dirlist, filelist in iso.walk(iso_path="/"):
        common.makeFolders(extractfolder + dirname[1:])
        for file in filelist:
            with open(extractfolder + dirname[1:] + "/" + file, "wb") as f:
                iso.get_file_from_iso_fp(f, iso_path=dirname + "/" + file)
    iso.close()
    if workfolder != "":
        common.copyFolder(extractfolder, workfolder)
    common.logMessage("Done!")


def repackIso(isofile, isopatch, workfolder, patchfile=""):
    try:
        import pycdlib
    except ImportError:
        common.logError("pycdlib not found")
        return
    common.logMessage("Repacking ISO", isopatch, "...")
    common.copyFile(isofile, isopatch)
    iso = pycdlib.PyCdlib()
    iso.open(isopatch, "r+b")
    files = common.getFiles(workfolder)
    for file in common.showProgress(files):
        filelen = os.path.getsize(workfolder + file)
        with open(workfolder + file, "rb") as f:
            iso.modify_file_in_place(f, filelen, "/" + file)
    iso.close()
    common.logMessage("Done!")
    # Create xdelta patch
    if patchfile != "":
        common.xdeltaPatch(patchfile, isofile, isopatch)


# UMD functions
class UMDFile():
    def __init__(self):
        self.realname = ""
        self.filename = ""
        self.pos = 0
        self.lba = 0
        self.offset = 0
        self.offset = 0
        self.oldsize = 0
        self.filelba = 0


def repackUMD(umdfile, umdpatch, workfolder, patchfile="", sectorpadding=1):
    common.logMessage("Repacking UMD", umdpatch, "...")
    allfiles = common.getFiles(workfolder)
    isofiles = []
    with common.Stream(umdfile, "rb") as fin:
        rootlba = fin.readUIntAt(0x809e)
        rootlength = fin.readUIntAt(0x80a6)
        common.logDebug("rootlba", common.toHex(rootlba), "rootlength", common.toHex(rootlength))
        for file in allfiles:
            filename = file.replace(workfolder, "").replace("\\", "/")
            if not filename.startswith("/"):
                filename = "/" + filename
            isofile = UMDFile()
            isofile.realname = file
            isofile.filename = filename
            isofile.pos = searchUMD(fin, filename, "", rootlba, rootlength)
            if isofile.pos == 0:
                common.logError("File", filename, "not found")
                return
            isofile.lba = isofile.pos // 0x800
            isofile.offset = isofile.pos % 0x800
            isofile.oldsize = fin.readUIntAt(isofile.pos + 0xa)
            isofile.filelba = fin.readUIntAt(isofile.pos + 0x2)
            isofiles.append(isofile)
        # Sort files by file lba
        isofiles.sort(key=lambda x: x.filelba)
        with common.Stream(umdpatch, "wb") as f:
            # Copy everything up to the first file LBA
            fin.seek(0)
            f.write(fin.read(isofiles[0].filelba * 0x800))
            # Write all the files
            for isofile in common.showProgress(isofiles):
                common.logDebug(common.varsHex(isofile))
                # Try to keep the lba the same as before if we can
                if f.tell() // 0x800 < isofile.filelba:
                    f.seek(isofile.filelba * 0x800)
                offset = f.tell()
                with common.Stream(workfolder + isofile.realname, "rb") as subf:
                    f.write(subf.read())
                size = f.tell() - offset
                # Pad to sector
                f.seek((f.tell() // (sectorpadding * 0x800) + 1) * (sectorpadding * 0x800))
                # Update volume descriptor
                f.writeUIntAt(isofile.pos + 0x2, offset // 0x800)
                f.writeUIntAt(isofile.pos + 0xa, size)
                f.swapEndian()
                f.writeUIntAt(isofile.pos + 0xe, size)
                f.swapEndian()
            # If the file is smaller, match the original
            fin.seek(0, 2)
            if f.tell() < fin.tell():
                f.seek(fin.tell() - 1)
                f.writeByte(0)
            # Update primary volume descriptor
            f.writeUIntAt(0x8050, f.tell() // 0x800)
            f.swapEndian()
            f.writeUIntAt(0x8054, f.tell() // 0x800)
            f.swapEndian()
    common.logMessage("Done!")
    # Create xdelta patch
    if patchfile != "":
        common.xdeltaPatch(patchfile, umdfile, umdpatch)


def searchUMD(f, filename, path, lba, length):
    common.logDebug("searchUMD path", path, "filename", filename, "lba", common.toHex(lba), "length", common.toHex(length))
    totalsectors = (length + 0x800 - 1) // 0x800
    for i in range(totalsectors):
        pos = 0
        nbytes = 0
        while pos + nbytes < 0x800:
            pos += nbytes
            # Field size
            nbytes = f.readByteAt(0x800 * (lba + i) + pos)
            if nbytes == 0:
                break
            # Name size
            f.seek(0x800 * (lba + i) + pos + 0x20)
            nchars = f.readByte()
            if nchars < 2:
                continue
            name = f.readString(nchars)
            if name.endswith(";1"):
                name = name[:-2]
            if name == "." or name == "..":
                continue
            newpath = path + "/" + name
            # Check if it's a directory, and search recursively in that case
            dirmarker = f.readByteAt(0x800 * (lba + i) + pos + 0x19)
            if dirmarker == 0x2:
                newlba = f.readUIntAt(0x800 * (lba + i) + pos + 0x2)
                newlen = f.readUIntAt(0x800 * (lba + i) + pos + 0xa)
                found = searchUMD(f, filename, newpath, newlba, newlen)
                if found != 0:
                    return found
            elif newpath.lower() == filename.lower():
                return 0x800 * (lba + i) + pos
    return 0


# ELF functions
class ELF():
    def __init__(self):
        self.sections = []
        self.sectionsdict = {}


class ELFSection():
    def __init__(self):
        self.name = ""
        self.nameoff = 0
        self.type = 0
        self.flags = 0
        self.addr = 0
        self.offset = 0
        self.size = 0
        self.link = 0
        self.info = 0
        self.addralign = 0
        self.entsize = 0


def readELF(infile):
    elf = ELF()
    with common.Stream(infile, "rb") as f:
        f.seek(0x20)
        sectionsoff = f.readUInt()
        f.seek(0x2E)
        sectionsize = f.readUShort()
        sectionnum = f.readUShort()
        shstrndx = f.readUShort()
        common.logDebug("sectionsoff:", sectionsoff, "sectionsize:", sectionsize, "sectionnum", sectionnum, "shstrndx", shstrndx)
        # Read section headers
        f.seek(sectionsoff)
        for i in range(sectionnum):
            section = ELFSection()
            section.nameoff = f.readUInt()
            section.type = f.readUInt()
            section.flags = f.readUInt()
            section.addr = f.readUInt()
            section.offset = f.readUInt()
            section.size = f.readUInt()
            section.link = f.readUInt()
            section.info = f.readUInt()
            section.addralign = f.readUInt()
            section.entsize = f.readUInt()
            elf.sections.append(section)
        # Read section names
        for section in elf.sections:
            f.seek(elf.sections[shstrndx].offset + section.nameoff)
            section.name = f.readNullString()
            elf.sectionsdict[section.name] = section
        for i in range(sectionnum):
            common.logDebug(i, vars(elf.sections[i]))
    return elf


def extractBinaryStrings(elf, foundstrings, infile, func, encoding="shift_jis", elfsections=[".rodata"]):
    with common.Stream(infile, "rb") as f:
        for sectionname in elfsections:
            rodata = elf.sectionsdict[sectionname]
            f.seek(rodata.offset)
            while f.tell() < rodata.offset + rodata.size:
                pos = f.tell()
                check = func(f, encoding)
                if check != "":
                    if check not in foundstrings:
                        common.logDebug("Found string at", common.toHex(pos), check)
                        foundstrings.append(check)
                    pos = f.tell() - 1
                f.seek(pos + 1)
    return foundstrings


def repackBinaryStrings(elf, section, infile, outfile, readfunc, writefunc, encoding="shift_jis", elfsections=[".rodata"]):
    with common.Stream(infile, "rb") as fi:
        with common.Stream(outfile, "r+b") as fo:
            for sectionname in elfsections:
                rodata = elf.sectionsdict[sectionname]
                fi.seek(rodata.offset)
                while fi.tell() < rodata.offset + rodata.size:
                    pos = fi.tell()
                    check = readfunc(fi, encoding)
                    if check != "":
                        if check in section and section[check][0] != "":
                            common.logDebug("Replacing string", check, "at", common.toHex(pos), "with", section[check][0])
                            fo.seek(pos)
                            endpos = fi.tell() - 1
                            newlen = writefunc(fo, section[check][0], endpos - pos + 1)
                            if newlen < 0:
                                fo.writeZero(1)
                                common.logError("String", section[check][0], "is too long.")
                            else:
                                fo.writeZero(endpos - fo.tell())
                        else:
                            pos = fi.tell() - 1
                    fi.seek(pos + 1)


def decryptBIN(ebinout, binout):
    try:
        import pyeboot.decrypt
    except ImportError:
        common.logError("pyeboot not found")
        return
    pyeboot.decrypt(ebinout, binout)


def signBIN(binout, ebinout, tag):
    common.logMessage("Signing BIN ...")
    try:
        import pyeboot.sign
        pyeboot.sign(binout, ebinout, str(tag))
    except ImportError:
        common.logMessage("pyeboot not found, copying BOOT to EBOOT...")
        common.copyFile(binout, ebinout)


# https://www.psdevwiki.com/ps3/Graphic_Image_Map_(GIM)
class GIM:
    def __init__(self):
        self.rootoff = 0
        self.rootsize = 0
        self.images = []


class GIMImage:
    def __init__(self):
        self.picoff = 0
        self.picsize = 0
        self.imgoff = 0
        self.imgsize = 0
        self.imgframeoff = 0
        self.format = 0
        self.width = 0
        self.height = 0
        self.tiled = 0
        self.blockedwidth = 0
        self.blockedheight = 0
        self.tilewidth = 0
        self.tileheight = 0
        self.paloff = 0
        self.palsize = 0
        self.palframeoff = 0
        self.palformat = 0
        self.palette = []
        self.colors = []


class TGAImage:
    def __init__(self):
        self.rootoff = 0
        self.format = 0
        self.width = 0
        self.height = 0
        self.imgoff = 0
        self.colors = []


class GMO:
    def __init__(self):
        self.size = 0
        self.names = []
        self.offsets = []
        self.gims = []


def readGMO(file):
    gmo = GMO()
    with common.Stream(file, "rb") as f:
        f.seek(16 + 4)
        gmo.size = f.readUInt()
        f.seek(8, 1)
        while f.tell() < gmo.size + 16:
            readGMOChunk(f, gmo, gmo.size + 16)
    for gimoffset in gmo.offsets:
        common.logDebug("Reading GIM at", common.toHex(gimoffset))
        gim = readGIM(file, gimoffset)
        gmo.gims.append(gim)
    return gmo


def readGMOChunk(f, gmo, maxsize, nesting=""):
    offset = f.tell()
    id = f.readUShort()
    headerlen = f.readUShort()
    blocklen = f.readUInt()
    common.logDebug(nesting + "GMO ID", common.toHex(id), "at", common.toHex(offset), "len", common.toHex(headerlen), common.toHex(blocklen))
    if id == 0xa:  # Texture name
        f.seek(8, 1)
        texname = f.readEncodedString().replace(":", "")
        while texname in gmo.names:
            texname += "_"
        common.logDebug(nesting + "0x0A at", common.toHex(offset), common.toHex(offset + blocklen), texname)
        gmo.names.append(texname)
    elif id == 0x8013:  # Texture data
        f.seek(4, 1)
        gmo.offsets.append(f.tell())
        common.logDebug(nesting + "0x8013 at", common.toHex(f.tell()), common.toHex(offset), common.toHex(offset + blocklen))
    if id != 0x7 and id != 0xc and headerlen > 0:
        f.seek(offset + headerlen)
        common.logDebug(nesting + "Raeding nested blocks:")
        while f.tell() < offset + blocklen - 1 and f.tell() < maxsize:
            readGMOChunk(f, gmo, maxsize, nesting + " ")
        common.logDebug(nesting + "Done")
        f.seek(offset + blocklen)
    else:
        f.seek(offset + blocklen)


def readGIM(file, start=0):
    gim = GIM()
    with common.Stream(file, "rb") as f:
        f.seek(start)
        if f.readString(3) == "MIG":
            f.seek(start + 16)
            gim.rootoff = f.tell()
            id = f.readUShort()
            if id != 0x02:
                common.logError("Unexpected id in block 0:", common.toHex(id), common.toHex(f.tell() - 2))
                return None
            f.seek(2, 1)
            gim.rootsize = f.readUInt()
            nextblock = gim.rootoff + f.readUInt()
            image = None
            while nextblock > 0 and nextblock < start + gim.rootsize + 16:
                f.seek(nextblock)
                nextblock, image = readGIMBlock(f, gim, image)
        else:
            # This is a TGA file, assuming 32bit RGBA
            image = TGAImage()
            image.rootoff = f.tell()
            f.seek(start + 2)
            image.format = f.readByte()
            f.seek(9, 1)
            image.width = f.readUShort()
            image.height = f.readUShort()
            f.seek(2, 1)
            image.imgoff = f.tell()
            for i in range(image.height):
                for j in range(image.width):
                    image.colors.append(readColor(f, 0x03))
            gim = image
    return gim


def readGIMBlock(f, gim, image):
    offset = f.tell()
    id = f.readUShort()
    f.seek(2, 1)
    if id == 0xFF:
        # Info block
        common.logDebug("GIM 0xFF at", common.toHex(offset))
        return 0, image
    elif id == 0x03:
        # Picture block
        common.logDebug("GIM 0x03 at", common.toHex(offset))
        image = GIMImage()
        gim.images.append(image)
        image.picoff = offset
        image.picsize = f.readUInt()
        nextblock = f.readUInt()
        common.logDebug("picoff", image.picoff, "picsize", image.picsize)
        return image.picoff + nextblock, image
    elif id == 0x04:
        # Image block
        common.logDebug("GIM 0x04 at", common.toHex(offset))
        image.imgoff = offset
        image.imgsize = f.readUInt()
        nextblock = f.readUInt()
        f.seek(4, 1)
        image.imgframeoff = f.readUShort()
        f.seek(2, 1)
        image.format = f.readUShort()
        if image.format == 0x04:
            image.bpp = 4
        elif image.format == 0x05:
            image.bpp = 8
        elif image.format == 0x03 or image.format == 0x07:
            image.bpp = 32
        else:
            image.bpp = 16
        image.tiled = f.readUShort()
        image.width = f.readUShort()
        image.height = f.readUShort()
        if image.tiled == 0x01:
            image.tilewidth = 0x80 // image.bpp
            image.tileheight = 8
            image.blockedwidth = math.ceil(image.width / image.tilewidth) * image.tilewidth
            image.blockedheight = math.ceil(image.height / image.tileheight) * image.tileheight
        if image.format > 0x05:
            common.logError("Unsupported image format:", image.format)
            return image.imgoff + nextblock, image
        f.seek(image.imgoff + 32 + image.imgframeoff)
        for i in range(image.blockedheight if image.tiled == 0x01 else image.height):
            for j in range(image.blockedwidth if image.tiled == 0x01 else image.width):
                index = 0
                if image.format == 0x04:
                    index = f.readHalf()
                elif image.format == 0x05:
                    index = f.readByte()
                else:
                    index = readColor(f, image.format)
                image.colors.append(index)
        common.logDebug("imgoff", image.imgoff, "imgsize", image.imgsize, "imgframeoff", image.imgframeoff, "format", image.format, "bpp", image.bpp)
        common.logDebug("tiled", image.tiled, "width", image.width, "height", image.height)
        common.logDebug("blockedwidth", image.blockedwidth, "blockedheight", image.blockedheight, "tilewidth", image.tilewidth, "tileheight", image.tileheight)
        return image.imgoff + nextblock, image
    elif id == 0x05:
        # Palette
        common.logDebug("GIM 0x05 at", common.toHex(offset))
        image.paloff = offset
        image.palsize = f.readUInt()
        nextblock = f.readUInt()
        f.seek(4, 1)
        image.palframeoff = f.readUShort()
        f.seek(2, 1)
        image.palformat = f.readUShort()
        f.seek(image.paloff + 32 + image.palframeoff)
        while f.tell() < image.paloff + nextblock:
            image.palette.append(readColor(f, image.palformat))
        common.logDebug("paloff", image.paloff, "palsize", image.palsize, "palframeoff", image.palframeoff)
        common.logDebug("palformat", image.palformat, "length", len(image.palette))
        return image.paloff + nextblock, image
    else:
        common.logWarning("Skipping unknown block at", offset, ":", id)
        f.seek(4, 1)
        return offset + f.readUInt(), image


def writeGIM(file, gim, infile, backwardspal=False):
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    img = Image.open(infile)
    img = img.convert("RGBA")
    pixels = img.load()
    currheight = 0
    with common.Stream(file, "rb+") as f:
        if isinstance(gim, GIM):
            for image in gim.images:
                f.seek(image.imgoff + 32 + image.imgframeoff)
                if image.tiled == 0x00:
                    for i in range(image.height):
                        for j in range(image.width):
                            writeGIMPixel(f, image, pixels[j, currheight + i], backwardspal)
                else:
                    for blocky in range(image.blockedheight // image.tileheight):
                        for blockx in range(image.blockedwidth // image.tilewidth):
                            for y in range(image.tileheight):
                                for x in range(image.tilewidth):
                                    pixelx = blockx * image.tilewidth + x
                                    pixely = currheight + blocky * image.tileheight + y
                                    if pixelx >= image.width or pixely >= currheight + image.height:
                                        writeGIMPixel(f, image, None, backwardspal)
                                    else:
                                        writeGIMPixel(f, image, pixels[pixelx, pixely], backwardspal)
                if len(image.palette) > 0:
                    palsize = 5 * (len(image.palette) // 8)
                    currheight += max(image.height, palsize)
                else:
                    currheight += image.height
        else:
            f.seek(gim.imgoff)
            for i in range(gim.height):
                for j in range(gim.width):
                   writeColor(f, 0x03, pixels[j, gim.height - 1 - i])


def writeGIMPixel(f, image, color, backwards=False):
    if image.format == 0x04 or image.format == 0x05:
        index = common.getPaletteIndex(image.palette, color, False, 0, -1, True, False, backwards) if color is not None else 0
        if image.format == 0x04:
            f.writeHalf(index)
        elif image.format == 0x05:
            f.writeByte(index)
    else:
        writeColor(f, image.format, color if color is not None else (0, 0, 0, 0))


def readColor(f, format):
    r, g, b, a = (0, 0, 0, 255)
    if format == 0x00:  # RGBA5650
        color = f.readUShort()
        r = ((color & 0x001F)) << 3
        g = ((color & 0x07E0) >> 5) << 2
        b = ((color & 0xF800) >> 11) << 3
    elif format == 0x01:  # RGBA5551
        color = f.readUShort()
        r = ((color & 0x001F)) << 3
        g = ((color & 0x03E0) >> 5) << 3
        b = ((color & 0x7C00) >> 10) << 3
        a = ((color & 0x8000) >> 15) << 7
        a += 127
    elif format == 0x02:  # RGBA4444
        color = f.readUShort()
        r = ((color & 0x000F)) * 0x11
        g = ((color & 0x00F0) >> 4) * 0x11
        b = ((color & 0x0F00) >> 8) * 0x11
        a = ((color & 0xF000) >> 12) * 0x11
    elif format == 0x03:  # RGBA8888
        color = f.readUInt()
        r = (color & 0x000000FF)
        g = (color & 0x0000FF00) >> 8
        b = (color & 0x00FF0000) >> 16
        a = (color & 0xFF000000) >> 24
    return (r, g, b, a)


def writeColor(f, format, color):
    if format == 0x00:  # RGBA5650
        enc = ((color[2] >> 3) << 11) | ((color[1] >> 2) << 5) | (color[0] >> 3)
        f.writeUShort(enc)
    elif format == 0x01:  # RGBA5551
        a = color[3] - 127
        enc = ((a >> 7) << 15) | ((color[2] >> 3) << 10) | ((color[1] >> 3) << 5) | (color[0] >> 3)
        f.writeUShort(enc)
    elif format == 0x02:  # RGBA4444
        enc = ((color[3] >> 4) << 12) | ((color[2] >> 4) << 8) | ((color[1] >> 4) << 4) | (color[0] >> 4)
        f.writeUShort(enc)
    elif format == 0x03:  # RGBA8888
        enc = (color[3] << 24) | (color[2] << 16) | (color[1] << 8) | color[0]
        f.writeUInt(enc)


def drawGIM(outfile, gim):
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    width = 0
    height = 0
    palette = False
    if isinstance(gim, GIM):
        for image in gim.images:
            width = max(width, image.width)
            if len(image.palette) > 0:
                palette = True
                palsize = 5 * (len(image.palette) // 8)
                height += max(image.height, palsize)
            else:
                height += image.height
    else:
        width = gim.width
        height = gim.height
    img = Image.new("RGBA", (width + (40 if palette else 0), height), (0, 0, 0, 0))
    pixels = img.load()
    currheight = 0
    if isinstance(gim, GIM):
        for image in gim.images:
            i = 0
            if image.tiled == 0x00:
                for y in range(image.height):
                    for x in range(image.width):
                        drawGIMPixel(image, pixels, x, currheight + y, i)
                        i += 1
            else:
                for blocky in range(image.blockedheight // image.tileheight):
                    for blockx in range(image.blockedwidth // image.tilewidth):
                        for y in range(image.tileheight):
                            for x in range(image.tilewidth):
                                pixelx = blockx * image.tilewidth + x
                                pixely = currheight + blocky * image.tileheight + y
                                if pixelx >= image.width or pixely >= currheight + image.height:
                                    i += 1
                                    continue
                                drawGIMPixel(image, pixels, pixelx, pixely, i)
                                i += 1
            if len(image.palette) > 0:
                pixels = common.drawPalette(pixels, image.palette, image.width, currheight)
                palsize = 5 * (len(image.palette) // 8)
                currheight += max(image.height, palsize)
            else:
                currheight += image.height
    else:
        i = 0
        for y in range(gim.height):
            for x in range(gim.width):
                pixels[x, gim.height - 1 - y] = gim.colors[i]
                i += 1
    img.save(outfile, "PNG")


def drawGIMPixel(image, pixels, x, y, i):
    if len(image.palette) > 0:
        pixels[x, y] = image.palette[image.colors[i]]
    else:
        pixels[x, y] = image.colors[i]


# Font files
# https://github.com/tpunix/pgftool/blob/master/pgf.h
class PGF:
    def __init__(self):
        self.headerlen = 0
        self.charmaplen = 0
        self.charptrlen = 0
        self.charmapbpe = 0
        self.charptrbpe = 0
        self.charmapmin = 0
        self.charmapmax = 0
        self.charptrscale = 0
        self.dimensionlen = 0
        self.bearingxlen = 0
        self.bearingylen = 0
        self.advancelen = 0
        self.shadowmaplen = 0
        self.shadowmapbpe = 0
        self.dimensionmap = []
        self.bearingxmap = []
        self.bearingymap = []
        self.advancemap = []
        self.shadowmap = []
        self.charmap = []
        self.charptr = []
        self.mapend = 0
        self.glyphpos = 0
        self.ucslist = []
        self.glyphs = []
        self.reversetable = {}

    def ptr2ucs(self, ptr):
        for i in range(self.charmaplen):
            if self.charmap[i] == ptr:
                return self.charmapmin + i
        return 0xffff


class PGFGlyph:
    def __init__(self):
        self.index = 0
        self.ucs = 0
        self.char = ""
        self.size = 0
        self.oldsize = 0
        self.width = 0
        self.height = 0
        self.left = 0
        self.top = 0
        self.flag = 0
        self.totlen = 0
        self.shadow = False
        self.shadowflag = 0
        self.shadowid = 0
        self.dimensionid = -1
        self.bearingxid = -1
        self.bearingyid = -1
        self.advanceid = -1
        self.dimension = {"x": 0, "y": 0}
        self.bearingx = {"x": 0, "y": 0}
        self.bearingy = {"x": 0, "y": 0}
        self.advance = {"x": 0, "y": 0}
        self.bitmap = None


def getBPEValue(bpe, buf, pos, float=False):
    v = 0
    for i in range(bpe):
        v |= ((buf[pos // 8] >> (pos % 8)) & 1) << i
        pos += 1
    if float:
        v = ctypes.c_int(v).value
        v /= 64
    return v, pos


def readBPETable(f, num, bpe):
    table = []
    buf = f.read(((num * bpe + 31) // 32) * 4)
    pos = 0
    for _ in range(num):
        v, pos = getBPEValue(bpe, buf, pos)
        table.append(v)
    return table


def setBPEValue(bpe, buf, pos, data, float=False):
    if float:
        data = ctypes.c_int(data * 64).value
    for i in range(bpe):
        mask = 1 << (pos % 8)
        bit = ((data >> i) << (pos % 8)) & mask
        buf[pos // 8] &= ~mask
        buf[pos // 8] |= bit
        pos += 1
    return pos


def setBPETable(f, num, bpe, table):
    buf = bytearray(((num * bpe + 31) // 32) * 4)
    pos = 0
    for i in range(len(table)):
        pos = setBPEValue(bpe, buf, pos, table[i])
    f.write(buf)


# https://github.com/tpunix/pgftool/blob/master/libpgf.c
def readPGFData(file):
    pgf = PGF()
    with common.Stream(file, "rb") as f:
        # Read header
        f.seek(0x2)
        pgf.headerlen = f.readUShort()
        f.seek(0x10)
        pgf.charmaplen = f.readUInt()
        pgf.charptrlen = f.readUInt()
        pgf.charmapbpe = f.readUInt()
        pgf.charptrbpe = f.readUInt()
        f.seek(0xb6)
        pgf.charmapmin = f.readUShort()
        pgf.charmapmax = f.readUShort()
        f.seek(0x100)
        pgf.charptrscale = f.readUShort()
        pgf.dimensionlen = f.readByte()
        pgf.bearingxlen = f.readByte()
        pgf.bearingylen = f.readByte()
        pgf.advancelen = f.readByte()
        f.seek(102, 1)
        pgf.shadowmaplen = f.readUInt()
        pgf.shadowmapbpe = f.readUInt()
        common.logDebug(vars(pgf))
        # Read other maps
        f.seek(pgf.headerlen)
        for i in range(pgf.dimensionlen):
            pgf.dimensionmap.append({"x": f.readInt() / 64, "y": f.readInt() / 64})
        for i in range(pgf.bearingxlen):
            pgf.bearingxmap.append({"x": f.readInt() / 64, "y": f.readInt() / 64})
        for i in range(pgf.bearingylen):
            pgf.bearingymap.append({"x": f.readInt() / 64, "y": f.readInt() / 64})
        for i in range(pgf.advancelen):
            pgf.advancemap.append({"x": f.readInt() / 64, "y": f.readInt() / 64})
            common.logDebug("Advance", i, pgf.advancemap[i])
        pgf.mapend = f.tell()
        # Read shadowmap table
        if pgf.shadowmaplen > 0:
            pgf.shadowmap = readBPETable(f, pgf.shadowmaplen, pgf.shadowmapbpe)
        # Read charmap table
        pgf.charmap = readBPETable(f, pgf.charmaplen, pgf.charmapbpe)
        # Read charptr table
        pgf.charptr = readBPETable(f, pgf.charptrlen, pgf.charptrbpe)
        for i in range(len(pgf.charptr)):
            pgf.charptr[i] *= pgf.charptrscale
        # Generate dummy UCS list
        for i in range(65536):
            pgf.ucslist.append(i)
        # Load all glyphs
        pgf.glyphpos = f.tell()
        for i in range(pgf.charptrlen):
            ucs = pgf.ptr2ucs(i)
            if pgf.ucslist[ucs] == 0:
                continue
            glyph = PGFGlyph()
            glyph.index = i
            glyph.ucs = ucs
            glyph.char = struct.pack(">H", ucs).decode("utf-16-be")
            for j in range(len(pgf.shadowmap)):
                if pgf.shadowmap[j] == ucs:
                    glyph.shadow = True
            f.seek(pgf.glyphpos + pgf.charptr[i])
            buf = f.read(64)
            pos = 0
            glyph.size, pos = getBPEValue(14, buf, pos)
            glyph.width, pos = getBPEValue(7, buf, pos)
            glyph.height, pos = getBPEValue(7, buf, pos)
            glyph.left, pos = getBPEValue(7, buf, pos)
            glyph.top, pos = getBPEValue(7, buf, pos)
            glyph.flag, pos = getBPEValue(6, buf, pos)
            if glyph.left > 63:
                glyph.left = ctypes.c_int(glyph.left | 0xffffff80).value
            if glyph.top > 63:
                glyph.top = ctypes.c_int(glyph.top | 0xffffff80).value
            glyph.shadowflag, pos = getBPEValue(7, buf, pos)
            glyph.shadowid, pos = getBPEValue(9, buf, pos)
            if glyph.flag & 0x04:
                glyph.dimensionid, pos = getBPEValue(8, buf, pos)
                glyph.dimension["x"] = pgf.dimensionmap[glyph.dimensionid]["x"]
                glyph.dimension["y"] = pgf.dimensionmap[glyph.dimensionid]["y"]
            else:
                glyph.dimension["x"], pos = getBPEValue(32, buf, pos, True)
                glyph.dimension["y"], pos = getBPEValue(32, buf, pos, True)
            if glyph.flag & 0x08:
                glyph.bearingxid, pos = getBPEValue(8, buf, pos)
                glyph.bearingx["x"] = pgf.bearingxmap[glyph.bearingxid]["x"]
                glyph.bearingx["y"] = pgf.bearingxmap[glyph.bearingxid]["y"]
            else:
                glyph.bearingx["x"], pos = getBPEValue(32, buf, pos, True)
                glyph.bearingx["y"], pos = getBPEValue(32, buf, pos, True)
            if glyph.flag & 0x10:
                glyph.bearingyid, pos = getBPEValue(8, buf, pos)
                glyph.bearingy["x"] = pgf.bearingymap[glyph.bearingyid]["x"]
                glyph.bearingy["y"] = pgf.bearingymap[glyph.bearingyid]["y"]
            else:
                glyph.bearingy["x"], pos = getBPEValue(32, buf, pos, True)
                glyph.bearingy["y"], pos = getBPEValue(32, buf, pos, True)
            if glyph.flag & 0x20:
                glyph.advanceid, pos = getBPEValue(8, buf, pos)
                glyph.advance["x"] = pgf.advancemap[glyph.advanceid]["x"]
                glyph.advance["y"] = pgf.advancemap[glyph.advanceid]["y"]
            else:
                glyph.advance["x"], pos = getBPEValue(32, buf, pos, True)
                glyph.advance["y"], pos = getBPEValue(32, buf, pos, True)
            glyph.totlen = pos

            if glyph.char not in pgf.reversetable:
                pgf.reversetable[glyph.char] = []
            pgf.reversetable[glyph.char].append(len(pgf.glyphs))
            pgf.glyphs.append(glyph)
            common.logDebug(vars(glyph))
    return pgf


fontpalette = [(0x0,  0x0,  0x0,  0xff), (0x1f, 0x1f, 0x1f, 0xff), (0x2f, 0x2f, 0x2f, 0xff), (0x3f, 0x3f, 0x3f, 0xff),
               (0x4f, 0x4f, 0x4f, 0xff), (0x5f, 0x5f, 0x5f, 0xff), (0x6f, 0x6f, 0x6f, 0xff), (0x7f, 0x7f, 0x7f, 0xff),
               (0x8f, 0x8f, 0x8f, 0xff), (0x9f, 0x9f, 0x9f, 0xff), (0xaf, 0xaf, 0xaf, 0xff), (0xbf, 0xbf, 0xbf, 0xff),
               (0xcf, 0xcf, 0xcf, 0xff), (0xdf, 0xdf, 0xdf, 0xff), (0xef, 0xef, 0xef, 0xff), (0xff, 0xff, 0xff, 0xff)]


def extractPGFBitmap(buf, glyph, outfile):
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    pos = 0
    i = 0
    bitmapdata = []
    while len(bitmapdata) < glyph.width * glyph.height:
        nb, pos = getBPEValue(4, buf, pos)
        if nb < 8:
            data, pos = getBPEValue(4, buf, pos)
            for i in range(nb + 1):
                bitmapdata.append(data)
        else:
            for i in range(16 - nb):
                data, pos = getBPEValue(4, buf, pos)
                bitmapdata.append(data)
    if glyph.flag & 3 == 2:
        bitmap = [0] * len(bitmapdata)
        i = 0
        for h in range(glyph.width):
            for v in range(glyph.height):
                bitmap[v * glyph.width + h] = bitmapdata[i]
                i += 1
    else:
        bitmap = bitmapdata
    img = Image.new("RGBA", (glyph.width, glyph.height), (0, 0, 0, 0))
    pixels = img.load()
    i = 0
    for y in range(glyph.height):
        for x in range(glyph.width):
            pixels[x, y] = fontpalette[bitmap[i]]
            i += 1
    img.save(outfile)


def bitmapRLE(pixels):
    data = bytearray(1024)
    i = j = pos = rcnt = scnt = rlen = slen = 0
    while i < len(pixels):
        k = i
        rcnt = scnt = 0
        while k < len(pixels):
            rlen = 0
            slen = 0
            j = k + 1
            while j < k + 9 and j < len(pixels):
                if pixels[j - 1] == pixels[j]:
                    j -= 1
                    break
                j += 1
            rlen = j - k
            j = k + 1
            while j < k + 8 and j < len(pixels):
                if pixels[j - 1] != pixels[j]:
                    break
                j += 1
            slen = j - k

            if slen > 2:
                scnt = slen
                break
            elif slen == 2:
                scnt += 2
                k += slen
                if scnt > 6 or rcnt == 0:
                    break
            else:
                rcnt += rlen + scnt
                k += rlen
                scnt = 0
                if rcnt > 7:
                    break

        if rcnt > 8:
            rcnt = 8
        if scnt > 8:
            scnt = 8

        if rcnt > 0:
            pos = setBPEValue(4, data, pos, 16 - rcnt)
            for j in range(rcnt):
                pos = setBPEValue(4, data, pos, pixels[i + j])
            i += rcnt
        elif scnt > 0:
            pos = setBPEValue(4, data, pos, scnt - 1)
            pos = setBPEValue(4, data, pos, pixels[i])
            i += scnt
    return data[:int(math.ceil(pos / 8))]


def repackPGFBitmap(glyph, infile):
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    img = Image.open(infile)
    img = img.convert("RGBA")
    pixels = img.load()
    bmph = []
    bmpv = []
    for y in range(img.height):
        for x in range(img.width):
            bmph.append(common.getPaletteIndex(fontpalette, pixels[x, y]))
    for x in range(img.width):
        for y in range(img.height):
            bmpv.append(common.getPaletteIndex(fontpalette, pixels[x, y]))
    rleh = bitmapRLE(bmph)
    rlev = bitmapRLE(bmpv)
    if len(rleh) <= len(rlev):
        return rleh, 0x01, img.width, img.height
    return rlev, 0x02, img.width, img.height


def extractPGFData(file, outfile, bitmapout="", justadvance=False):
    pgf = readPGFData(file)
    with common.Stream(file, "rb") as fin:
        with codecs.open(outfile, "w", "utf-8") as f:
            for glyph in pgf.glyphs:
                char = glyph.char.replace("=", "<3D>")
                if justadvance:
                    f.write(char + "=" + str(glyph.advance["x"]) + "\n")
                else:
                    data = json.dumps({
                        "width": glyph.width, "height": glyph.height, "left": glyph.left, "top": glyph.top,
                        "dimension": glyph.dimension, "bearingx": glyph.bearingx, "bearingy": glyph.bearingy, "advance": glyph.advance
                    })
                    f.write(char + "=" + data + "\n")
                if bitmapout != "" and glyph.width > 0 and glyph.height > 0:
                    fin.seek(pgf.glyphpos + pgf.charptr[glyph.index] + glyph.totlen // 8)
                    buf = fin.read(1024)
                    extractPGFBitmap(buf, glyph, bitmapout + str(glyph.index).zfill(4) + ".png")


def checkPGFDataMap(datamap, newvalue):
    mapid = -1
    newvaluex = int(newvalue["x"] * 64)
    newvaluey = int(newvalue["y"] * 64)
    for j in range(len(datamap)):
        mapvaluex = int(float(datamap[j]["x"]) * 64)
        mapvaluey = int(float(datamap[j]["y"]) * 64)
        if mapvaluex == newvaluex and mapvaluey == newvaluey:
            mapid = j
            break
    if mapid == -1 and len(datamap) < 255:
        datamap.append({"x": newvalue["x"], "y": newvalue["y"]})
        mapid = len(datamap) - 1
    return mapid


def repackPGFData(fontin, fontout, configfile, bitmapin=""):
    pgf = readPGFData(fontin)
    section = {}
    if os.path.isfile(configfile):
        with codecs.open(configfile, "r", "utf-8") as f:
            section = common.getSection(f, "", "##")
    with common.Stream(fontin, "rb") as fin:
        # Set the new glyphs information
        for char in section:
            jsondata = json.loads(section[char][0])
            char = char.replace("<3D>", "=")
            for glyphindex in pgf.reversetable[char]:
                glyph = pgf.glyphs[glyphindex]
                newsize = 8
                glyph.width = int(jsondata["width"])
                glyph.height = int(jsondata["height"])
                glyph.left = int(jsondata["left"])
                glyph.top = int(jsondata["top"])
                glyph.dimension["x"] = float(jsondata["dimension"]["x"])
                glyph.dimension["y"] = float(jsondata["dimension"]["y"])
                glyph.dimensionid = checkPGFDataMap(pgf.dimensionmap, glyph.dimension)
                newsize += 1 if glyph.dimensionid >= 0 else 8
                glyph.bearingx["x"] = float(jsondata["bearingx"]["x"])
                glyph.bearingx["y"] = float(jsondata["bearingx"]["y"])
                glyph.bearingxid = checkPGFDataMap(pgf.bearingxmap, glyph.bearingx)
                newsize += 1 if glyph.bearingxid >= 0 else 8
                glyph.bearingy["x"] = float(jsondata["bearingy"]["x"])
                glyph.bearingy["y"] = float(jsondata["bearingy"]["y"])
                glyph.bearingyid = checkPGFDataMap(pgf.bearingymap, glyph.bearingy)
                newsize += 1 if glyph.bearingyid >= 0 else 8
                glyph.advance["x"] = float(jsondata["advance"]["x"])
                glyph.advance["y"] = float(jsondata["advance"]["y"])
                glyph.advanceid = checkPGFDataMap(pgf.advancemap, glyph.advance)
                newsize += 1 if glyph.advanceid >= 0 else 8
                bitmapfile = bitmapin + str(glyph.index).zfill(4) + ".png"
                if not os.path.isfile(bitmapfile):
                    fin.seek(pgf.glyphpos + pgf.charptr[glyph.index] + glyph.totlen // 8)
                    glyph.bitmap = fin.read(glyph.size - glyph.totlen // 8)
                    rleflag = glyph.flag & 0b11
                else:
                    glyph.bitmap, rleflag, glyph.width, glyph.height = repackPGFBitmap(glyph, bitmapfile)
                glyph.oldsize = glyph.size
                glyph.size = newsize + len(glyph.bitmap)
                if not glyph.shadow:
                    glyph.shadowid = 0
                    glyph.shadowflag = 21
                else:
                    # TODO: shadow support
                    pass
                glyph.flag = rleflag
                if glyph.dimensionid >= 0:
                    glyph.flag |= 0b000100
                if glyph.bearingxid >= 0:
                    glyph.flag |= 0b001000
                if glyph.bearingyid >= 0:
                    glyph.flag |= 0b010000
                if glyph.advanceid >= 0:
                    glyph.flag |= 0b100000
        pgf.dimensionlen = len(pgf.dimensionmap)
        pgf.bearingxlen = len(pgf.bearingxmap)
        pgf.bearingylen = len(pgf.bearingymap)
        pgf.advancelen = len(pgf.advancemap)
        # Write the file
        with common.Stream(fontout, "wb") as f:
            # Copy the header
            fin.seek(0)
            f.write(fin.read(pgf.headerlen))
            # Write the new lengths
            f.seek(0x102)
            f.writeByte(pgf.dimensionlen)
            f.writeByte(pgf.bearingxlen)
            f.writeByte(pgf.bearingylen)
            f.writeByte(pgf.advancelen)
            # Write the maps
            f.seek(pgf.headerlen)
            for i in range(pgf.dimensionlen):
                f.writeInt(int(pgf.dimensionmap[i]["x"] * 64))
                f.writeInt(int(pgf.dimensionmap[i]["y"] * 64))
            for i in range(pgf.bearingxlen):
                f.writeInt(int(pgf.bearingxmap[i]["x"] * 64))
                f.writeInt(int(pgf.bearingxmap[i]["y"] * 64))
            for i in range(pgf.bearingylen):
                f.writeInt(int(pgf.bearingymap[i]["x"] * 64))
                f.writeInt(int(pgf.bearingymap[i]["y"] * 64))
            for i in range(pgf.advancelen):
                f.writeInt(int(pgf.advancemap[i]["x"] * 64))
                f.writeInt(int(pgf.advancemap[i]["y"] * 64))
            # Copy other tables
            fin.seek(pgf.mapend)
            if pgf.shadowmaplen > 0:
                f.write(fin.read(((pgf.shadowmaplen * pgf.shadowmapbpe + 31) // 32) * 4))
            f.write(fin.read(((pgf.charmaplen * pgf.charmapbpe + 31) // 32) * 4))
            charptrpos = f.tell()
            f.write(fin.read(((pgf.charptrlen * pgf.charptrbpe + 31) // 32) * 4))
            # Write the characters and store the pointers
            charptrs = []
            glyphpos = f.tell()
            for i in range(len(pgf.glyphs)):
                glyph = pgf.glyphs[i]
                glyphptr = f.tell() - glyphpos
                charptrs.append(glyphptr // pgf.charptrscale)
                data = bytearray(8)
                pos = 0
                pos = setBPEValue(14, data, pos, glyph.size)
                pos = setBPEValue(7, data, pos, glyph.width)
                pos = setBPEValue(7, data, pos, glyph.height)
                pos = setBPEValue(7, data, pos, glyph.left)
                pos = setBPEValue(7, data, pos, glyph.top)
                pos = setBPEValue(6, data, pos, glyph.flag)
                pos = setBPEValue(7, data, pos, glyph.shadowflag)
                pos = setBPEValue(9, data, pos, glyph.shadowid)
                f.write(data)
                if glyph.dimensionid >= 0:
                    f.writeByte(glyph.dimensionid)
                else:
                    f.writeInt(int(glyph.dimension["x"] * 64))
                    f.writeInt(int(glyph.dimension["y"] * 64))
                if glyph.bearingxid >= 0:
                    f.writeByte(glyph.bearingxid)
                else:
                    f.writeInt(int(glyph.bearingx["x"] * 64))
                    f.writeInt(int(glyph.bearingx["y"] * 64))
                if glyph.bearingyid >= 0:
                    f.writeByte(glyph.bearingyid)
                else:
                    f.writeInt(int(glyph.bearingy["x"] * 64))
                    f.writeInt(int(glyph.bearingy["y"] * 64))
                if glyph.advanceid >= 0:
                    f.writeByte(glyph.advanceid)
                else:
                    f.writeInt(int(glyph.advance["x"] * 64))
                    f.writeInt(int(glyph.advance["y"] * 64))
                if glyph.width > 0 and glyph.height > 0:
                    if glyph.bitmap is None:
                        fin.seek(pgf.glyphpos + pgf.charptr[glyph.index] + glyph.totlen // 8)
                        glyph.bitmap = fin.read((glyph.oldsize if glyph.oldsize > 0 else glyph.size) - glyph.totlen // 8)
                    f.write(glyph.bitmap)
                if (f.tell() - glyphpos) % pgf.charptrscale > 0:
                    f.writeZero(pgf.charptrscale - ((f.tell() - pgf.glyphpos) % pgf.charptrscale))
            # Write the new char ptr table
            f.seek(charptrpos)
            setBPETable(f, pgf.charptrlen, pgf.charptrbpe, charptrs)


def mpstopmf(infile, outfile, duration):
    with common.Stream(infile, "rb", False) as fin:
        # Check header
        check1 = fin.readUInt()
        check2 = fin.readByte()
        if check1 != 0x1ba or check2 != 0x44:
            common.logError("Input header is wrong", common.toHex(check1), common.toHeck(check2))
            return
        fin.seek(0)
        mpsdata = fin.read()
    # https://github.com/TeamPBCN/pmftools/blob/main/mps2pmf/mps2pmf.cpp
    with common.Stream(outfile, "wb", False) as f:
        # Magic
        f.writeString("PSMF")
        f.writeString("0012")
        # Header size
        f.writeUInt(0x800)
        # MPS size
        f.writeUInt(len(mpsdata))
        f.seek(0x50)
        # Other header values
        f.writeUInt(0x4e)
        f.writeUInt(1)
        f.writeUShort(0x5f90)
        f.writeUShort(0)
        f.writeUInt(duration)
        f.writeUInt(0x61a8)
        f.writeUShort(1)
        f.writeUShort(0x5f90)
        f.writeUShort(0x201)
        f.writeUShort(0)
        f.writeUShort(0x34)
        f.writeUShort(0)
        f.writeUShort(1)
        f.writeUShort(0x5f90)
        f.writeUShort(0)
        f.writeUInt(duration)
        f.writeUShort(1)
        f.writeUInt(0x22)
        f.writeUShort(0x2)
        f.writeUShort(0xe000)
        f.writeUShort(0x21ef)
        f.writeUShort(0)
        f.writeUInt(0x0)
        f.writeUInt(0x1e11)
        f.writeUInt(0xbd00)
        f.writeUShort(0x2004)
        f.seek(0xa0)
        f.writeUShort(0x202)
        # Everything else is 0, write the MPS data
        f.seek(0x800)
        f.write(mpsdata)
