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
        common.logMessage("Creating xdelta patch", patchfile, "...")
        xdelta = common.bundledFile("xdelta.exe")
        if not os.path.isfile(xdelta):
            common.logError("xdelta not found")
            return
        common.execute(xdelta + " -f -e -s \"{bin}\" \"{binpatch}\" {patch}".format(bin=binfile, binpatch=binpatch, patch=patchfile), False)
        common.logMessage("Done!")


# Binary-related functions
def extractEXE(binranges, detectFunc=common.detectEncodedString, encoding="shift_jis", exein="", exefile="data/exe_output.txt", writepos=False):
    common.logMessage("Extracting EXE to", exefile, "...")
    strings, positions = extractBinaryStrings(exein, binranges, detectFunc, encoding)
    with codecs.open(exefile, "w", "utf-8") as out:
        for i in range(len(strings)):
            if writepos:
                out.write(str(positions[i][0]) + "!")
            out.write(strings[i] + "=\n")
    common.logMessage("Done! Extracted", len(strings), "lines")


def extractBinaryStrings(infile, binranges, func=common.detectEncodedString, encoding="shift_jis"):
    strings = []
    positions = []
    insize = os.path.getsize(infile)
    with common.Stream(infile, "rb") as f:
        for binrange in binranges:
            f.seek(binrange[0])
            while f.tell() < binrange[1] and f.tell() < insize - 2:
                pos = f.tell()
                check = func(f, encoding)
                if check != "":
                    if check not in strings:
                        common.logDebug("Found string at", pos)
                        strings.append(check)
                        positions.append([pos])
                    else:
                        positions[strings.index(check)].append(pos)
                    pos = f.tell() - 1
                f.seek(pos + 1)
    return strings, positions


def repackEXE(binranges, detectFunc=common.detectEncodedString, writeFunc=common.writeEncodedString, encoding="shift_jis", comments="#", exein="", exeout="", exefile="data/exe_input.txt"):
    if not os.path.isfile(exefile):
        common.logError("Input file", exefile, "not found")
        return False

    common.copyFile(exein, exeout)
    common.logMessage("Repacking EXE from", exefile, "...")
    section = {}
    with codecs.open(exefile, "r", "utf-8") as bin:
        section = common.getSection(bin, "", comments)
        chartot, transtot = common.getSectionPercentage(section)
    repackBinaryStrings(section, exein, exeout, binranges, detectFunc, writeFunc, encoding)
    common.logMessage("Done! Translation is at {0:.2f}%".format((100 * transtot) / chartot))
    return True


def repackBinaryStrings(section, infile, outfile, binranges, detectFunc=common.detectEncodedString, writeFunc=common.writeEncodedString, encoding="shift_jis"):
    insize = os.path.getsize(infile)
    with common.Stream(infile, "rb") as fi:
        with common.Stream(outfile, "r+b") as fo:
            for binrange in binranges:
                fi.seek(binrange[0])
                while fi.tell() < binrange[1] and fi.tell() < insize - 2:
                    pos = fi.tell()
                    check = detectFunc(fi, encoding)
                    if check != "":
                        if check in section and section[check][0] != "":
                            common.logDebug("Replacing string at", pos)
                            newsjis = section[check][0]
                            if len(section[check]) > 1:
                                section[check].pop(0)
                            if newsjis == "!":
                                newsjis = ""
                            newsjislog = newsjis.encode("ascii", "ignore")
                            fo.seek(pos)
                            endpos = fi.tell() - 1
                            newlen = writeFunc(fo, newsjis, endpos - pos + 1, encoding)
                            fo.seek(-1, 1)
                            if fo.readByte() != 0:
                                fo.writeZero(1)
                            if newlen < 0:
                                common.logError("String", newsjislog, "is too long.")
                            else:
                                fo.writeZero(endpos - fo.tell())
                        else:
                            pos = fi.tell() - 1
                    fi.seek(pos + 1)


# Images
def extractTIM(infolder, outfolder, extensions=".tim", readfunc=None):
    common.makeFolder(outfolder)
    common.logMessage("Extracting TIM to", outfolder, "...")
    files = common.getFiles(infolder, extensions)
    for file in common.showProgress(files):
        common.logDebug("Processing", file, "...")
        extension = os.path.splitext(file)[1]
        if readfunc is not None:
            tim, forcepal = readfunc(infolder + file)
        else:
            forcepal = -1
            with common.Stream(infolder + file, "rb") as f:
                tim = readTIM(f)
        if tim is None:
            continue
        # Export img
        common.makeFolders(outfolder + os.path.dirname(file))
        outfile = outfolder + file.replace(extension, ".png")
        drawTIM(outfile, tim, forcepal)
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
                color = (color[0], color[1], color[2], 255)
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
                color = (color[0], color[1], color[2], 255)
                tim.data.append(color)
            elif tim.bpp == 24:
                tim.data.append((f.readByte(), f.readByte(), f.readByte(), 255))
    except struct.error:
        common.logWarning("Malformed TIM")
    return tim


def getUniqueCLUT(tim):
    clut = 0
    # Look for a palette with all different colors to export
    for i in range(len(tim.cluts)):
        if len(tim.cluts[i]) == len(set(tim.cluts[i])):
            clut = i
            break
    return clut


def drawTIM(outfile, tim, forcepal=-1):
    if tim.width == 0 or tim.height == 0:
        return
    clut = forcepal if forcepal != -1 else getUniqueCLUT(tim)
    clutsize = 5 * (len(tim.cluts[clut]) // 8)
    img = Image.new("RGBA", (tim.width + 40, max(tim.height, clutsize)), (0, 0, 0, 0))
    pixels = img.load()
    x = 0
    for i in range(tim.height):
        for j in range(tim.width):
            if tim.bpp == 4 or tim.bpp == 8:
                pixels[j, i] = tim.cluts[clut][tim.data[x]]
            else:
                pixels[j, i] = tim.data[x]
            x += 1
    pixels = common.drawPalette(pixels, tim.cluts[clut], tim.width, 0)
    img.save(outfile, "PNG")


def writeTIM(f, tim, infile, forcepal=-1):
    if tim.bpp > 8:
        common.logError("writeTIM bpp", tim.bpp, "not supported")
        return
    clut = forcepal if forcepal != -1 else getUniqueCLUT(tim)
    img = Image.open(infile)
    img = img.convert("RGBA")
    pixels = img.load()
    f.seek(tim.dataoff)
    for i in range(tim.height):
        for j in range(tim.width):
            index = common.getPaletteIndex(tim.cluts[clut], pixels[j, i], zerotrasp=False)
            if tim.bpp == 4:
                f.writeHalf(index)
            else:
                f.writeByte(index)
