import ctypes
import codecs
import json
import math
import os
import struct
import pycdlib
from PIL import Image
from hacktools import common


def extractIso(isofile, extractfolder, workfolder=""):
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


def repackUMD(isofile, isopatch, workfolder, patchfile=""):
    common.logMessage("Repacking ISO", isopatch, "...")
    common.copyFile(isofile, isopatch)
    umdreplace = common.bundledExecutable("UMD-replace.exe")
    if not os.path.isfile(umdreplace):
        common.logError("UMD-replace not found")
        return
    files = common.getFiles(workfolder)
    for file in common.showProgress(files):
        common.execute(umdreplace + " \"{imagename}\" \"{filename}\" \"{newfile}\"".format(imagename=isopatch, filename=file, newfile=workfolder + file), False)
    common.logMessage("Done!")
    # Create xdelta patch
    if patchfile != "":
        common.xdeltaPatch(patchfile, isofile, isopatch)


def signBIN(binout, ebinout, tag):
    common.logMessage("Signing BIN ...")
    sign_np = common.bundledExecutable("sign_np.exe")
    if not os.path.isfile(sign_np):
        common.logMessage("sign_np not found, copying BOOT to EBOOT...")
        common.copyFile(binout, ebinout)
    else:
        common.execute(sign_np + " -elf {binout} {ebinout} {tag}".format(binout=binout, ebinout=ebinout, tag=str(tag)), False)
        common.logMessage("Done!")


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


def repackBinaryStrings(elf, section, infile, outfile, detectFunc, writeFunc, encoding="shift_jis", elfsections=[".rodata"]):
    with common.Stream(infile, "rb") as fi:
        with common.Stream(outfile, "r+b") as fo:
            for sectionname in elfsections:
                rodata = elf.sectionsdict[sectionname]
                fi.seek(rodata.offset)
                while fi.tell() < rodata.offset + rodata.size:
                    pos = fi.tell()
                    check = detectFunc(fi, encoding)
                    if check != "":
                        if check in section and section[check][0] != "":
                            common.logDebug("Replacing string at", pos)
                            fo.seek(pos)
                            endpos = fi.tell() - 1
                            newlen = writeFunc(fo, section[check][0], endpos - pos + 1)
                            if newlen < 0:
                                fo.writeZero(1)
                                common.logError("String", section[check][0], "is too long.")
                            else:
                                fo.writeZero(endpos - fo.tell())
                        else:
                            pos = fi.tell() - 1
                    fi.seek(pos + 1)


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
        texname = f.readNullString()
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
        if f.readString(3) == 'MIG':
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


def writeGIM(file, gim, infile):
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
                            writeGIMPixel(f, image, pixels[j, currheight + i])
                else:
                    for blocky in range(image.blockedheight // image.tileheight):
                        for blockx in range(image.blockedwidth // image.tilewidth):
                            for y in range(image.tileheight):
                                for x in range(image.tilewidth):
                                    pixelx = blockx * image.tilewidth + x
                                    pixely = currheight + blocky * image.tileheight + y
                                    if pixelx >= image.width or pixely >= currheight + image.height:
                                        writeGIMPixel(f, image, None)
                                    else:
                                        writeGIMPixel(f, image, pixels[pixelx, pixely])
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


def writeGIMPixel(f, image, color):
    if image.format == 0x04 or image.format == 0x05:
        index = common.getPaletteIndex(image.palette, color, False, 0, -1, True, False) if color is not None else 0
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
def extractFontData(file, outfile):
    common.logMessage("Extracting font data to", outfile, "...")
    # dump_pgf = common.bundledExecutable("dump_pgf.exe")
    # common.execute(dump_pgf + " -i " + file + " > info.txt")
    if os.path.isfile("info.txt"):
        with codecs.open(outfile, "w", "utf-8") as fout:
            with codecs.open("info.txt", "r", "utf-8") as fin:
                lines = fin.readlines()
            char = ""
            for line in lines:
                line = line.strip()
                if line.startswith("----"):
                    charcode = int(line.split("U_")[1].split(" ")[0], 16)
                    char = chr(charcode)
                elif line.startswith("dimension"):
                    width = int(float(line.split("h=")[1].split("v=")[0].strip()))
                    fout.write(char + "=" + str(width) + "\n")
        # os.remove("info.txt")
    common.logMessage("Done!")


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


def setBPEValue(bpe, buf, pos, data):
    for i in range(bpe):
        mask = 1 << (pos % 8)
        bit = ((data >> i) << (pos % 8)) & mask
        buf[pos // 8] &= ~mask
        buf[pos // 8] |= bit
        pos += 1
    return pos


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


def extractPGFBitmap(f, pgf, glyph, outfile):
    f.seek(pgf.glyphpos + pgf.charptr[glyph.index] + glyph.totlen // 8)
    buf = f.read(1024)
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
                if bitmapout != "" and glyph.index < 200 and glyph.width > 0 and glyph.height > 0:
                    extractPGFBitmap(fin, pgf, glyph, bitmapout + str(glyph.index) + ".png")


def repackPGFData(fontin, fontout, configfile):
    pgf = readPGFData(fontin)
    common.copyFile(fontin, fontout)
    with codecs.open(configfile, "r", "utf-8") as f:
        section = common.getSection(f, "")
    with common.Stream(fontout, "rb+") as f:
        for char in section:
            jsondata = json.loads(section[char][0])
            char = char.replace("<3D>", "=")
            for glyphindex in pgf.reversetable[char]:
                glyph = pgf.glyphs[glyphindex]
                f.seek(pgf.glyphpos + pgf.charptr[glyph.index])
                data = bytearray(f.read(8))
                pos = 0
                pos = setBPEValue(14, data, pos, glyph.size)
                pos = setBPEValue(7, data, pos, jsondata["width"])
                pos = setBPEValue(7, data, pos, jsondata["height"])
                pos = setBPEValue(7, data, pos, jsondata["left"])
                pos = setBPEValue(7, data, pos, jsondata["top"])
                pos = setBPEValue(6, data, pos, glyph.flag)
                f.seek(-8, 1)
                f.write(data)
                f.seek(1 if glyph.flag & 0x04 else 8, 1)
                f.seek(1 if glyph.flag & 0x08 else 8, 1)
                f.seek(1 if glyph.flag & 0x10 else 8, 1)
                newadvancex = int(float(jsondata["advance"]["x"]) * 64)
                newadvancey = int(float(jsondata["advance"]["y"]) * 64)
                if glyph.flag & 0x20:
                    # Need to use an advance ID
                    advanceid = -1
                    for j in range(len(pgf.advancemap)):
                        mapadvancex = int(float(pgf.advancemap[j]["x"]) * 64)
                        mapadvancey = int(float(pgf.advancemap[j]["y"]) * 64)
                        if mapadvancex == newadvancex and mapadvancey == newadvancey:
                            advanceid = j
                            break
                    if advanceid >= 0:
                        f.writeByte(advanceid)
                    else:
                        common.logDebug("Advance not found in map, adding it", section[char][0])
                        newadvanceid = len(pgf.advancemap)
                        f.writeByte(newadvanceid)
                        pgf.advancemap.append({"x": float(jsondata["advance"]["x"]), "y": float(jsondata["advance"]["y"])})
                else:
                    # Just write the advance
                    f.writeInt(newadvancex)
                    f.writeInt(newadvancey)
        if len(pgf.advancemap) > pgf.advancelen:
            f.seek(0x105)
            f.writeByte(len(pgf.advancemap))
            f.seek(pgf.mapend)
            otherdata = f.read()
            f.seek(pgf.mapend)
            for i in range(pgf.advancelen, len(pgf.advancemap)):
                f.writeInt(int(pgf.advancemap[i]["x"] * 64))
                f.writeInt(int(pgf.advancemap[i]["y"] * 64))
            f.write(otherdata)
