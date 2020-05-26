import math
import os
from PIL import Image
from hacktools import common


# Generic extract/repack functions
def extractARC(infolder, outfolder):
    common.makeFolder(outfolder)
    common.logMessage("Extracting ARC to", outfolder, "...")
    files = common.getFiles(infolder, ".arc")
    for file in common.showProgress(files):
        common.logDebug("Processing", file, "...")
        common.execute("wszst EXTRACT " + infolder + file + " -D " + outfolder + file, False)
    common.logMessage("Done! Extracted", len(files), "files")


def extractTPL(infolder, outfolder, splitName=True):
    common.makeFolder(outfolder)
    common.logMessage("Extracting TPL to", outfolder, "...")
    files = common.getFiles(infolder, ".tpl")
    for file in common.showProgress(files):
        common.logDebug("Processing", file, "...")
        filename = file.split("/")[0] if splitName else file
        common.execute("wimgt DECODE " + infolder + file + " -D " + outfolder + filename + "/" + os.path.basename(file).replace(".tpl", ".png"), False)
    common.logMessage("Done! Extracted", len(files), "files")


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


# TPL files
# http://wiki.tockdom.com/wiki/TPL_(File_Format)
class TPL:
    imgnum = 0
    tableoff = 0
    images = []


class TPLImage:
    imgoff = 0
    paloff = 0
    palformat = 0x02
    paldataoff = 0
    palette = []
    width = 0
    height = 0
    format = 0x09
    dataoff = 0
    tilewidth = 8
    tileheight = 8
    blockwidth = 0
    blockheight = 0


def readTPL(file):
    tpl = TPL()
    with common.Stream(file, "rb", False) as f:
        f.seek(4)  # Header
        tpl.imgnum = f.readUInt()
        tpl.tableoff = f.readUInt()
        tpl.images = []
        for i in range(tpl.imgnum):
            image = TPLImage()
            tpl.images.append(image)
            f.seek(tpl.tableoff + i * 8)
            image.imgoff = f.readUInt()
            image.paloff = f.readUInt()
            f.seek(image.paloff)
            palcount = f.readUShort()
            f.seek(1, 1)  # Unpacked
            f.seek(1, 1)  # Padding
            image.palformat = f.readUInt()
            image.paldataoff = f.readUInt()
            if image.palformat != 0x02:
                common.logError("Unimplemented palette format:", image.palformat)
                continue
            f.seek(image.paldataoff)
            image.palette = []
            for j in range(palcount):
                image.palette.append(common.readRGB5A3(f.readShort()))
            f.seek(image.imgoff)
            image.height = f.readUShort()
            image.width = f.readUShort()
            image.format = f.readUInt()
            image.dataoff = f.readUInt()
            if image.format != 0x08 and image.format != 0x09:
                common.logError("Unimplemented image format:", image.format)
                continue
            image.tilewidth = 8
            image.tileheight = 8 if image.format == 0x08 else 4
            image.blockwidth = math.ceil(image.width / image.tilewidth) * image.tilewidth
            image.blockheight = math.ceil(image.height / image.tileheight) * image.tileheight
    return tpl


def writeTPL(file, tpl, infile):
    with common.Stream(file, "r+b", False) as f:
        for i in range(tpl.imgnum):
            image = tpl.images[i]
            imgfile = infile
            if i > 0:
                imgfile = imgfile.replace(".png", ".mm" + str(i) + ".png")
            img = Image.open(imgfile)
            img = img.convert("RGBA")
            pixels = img.load()
            f.seek(image.dataoff)
            for y in range(0, image.blockheight, image.tileheight):
                for x in range(0, image.blockwidth, image.tilewidth):
                    for y2 in range(image.tileheight):
                        for x2 in range(image.tilewidth):
                            index = 0
                            if x + x2 < img.width and y + y2 < img.height:
                                color = pixels[x + x2, y + y2]
                                index = common.getPaletteIndex(image.palette, color, False, 0, -1, True, False)
                            if image.format == 0x08:
                                f.writeHalf(index)
                            else:
                                f.writeByte(index)


# Font files
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
                    glyphs[c] = common.FontGlyph(hdwc[firstcode + i][0], hdwc[firstcode + i][1], hdwc[firstcode + i][2], c, firstchar + i, firstcode + i)
            elif sectiontype == 1:
                for i in range(lastchar - firstchar + 1):
                    charcode = f.readUShort()
                    if charcode == 0xFFFF or charcode >= len(hdwc):
                        continue
                    c = common.codeToChar(firstchar + i)
                    glyphs[c] = common.FontGlyph(hdwc[charcode][0], hdwc[charcode][1], hdwc[charcode][2], c, firstchar + i, firstcode + i)
            else:
                common.logWarning("Unknown section type", sectiontype)
    return glyphs
