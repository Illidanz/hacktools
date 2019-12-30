import math
import os
from PIL import Image
from hacktools import common


def extractIso(isofile, extractfolder, workfolder=""):
    common.logMessage("Extracting ISO", isofile, "...")
    common.makeFolder(extractfolder)
    common.execute("wit EXTRACT -o {iso} {folder}".format(iso=isofile, folder=extractfolder), False)
    if workfolder != "":
        common.copyFolder(extractfolder, workfolder)
    common.logMessage("Done!")


def repackIso(isofile, isopatch, workfolder, patchfile=""):
    common.logMessage("Repacking ISO", isopatch, "...")
    if os.path.isfile(isopatch):
        os.remove(isopatch)
    common.execute("wit COPY {folder} {iso}".format(folder=workfolder, iso=isopatch), False)
    common.logMessage("Done!")


# https://github.com/marco-calautti/Rainbow/blob/master/Rainbow.ImgLib/ImgLib/Common/ImageUtils.cs
cc38 = [
    0x00, 0x24, 0x49, 0x6d,  0x92, 0xb6, 0xdb, 0xff
]
cc48 = [
    0x00, 0x11, 0x22, 0x33,  0x44, 0x55, 0x66, 0x77,  0x88, 0x99, 0xaa, 0xbb,  0xcc, 0xdd, 0xee, 0xff
]
cc58 = [
    0x00, 0x08, 0x10, 0x19,  0x21, 0x29, 0x31, 0x3a,  0x42, 0x4a, 0x52, 0x5a,  0x63, 0x6b, 0x73, 0x7b,
    0x84, 0x8c, 0x94, 0x9c,  0xa5, 0xad, 0xb5, 0xbd,  0xc5, 0xce, 0xd6, 0xde,  0xe6, 0xef, 0xf7, 0xff
]


# https://github.com/marco-calautti/Rainbow/blob/master/Rainbow.ImgLib/ImgLib/Encoding/Implementation/ColorCodecRGB5A3.cs
def readRGB5A3(color):
    r, g, b, a = (0, 0, 0, 0)
    if color & 0x8000 != 0:
        a = 255
        r = cc58[(color >> 10) & 0x1F]
        g = cc58[(color >> 5) & 0x1F]
        b = cc58[(color) & 0x1F]
    else:
        a = cc38[(color >> 12) & 0x7]
        r = cc48[(color >> 8) & 0xF]
        g = cc48[(color >> 4) & 0xF]
        b = cc48[(color) & 0xF]
    return (r, g, b, a)


# http://wiki.tockdom.com/wiki/TPL_(File_Format)
def writeTPL(file, infile):
    with common.Stream(file, "r+b", False) as f:
        f.seek(4)  # Header
        imgnum = f.readUInt()
        tableoff = f.readUInt()
        for i in range(imgnum):
            imgfile = infile
            if i > 0:
                imgfile = imgfile.replace(".png", ".mm" + str(i) + ".png")
            img = Image.open(imgfile)
            img = img.convert("RGBA")
            pixels = img.load()
            f.seek(tableoff + i * 8)
            imgoff = f.readUInt()
            paloff = f.readUInt()
            f.seek(paloff)
            palcount = f.readUShort()
            f.seek(1, 1)  # Unpacked
            f.seek(1, 1)  # Padding
            palformat = f.readUInt()
            paldataoff = f.readUInt()
            if palformat != 0x02:
                common.logError("Unimplemented palette format: " + str(palformat))
                continue
            palette = []
            f.seek(paldataoff)
            for j in range(palcount):
                palette.append(readRGB5A3(f.readShort()))
            f.seek(imgoff)
            height = f.readUShort()
            width = f.readUShort()
            format = f.readUInt()
            dataoff = f.readUInt()
            if format != 0x08 and format != 0x09:
                common.logError("Unimplemented image format: " + str(format))
                continue
            blockwidth = 8
            blockheight = 8 if format == 0x08 else 4
            blockedwidth = math.ceil(width / blockwidth) * blockwidth
            blockedheight = math.ceil(height / blockheight) * blockheight
            x = 0
            y = 0
            f.seek(dataoff)
            while y < blockedheight:
                for y2 in range(blockheight):
                    for x2 in range(blockwidth):
                        index = 0
                        if x + x2 < img.width and y + y2 < img.height:
                            color = pixels[x + x2, y + y2]
                            index = common.getPaletteIndex(palette, color, False, 0, -1, True, False)
                        if format == 0x08:
                            f.writeHalf(index)
                        else:
                            f.writeByte(index)
                x += blockwidth
                if x >= blockedwidth:
                    x = 0
                    y += blockheight


def getFontGlyphs(file):
    glyphs = {}
    with common.Stream(file, "rb", False) as f:
        # Header
        f.seek(36)
        hdwcoffset = f.readUInt()
        pamcoffset = f.readUInt()
        common.logDebug("hdwcoffset:", hdwcoffset, "pamcoffset:", pamcoffset)
        # HDWC
        f.seek(hdwcoffset - 4)
        hdwclen = f.readUInt()
        tilenum = (hdwclen - 16) // 3
        firstcode = f.readUShort()
        lastcode = f.readUShort()
        f.seek(4, 1)
        common.logDebug("firstcode:", firstcode, "lastcode:", lastcode, "tilenum", tilenum)
        hdwc = []
        for i in range(tilenum):
            hdwcstart = f.readSByte()
            hdwcwidth = f.readByte()
            hdwclength = f.readByte()
            hdwc.append((hdwcstart, hdwcwidth, hdwclength))
        # PAMC
        nextoffset = pamcoffset
        while nextoffset != 0x00:
            f.seek(nextoffset)
            firstchar = f.readUShort()
            lastchar = f.readUShort()
            sectiontype = f.readUShort()
            f.seek(2, 1)
            nextoffset = f.readUInt()
            common.logDebug("firstchar:", common.toHex(firstchar), "lastchar:", common.toHex(lastchar), "sectiontype:", sectiontype, "nextoffset:", nextoffset)
            if sectiontype == 0:
                firstcode = f.readUShort()
                for i in range(lastchar - firstchar + 1):
                    c = common.codeToChar(firstchar + i)
                    glyphs[c] = hdwc[firstcode + i] + (firstchar + i,)
            elif sectiontype == 1:
                for i in range(lastchar - firstchar + 1):
                    charcode = f.readUShort()
                    if charcode == 0xFFFF or charcode >= len(hdwc):
                        continue
                    c = common.codeToChar(firstchar + i)
                    glyphs[c] = hdwc[charcode] + (firstchar + i,)
            else:
                common.logError("Unknown section type", sectiontype)
    return glyphs
