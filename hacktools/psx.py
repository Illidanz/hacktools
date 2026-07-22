"""Support for PSX BIN/CUE images, EXE string repacking and TIM images."""
import codecs
import struct
import os
from hacktools import common


# Image functions
def extractBIN(infolder: str, outfolder: str, cuefile: str) -> None:
    """Extract a BIN/CUE image with pydumpsxiso.

    The image is extracted to infolder along with the rebuild xml file,
    then everything is copied to outfolder, adjusting the xml to point to
    the repack folder.

    Args:
        infolder: Path of the folder to extract to.
        outfolder: Path of the work folder the files are copied to.
        cuefile: Path of the cue file.
    """
    try:
        import pydumpsxiso
    except ImportError:
        common.logError("pydumpsxiso not found")
        return
    common.logMessage("Extracting BIN", cuefile, "...")
    common.makeFolder(infolder)
    pydumpsxiso.run(cuefile.replace(".cue", ".bin"), infolder[:-1], infolder[:-1] + ".xml")
    common.logMessage("Copying data to", outfolder, "...")
    common.copyFolder(infolder, outfolder)
    with open(infolder[:-1] + ".xml", "r") as f:
        xml = f.read()
    with open(outfolder[:-1] + ".xml", "w") as f:
        f.write(xml.replace("extract/", "repack/"))
    common.logMessage("Done!")


def repackBIN(infolder: str, binin: str, binout: str, cuefile: str, patchfile: str = "") -> None:
    """Repack a BIN/CUE image with pymkpsxiso.

    Args:
        infolder: Path of the folder holding the rebuild xml file, as
            extracted by :func:`extractBIN`.
        binin: Path of the original bin file, used to create the patch.
        binout: Path of the output bin file.
        cuefile: Path of the output cue file.
        patchfile: Path of the xdelta patch to create, or empty to skip
            patch creation.
    """
    try:
        import pymkpsxiso
    except ImportError:
        common.logError("pymkpsxiso not found")
        return
    common.logMessage("Repacking BIN", binout, "...")
    pymkpsxiso.run(binout, cuefile, infolder[:-1] + ".xml")
    common.logMessage("Done!")
    # Create xdelta patch
    if patchfile != "":
        common.xdeltaPatch(patchfile, binin, binout)


# Binary-related functions
def extractEXE(binrange, readfunc=common.detectEncodedString, encoding: str = "shift_jis", exein: str = "", exefile: str = "data/exe_output.txt", writepos: bool = False) -> None:
    """Extract strings from ranges of the EXE to a text file.

    Args:
        binrange: A (start, end) range, or a list of them.
        readfunc: Function used to detect strings, called with
            (stream, encoding).
        encoding: Encoding passed to readfunc.
        exein: Path of the EXE file.
        exefile: Path of the output text file.
        writepos: Whether to write the position of each string before it.
    """
    common.logMessage("Extracting EXE to", exefile, "...")
    if isinstance(binrange, tuple):
        binrange = [binrange]
    strings, positions = common.extractBinaryStrings(exein, binrange, readfunc, encoding)
    with codecs.open(exefile, "w", "utf-8") as out:
        for i in range(len(strings)):
            if writepos:
                out.write(common.toHex(positions[i][0]) + "!")
            out.write(strings[i] + "=\n")
    common.logMessage("Done! Extracted", len(strings), "lines")


def repackEXE(binrange, freeranges: list | None = None, manualptrs: dict | None = None, readfunc=common.detectEncodedString, writefunc=common.writeEncodedString, encoding: str = "shift_jis", comments: str = "#", exein: str = "", exeout: str = "", ptrfile: str = "data/manualptrs.asm", exefile: str = "data/exe_input.txt") -> bool:
    """Repack translated strings into the EXE.

    Strings are repacked with common.repackBinaryStrings, using 0x8000f800
    as the pointer start. Pointers that aren't found automatically are
    looked up in manualptrs, and an asm file is written with a li opcode
    for each of them.

    Args:
        binrange: A (start, end) range, or a list of them.
        freeranges: List of (start, end) ranges that can hold relocated
            strings.
        manualptrs: Dictionary of pointer -> list of (location, register)
            tuples for the manual pointers.
        readfunc: Function used to detect strings, called with
            (stream, encoding).
        writefunc: Function used to write strings, called with
            (stream, string, maxlen, encoding).
        encoding: Encoding passed to readfunc and writefunc.
        comments: Comment marker used in the text file.
        exein: Path of the original EXE file.
        exeout: Path of the output EXE file.
        ptrfile: Path of the asm file written for the manual pointers.
        exefile: Path of the input text file.

    Returns:
        False if the input text file is missing, True otherwise.
    """
    if not os.path.isfile(exefile):
        common.logError("Input file", exefile, "not found")
        return False

    common.copyFile(exein, exeout)
    common.logMessage("Repacking EXE from", exefile, "...")
    section = {}
    with codecs.open(exefile, "r", "utf-8") as bin:
        section = common.getSection(bin, "", comments)
        chartot, transtot = common.getSectionPercentage(section)
    if isinstance(binrange, tuple):
        binrange = [binrange]
    notfound, freeranges = common.repackBinaryStrings(section, exein, exeout, binrange, freeranges, readfunc, writefunc, encoding, 0x8000f800)
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
def extractTIM(infolder: str, outfolder: str, extensions: str = ".tim", readfunc=None) -> None:
    """Extract all the TIM images in a folder to png.

    Args:
        infolder: Path of the folder to scan.
        outfolder: Path of the folder to extract to.
        extensions: Extension or list of extensions to filter by.
        readfunc: Optional function called with each file path, returning a
            (tim, transp, forcepal) tuple, for files that need custom
            parsing.
    """
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
    """Structure of a TIM image.

    Attributes:
        bpp: Bits per pixel, 4, 8, 16 or 24.
        clutsize: Size of the CLUT section.
        clutposx: X position of the CLUT in the framebuffer.
        clutposy: Y position of the CLUT in the framebuffer.
        clutwidth: Number of colors in each CLUT.
        clutheight: Number of CLUTs.
        clutoff: Offset of the CLUT data.
        cluts: List of CLUTs, each a list of RGBA tuples.
        posx: X position of the image in the framebuffer.
        posy: Y position of the image in the framebuffer.
        width: Width of the image in pixels.
        height: Height of the image.
        size: Size of the image data section.
        dataoff: Offset of the image data.
        data: Image data, a list of palette indexes or RGBA tuples
            depending on the bpp.
    """
    def __init__(self):
        self.bpp: int = 0
        self.clutsize: int = 0
        self.clutposx: int = 0
        self.clutposy: int = 0
        self.clutwidth: int = 0
        self.clutheight: int = 0
        self.clutoff: int = 0
        self.cluts: list = []
        self.posx: int = 0
        self.posy: int = 0
        self.width: int = 0
        self.height: int = 0
        self.size: int = 0
        self.dataoff: int = 0
        self.data: list = []


def readTIM(f: common.Stream, forcesize: int = 0) -> "TIM | None":
    """Read a TIM image from the current stream position.

    Args:
        f: Stream to read from.
        forcesize: Number of pixels to read, or 0 to calculate it from the
            data size.

    Returns:
        The parsed image, or None if the header or image type is not valid.
    """
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


def readCLUTData(f: common.Stream, clutwidth: int) -> list:
    """Read a single CLUT of a TIM image.

    Args:
        f: Stream to read from.
        clutwidth: Number of colors to read.

    Returns:
        The palette, as a list of RGBA tuples.
    """
    clut = []
    for j in range(clutwidth):
        color = common.readRGB5A1(f.readUShort())
        clut.append(color)
    return clut


def readTIMData(f: common.Stream, tim: TIM, pixelnum: int) -> None:
    """Read the pixel data of a TIM image.

    Palette indexes are read for 4 and 8bpp images, RGBA colors otherwise.
    Reading stops with a warning if the stream ends early.

    Args:
        f: Stream to read from.
        tim: Image the data belongs to, updated in place.
        pixelnum: Number of pixels to read.
    """
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


def getUniqueCLUT(tim: TIM, transp: bool = False) -> int:
    """Get the index of the first CLUT with no duplicated colors.

    Args:
        tim: Image to search the CLUTs of.
        transp: Whether the alpha channel counts when comparing colors.

    Returns:
        The index of the first CLUT with all different colors, or 0 if
        there's none.
    """
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


def drawTIM(outfile: str, tim: TIM, transp: bool = False, forcepal: int = -1, allpalettes: bool = False, nopal: bool = False):
    """Draw a TIM image to a png file.

    For 4 and 8bpp images, the palette is drawn on the right side of the
    image, unless disabled with nopal.

    Args:
        outfile: Path of the png file to create, or "" to return the image
            without saving it.
        tim: Image to draw.
        transp: Whether to keep the alpha channel of the colors.
        forcepal: Index of the CLUT to use, or -1 to pick the first one
            with no duplicated colors.
        allpalettes: Whether to draw all the CLUTs instead of just the
            used one.
        nopal: Whether to skip drawing the palette.

    Returns:
        The image object if outfile is "", nothing otherwise.
    """
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


def writeTIM(f: common.Stream, tim: TIM, infile, transp: bool = False, forcepal: int = -1, palsize: int = 0) -> None:
    """Write a png image back into a TIM, only supported for 4 and 8bpp.

    Args:
        f: Stream opened on the TIM file.
        tim: Image structure returned by :func:`readTIM`.
        infile: Path of the png file, or a PIL pixel access object.
        transp: Whether the alpha channel counts when matching colors.
        forcepal: Index of the CLUT to use, or -1 to pick the first one
            with no duplicated colors.
        palsize: Width of the palette drawn on the right side of the png,
            ignored when matching pixels.
    """
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
