import math
import pycdlib
from io import BytesIO
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
            extracted = BytesIO()
            iso.get_file_from_iso_fp(extracted, iso_path=dirname + "/" + file)
            extracted.seek(0)
            with open(extractfolder + dirname[1:] + "/" + file, "wb") as f:
                f.write(extracted.read())
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
        filebytes = BytesIO()
        with open(workfolder + file, "rb") as f:
            filebytes.write(f.read())
        filelen = filebytes.tell()
        filebytes.seek(0)
        iso.modify_file_in_place(filebytes, filelen, "/" + file)
    iso.close()
    common.logMessage("Done!")
    # Create xdelta patch
    if patchfile != "":
        common.xdeltaPatch(patchfile, isofile, isopatch)


class ELF():
    sections = []
    sectionsdict = {}


class ELFSection():
    name = ""
    nameoff = 0
    type = 0
    flags = 0
    addr = 0
    offset = 0
    size = 0
    link = 0
    info = 0
    addralign = 0
    entsize = 0


def readELF(infile):
    elf = ELF()
    elf.sections = []
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


def extractBinaryStrings(elf, foundstrings, infile, func, encoding="shift_jis"):
    with common.Stream(infile, "rb") as f:
        rodata = elf.sectionsdict[".rodata"]
        f.seek(rodata.offset)
        while f.tell() < rodata.offset + rodata.size:
            pos = f.tell()
            check = func(f, encoding)
            if check != "":
                if check not in foundstrings:
                    common.logDebug("Found string at", pos)
                    foundstrings.append(check)
                pos = f.tell() - 1
            f.seek(pos + 1)
    return foundstrings


def repackBinaryStrings(elf, section, infile, outfile, detectFunc, writeFunc, encoding="shift_jis"):
    rodata = elf.sectionsdict[".rodata"]
    with common.Stream(infile, "rb") as fi:
        with common.Stream(outfile, "r+b") as fo:
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
    rootoff = 0
    rootsize = 0
    images = []


class GIMImage:
    picoff = 0
    picsize = 0
    imgoff = 0
    imgsize = 0
    imgframeoff = 0
    format = 0
    width = 0
    height = 0
    tiled = 0
    blockedwidth = 0
    blockedheight = 0
    tilewidth = 0
    tileheight = 0
    paloff = 0
    palsize = 0
    palframeoff = 0
    palformat = 0
    palette = []
    colors = []


class GMO:
    size = 0
    names = []
    offsets = []
    gims = []


def readGMO(file):
    gmo = GMO()
    gmo.names = []
    gmo.offsets = []
    gmo.gims = []
    with common.Stream(file, "rb") as f:
        f.seek(16 + 4)
        gmo.size = f.readUInt()
        f.seek(8, 1)
        while f.tell() < gmo.size + 16:
            offset = f.tell()
            id = f.readUShort()
            if id <= 0x06 or (id >= 0x08 and id <= 0x0B):
                blocklen = f.readUShort()
                if id == 0x0A:  # Texture name
                    f.seek(12, 1)
                    texname = f.readNullString()
                    common.logDebug("0x0A at", offset, texname)
                    gmo.names.append(texname)
                f.seek(offset + blocklen)
            elif id == 0x07 or id == 0x0C or (id >= 0x8000 and id < 0x9000):
                f.seek(2, 1)
                blocklen = f.readUInt()
                if id == 0x8013:  # Texture data
                    f.seek(4, 1)
                    gmo.offsets.append(f.tell())
                    common.logDebug("0x8013 at", offset)
                f.seek(offset + blocklen)
            else:
                common.logError("Unknown ID", id, "at", offset)
                break
    for gimoffset in gmo.offsets:
        gmo.gims.append(readGIM(file, gimoffset))
    return gmo


def readGIM(file, start=0):
    gim = GIM()
    gim.images = []
    with common.Stream(file, "rb") as f:
        f.seek(start + 16)
        gim.rootoff = f.tell()
        id = f.readUShort()
        if id != 0x02:
            common.logError("Unexpected id in block 0:", id)
            return None
        f.seek(2, 1)
        gim.rootsize = f.readUInt()
        nextblock = gim.rootoff + f.readUInt()
        image = None
        while nextblock > 0 and nextblock < start + gim.rootsize + 16:
            f.seek(nextblock)
            nextblock, image = readGIMBlock(f, gim, image)
    return gim


def readGIMBlock(f, gim, image):
    offset = f.tell()
    id = f.readUShort()
    f.seek(2, 1)
    if id == 0xFF:
        # Info block
        common.logDebug("GIM 0xFF at", offset)
        return 0, image
    elif id == 0x03:
        # Picture block
        common.logDebug("GIM 0x03 at", offset)
        image = GIMImage()
        image.palette = []
        image.colors = []
        gim.images.append(image)
        image.picoff = offset
        image.picsize = f.readUInt()
        nextblock = f.readUInt()
        common.logDebug("picoff", image.picoff, "picsize", image.picsize)
        return image.picoff + nextblock, image
    elif id == 0x04:
        # Image block
        common.logDebug("GIM 0x04 at", offset)
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
        common.logDebug("GIM 0x05 at", offset)
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
    for image in gim.images:
        width = max(width, image.width)
        if len(image.palette) > 0:
            palette = True
            palsize = 5 * (len(image.palette) // 8)
            height += max(image.height, palsize)
        else:
            height += image.height
    img = Image.new("RGBA", (width + (40 if palette else 0), height), (0, 0, 0, 0))
    pixels = img.load()
    currheight = 0
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
    img.save(outfile, "PNG")


def drawGIMPixel(image, pixels, x, y, i):
    if len(image.palette) > 0:
        pixels[x, y] = image.palette[image.colors[i]]
    else:
        pixels[x, y] = image.colors[i]
