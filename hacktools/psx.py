import codecs
import struct
import os
from hacktools import common


# Image functions
def extractBIN(infolder, outfolder, cuefile):
    try:
        import pymkpsxiso
    except ImportError:
        common.logError("pymkpsxiso not found")
        return
    common.logMessage("Extracting BIN", cuefile, "...")
    common.makeFolder(infolder)
    pymkpsxiso.dump(cuefile.replace(".cue", ".bin"), infolder[:-1], infolder[:-1] + ".xml")
    common.logMessage("Copying data to", outfolder, "...")
    common.copyFolder(infolder, outfolder)
    with open(infolder[:-1] + ".xml", "r") as f:
        xml = f.read()
    with open(outfolder[:-1] + ".xml", "w") as f:
        f.write(xml.replace("extract/", "repack/"))
    common.logMessage("Done!")


def repackBIN(infolder, binin, binout, cuefile, patchfile=""):
    try:
        import pymkpsxiso
    except ImportError:
        common.logError("pymkpsxiso not found")
        return
    common.logMessage("Repacking BIN", binout, "...")
    pymkpsxiso.make(binout, cuefile, infolder[:-1] + ".xml")
    common.logMessage("Done!")
    # Create xdelta patch
    if patchfile != "":
        common.xdeltaPatch(patchfile, binin, binout)


# Binary-related functions
def extractEXE(binrange, readfunc=common.detectEncodedString, encoding="shift_jis", exein="", exefile="data/exe_output.txt", writepos=False):
    common.logMessage("Extracting EXE to", exefile, "...")
    if type(binrange) == tuple:
        binrange = [binrange]
    strings, positions = common.extractBinaryStrings(exein, binrange, readfunc, encoding)
    with codecs.open(exefile, "w", "utf-8") as out:
        for i in range(len(strings)):
            if writepos:
                out.write(common.toHex(positions[i][0]) + "!")
            out.write(strings[i] + "=\n")
    common.logMessage("Done! Extracted", len(strings), "lines")


def repackEXE(binrange, freeranges=None, manualptrs=None, readfunc=common.detectEncodedString, writefunc=common.writeEncodedString, encoding="shift_jis", comments="#", exein="", exeout="", ptrfile="data/manualptrs.asm", exefile="data/exe_input.txt"):
    if not os.path.isfile(exefile):
        common.logError("Input file", exefile, "not found")
        return False

    common.copyFile(exein, exeout)
    common.logMessage("Repacking EXE from", exefile, "...")
    section = {}
    with codecs.open(exefile, "r", "utf-8") as bin:
        section = common.getSection(bin, "", comments)
        chartot, transtot = common.getSectionPercentage(section)
    if type(binrange) == tuple:
        binrange = [binrange]
    notfound = common.repackBinaryStrings(section, exein, exeout, binrange, freeranges, readfunc, writefunc, encoding, 0x8000f800)
    # Handle not found pointers by manually replacing the opcodes
    if len(notfound) > 0 and manualptrs is not None:
        with open(ptrfile, "w") as f:
            for ptr in notfound:
                if ptr.old not in manualptrs:
                    common.logError("Manual pointer", common.toHex(ptr.old), "->", common.toHex(ptr.new), "not found for string", ptr.str)
                    continue
                for manualptr in manualptrs[ptr.old]:
                    ptrloc = manualptr[0]
                    ptrreg = manualptr[1]
                    common.logDebug("Reassembling manual pointer", common.toHex(ptr.old), "->", common.toHex(ptr.new), "at", common.toHex(ptrloc), ptrreg)
                    f.write(".org 0x" + common.toHex(ptrloc) + "\n")
                    f.write(".area 0x8,0x0\n")
                    f.write("  li " + ptrreg + ",0x" + common.toHex(ptr.new) + "\n")
                    f.write(".endarea\n\n")
    common.logMessage("Done! Translation is at {0:.2f}%".format((100 * transtot) / chartot))
    return True


# Images
def extractTIM(infolder, outfolder, extensions=".tim", readfunc=None):
    common.makeFolder(outfolder)
    common.logMessage("Extracting TIM to", outfolder, "...")
    files = common.getFiles(infolder, extensions)
    for file in common.showProgress(files):
        common.logDebug("Processing", file, "...")
        extension = os.path.splitext(file)[1]
        if readfunc is not None:
            tim, transp, forcepal = readfunc(infolder + file)
        else:
            transp = False
            forcepal = -1
            with common.Stream(infolder + file, "rb") as f:
                tim = readTIM(f)
        if tim is None:
            continue
        # Export img
        common.makeFolders(outfolder + os.path.dirname(file))
        outfile = outfolder + file.replace(extension, ".png")
        drawTIM(outfile, tim, transp, forcepal)
    common.logMessage("Done! Extracted", len(files), "files")


class TIM:
    def __init__(self):
        self.bpp = 0
        self.clutsize = 0
        self.clutposx = 0
        self.clutposy = 0
        self.clutwidth = 0
        self.clutheight = 0
        self.clutoff = 0
        self.cluts = []
        self.posx = 0
        self.posy = 0
        self.width = 0
        self.height = 0
        self.size = 0
        self.dataoff = 0
        self.data = []


def readTIM(f, forcesize=0):
    tim = TIM()
    # Read header
    header = f.readUInt()
    if header != 0x10:
        return None
    type = f.readUInt()
    if type == 0x08:
        tim.bpp = 4
    elif type == 0x09:
        tim.bpp = 8
    elif type == 0x02:
        tim.bpp = 16
    elif type == 0x03:
        tim.bpp = 24
    else:
        common.logError("Unknown TIM type", common.toHex(type))
        return None
    # Read palettes
    if tim.bpp == 4 or tim.bpp == 8:
        tim.clutsize = f.readUInt()
        tim.clutposx = f.readUShort()
        tim.clutposy = f.readUShort()
        tim.clutwidth = f.readUShort()
        tim.clutheight = f.readUShort()
        tim.clutoff = f.tell()
        for i in range(tim.clutheight):
            clut = readCLUTData(f, tim.clutwidth)
            tim.cluts.append(clut)
    # Read size
    tim.size = f.readUInt()
    tim.posx = f.readUShort()
    tim.posy = f.readUShort()
    tim.width = f.readUShort()
    tim.height = f.readUShort()
    if tim.bpp == 4:
        tim.width *= 4
    elif tim.bpp == 8:
        tim.width *= 2
    elif tim.bpp == 24:
        tim.width //= 1.5
    tim.dataoff = f.tell()
    common.logDebug("TIM bpp", tim.bpp, "width", tim.width, "height", tim.height, "size", tim.size)
    pixelnum = forcesize if forcesize != 0 else (((tim.size - 12) * 8) // tim.bpp)
    readTIMData(f, tim, pixelnum)
    return tim


def readCLUTData(f, clutwidth):
    clut = []
    for j in range(clutwidth):
        color = common.readRGB5A1(f.readUShort())
        clut.append(color)
    return clut


def readTIMData(f, tim, pixelnum):
    try:
        for i in range(pixelnum):
            if tim.bpp == 4:
                tim.data.append(f.readHalf())
            elif tim.bpp == 8:
                tim.data.append(f.readByte())
            elif tim.bpp == 16:
                color = common.readRGB5A1(f.readUShort())
                tim.data.append(color)
            elif tim.bpp == 24:
                tim.data.append((f.readByte(), f.readByte(), f.readByte(), 255))
    except struct.error:
        common.logWarning("Malformed TIM")


def getUniqueCLUT(tim, transp=False):
    clut = 0
    # Look for a palette with all different colors to export
    for i in range(len(tim.cluts)):
        checkclut = []
        for color in tim.cluts[i]:
            if transp:
                checkclut.append(color)
            else:
                checkclut.append((color[0], color[1], color[2]))
        if len(checkclut) == len(set(checkclut)):
            clut = i
            break
    return clut


def drawTIM(outfile, tim, transp=False, forcepal=-1, allpalettes=False, nopal=False):
    if tim.width == 0 or tim.height == 0:
        return
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    clutwidth = clutheight = 0
    if tim.bpp == 4 or tim.bpp == 8:
        clut = forcepal if forcepal != -1 else getUniqueCLUT(tim, transp)
        if not nopal:
            clutwidth = 40
            clutheight = 5 * (len(tim.cluts[clut]) // 8)
            if allpalettes:
                clutheight *= len(tim.cluts)
    img = Image.new("RGBA", (tim.width + clutwidth, max(tim.height, clutheight)), (0, 0, 0, 0))
    pixels = img.load()
    x = 0
    for i in range(tim.height):
        for j in range(tim.width):
            if x >= len(tim.data):
                common.logWarning("Out of TIM data")
                break
            if tim.bpp == 4 or tim.bpp == 8:
                if len(tim.cluts[clut]) > tim.data[x]:
                    color = tim.cluts[clut][tim.data[x]]
                else:
                    common.logWarning("Index", tim.data[x], "not in CLUT")
                    color = (0, 0, 0, 0)
            else:
                color = tim.data[x]
            if not transp:
                color = (color[0], color[1], color[2], 255)
            pixels[j, i] = color
            x += 1
    if (tim.bpp == 4 or tim.bpp == 8) and not nopal:
        if allpalettes:
            for i in range(len(tim.cluts)):
                pixels = common.drawPalette(pixels, tim.cluts[i], tim.width, i * (clutheight // len(tim.cluts)), transp)
        else:
            pixels = common.drawPalette(pixels, tim.cluts[clut], tim.width, 0, transp)
    if outfile == "":
        return img
    img.save(outfile, "PNG")


def writeTIM(f, tim, infile, transp=False, forcepal=-1, palsize=0):
    if tim.bpp > 8:
        common.logError("writeTIM bpp", tim.bpp, "not supported")
        return
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    clut = forcepal if forcepal != -1 else getUniqueCLUT(tim, transp)
    maxwidth = tim.width
    maxheight = tim.height
    if isinstance(infile, str):
        img = Image.open(infile)
        img = img.convert("RGBA")
        pixels = img.load()
        maxwidth = img.width - palsize
        maxheight = img.height
    else:
        pixels = infile
    f.seek(tim.dataoff)
    for i in range(tim.height):
        for j in range(tim.width):
            if j >= maxwidth or i >= maxheight:
                index = 0
            else:
                index = common.getPaletteIndex(tim.cluts[clut], pixels[j, i], checkalpha=transp, zerotransp=False)
            if tim.bpp == 4:
                f.writeHalf(index)
            else:
                f.writeByte(index)
