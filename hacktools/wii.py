import codecs
import math
import os
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


def extractBREFT(infolder, tempfolder, outfolder):
    common.makeFolder(tempfolder)
    common.makeFolder(outfolder)
    common.logMessage("Extracting BREFT to", outfolder, "...")
    files = common.getFiles(infolder, ".breft")
    for file in common.showProgress(files):
        common.logDebug("Processing", file, "...")
        outfile = file.split("/")
        outfile = "/" + outfile[1] + "/" + outfile[3]
        common.execute("wszst EXTRACT " + infolder + file + " -D " + tempfolder + outfile, False)
        for imgfile in os.listdir(tempfolder + outfile + "/files"):
            common.execute("wimgt DECODE " + tempfolder + outfile + "/files/" + imgfile + " -D " + outfolder + outfile + "/" + imgfile + ".png", False)
    common.logMessage("Done! Extracted", len(files), "files")


def extractBRFNT(infile, outfile):
    brfnt2tpl = common.bundledExecutable("brfnt2tpl.exe")
    if not os.path.isfile(brfnt2tpl):
        common.logError("brfnt2tpl not found")
        return
    common.execute(brfnt2tpl + " {file}".format(file=infile), False)
    common.execute("wimgt DECODE " + infile.replace(".brfnt", ".tpl") + " -D " + outfile, False)
    os.remove(infile.replace(".brfnt", ".tpl"))
    os.remove(infile.replace(".brfnt", ".vbfta"))


def repackBRFNT(outfile, workfile):
    brfnt2tpl = common.bundledExecutable("brfnt2tpl.exe")
    if not os.path.isfile(brfnt2tpl):
        common.logError("brfnt2tpl not found")
        return
    common.execute(brfnt2tpl + " {file}".format(file=outfile), False)
    tplfile = outfile.replace(".brfnt", ".tpl")
    tpl = readTPL(tplfile)
    writeTPL(tplfile, tpl, workfile)
    common.execute(brfnt2tpl + " {file}".format(file=outfile.replace(".brfnt", ".tpl")), False)
    os.remove(outfile.replace(".brfnt", ".tpl"))
    os.remove(outfile.replace(".brfnt", ".vbfta"))


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
    def __init__(self):
        self.imgnum = 0
        self.tableoff = 0
        self.images = []


class TPLImage:
    def __init__(self):
        self.imgoff = 0
        self.paloff = 0
        self.palformat = 0x02
        self.paldataoff = 0
        self.palette = []
        self.width = 0
        self.height = 0
        self.format = 0x09
        self.dataoff = 0
        self.tilewidth = 8
        self.tileheight = 8
        self.blockwidth = 0
        self.blockheight = 0


def readTPL(file):
    tpl = TPL()
    with common.Stream(file, "rb", False) as f:
        f.seek(4)  # Header
        tpl.imgnum = f.readUInt()
        tpl.tableoff = f.readUInt()
        for i in range(tpl.imgnum):
            image = TPLImage()
            tpl.images.append(image)
            f.seek(tpl.tableoff + i * 8)
            image.imgoff = f.readUInt()
            image.paloff = f.readUInt()
            if image.paloff > 0:
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
                for j in range(palcount):
                    image.palette.append(common.readRGB5A3(f.readShort()))
            f.seek(image.imgoff)
            image.height = f.readUShort()
            image.width = f.readUShort()
            image.format = f.readUInt()
            image.dataoff = f.readUInt()
            if image.format != 0x02 and image.format != 0x08 and image.format != 0x09:
                common.logError("Unimplemented image format:", image.format)
                continue
            image.tilewidth = 8
            image.tileheight = 8 if image.format == 0x08 else 4
            image.blockwidth = math.ceil(image.width / image.tilewidth) * image.tilewidth
            image.blockheight = math.ceil(image.height / image.tileheight) * image.tileheight
    return tpl


def writeTPL(file, tpl, infile):
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    with common.Stream(file, "r+b", False) as f:
        for i in range(tpl.imgnum):
            image = tpl.images[i]
            imgfile = infile
            if i > 0:
                imgfile = imgfile.replace(".png", ".mm" + str(i) + ".png")
            img = Image.open(imgfile)
            img = img.convert("RGBA")
            if img.width != image.width or img.height != image.height:
                image.width = img.width
                image.height = img.height
                image.blockwidth = math.ceil(image.width / image.tilewidth) * image.tilewidth
                image.blockheight = math.ceil(image.height / image.tileheight) * image.tileheight
                f.seek(image.imgoff)
                f.writeUShort(image.height)
                f.writeUShort(image.width)
            pixels = img.load()
            f.seek(image.dataoff)
            for y in range(0, image.blockheight, image.tileheight):
                for x in range(0, image.blockwidth, image.tilewidth):
                    for y2 in range(image.tileheight):
                        for x2 in range(image.tilewidth):
                            index = 0
                            if x + x2 < img.width and y + y2 < img.height:
                                color = pixels[x + x2, y + y2]
                                if image.format == 0x02:
                                    index = ((color[3] // 0x11) << 4) | (color[0] // 0x11)
                                else:
                                    index = common.getPaletteIndex(image.palette, color, False, 0, -1, True, False)
                            if image.format == 0x08:
                                f.writeHalf(index, False)
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
                    if charcode == 0xffff or charcode >= len(hdwc):
                        continue
                    c = common.codeToChar(firstchar + i)
                    glyphs[c] = common.FontGlyph(hdwc[charcode][0], hdwc[charcode][1], hdwc[charcode][2], c, firstchar + i, charcode)
            else:
                common.logWarning("Unknown section type", sectiontype)
    return glyphs


def extractFontData(file, outfile):
    common.logMessage("Extracting font data to", outfile, "...")
    glyphs = getFontGlyphs(file)
    with codecs.open(outfile, "w", "utf-8") as f:
        for glyph in glyphs.values():
            char = glyph.char if glyph.char != "=" else "<3D>"
            f.write(char + "=" + str(glyph.start) + "," + str(glyph.width) + "," + str(glyph.length) + "\n")
    common.logMessage("Done!")


def repackFontData(infile, outfile, datafile):
    common.logMessage("Repacking font data from", datafile, "...")
    common.copyFile(infile, outfile)
    glyphs = getFontGlyphs(infile)
    with codecs.open(datafile, "r", "utf-8") as f:
        section = common.getSection(f, "")
    if len(section) == 0:
        return
    with common.Stream(outfile, "rb+", False) as f:
        # Header
        f.seek(36)
        hdwcoffset = f.readUInt()
        # HDWC
        f.seek(hdwcoffset - 4)
        hdwclen = f.readUInt()
        tilenum = (hdwclen - 16) // 3
        f.seek(8, 1)
        for i in range(tilenum):
            found = False
            for glyph in glyphs.values():
                if glyph.index == i:
                    sectionglyph = glyph.char if glyph.char != "=" else "<3D>"
                    if sectionglyph in section:
                        common.logDebug("Writing", section[sectionglyph][0], "at", f.tell())
                        fontdata = section[sectionglyph][0].split(",")
                        f.writeSByte(int(fontdata[0]))
                        f.writeByte(int(fontdata[1]))
                        f.writeByte(int(fontdata[2]))
                        found = True
                        break
            if not found:
                f.seek(3, 1)
    common.logMessage("Done!")
