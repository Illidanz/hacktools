import codecs
import struct
import os
from PIL import Image
from hacktools import common


# Image functions
def extractBIN(infolder, outfolder, cuefile):
    common.logMessage("Extracting BIN", cuefile, "...")
    if not os.path.isfile("psximager\\psxrip.exe"):
        common.logError("psximager not found")
        return
    common.clearFolder(infolder)
    common.execute("psximager\\psxrip.exe \"{iso}\" \"{folder}\"".format(iso=cuefile, folder=infolder[:-1]), False)
    common.copyFile("data/extract.sys", "data/repack.sys")
    with open("data/extract.cat", "r") as fin:
        with open("data/repack.cat", "w") as fout:
            fout.write(fin.read().replace("data/extract", "data/repack"))
    common.copyFolder(infolder, outfolder)
    common.logMessage("Done!")


def repackBIN(binfile, binpatch, cuefile, patchfile=""):
    common.logMessage("Repacking BIN", binpatch, "...")
    if not os.path.isfile("psximager\\psxbuild.exe"):
        common.logError("psximager not found")
        return
    common.execute("psximager\\psxbuild.exe \"{cat}\" \"{bin}\"".format(cat="data/repack.cat", bin=binpatch), False)
    with open(cuefile, "w") as fout:
        fout.write("FILE \"" + binpatch.replace("data/", "") + "\" BINARY\r\n")
        fout.write("  TRACK 01 MODE2/2352\r\n")
        fout.write("    INDEX 01 00:00:00\r\n")
    common.logMessage("Done!")
    # Create xdelta patch
    if patchfile != "":
        common.xdeltaPatch(patchfile, binfile, binpatch)


# Binary-related functions
def extractEXE(binrange, detectFunc=common.detectEncodedString, encoding="shift_jis", exein="", exefile="data/exe_output.txt", writepos=False):
    common.logMessage("Extracting EXE to", exefile, "...")
    if type(binrange) == tuple:
        binrange = [binrange]
    strings, positions = common.extractBinaryStrings(exein, binrange, detectFunc, encoding)
    with codecs.open(exefile, "w", "utf-8") as out:
        for i in range(len(strings)):
            if writepos:
                out.write(str(positions[i][0]) + "!")
            out.write(strings[i] + "=\n")
    common.logMessage("Done! Extracted", len(strings), "lines")


def repackEXE(binrange, freeranges=None, manualptrs=None, detectFunc=common.detectEncodedString, writeFunc=common.writeEncodedString, encoding="shift_jis", comments="#", exein="", exeout="", ptrfile="data/manualptrs.asm", exefile="data/exe_input.txt"):
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
    notfound = common.repackBinaryStrings(section, exein, exeout, binrange, freeranges, detectFunc, writeFunc, encoding, 0x8000F800)
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
    bpp = 0
    clutsize = 0
    clutposx = 0
    clutposy = 0
    clutwidth = 0
    clutheight = 0
    clutoff = 0
    cluts = []
    posx = 0
    posy = 0
    width = 0
    height = 0
    size = 0
    dataoff = 0
    data = []


def readTIM(f, forcesize=0):
    tim = TIM()
    tim.cluts = []
    tim.data = []
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
            clut = []
            for j in range(tim.clutwidth):
                color = common.readRGB5A1(f.readUShort())
                clut.append(color)
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
    # Read data
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
    return tim


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


def drawTIM(outfile, tim, transp=False, forcepal=-1):
    if tim.width == 0 or tim.height == 0:
        return
    clutwidth = clutheight = 0
    if tim.bpp == 4 or tim.bpp == 8:
        clut = forcepal if forcepal != -1 else getUniqueCLUT(tim, transp)
        clutwidth = 40
        clutheight = 5 * (len(tim.cluts[clut]) // 8)
    img = Image.new("RGBA", (tim.width + clutwidth, max(tim.height, clutheight)), (0, 0, 0, 0))
    pixels = img.load()
    x = 0
    for i in range(tim.height):
        for j in range(tim.width):
            if tim.bpp == 4 or tim.bpp == 8:
                color = tim.cluts[clut][tim.data[x]]
            else:
                color = tim.data[x]
            if not transp:
                color = (color[0], color[1], color[2], 255)
            pixels[j, i] = color
            x += 1
    if tim.bpp == 4 or tim.bpp == 8:
        pixels = common.drawPalette(pixels, tim.cluts[clut], tim.width, 0, transp)
    img.save(outfile, "PNG")


def writeTIM(f, tim, infile, transp=False, forcepal=-1):
    if tim.bpp > 8:
        common.logError("writeTIM bpp", tim.bpp, "not supported")
        return
    clut = forcepal if forcepal != -1 else getUniqueCLUT(tim, transp)
    img = Image.open(infile)
    img = img.convert("RGBA")
    pixels = img.load()
    f.seek(tim.dataoff)
    for i in range(tim.height):
        for j in range(tim.width):
            index = common.getPaletteIndex(tim.cluts[clut], pixels[j, i], checkalpha=transp, zerotransp=False)
            if tim.bpp == 4:
                f.writeHalf(index)
            else:
                f.writeByte(index)
