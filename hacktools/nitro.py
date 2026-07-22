"""Support for the NDS Nitro file formats.

Includes NFTR fonts, NARC archives, the NCLR/NCGR/NSCR/NCER graphic
formats and their raw NBFP/NBFC/NBFS variants, and the textures of
NSBMD/NSBTX 3D models.
"""
import math
import os
import shlex
import shutil
import subprocess
import struct
from hacktools import common


# Generic extract/repack functions
def extractNSBMD(infolder: str, outfolder: str, extension: str = ".nsbmd", readfunc=None) -> None:
    """Extract the textures of all the NSBMD models in a folder to png.

    Args:
        infolder: Path of the folder to scan.
        outfolder: Path of the folder to extract to.
        extension: Extension of the model files.
        readfunc: Optional function called with each file name, returning
            whether the first palette color should be transparent.
    """
    common.makeFolder(outfolder)
    common.logMessage("Extracting NSBMD to", outfolder, "...")
    files = common.getFiles(infolder, extension)
    for file in common.showProgress(files):
        common.logDebug("Processing", file, "...")
        zerotransp = False
        if readfunc is not None:
            zerotransp = readfunc(file)
        nsbmd = readNSBMD(infolder + file, zerotransp)
        if nsbmd is not None and len(nsbmd.textures) > 0:
            common.makeFolders(outfolder + os.path.dirname(file))
            for texi in range(len(nsbmd.textures)):
                drawNSBMD(outfolder + file.replace(extension, "") + "_" + nsbmd.textures[texi].name + ".png", nsbmd, texi)
    common.logMessage("Done! Extracted", len(files), "files")


def repackNSBMD(workfolder: str, infolder: str, outfolder: str, extension: str = ".nsbmd", readfunc=None, writefunc=None) -> None:
    """Repack the textures of all the NSBMD models in a folder from png.

    Args:
        workfolder: Path of the folder with the png files to pack.
        infolder: Path of the folder with the original models.
        outfolder: Path of the folder the repacked models are written to.
        extension: Extension of the model files.
        readfunc: Optional function called with each file name, returning
            whether the first palette color should be transparent.
        writefunc: Optional function called with (file, nsbmd), returning
            the (fixtransp, checkalpha, zerotransp, backwards) options used
            when matching palette colors.
    """
    common.logMessage("Repacking NSBMD from", workfolder, "...")
    files = common.getFiles(infolder, extension)
    for file in common.showProgress(files):
        common.logDebug("Processing", file, "...")
        common.copyFile(infolder + file, outfolder + file)
        zerotransp = False
        if readfunc is not None:
            zerotransp = readfunc(file)
        nsbmd = readNSBMD(infolder + file, zerotransp)
        if nsbmd is not None and len(nsbmd.textures) > 0:
            fixtransp = checkalpha = zerotransp = backwards = False
            if writefunc is not None:
                fixtransp, checkalpha, zerotransp, backwards = writefunc(file, nsbmd)
            for texi in range(len(nsbmd.textures)):
                pngname = file.replace(extension, "") + "_" + nsbmd.textures[texi].name + ".png"
                if os.path.isfile(workfolder + pngname):
                    common.logDebug(" Repacking", pngname, "...")
                    writeNSBMD(outfolder + file, nsbmd, texi, workfolder + pngname, fixtransp, checkalpha, zerotransp, backwards)
    common.logMessage("Done!")


def extractIMG(infolder: str, outfolder: str, extensions=".NCGR", readfunc=None) -> None:
    """Extract all the Nitro graphics in a folder to png.

    The palette, map and cell files matching each image name are loaded
    with :func:`readNitroGraphic`. Images with a cell file are drawn with
    :func:`drawNCER`, the others with :func:`drawNCGR`.

    Args:
        infolder: Path of the folder to scan.
        outfolder: Path of the folder to extract to.
        extensions: Extension or list of extensions to filter by.
        readfunc: Optional function called with (infolder, file, extension),
            returning a (palettes, image, map, cell, width, height, mapfile,
            cellfile) tuple, for files that need custom loading.
    """
    common.makeFolder(outfolder)
    common.logMessage("Extracting IMG to", outfolder, "...")
    files = common.getFiles(infolder, extensions)
    for file in common.showProgress(files):
        common.logDebug("Processing", file, "...")
        extension = os.path.splitext(file)[1]
        if readfunc is not None:
            palettes, image, map, cell, width, height, mapfile, cellfile = readfunc(infolder, file, extension)
        else:
            palettefile = file.replace(extension, ".NCLR")
            mapfile = file.replace(extension, ".NSCR")
            cellfile = file.replace(extension, ".NCER")
            palettes, image, map, cell, width, height = readNitroGraphic(infolder + palettefile, infolder + file, infolder + mapfile, infolder + cellfile)
        if image is None:
            continue
        # Export img
        common.makeFolders(outfolder + os.path.dirname(file))
        outfile = outfolder + file.replace(extension, ".png")
        if cell is not None:
            drawNCER(outfile, cell, image, palettes, True, True)
        else:
            drawNCGR(outfile, map, image, palettes, width, height)
    common.logMessage("Done! Extracted", len(files), "files")


def repackIMG(workfolder: str, infolder: str, outfolder: str, extensions=".NCGR", readfunc=None, writefunc=None, clean: bool = False) -> None:
    """Repack all the Nitro graphics in a folder from png or psd files.

    Args:
        workfolder: Path of the folder with the png or psd files to pack.
        infolder: Path of the folder with the original files.
        outfolder: Path of the folder the repacked files are written to.
        extensions: Extension or list of extensions to filter by.
        readfunc: Optional function called with (infolder, file, extension),
            returning a (palettes, image, map, cell, width, height, mapfile,
            cellfile) tuple, for files that need custom loading.
        writefunc: Optional function called with (workfolder, infolder,
            outfolder, file, image, palettes, map, cell, width, height),
            returning the same data updated, plus a transptile option.
        clean: Whether to delete output files with no matching image,
            instead of copying the originals.
    """
    common.logMessage("Repacking IMG from", workfolder, "...")
    files = common.getFiles(infolder, extensions)
    for file in common.showProgress(files):
        common.logDebug("Processing", file, "...")
        extension = os.path.splitext(file)[1]
        if readfunc is not None:
            palettes, image, map, cell, width, height, mapfile, cellfile = readfunc(infolder, file, extension)
        else:
            palettefile = file.replace(extension, ".NCLR")
            mapfile = file.replace(extension, ".NSCR")
            cellfile = file.replace(extension, ".NCER")
            palettes, image, map, cell, width, height = readNitroGraphic(infolder + palettefile, infolder + file, infolder + mapfile, infolder + cellfile)
        pngfile = file.replace(extension, ".psd")
        if not os.path.isfile(workfolder + pngfile):
            pngfile = file.replace(extension, ".png")
            if not os.path.isfile(workfolder + pngfile):
                pngfile = ""
        if image is None or pngfile == "":
            if clean:
                if os.path.isfile(outfolder + file):
                    os.remove(outfolder + file)
                if os.path.isfile(outfolder + mapfile):
                    os.remove(outfolder + mapfile)
                if os.path.isfile(outfolder + cellfile):
                    os.remove(outfolder + cellfile)
            else:
                common.makeFolders(outfolder + os.path.dirname(file))
                common.copyFile(infolder + file, outfolder + file)
                if os.path.isfile(infolder + mapfile):
                    common.copyFile(infolder + mapfile, outfolder + mapfile)
                if os.path.isfile(workfolder + cellfile):
                    common.copyFile(workfolder + cellfile, outfolder + cellfile)
                elif os.path.isfile(infolder + cellfile):
                    common.copyFile(infolder + cellfile, outfolder + cellfile)
            continue
        common.makeFolders(outfolder + os.path.dirname(file))
        common.copyFile(infolder + file, outfolder + file)
        transptile = False
        if writefunc is not None:
            image, palettes, map, cell, width, height, transptile = writefunc(workfolder, infolder, outfolder, file, image, palettes, map, cell, width, height)
        if image is not None:
            if map is None and cell is None:
                writeNCGR(outfolder + file, image, workfolder + pngfile, palettes, width, height)
            elif cell is None:
                common.copyFile(infolder + mapfile, outfolder + mapfile)
                writeMappedNSCR(outfolder + file, outfolder + mapfile, image, map, workfolder + pngfile, palettes, width, height, transptile)
            else:
                if os.path.isfile(workfolder + cellfile):
                    cell = readNCER(workfolder + cellfile)
                    common.copyFile(workfolder + cellfile, outfolder + cellfile)
                else:
                    common.copyFile(infolder + cellfile, outfolder + cellfile)
                writeNCER(outfolder + file, outfolder + cellfile, image, cell, workfolder + pngfile, palettes, width, height)
    common.logMessage("Done!")


# Font
class FontNFTR:
    """Structure of an NFTR font.

    Attributes:
        height: Line height of the font.
        width: Max character width of the font.
        plgcoffset: Offset of the PLGC section, holding the glyph images.
        hdwcoffset: Offset of the HDWC section, holding the glyph widths.
        pamcoffset: Offset of the first PAMC section, holding the character map.
        plgcsize: Size of the PLGC section.
        glyphwidth: Width of the glyph images.
        glyphheight: Height of the glyph images.
        glyphlength: Length in bytes of a single glyph image.
        depth: Bits per pixel of the glyph images.
        rotation: Rotation of the glyph images.
        tilenum: Number of glyphs in the font.
        firstcode: First glyph index from the HDWC section.
        lastcode: Last glyph index from the HDWC section.
        plgc: Glyph images, as a list of PIL images, only filled when
            requested with generateglyphs.
        colors: Grayscale palette generated from the depth.
        hdwc: List of HDWC entries.
        pamc: List of PAMC entries.
        glyphs: Dictionary of character -> FontGlyph.
    """
    def __init__(self):
        self.height: int = 0
        self.width: int = 0
        self.plgcoffset: int = 0
        self.hdwcoffset: int = 0
        self.pamcoffset: int = 0
        self.plgcsize: int = 0
        self.glyphwidth: int = 0
        self.glyphheight: int = 0
        self.glyphlength: int = 0
        self.depth: int = 0
        self.rotation: int = 0
        self.tilenum: int = 0
        self.firstcode: int = 0
        self.lastcode: int = 0
        self.plgc: list = []
        self.colors: list = []
        self.hdwc: list[FontHDWC] = []
        self.pamc: list[FontPAMC] = []
        self.glyphs: dict = {}


class FontHDWC:
    """Width data of a single NFTR glyph.

    Attributes:
        start: Left offset of the glyph.
        width: Width of the glyph.
        length: Horizontal space occupied by the glyph when drawn.
    """
    def __init__(self):
        self.start: int = 0
        self.width: int = 0
        self.length: int = 0


class FontPAMC:
    """Header of a single NFTR character map section.

    Attributes:
        firstchar: First character code of the section.
        lastchar: Last character code of the section.
        type: Type of the section, 0 to 2.
        nextoffset: Offset of the next PAMC section, 0 for the last one.
    """
    def __init__(self):
        self.firstchar: int = 0
        self.lastchar: int = 0
        self.type: int = 0
        self.nextoffset: int = 0


def readNFTR(file: str, generateglyphs: bool = False, encoding: str = "shift_jis") -> FontNFTR:
    """Read the glyph information of an NFTR font.

    Args:
        file: Path of the font file.
        generateglyphs: Whether to also render the glyph images with PIL.
        encoding: Encoding of the character codes.

    Returns:
        The parsed font structure.
    """
    nftr = FontNFTR()
    with common.Stream(file, "rb") as f:
        # Header
        f.seek(25)
        nftr.height = f.readByte()
        f.seek(3, 1)
        nftr.width = f.readByte()
        f.seek(2, 1)
        nftr.plgcoffset = f.readUInt()
        nftr.hdwcoffset = f.readUInt()
        nftr.pamcoffset = f.readUInt()
        # PLGC
        f.seek(nftr.plgcoffset - 4)
        nftr.plgcsize = f.readUInt()
        nftr.glyphwidth = f.readByte()
        nftr.glyphheight = f.readByte()
        nftr.glyphlength = f.readUShort()
        f.seek(2, 1)
        nftr.depth = f.readByte()
        nftr.rotation = f.readByte()
        nftr.tilenum = (nftr.plgcsize - 0x10) // nftr.glyphlength
        common.logDebug(vars(nftr))
        # Generate colors
        numcolors = pow(2, nftr.depth)
        for i in range(numcolors):
            nftr.colors.append((0, 0, 0, int(255 * i / (numcolors - 1))))
        # Read the glyphs graphics
        if generateglyphs:
            try:
                from PIL import Image
                data = f.readByte()
                for i in range(nftr.tilenum):
                    glyph = Image.new("RGBA", (nftr.glyphwidth, nftr.glyphheight), nftr.colors[0])
                    pixels = glyph.load()
                    x = 0
                    y = 0
                    byteindex = 0
                    bitmask = 0x80
                    while byteindex < nftr.glyphlength and y < nftr.glyphheight:
                        intensitymask = pow(2, nftr.depth - 1)
                        intensity = 0
                        while intensitymask > 0:
                            if data & bitmask > 0:
                                intensity += intensitymask
                            bitmask >>= 1
                            if bitmask == 0:
                                bitmask = 0x80
                                byteindex += 1
                                data = f.readByte()
                            intensitymask >>= 1
                        if intensity > 0:
                            pixels[x, y] = nftr.colors[intensity]
                        x += 1
                        if x >= nftr.glyphwidth:
                            x = 0
                            y += 1
                    while byteindex < nftr.glyphlength:
                        data = f.readByte()
                        byteindex += 1
                    if nftr.rotation != 0:
                        angle = 90
                        if nftr.rotation == 2:
                            angle = 270
                        elif nftr.rotation == 3:
                            angle = 180
                        glyph = glyph.rotate(angle)
                    nftr.plgc.append(glyph)
            except ImportError:
                common.logError("PIL not found")
        # HDWC
        f.seek(nftr.hdwcoffset)
        nftr.firstcode = f.readUShort()
        nftr.lastcode = f.readUShort()
        f.seek(4, 1)
        for i in range(nftr.tilenum):
            hdwc = FontHDWC()
            hdwc.start = f.readSByte()
            hdwc.width = f.readByte()
            hdwc.length = f.readByte()
            common.logDebug(" ", vars(hdwc))
            nftr.hdwc.append(hdwc)
        # PAMC
        nextoffset = nftr.pamcoffset
        while nextoffset != 0x00:
            f.seek(nextoffset)
            pamc = FontPAMC()
            pamc.firstchar = f.readUShort()
            pamc.lastchar = f.readUShort()
            pamc.type = f.readUInt()
            nextoffset = pamc.nextoffset = f.readUInt()
            common.logDebug(" ", vars(pamc))
            if pamc.type == 0:
                firstcode = f.readUShort()
                for i in range(pamc.lastchar - pamc.firstchar + 1):
                    c = common.codeToChar(pamc.firstchar + i, encoding)
                    hdwc = nftr.hdwc[firstcode + i]
                    nftr.glyphs[c] = common.FontGlyph(hdwc.start, hdwc.width, hdwc.length, c, pamc.firstchar + i, firstcode + i)
            elif pamc.type == 1:
                for i in range(pamc.lastchar - pamc.firstchar + 1):
                    charcode = f.readUShort()
                    if charcode == 0xFFFF or charcode >= len(nftr.hdwc):
                        continue
                    c = common.codeToChar(pamc.firstchar + i, encoding)
                    hdwc = nftr.hdwc[charcode]
                    nftr.glyphs[c] = common.FontGlyph(hdwc.start, hdwc.width, hdwc.length, c, pamc.firstchar + i, charcode)
            elif pamc.type == 2:
                groupnum = f.readUShort()
                for i in range(groupnum - pamc.firstchar):
                    charcode = f.readUShort()
                    c = common.codeToChar(charcode, encoding)
                    tilenum = f.readUShort()
                    hdwc = nftr.hdwc[tilenum]
                    nftr.glyphs[c] = common.FontGlyph(hdwc.start, hdwc.width, hdwc.length, c,  charcode, tilenum)
            else:
                common.logWarning("Unknown section type", pamc.type)
    return nftr


def extractFontData(fontfiles, out: str) -> None:
    """Write the length of the ASCII glyphs of some fonts to a binary file.

    Args:
        fontfiles: Path of the font file, or a list of paths.
        out: Path of the output file.
    """
    if isinstance(fontfiles, str):
        fontfiles = [fontfiles]
    with common.Stream(out, "wb") as f:
        for fontfile in fontfiles:
            nftr = readNFTR(fontfile)
            for i in range(0x20, 0x7f):
                f.writeByte(nftr.glyphs[chr(i)].length)


# Archives
class NARC:
    """Structure of a NARC archive.

    Attributes:
        btaf: Offset of the BTAF section, holding the file offsets.
        btnf: Offset of the BTNF section, holding the file names.
        gmif: Offset of the GMIF section, holding the file data.
        files: List of files in the archive.
    """
    def __init__(self):
        self.btaf: int = 0
        self.btnf: int = 0
        self.gmif: int = 0
        self.files: list[NARCFile] = []


class NARCFile:
    """Structure of a single file entry in a NARC archive.

    Attributes:
        start: Absolute offset of the file data.
        size: Size of the file.
        path: Directory part of the file path.
        name: Name of the file.
        fullname: Path and name of the file.
    """
    def __init__(self):
        self.start: int = 0
        self.size: int = 0
        self.path: str = ""
        self.name: str = ""
        self.fullname: str = ""


def readNARC(narcfile: str) -> "NARC | None":
    """Read the file table of a NARC archive.

    Args:
        narcfile: Path of the NARC file.

    Returns:
        The parsed archive structure, or None if a section has a wrong
        header.
    """
    common.logDebug("Reading", narcfile)
    narc = NARC()
    with common.Stream(narcfile, "rb") as f:
        # Read BTAF
        f.seek(16)
        narc.btaf = f.tell()
        check = f.readString(4)
        if check != "BTAF":
            common.logError("Encountered", check, "instead of BTAF")
            return None
        sectionsize = f.readUInt()
        narc.btnf = narc.btaf + sectionsize
        filenum = f.readUInt()
        common.logDebug("filenum:", filenum)
        for i in range(filenum):
            subfile = NARCFile()
            subfile.start = 8 + f.readUInt()
            subfile.size = 8 + f.readUInt() - subfile.start
            common.logDebug(vars(subfile))
            narc.files.append(subfile)
        # Read BTNF
        f.seek(narc.btnf)
        check = f.readString(4)
        if check != "BTNF":
            common.logError("Encountered", check, "instead of BTNF")
            return None
        sectionsize = f.readUInt()
        narc.gmif = narc.btnf + sectionsize
        for subfile in narc.files:
            subfile.start += narc.gmif
        # TODO: handle directories
        f.seek(8, 1)
        for i in range(filenum):
            namelen = f.readByte()
            narc.files[i].name = f.readString(namelen)
            narc.files[i].fullname = narc.files[i].path + narc.files[i].name
        # Read GMIF
        f.seek(narc.gmif)
        check = f.readString(4)
        if check != "GMIF":
            common.logError("Encountered", check, "instead of GMIF")
            return None
    return narc


def extractNARCFile(narcfile: str, outfolder: str) -> None:
    """Extract all the files of a NARC archive to a folder.

    Args:
        narcfile: Path of the NARC file.
        outfolder: Path of the folder to extract to.
    """
    narc = readNARC(narcfile)
    if narc is None:
        return
    extractNARC(narcfile, outfolder, narc)


def extractNARC(narcfile, outfolder: str, narc: NARC) -> None:
    """Extract all the files of an already parsed NARC archive.

    Args:
        narcfile: Path of the NARC file.
        outfolder: Path of the folder to extract to.
        narc: Archive structure returned by :func:`readNARC`.
    """
    common.logDebug("Extracting", narcfile, "to", outfolder)
    if not outfolder.endswith("/"):
        outfolder = outfolder + "/"
    common.makeFolder(outfolder)
    with common.Stream(narcfile, "rb") as f:
        for i in range(len(narc.files)):
            file = narc.files[i]
            f.seek(file.start)
            with common.Stream(outfolder + file.fullname, "wb") as fout:
                fout.write(f.read(file.size))


def repackNARCFile(narcfilein: str, narcfileout: str, infolder: str) -> None:
    """Repack a NARC archive, replacing the files found in a folder.

    Args:
        narcfilein: Path of the original NARC file.
        narcfileout: Path of the output NARC file.
        infolder: Path of the folder with the replacement files.
    """
    narc = readNARC(narcfilein)
    if narc is None:
        return
    repackNARC(narcfilein, narcfileout, infolder, narc)


def repackNARC(narcfilein: str, narcfileout: str, infolder: str, narc: NARC) -> None:
    """Repack an already parsed NARC archive.

    Files that exist in infolder replace the original ones, and the file
    table and section sizes are updated, so files can grow.

    Args:
        narcfilein: Path of the original NARC file.
        narcfileout: Path of the output NARC file.
        infolder: Path of the folder with the replacement files.
        narc: Archive structure returned by :func:`readNARC`.
    """
    common.logDebug("Repacking", narcfileout, "from", infolder)
    with common.Stream(narcfilein, "rb") as fin:
        with common.Stream(narcfileout, "wb") as f:
            f.write(fin.read(narc.gmif + 8))
            filepos = f.tell()
            for i in range(len(narc.files)):
                file = narc.files[i]
                # Read file data
                filepath = infolder + "/" + file.fullname
                if not os.path.isfile(filepath):
                    fin.seek(file.start)
                    filedata = fin.read(file.size)
                else:
                    with common.Stream(filepath, "rb") as subf:
                        filedata = subf.read()
                # Write it in the archive
                f.seek(filepos)
                filestart = f.tell()
                f.write(filedata)
                fileend = f.tell()
                # Pad with 0s
                if f.tell() % 4 > 0:
                    f.writeZero(f.tell() % 4)
                filepos = f.tell()
                # Update the pointers
                f.seek(narc.btaf + 12 + i * 8)
                f.writeUInt(filestart - narc.gmif - 8)
                f.writeUInt(fileend - narc.gmif - 8)
            # Write the new GMIF section size
            f.seek(narc.gmif + 4)
            f.writeUInt(filepos - narc.gmif)
            # Write the new NARC size
            f.seek(8)
            f.writeUInt(filepos)


# Graphics
class NCGR:
    """Structure of an NCGR tile file.

    Attributes:
        width: Width of the image in pixels.
        height: Height of the image.
        bpp: Bits per pixel, 4 or 8.
        tilesize: Size of a single tile.
        tileoffset: Offset of the tile data.
        tilelen: Length of the tile data.
        lineal: Whether the tiles are stored in lineal order, instead of
            tiled.
        tiles: List of tiles, each a flat list of palette indexes.
    """
    def __init__(self):
        self.width: int = 0
        self.height: int = 0
        self.bpp: int = 4
        self.tilesize: int = 8
        self.tileoffset: int = 0
        self.tilelen: int = 0
        self.lineal: bool = False
        self.tiles: list = []


class NSCR:
    """Structure of an NSCR tile map file.

    Attributes:
        width: Width of the image in pixels.
        height: Height of the image.
        maplen: Length of the map data.
        mapoffset: Offset of the map data.
        maps: List of map entries.
    """
    def __init__(self):
        self.width: int = 0
        self.height: int = 0
        self.maplen: int = 0
        self.mapoffset: int = 0
        self.maps: list[Map] = []


class Map:
    """Structure of a single NSCR map entry.

    Attributes:
        pal: Palette of the tile.
        xflip: Whether the tile is flipped horizontally.
        yflip: Whether the tile is flipped vertically.
        tile: Index of the tile.
    """
    def __init__(self):
        self.pal: int = 0
        self.xflip: bool = False
        self.yflip: bool = False
        self.tile: int = 0


class NCER:
    """Structure of an NCER cell file.

    Attributes:
        banknum: Number of banks in the file.
        tbank: Bank type, 0x01 for extended banks with a bounding box.
        bankoffset: Offset of the bank data.
        blocksize: Tile offset shift of the banks.
        partitionoffset: Offset of the partition data, if any.
        maxpartitionsize: Max partition size from the partition data.
        firstpartitionoffset: Offset of the first partition.
        banks: List of banks in the file.
    """
    def __init__(self):
        self.tbank: int = 0
        self.bankoffset: int = 0
        self.blocksize: int = 0
        self.partitionoffset: int = 0
        self.maxpartitionsize: int = 0
        self.firstpartitionoffset: int = 0
        self.banks: list[Bank] = []


class Bank:
    """Structure of a single NCER bank, a group of cells forming a sprite.

    Attributes:
        cellnum: Number of cells in the bank.
        cellinfo: Raw cell info value.
        celloffset: Offset of the cell data, relative to the end of the
            bank data.
        objoffset: Absolute offset of the cell data.
        partitionoffset: Offset of the bank partition.
        partitionsize: Size of the bank partition.
        cells: List of cells in the bank, sorted by drawing order.
        xmax: Right edge of the bounding box.
        ymax: Bottom edge of the bounding box.
        xmin: Left edge of the bounding box.
        ymin: Top edge of the bounding box.
        width: Width of the bank.
        height: Height of the bank.
        layernum: Number of layers used for psd exporting, computed so
            intersecting cells end up on different layers.
        duplicate: Whether the bank has the same cells as a previous one.
    """
    def __init__(self):
        self.cellnum: int = 0
        self.cellinfo: int = 0
        self.celloffset: int = 0
        self.objoffset: int = 0
        self.partitionoffset: int = 0
        self.partitionsize: int = 0
        self.cells: list[Cell] = []
        self.xmax: int = 0
        self.ymax: int = 0
        self.xmin: int = 0
        self.ymin: int = 0
        self.width: int = 0
        self.height: int = 0
        self.layernum: int = 0
        self.duplicate: bool = False


class Cell:
    """Structure of a single NCER cell, an OBJ entry of a bank.

    Attributes:
        x: X position of the cell in the bank.
        y: Y position of the cell in the bank.
        width: Width of the cell, derived from shape and size.
        height: Height of the cell, derived from shape and size.
        numcell: Index of the cell in the bank.
        shape: OBJ shape attribute.
        size: OBJ size attribute.
        objoffset: Offset of the OBJ entry.
        tileoffset: Tile offset of the cell.
        rsflag: Whether rotation/scaling is enabled.
        objdisable: Whether the OBJ is disabled, without rsflag.
        doublesize: Whether the OBJ is double size, with rsflag.
        objmode: OBJ mode attribute.
        mosaic: Whether the mosaic effect is enabled.
        depth: Whether the cell is 8bpp instead of 4bpp.
        xflip: Whether the cell is flipped horizontally.
        yflip: Whether the cell is flipped vertically.
        selectparam: Rotation/scaling parameter selection, with rsflag.
        priority: Drawing priority of the cell.
        pal: Palette of the cell.
        layer: Layer used for psd exporting.
    """
    def __init__(self):
        self.x: int = 0
        self.y: int = 0
        self.width: int = 0
        self.height: int = 0
        self.numcell: int = 0
        self.shape: int = 0
        self.size: int = 0
        self.objoffset: int = 0
        self.tileoffset: int = 0
        self.rsflag: bool = False
        self.objdisable: bool = False
        self.doublesize: bool = False
        self.objmode: int = 0
        self.mosaic: bool = False
        self.depth: bool = False
        self.xflip: bool = False
        self.yflip: bool = False
        self.selectparam: int = 0
        self.priority: int = 0
        self.pal: int = 0
        self.layer: int = -1


def readNitroGraphic(palettefile: str, tilefile: str, mapfile: str, cellfile: str, ignorepalindex: bool = False, ignoredupes: bool = False):
    """Read a Nitro graphic with all its related files.

    The map and cell files are optional, the palette and tile ones aren't.

    Args:
        palettefile: Path of the NCLR palette file.
        tilefile: Path of the NCGR tile file.
        mapfile: Path of the NSCR map file.
        cellfile: Path of the NCER cell file.
        ignorepalindex: Whether to ignore the palette index section.
        ignoredupes: Whether to skip marking duplicate cell banks.

    Returns:
        A (palettes, ncgr, nscr, ncer, width, height) tuple, with None for
        the files that weren't found.
    """
    if not os.path.isfile(palettefile):
        common.logError("Palette", palettefile, "not found")
        return [], None, None, None, 0, 0
    palettes = readNCLR(palettefile, ignorepalindex)
    # Read tiles
    ncgr = readNCGR(tilefile)
    width = ncgr.width
    height = ncgr.height
    # Read maps
    nscr = None
    if os.path.isfile(mapfile):
        nscr = readNSCR(mapfile)
        width = nscr.width
        height = nscr.height
    # Read banks
    ncer = None
    if os.path.isfile(cellfile):
        ncer = readNCER(cellfile, ignoredupes)
    return palettes, ncgr, nscr, ncer, width, height


def readNCLR(nclrfile: str, ignoreindex: bool = False) -> dict:
    """Read the palettes of an NCLR file.

    Args:
        nclrfile: Path of the NCLR file.
        ignoreindex: Whether to ignore the palette index section.

    Returns:
        A dictionary of palette index -> list of RGBA tuples.
    """
    palettes = []
    with common.Stream(nclrfile, "rb") as f:
        # Read header
        f.seek(14)
        sections = f.readUShort()
        f.seek(20)
        length = f.readUInt()
        bpp = 8 if f.readUShort() == 0x04 else 4
        f.seek(6, 1)  # 0x00
        pallen = f.readUInt()
        if pallen == 0 or pallen > length:
            pallen = length - 0x18
        offset = f.readUInt()
        colornum = 0x10 if bpp == 4 else 0x100
        if pallen // 2 < colornum:
            colornum = pallen // 2
        common.logDebug("bpp", bpp, "length", length, "pallen", pallen, "colornum", colornum)
        # Read palettes
        f.seek(0x18 + offset)
        for i in range(pallen // (colornum * 2)):
            palette = []
            for j in range(colornum):
                palette.append(common.readPalette(f.readUShort()))
            palettes.append(palette)
        # Read index
        if sections == 2 and not ignoreindex:
            f.seek(16, 1)
            indexedpalettes = {}
            for i in range(len(palettes)):
                indexedpalettes[f.readUShort()] = palettes[i]
        else:
            indexedpalettes = {i: palettes[i] for i in range(0, len(palettes))}
    common.logDebug("Loaded", len(indexedpalettes), "palettes")
    if 0 not in indexedpalettes.keys():
        indexedpalettes[0] = indexedpalettes[list(indexedpalettes.keys())[0]]
    return indexedpalettes


def readNCGR(ncgrfile: str) -> NCGR:
    """Read the tiles of an NCGR file.

    Args:
        ncgrfile: Path of the NCGR file.

    Returns:
        The parsed tile structure.
    """
    ncgr = NCGR()
    with common.Stream(ncgrfile, "rb") as f:
        f.seek(24)
        ncgr.height = f.readUShort()
        ncgr.width = f.readUShort()
        ncgr.bpp = 8 if f.readUInt() == 0x04 else 4
        ncgr.tilesize = 8
        f.seek(4, 1)
        flag = f.readUInt()
        ncgr.lineal = (flag & 0xFF) != 0x00
        ncgr.tilelen = f.readUInt()
        f.seek(4, 1)
        ncgr.tileoffset = f.tell()
        tiledata = f.read(ncgr.tilelen)
        if ncgr.width != 0xFFFF:
            ncgr.width *= ncgr.tilesize
            ncgr.height *= ncgr.tilesize
        common.logDebug(vars(ncgr))
        readNCGRTiles(ncgr, tiledata)
    common.logDebug("Loaded", len(ncgr.tiles), "tiles")
    return ncgr


def readNCGRTiles(ncgr: NCGR, tiledata: bytes) -> None:
    """Split raw tile data into the tiles of an NCGR structure.

    Args:
        ncgr: Tile structure to fill.
        tiledata: Raw tile data.
    """
    for i in range(ncgr.tilelen // (8 * ncgr.bpp)):
        singletile = []
        for j in range(ncgr.tilesize * ncgr.tilesize):
            x = i * (ncgr.tilesize * ncgr.tilesize) + j
            if ncgr.bpp == 4:
                index = (tiledata[x // 2] >> ((x % 2) << 2)) & 0x0f
            else:
                index = tiledata[x]
            singletile.append(index)
        ncgr.tiles.append(singletile)


def readNSCR(nscrfile: str) -> NSCR:
    """Read the map entries of an NSCR file.

    Args:
        nscrfile: Path of the NSCR file.

    Returns:
        The parsed map structure.
    """
    nscr = NSCR()
    with common.Stream(nscrfile, "rb") as f:
        f.seek(24)
        nscr.width = f.readUShort()
        nscr.height = f.readUShort()
        f.seek(4, 1)
        nscr.maplen = f.readUInt()
        nscr.mapoffset = f.tell()
        mapdata = f.read(nscr.maplen)
        common.logDebug(vars(nscr))
        for i in range(0, len(mapdata), 2):
            data = struct.unpack("<h", mapdata[i:i+2])[0]
            submap = readMapData(data)
            nscr.maps.append(submap)
    common.logDebug("Loaded", len(nscr.maps), "maps")
    return nscr


def readMapData(data: int) -> Map:
    """Parse a single 16-bit map entry.

    Args:
        data: Raw map entry value.

    Returns:
        The parsed map entry.
    """
    map = Map()
    map.pal = (data >> 12) & 0xf
    map.xflip = (data >> 10) & 1
    map.yflip = (data >> 11) & 1
    map.tile = data & 0x3ff
    return map


def getNCERCellSize(shape: int, size: int) -> tuple:
    """Get the size of a cell from its OBJ shape and size attributes.

    Args:
        shape: OBJ shape attribute, 0 to 2.
        size: OBJ size attribute, 0 to 3.

    Returns:
        The (width, height) of the cell.
    """
    cellsize = (0, 0)
    if shape == 0:
        if size == 0:
            cellsize = (8, 8)
        elif size == 1:
            cellsize = (16, 16)
        elif size == 2:
            cellsize = (32, 32)
        elif size == 3:
            cellsize = (64, 64)
    elif shape == 1:
        if size == 0:
            cellsize = (16, 8)
        elif size == 1:
            cellsize = (32, 8)
        elif size == 2:
            cellsize = (32, 16)
        elif size == 3:
            cellsize = (64, 32)
    elif shape == 2:
        if size == 0:
            cellsize = (8, 16)
        elif size == 1:
            cellsize = (8, 32)
        elif size == 2:
            cellsize = (16, 32)
        elif size == 3:
            cellsize = (32, 64)
    return cellsize


def readNCER(ncerfile: str, ignoredupes: bool = False) -> NCER:
    """Read the banks and cells of an NCER file.

    The size and position of each bank is computed from its cells, and the
    layers used for psd exporting are assigned so intersecting cells end
    up on different layers.

    Args:
        ncerfile: Path of the NCER file.
        ignoredupes: Whether to skip marking duplicate banks.

    Returns:
        The parsed cell structure.
    """
    ncer = NCER()
    with common.Stream(ncerfile, "rb") as f:
        f.seek(24)
        ncer.banknum = f.readUShort()
        ncer.tbank = f.readUShort()
        ncer.bankoffset = f.readUInt()
        ncer.blocksize = f.readUInt() & 0xff
        ncer.partitionoffset = f.readUInt()
        for i in range(ncer.banknum):
            bank = Bank()
            ncer.banks.append(bank)
        # Partition data
        if ncer.partitionoffset > 0:
            f.seek(16 + ncer.partitionoffset + 8)
            ncer.maxpartitionsize = f.readUInt()
            ncer.firstpartitionoffset = f.readUInt()
            f.seek(ncer.firstpartitionoffset - 8, 1)
            for i in range(ncer.banknum):
                ncer.banks[i].partitionoffset = f.readUInt()
                ncer.banks[i].partitionsize = f.readUInt()
        common.logDebug(vars(ncer))
        f.seek(16 + ncer.bankoffset + 8)
        for i in range(len(ncer.banks)):
            bank = ncer.banks[i]
            bank.cellnum = f.readUShort()
            bank.cellinfo = f.readUShort()
            bank.celloffset = f.readUInt()
            if ncer.tbank == 0x01:
                bank.xmax = f.readShort()
                bank.ymax = f.readShort()
                bank.xmin = f.readShort()
                bank.ymin = f.readShort()
                bank.width = bank.xmax - bank.xmin + 1
                bank.height = bank.ymax - bank.ymin + 1
            pos = f.tell()
            bank.objoffset = pos + (ncer.banknum - (i + 1)) * (8 if ncer.tbank == 0x00 else 0x10) + bank.celloffset
            f.seek(bank.objoffset)
            for j in range(bank.cellnum):
                cell = Cell()
                cell.objoffset = f.tell()
                obj0 = f.readUShort()
                obj1 = f.readUShort()
                obj2 = f.readUShort()
                cell.y = obj0 & 0xff
                if cell.y >= 128:
                    cell.y -= 256
                cell.shape = (obj0 >> 14) & 3
                cell.x = obj1 & 0x01ff
                if cell.x >= 0x100:
                    cell.x -= 0x200
                cell.size = (obj1 >> 14) & 3
                cell.tileoffset = obj2 & 0x03ff
                cell.rsflag = ((obj0 >> 8) & 1) == 1
                if not cell.rsflag:
                    cell.objdisable = ((obj0 >> 9) & 1) == 1
                else:
                    cell.doublesize = ((obj0 >> 9) & 1) == 1
                cell.objmode = (obj0 >> 10) & 3
                cell.mosaic = ((obj0 >> 12) & 1) == 1
                cell.depth = ((obj0 >> 13) & 1) == 1
                if not cell.rsflag:
                    # cell.unused = (obj1 >> 9) & 7
                    cell.xflip = ((obj1 >> 12) & 1) == 1
                    cell.yflip = ((obj1 >> 13) & 1) == 1
                else:
                    cell.selectparam = (obj1 >> 9) & 0x1f
                cell.priority = (obj2 >> 10) & 3
                cell.pal = (obj2 >> 12) & 0xf
                cellsize = getNCERCellSize(cell.shape, cell.size)
                cell.width = cellsize[0]
                cell.height = cellsize[1]
                cell.numcell = j
                bank.cells.append(cell)
            # Calculate bank size
            minx = miny = 512
            maxx = maxy = -512
            malformedtbank = False
            for cell in bank.cells:
                minx = min(minx, cell.x)
                miny = min(miny, cell.y)
                maxx = max(maxx, cell.x + cell.width)
                maxy = max(maxy, cell.y + cell.height)
            if ncer.tbank == 0x01 and (maxx - minx > bank.width or maxy - miny > bank.height):
                malformedtbank = True
                common.logWarning("Malformed tbank", ncerfile, bank.width, minx, maxx, bank.height, miny, maxy)
            if ncer.tbank == 0x00 or malformedtbank:
                bank.width = maxx - minx
                bank.height = maxy - miny
            for cell in bank.cells:
                cell.x -= minx
                cell.y -= miny
            common.logDebug(vars(bank))
            for cell in bank.cells:
                common.logDebug(vars(cell))
            # Sort cells based on priority
            bank.cells.sort(key=lambda x: (x.priority, x.numcell), reverse=True)
            f.seek(pos)
            # Calculate layers for .psd exporting, first put the first cell on the first layer
            cells = sorted(bank.cells, key=lambda x: (x.priority, x.numcell))
            if bank.cellnum > 0:
                bank.layernum = 1
                cells[0].layer = 0
                if len(cells) > 1:
                    for j in range(1, len(cells)):
                        cell = cells[j]
                        # For every other cell in the current layer, check if it's intersected
                        hit = False
                        for layercheck in cells:
                            if cell != layercheck and layercheck.layer == bank.layernum - 1:
                                if cellIntersect(cell, layercheck):
                                    hit = True
                                    break
                        if hit:
                            # All layers are full, make a new one
                            cells[j].layer = bank.layernum
                            bank.layernum += 1
                        else:
                            cells[j].layer = bank.layernum - 1
    # Mark banks as duplicate
    if not ignoredupes:
        for bank in ncer.banks:
            if bank.duplicate:
                continue
            for bank2 in ncer.banks:
                if bank2.duplicate or bank == bank2 or bank.cellnum != bank2.cellnum:
                    continue
                samecells = True
                for i in range(bank.cellnum):
                    if bank.cells[i].width != bank2.cells[i].width or bank.cells[i].height != bank2.cells[i].height or bank.cells[i].tileoffset != bank2.cells[i].tileoffset:
                        samecells = False
                        break
                if samecells:
                    bank2.duplicate = True
    common.logDebug("Loaded", len(ncer.banks), "banks")
    return ncer


def cellIntersect(a: Cell, b: Cell) -> bool:
    """Check if the bounding boxes of two cells intersect.

    Args:
        a: First cell.
        b: Second cell.

    Returns:
        True if the cells intersect.
    """
    return (a.x < b.x + b.width) and (a.x + a.width > b.x) and (a.y < b.y + b.height) and (a.y + a.height > b.y)


def tileToPixels(pixels, width: int, ncgr: NCGR, tile: int, xflip: bool, yflip: bool, i: int, j: int, palette: list, pali: int, usetransp: bool = True):
    """Draw a single tile of an NCGR on an image.

    Args:
        pixels: PIL pixel access object to draw on.
        width: Width of the image.
        ncgr: Tile structure holding the tiles.
        tile: Index of the tile to draw.
        xflip: Whether the tile is flipped horizontally.
        yflip: Whether the tile is flipped vertically.
        i: Y position to draw at, in tiles.
        j: X position to draw at, in tiles.
        palette: Palette to use, as a list of RGBA tuples.
        pali: Index of the first palette color to use.
        usetransp: Whether to skip drawing index 0, leaving it transparent.

    Returns:
        The pixels object.
    """
    try:
        tiledata = ncgr.tiles[tile]
    except IndexError:
        common.logWarning("Unable to get tile", tile)
        return pixels
    if xflip or yflip:
        tiledata = common.flipTile(tiledata, xflip, yflip, ncgr.tilesize, ncgr.tilesize)
    for i2 in range(ncgr.tilesize):
        for j2 in range(ncgr.tilesize):
            try:
                index = tiledata[i2 * ncgr.tilesize + j2]
                if not usetransp or index > 0:
                    if ncgr.lineal:
                        lineal = (i * width * ncgr.tilesize) + (j * ncgr.tilesize * ncgr.tilesize) + (i2 * ncgr.tilesize + j2)
                        pixelx = lineal % width
                        pixely = int(math.floor(lineal / width))
                    else:
                        pixelx = j * ncgr.tilesize + j2
                        pixely = i * ncgr.tilesize + i2
                    pixels[pixelx, pixely] = palette[pali + index]
            except IndexError:
                common.logWarning("Unable to set pixels at", i, j, i2, j2, "for tile", tile, "with palette", pali)
    return pixels


def drawNCER(outfile: str, ncer: NCER, ncgr: NCGR, palettes: dict, usetransp: bool = True, layered: bool = False) -> None:
    """Draw the banks of an NCER to a png file.

    The banks are stacked vertically, with the palettes drawn on the right
    side. When layered is set and ImageMagick is available, a psd file is
    also created with each bank layer on its own named layer.

    Args:
        outfile: Path of the png file to create.
        ncer: Cell structure returned by :func:`readNCER`.
        ncgr: Tile structure returned by :func:`readNCGR`.
        palettes: Dictionary of palette index -> list of RGBA tuples.
        usetransp: Whether to skip drawing index 0, leaving it transparent.
        layered: Whether to create the psd file.
    """
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    palsize = 0
    for palette in palettes.values():
        palsize += 5 * (len(palette) // 8)
    width = height = 0
    for bank in ncer.banks:
        if bank.duplicate:
            continue
        width = max(width, bank.width)
        height += bank.height
    img = Image.new("RGBA", (width + 40, max(height, palsize)), (0, 0, 0, 0))
    pixels = img.load()
    # Draw palette
    palstart = 0
    for palette in palettes.values():
        pixels = common.drawPalette(pixels, palette, width, palstart * 10)
        palstart += 1
    layers = []
    # If all banks have a single layer, disable layering
    if layered:
        allone = True
        for bank in ncer.banks:
            if bank.layernum > 1:
                allone = False
                break
        layered = not allone
    # Save just the palette as a separate layer
    if layered:
        img.save(outfile, "PNG")
    # Loop and draw the banks
    currheight = 0
    for bankn in range(len(ncer.banks)):
        bank = ncer.banks[bankn]
        if bank.width == 0 or bank.height == 0 or bank.duplicate:
            continue
        if layered:
            banklayers = []
            for i in range(bank.layernum):
                banklayers.append(Image.new("RGBA", (img.width, img.height), (0, 0, 0, 0)))
        for celln in range(len(bank.cells)):
            cell = bank.cells[celln]
            x = (bank.partitionoffset // (8 * ncgr.bpp)) + ((cell.tileoffset << ncer.blocksize) * 0x20 // (8 * ncgr.bpp))
            if cell.pal in palettes.keys():
                pali = 0
                palette = palettes[cell.pal]
            else:
                pali = cell.pal * 16
                palette = palettes[0]
            cellimg = Image.new("RGBA", (cell.width, cell.height), (0, 0, 0, 0))
            cellpixels = cellimg.load()
            for i in range(cell.height // ncgr.tilesize):
                for j in range(cell.width // ncgr.tilesize):
                    cellpixels = tileToPixels(cellpixels, cell.width, ncgr, x, cell.xflip, cell.yflip, i, j, palette, pali, usetransp)
                    x += 1
            if layered:
                banklayers[cell.layer].paste(cellimg, (cell.x, currheight + cell.y), cellimg)
            img.paste(cellimg, (cell.x, currheight + cell.y), cellimg)
        if layered:
            for i in range(bank.layernum):
                layerfile = outfile.replace(".png", "_" + str(bankn) + "_" + str(i) + ".png")
                banklayers[i].save(layerfile, "PNG")
                layers.append(layerfile)
        currheight += bank.height
    magickcmd = ""
    if os.path.isfile("magick"):
        magickcmd = "./magick"
    elif shutil.which("magick"):
        magickcmd = shutil.which("magick")
    if layered and magickcmd != "":
        with open("script.scr", "w") as script:
            script.write("\"" + outfile + "\" -label \"palette\" -background none -mosaic -set colorspace RGBA")
            for layer in layers:
                script.write(" ( -page +0+0 -label \"" + os.path.basename(layer).replace(".png", "") + "\" \"" + layer + "\"[0] -background none -mosaic -set colorspace RGBA )")
            script.write(" ( -clone 0--1 -background none -mosaic ) -reverse -write \"" + outfile.replace(".png", ".psd") + "\"")
        cmd = magickcmd + " -script script.scr"
        common.execute(cmd, False)
        for layer in layers:
            os.remove(layer)
        os.remove(outfile)
        os.remove("script.scr")
    img.save(outfile, "PNG")


def drawNCGR(outfile: str, nscr: NSCR, ncgr: NCGR, palettes: dict, width: int, height: int, usetransp: bool = True) -> None:
    """Draw an NCGR to a png file, with the palettes on the right side.

    Args:
        outfile: Path of the png file to create.
        nscr: Map structure returned by :func:`readNSCR`, or None to draw
            the tiles sequentially.
        ncgr: Tile structure returned by :func:`readNCGR`.
        palettes: Dictionary of palette index -> list of RGBA tuples.
        width: Width of the image, 0xffff to assume a square image.
        height: Height of the image, 0xffff to assume a square image.
        usetransp: Whether to skip drawing index 0, leaving it transparent.
    """
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    if width == 0xffff or height == 0xffff:
        root = int(math.sqrt(len(ncgr.tiles)))
        if math.pow(root, 2) == len(ncgr.tiles):
            width = height = root * ncgr.tilesize
            common.logWarning("Assuming square size", width, "for", outfile)
        else:
            common.logError("Wrong width/height", width, height, "for", outfile)
            return
    palsize = 0
    for palette in palettes.values():
        palsize += 5 * (len(palette) // 8)
    img = Image.new("RGBA", (width + 40, max(height, palsize)), (0, 0, 0, 0))
    pixels = img.load()
    x = 0
    for i in range(height // ncgr.tilesize):
        for j in range(width // ncgr.tilesize):
            if nscr is not None:
                map = nscr.maps[x]
                if map.pal in palettes.keys():
                    pali = 0
                    palette = palettes[map.pal]
                else:
                    pali = map.pal * 16
                    palette = palettes[0]
                pixels = tileToPixels(pixels, width, ncgr, map.tile, map.xflip, map.yflip, i, j, palette, pali, usetransp)
            else:
                pixels = tileToPixels(pixels, width, ncgr, x, False, False, i, j, palettes[0], 0, usetransp)
            x += 1
    palstart = 0
    for palette in palettes.values():
        pixels = common.drawPalette(pixels, palette, width, palstart * 10)
        palstart += 1
    img.save(outfile, "PNG")


def writeNCGRData(f: common.Stream, bpp: int, index1: int, index2: int) -> None:
    """Write two pixels of tile data, packed in one byte for 4bpp.

    Args:
        f: Stream to write to.
        bpp: Bits per pixel, 4 or 8.
        index1: First palette index.
        index2: Second palette index.
    """
    if bpp == 4:
        f.writeByte(((index2) << 4) | index1)
    else:
        f.writeByte(index1)
        f.writeByte(index2)


def writeNCGRTile(f: common.Stream, pixels, width: int, ncgr: NCGR, i: int, j: int, palette: list) -> None:
    """Write a single tile of an NCGR from an image.

    Args:
        f: Stream to write to, seeked to the tile.
        pixels: PIL pixel access object to read from.
        width: Width of the image.
        ncgr: Tile structure the tile belongs to.
        i: Y position to read at, in tiles.
        j: X position to read at, in tiles.
        palette: Palette to use, as a list of RGBA tuples.
    """
    for i2 in range(ncgr.tilesize):
        for j2 in range(0, ncgr.tilesize, 2):
            if ncgr.lineal:
                lineal = (i * width * ncgr.tilesize) + (j * ncgr.tilesize * ncgr.tilesize) + (i2 * ncgr.tilesize + j2)
                pixelx = lineal % width
                pixely = int(math.floor(lineal / width))
            else:
                pixelx = j * ncgr.tilesize + j2
                pixely = i * ncgr.tilesize + i2
            index1 = common.getPaletteIndex(palette, pixels[pixelx, pixely])
            index2 = common.getPaletteIndex(palette, pixels[pixelx + 1, pixely])
            writeNCGRData(f, ncgr.bpp, index1, index2)


def writeNCGR(file: str, ncgr: NCGR, infile: str, palettes: dict, width: int = -1, height: int = -1) -> None:
    """Repack a png into an NCGR file with sequential tiles.

    Args:
        file: Path of the NCGR file to update.
        ncgr: Tile structure returned by :func:`readNCGR`.
        infile: Path of the png file to pack.
        palettes: Dictionary of palettes, only the first one is used.
        width: Width of the image, or -1 to use the NCGR one.
        height: Height of the image, or -1 to use the NCGR one.
    """
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    if width < 0:
        width = ncgr.width
        height = ncgr.height
    img = Image.open(infile)
    img = img.convert("RGBA")
    pixels = img.load()
    with common.Stream(file, "rb+") as f:
        f.seek(ncgr.tileoffset)
        for i in range(height // ncgr.tilesize):
            for j in range(width // ncgr.tilesize):
                writeNCGRTile(f, pixels, width, ncgr, i, j, palettes[0])


def writeNSCR(file: str, ncgr: NCGR, nscr: NSCR, infile: str, palettes: dict, width: int = -1, height: int = -1, skipfirst: bool = False) -> None:
    """Repack a png into an NCGR file, following its original map data.

    Tiles are written back where the map entries point, without changing
    the map, so the png needs to keep the original tile layout. Flipped
    tiles are skipped.

    Args:
        file: Path of the NCGR file to update.
        ncgr: Tile structure returned by :func:`readNCGR`.
        nscr: Map structure returned by :func:`readNSCR`.
        infile: Path of the png file to pack.
        palettes: Dictionary of palette index -> list of RGBA tuples.
        width: Width of the image, or -1 to use the NSCR one.
        height: Height of the image.
        skipfirst: Whether to skip the first tile.
    """
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    if width < 0:
        width = nscr.width
        # height = nscr.height
    img = Image.open(infile)
    img = img.convert("RGBA")
    pixels = img.load()
    with common.Stream(file, "rb+") as f:
        donetiles = []
        x = 0
        for i in range(height // ncgr.tilesize):
            for j in range(width // ncgr.tilesize):
                map = nscr.maps[x]
                # Skip flipped tiles since there's always(?) going to be an unflipped one next
                if map.xflip or map.yflip:
                    x += 1
                    continue
                if skipfirst and x == 0:
                    x += 1
                    continue
                # Write the tile if it's a new one
                if map.tile not in donetiles:
                    donetiles.append(map.tile)
                    tilenum = map.tile
                    if skipfirst:
                        tilenum -= 1
                    f.seek(ncgr.tileoffset + tilenum * (8 * ncgr.bpp))
                    writeNCGRTile(f, pixels, width, ncgr, i, j, palettes[map.pal])
                x += 1


def writeMappedNSCR(file: str, mapfile: str, ncgr: NCGR, nscr: NSCR, infile: str, palettes: dict, width: int = -1, height: int = -1, transptile: bool = False, writelen: bool = True, useoldpal: bool = False) -> None:
    """Repack a png into an NCGR and NSCR pair, rebuilding the map.

    Single map version of :func:`writeMultiMappedNSCR`, see that for the
    parameters.
    """
    writeMultiMappedNSCR(file, [mapfile], ncgr, [nscr], [infile], palettes, width, height, transptile, writelen, useoldpal)


def writeMultiMappedNSCR(file: str, mapfiles: list, ncgr: NCGR, nscrs: list, infiles: list, palettes: dict, width: int = -1, height: int = -1, transptile: bool = False, writelen: bool = True, useoldpal: bool = False) -> None:
    """Repack pngs into an NCGR and multiple NSCR maps, rebuilding them.

    Tiles are deduplicated across all the maps, reusing already written
    tiles and their flipped versions, and each map is rebuilt with the
    best palette for each tile.

    Args:
        file: Path of the NCGR file to update.
        mapfiles: Paths of the NSCR files to update.
        ncgr: Tile structure returned by :func:`readNCGR`.
        nscrs: Map structures returned by :func:`readNSCR`.
        infiles: Paths of the png files to pack.
        palettes: Dictionary of palette index -> list of RGBA tuples.
        width: Width of the images, or -1 to use the NSCR ones.
        height: Height of the images, or -1 to use the NSCR ones.
        transptile: Whether to reserve the first tile as a fully
            transparent one.
        writelen: Whether to write the new tile data length in the NCGR.
        useoldpal: Whether to keep the palette of the original map entries,
            instead of picking the best one.
    """
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    with common.Stream(file, "rb+") as f:
        tiles = []
        if transptile:
            # Start with a completely transparent tile
            tile = []
            for i2 in range(ncgr.tilesize):
                for j2 in range(ncgr.tilesize):
                    tile.append(0)
            tiles.append(tile)
            f.seek(ncgr.tileoffset)
            for i2 in range(ncgr.tilesize):
                for j2 in range(0, ncgr.tilesize, 2):
                    writeNCGRData(f, ncgr.bpp, 0, 0)
        for n in range(len(infiles)):
            imgwidth = width
            imgheight = height
            if imgwidth < 0:
                imgwidth = nscrs[n].width
            if imgheight < 0:
                imgheight = nscrs[n].height
            img = Image.open(infiles[n])
            img = img.convert("RGBA")
            pixels = img.load()
            x = 0
            with common.Stream(mapfiles[n], "rb+") as mapf:
                mapf.seek(nscrs[n].mapoffset)
                for i in range(imgheight // ncgr.tilesize):
                    for j in range(imgwidth // ncgr.tilesize):
                        tilecolors = []
                        for i2 in range(ncgr.tilesize):
                            for j2 in range(ncgr.tilesize):
                                tilecolors.append(pixels[j * ncgr.tilesize + j2, i * ncgr.tilesize + i2])
                        if useoldpal:
                            pal = nscrs[n].maps[x].pal
                        else:
                            pal = common.findBestPalette(palettes, tilecolors)
                        tile = []
                        for tilecolor in tilecolors:
                            tile.append(common.getPaletteIndex(palettes[pal], tilecolor))
                        # Search for a repeated tile
                        map = Map()
                        map.pal = pal
                        map.tile, map.xflip, map.yflip = searchTile(tile, tiles, ncgr.tilesize)
                        if map.tile == -1:
                            tiles.append(tile)
                            map.tile = len(tiles) - 1
                            f.seek(ncgr.tileoffset + map.tile * (8 * ncgr.bpp))
                            writeNCGRTile(f, pixels, imgwidth, ncgr, i, j, palettes[map.pal])
                        mapdata = (map.pal << 12) | (map.yflip << 11) | (map.xflip << 10) | map.tile
                        mapf.writeUShort(mapdata)
                        x += 1
        if writelen:
            f.seek(40)
            f.writeUInt(len(tiles) * (8 * ncgr.bpp))


def searchTile(tile: list, tiles: list, tilesize: int = 8):
    """Search for a tile in a list, also trying its flipped versions.

    Args:
        tile: Tile to search for, as a flat list of palette indexes.
        tiles: List of tiles to search in.
        tilesize: Size of the tiles.

    Returns:
        A (tile, xflip, yflip) tuple with the index of the matching tile,
        or -1 if not found, and the flips needed to match it.
    """
    tilex = common.flipTile(tile, True, False, tilesize, tilesize)
    tiley = common.flipTile(tile, False, True, tilesize, tilesize)
    tilexy = common.flipTile(tile, True, True, tilesize, tilesize)
    for i in range(len(tiles)):
        if tiles[i] == tile:
            return i, False, False
        if tiles[i] == tilex:
            return i, True, False
        if tiles[i] == tiley:
            return i, False, True
        if tiles[i] == tilexy:
            return i, True, True
    return -1, False, False


def writeNCER(file: str, ncerfile: str, ncgr: NCGR, ncer: NCER, infile: str, palettes: dict, width: int = 0, height: int = 0, appendTiles: bool = False, checkRepeat: bool = True, writelen: bool = True, fixtransp: bool = False, checkalpha: bool = False, zerotransp: bool = True) -> None:
    """Repack a png or psd into the NCGR and NCER files of a sprite.

    The image is expected in the layout drawn by :func:`drawNCER`. For psd
    files, the bank layers are extracted with ImageMagick and matched by
    name. Flipped and duplicate cells are skipped.

    Args:
        file: Path of the NCGR file to update.
        ncerfile: Path of the NCER file to update.
        ncgr: Tile structure returned by :func:`readNCGR`.
        ncer: Cell structure returned by :func:`readNCER`.
        infile: Path of the png or psd file to pack.
        palettes: Dictionary of palette index -> list of RGBA tuples.
        width: Unused.
        height: Unused.
        appendTiles: Whether cells that changed can have new tiles appended
            at the end of the NCGR, updating their OBJ entries.
        checkRepeat: Whether to skip tiles that were already written.
        writelen: Whether to write the new tile count in the NCGR, when
            tiles were appended.
        fixtransp: Whether to skip the first palette color when matching.
        checkalpha: Whether the alpha channel counts when matching colors.
        zerotransp: Whether fully transparent colors match index 0.
    """
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    psd = infile.endswith(".psd")
    if psd:
        magickcmd = ""
        if os.path.isfile("magick"):
            magickcmd = "./magick"
        elif shutil.which("magick"):
            magickcmd = shutil.which("magick")
        if magickcmd == "":
            common.logError("ImageMagick not found")
            return
        basename = os.path.basename(infile).replace(".psd", "")
        # Get the layer names by using identify
        identifycmd = magickcmd + " identify -verbose " + infile
        if os.name != "nt":
            psdinfo = subprocess.check_output(shlex.split(identifycmd))
        else:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            psdinfo = subprocess.check_output(identifycmd, startupinfo=startupinfo)
        layernames = []
        while psdinfo:
            parts = psdinfo.partition(b"label: ")
            lastpart = parts[2]
            if lastpart:
                index = lastpart.find(b"\n")
                if index != -1:
                    layernames.append(lastpart[:index].decode("ascii").strip())
            psdinfo = lastpart
        # Export them as PNG
        for i in range(len(layernames)):
            common.execute(magickcmd + " convert \"" + infile + "[0]\" \"" + infile + "[" + str(i + 1) + "]\" ( -clone 0 -alpha transparent ) -swap 0 +delete -coalesce -compose src-over -composite \"layer_" + layernames[i] + ".png\"", False)
    else:
        img = Image.open(infile)
        img = img.convert("RGBA")
        pixels = img.load()
    nexttile = len(ncgr.tiles)
    with common.Stream(file, "rb+") as f:
        with common.Stream(ncerfile, "rb+") as fn:
            currheight = 0
            donetiles = []
            cellboxes: dict[int, list[int]] = {}
            for nceri in range(len(ncer.banks)):
                bank = ncer.banks[nceri]
                if bank.width == 0 or bank.height == 0 or bank.duplicate:
                    continue
                if psd:
                    # Extract layers from the psd file, searching them by name
                    layers = []
                    for i in range(bank.layernum):
                        layername = "layer_" + basename + "_" + str(nceri) + "_" + str(i) + ".png"
                        if not os.path.isfile(layername):
                            common.logError("Layer", layername, "not found")
                            for layername in layernames:
                                os.remove("layer_" + layername + ".png")
                            return
                        # Copy the layer in a normal PIL image for cell access
                        layerimg = Image.open(layername)
                        layerimg = layerimg.convert("RGBA")
                        layers.append(layerimg)
                for cell in bank.cells:
                    # Skip flipped cells since there's always(?) going to be an unflipped one next
                    if cell.xflip or cell.yflip:
                        continue
                    if psd:
                        img = layers[cell.layer]
                        pixels = img.load()
                    tile = (bank.partitionoffset // (8 * ncgr.bpp)) + ((cell.tileoffset << ncer.blocksize) * 0x20 // (8 * ncgr.bpp))
                    if cell.pal in palettes.keys():
                        pali = 0
                        palette = palettes[cell.pal]
                    else:
                        pali = cell.pal * 16
                        palette = palettes[0]
                    sametile = checkRepeat and tile in donetiles
                    addingtiles = False
                    if sametile and appendTiles:
                        tiledata = []
                        for i in range(cell.height // ncgr.tilesize):
                            for j in range(cell.width // ncgr.tilesize):
                                for i2 in range(ncgr.tilesize):
                                    for j2 in range(0, ncgr.tilesize, 2):
                                        if ncgr.lineal:
                                            lineal = (i * cell.width * ncgr.tilesize) + (j * ncgr.tilesize * ncgr.tilesize) + (i2 * ncgr.tilesize + j2)
                                            pixelx = cell.x + (lineal % cell.width)
                                            pixely = currheight + cell.y + int(math.floor(lineal / cell.width))
                                        else:
                                            pixelx = cell.x + j * ncgr.tilesize + j2
                                            pixely = currheight + cell.y + i * ncgr.tilesize + i2
                                        index1 = common.getPaletteIndex(palette, pixels[pixelx, pixely], fixtransp, pali, 16 if ncgr.bpp == 4 else -1, checkalpha, zerotransp)
                                        index2 = common.getPaletteIndex(palette, pixels[pixelx + 1, pixely], fixtransp, pali, 16 if ncgr.bpp == 4 else -1, checkalpha, zerotransp)
                                        tiledata.append(index1)
                                        tiledata.append(index2)
                        sametile = tiledata == cellboxes[tile]
                        if not sametile:
                            # Check if we can find a repeated tile
                            addingtiles = True
                            tile = nexttile
                            for celltile in cellboxes:
                                if len(cellboxes[celltile]) >= len(tiledata) and tiledata == cellboxes[celltile][:len(tiledata)]:
                                    tile = celltile
                                    addingtiles = False
                                    sametile = True
                                    break
                            tileoffset = (tile * (8 * ncgr.bpp) // 0x20) >> ncer.blocksize
                            fn.seek(cell.objoffset + 4)
                            obj2 = 0
                            obj2 += tileoffset & 0x3ff
                            obj2 += (cell.priority & 3) << 10
                            obj2 += (cell.pal & 0xf) << 12
                            fn.writeUShort(obj2)
                    if not sametile:
                        currtile = tile
                        cellboxes[currtile] = []
                        for i in range(cell.height // ncgr.tilesize):
                            for j in range(cell.width // ncgr.tilesize):
                                if tile not in donetiles:
                                    donetiles.append(tile)
                                    f.seek(ncgr.tileoffset + tile * (8 * ncgr.bpp))
                                    for i2 in range(ncgr.tilesize):
                                        for j2 in range(0, ncgr.tilesize, 2):
                                            if ncgr.lineal:
                                                lineal = (i * cell.width * ncgr.tilesize) + (j * ncgr.tilesize * ncgr.tilesize) + (i2 * ncgr.tilesize + j2)
                                                pixelx = cell.x + (lineal % cell.width)
                                                pixely = currheight + cell.y + int(math.floor(lineal / cell.width))
                                            else:
                                                pixelx = cell.x + j * ncgr.tilesize + j2
                                                pixely = currheight + cell.y + i * ncgr.tilesize + i2
                                            index1 = common.getPaletteIndex(palette, pixels[pixelx, pixely], fixtransp, pali, 16 if ncgr.bpp == 4 else -1, checkalpha, zerotransp)
                                            index2 = common.getPaletteIndex(palette, pixels[pixelx + 1, pixely], fixtransp, pali, 16 if ncgr.bpp == 4 else -1, checkalpha, zerotransp)
                                            cellboxes[currtile].append(index1)
                                            cellboxes[currtile].append(index2)
                                            writeNCGRData(f, ncgr.bpp, index1, index2)
                                tile += 1
                                if addingtiles:
                                    nexttile += 1
                currheight += bank.height
        if writelen and nexttile > len(ncgr.tiles):
            tottiles = nexttile
            f.seek(32)
            f.writeUInt(tottiles)
            f.seek(4, 1)
            f.writeUInt(tottiles * (8 * ncgr.bpp))
    if psd:
        for layername in layernames:
            os.remove("layer_" + layername + ".png")


# 3D Models
NSBMDbpp = [0, 8, 2, 4, 8, 2, 8, 16]
"""Bits per pixel of each NSBMD texture format."""


class NSBMD:
    """Structure of the TEX0 block of an NSBMD or NSBTX file.

    Attributes:
        textures: List of textures in the file.
        palettes: List of palettes in the file.
        blockoffset: Offset of the TEX0 block.
        blocksize: Size of the TEX0 block.
        blocklimit: Offset of the end of the TEX0 block.
        texdatasize: Size of the texture data.
        texdataoffset: Offset of the texture data.
        sptexsize: Size of the 4x4-texel texture data.
        sptexoffset: Offset of the 4x4-texel texture data.
        spdataoffset: Offset of the 4x4-texel palette index data.
        paldatasize: Size of the palette data.
        paldefoffset: Offset of the palette definitions.
        paldataoffset: Offset of the palette data.
    """
    def __init__(self):
        self.textures: list[NSBMDTexture] = []
        self.palettes: list[NSBMDPalette] = []
        self.blocksize: int = 0
        self.blocklimit: int = 0
        self.texdatasize: int = 0
        self.texdataoffset: int = 0
        self.sptexsize: int = 0
        self.sptexoffset: int = 0
        self.spdataoffset: int = 0
        self.paldatasize: int = 0
        self.paldefoffset: int = 0
        self.paldataoffset: int = 0


class NSBMDTexture:
    """Structure of a single NSBMD texture.

    Attributes:
        name: Name of the texture.
        offset: Offset of the texture data.
        format: Format of the texture data, an index in :data:`NSBMDbpp`.
        width: Width of the texture.
        height: Height of the texture.
        size: Size of the texture data.
        data: Texture data.
        spdata: Palette index data, for 4x4-texel textures.
    """
    def __init__(self):
        self.name: str = ""
        self.offset: int = 0
        self.format: int = 0
        self.width: int = 0
        self.height: int = 0
        self.size: int = 0
        self.data = []
        self.spdata: list = []


class NSBMDPalette:
    """Structure of a single NSBMD palette.

    Attributes:
        name: Name of the palette.
        offset: Offset of the palette data.
        size: Size of the palette data.
        data: Palette colors, as a list of RGBA tuples.
    """
    def __init__(self):
        self.name: str = ""
        self.offset: int = 0
        self.size: int = 0
        self.data: list = []


def readTEX0(nsbmd: NSBMD, f: common.Stream, zerotransp: bool = False) -> NSBMD:
    """Read the textures and palettes of a TEX0 block.

    Args:
        nsbmd: Structure with the blockoffset already set, filled in place.
        f: Stream opened on the model file.
        zerotransp: Whether the first color of each palette should be
            transparent.

    Returns:
        The filled nsbmd structure.
    """
    # Read TEX0 block
    f.seek(nsbmd.blockoffset + 4)
    nsbmd.blocksize = f.readUInt()
    nsbmd.blocklimit = nsbmd.blocksize + nsbmd.blockoffset
    f.seek(4, 1)
    nsbmd.texdatasize = f.readUShort() * 8
    f.seek(6, 1)
    nsbmd.texdataoffset = f.readUInt() + nsbmd.blockoffset
    f.seek(4, 1)
    nsbmd.sptexsize = f.readUShort() * 8
    f.seek(6, 1)
    nsbmd.sptexoffset = f.readUInt() + nsbmd.blockoffset
    nsbmd.spdataoffset = f.readUInt() + nsbmd.blockoffset
    f.seek(4, 1)
    nsbmd.paldatasize = f.readUShort() * 8
    f.seek(2, 1)
    nsbmd.paldefoffset = f.readUInt() + nsbmd.blockoffset
    nsbmd.paldataoffset = f.readUInt() + nsbmd.blockoffset
    common.logDebug(vars(nsbmd))
    # Texture definition
    f.seek(1, 1)
    texnum = f.readByte()
    pos = f.tell()
    f.seek(nsbmd.paldefoffset + 1)
    palnum = f.readByte()
    f.seek(pos)
    common.logDebug("texnum:", texnum, "palnum:", palnum)
    f.seek(14 + (texnum * 4), 1)
    for i in range(texnum):
        offset = f.readUShort() * 8
        param = f.readUShort()
        f.seek(4, 1)
        tex = NSBMDTexture()
        tex.format = (param >> 10) & 7
        tex.width = 8 << ((param >> 4) & 7)
        tex.height = 8 << ((param >> 7) & 7)
        tex.size = tex.width * tex.height * NSBMDbpp[tex.format] // 8
        if tex.format == 5:
            tex.offset = offset + nsbmd.sptexoffset
        else:
            tex.offset = offset + nsbmd.texdataoffset
        nsbmd.textures.append(tex)
    # Texture name
    for tex in nsbmd.textures:
        tex.name = f.readString(16)
        common.logDebug(vars(tex))
    # Palette definition
    f.seek(nsbmd.paldefoffset + 2 + 14 + (palnum * 4))
    for i in range(palnum):
        pal = NSBMDPalette()
        pal.offset = (f.readUShort() * 8) + nsbmd.paldataoffset
        f.seek(2, 1)
        nsbmd.palettes.append(pal)
    # Palette size
    if palnum > 0:
        for i in range(palnum):
            r = i + 1
            while r < len(nsbmd.palettes) and nsbmd.palettes[r].offset == nsbmd.palettes[i].offset:
                r += 1
            if r != palnum:
                nsbmd.palettes[i].size = nsbmd.palettes[r].offset - nsbmd.palettes[i].offset
            else:
                nsbmd.palettes[i].size = nsbmd.blocklimit - nsbmd.palettes[i].offset
        nsbmd.palettes[i].size = nsbmd.blocklimit - nsbmd.palettes[i].offset
    # Palette name
    for pal in nsbmd.palettes:
        pal.name = f.readString(16)
        common.logDebug(vars(pal))
    # Traverse palettes
    for pal in nsbmd.palettes:
        f.seek(pal.offset)
        for i in range(pal.size // 2):
            palcolor = common.readPalette(f.readShort())
            if i == 0 and zerotransp:
                palcolor = (palcolor[0], palcolor[1], palcolor[2], 0)
            pal.data.append(palcolor)
    # Traverse texture
    spdataoffset = nsbmd.spdataoffset
    for texi in range(len(nsbmd.textures)):
        tex = nsbmd.textures[texi]
        if tex.format == 5:
            r = tex.size >> 1
            f.seek(spdataoffset)
            for i in range(r // 2):
                tex.spdata.append(f.readUShort())
            spdataoffset += r
        # Export texture
        f.seek(tex.offset)
        if tex.format == 5:
            for i in range(tex.size // 4):
                tex.data.append(f.readUInt())
        else:
            tex.data = f.read(tex.size)
    return nsbmd


def readNSBMD(nsbmdfile: str, zerotransp: bool = False) -> "NSBMD | None":
    """Read the textures and palettes of an NSBMD model.

    Args:
        nsbmdfile: Path of the NSBMD file, 3DG files are also supported.
        zerotransp: Whether the first color of each palette should be
            transparent.

    Returns:
        The parsed structure, or None if the model has no textures.
    """
    nsbmd = NSBMD()
    with common.Stream(nsbmdfile, "rb") as f:
        nsbmdstart = 0
        # 3DG have an additional header, skip it
        if f.readString(4) == "D3KT":
            f.seek(4, 1)
            nsbmdstart = f.readUShort()
        # Read the TEX0 offset
        f.seek(nsbmdstart + 20)
        check = f.readString(4)
        if check == "MDL0":
            # The model doesn't have any textures
            return None
        f.seek(-4, 1)
        texstart = f.readUShort()
        nsbmd.blockoffset = nsbmdstart + texstart
        return readTEX0(nsbmd, f, zerotransp)


def readNSBTX(nsbmdfile: str, zerotransp: bool = False) -> NSBMD:
    """Read the textures and palettes of an NSBTX file.

    Args:
        nsbmdfile: Path of the NSBTX file.
        zerotransp: Whether the first color of each palette should be
            transparent.

    Returns:
        The parsed structure.
    """
    nsbmd = NSBMD()
    with common.Stream(nsbmdfile, "rb") as f:
        nsbmdstart = 0
        # Read the TEX0 offset
        f.seek(nsbmdstart + 0x10)
        texstart = f.readUShort()
        nsbmd.blockoffset = nsbmdstart + texstart
        return readTEX0(nsbmd, f, zerotransp)


def drawNSBMD(file: str, nsbmd: NSBMD, texi: int) -> None:
    """Draw a single NSBMD texture to a png file.

    All the texture formats are supported. The palette, if any, is drawn
    on the right side.

    Args:
        file: Path of the png file to create.
        nsbmd: Structure returned by :func:`readNSBMD`.
        texi: Index of the texture to draw.
    """
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    tex = nsbmd.textures[texi]
    if tex.format != 7 and len(nsbmd.palettes) == 0:
        common.logDebug("Skipping texture with no palettes")
        return
    common.logDebug("Exporting", tex.name, "...")
    palette = None
    if tex.format != 7:
        palette = nsbmd.palettes[texi].data if texi < len(nsbmd.palettes) else nsbmd.palettes[0].data
        img = Image.new("RGBA", (tex.width + 40, max(tex.height, (len(palette) // 8) * 5)), (0, 0, 0, 0))
    else:
        img = Image.new("RGBA", (tex.width, tex.height), (0, 0, 0, 0))
    pixels = img.load()
    # A3I5 Translucent Texture (3bit Alpha, 5bit Color Index)
    if tex.format == 1:
        for i in range(tex.height):
            for j in range(tex.width):
                x = i * tex.width + j
                index = tex.data[x] & 0x1f
                alpha = (tex.data[x] >> 5)
                alpha = int(((alpha * 4) + (alpha / 2)) * 8)
                if index < len(palette):
                    pixels[j, i] = (palette[index][0], palette[index][1], palette[index][2], alpha)
                else:
                    common.logWarning("Index", index, "is out of range", len(palette))
    # 4-color Palette
    elif tex.format == 2:
        for i in range(tex.height):
            for j in range(tex.width):
                x = i * tex.width + j
                index = (tex.data[x // 4] >> ((x % 4) << 1)) & 3
                if index < len(palette):
                    pixels[j, i] = palette[index]
                else:
                    common.logWarning("Index", index, "is out of range", len(palette))
    # 16-color Palette
    elif tex.format == 3:
        for i in range(tex.height):
            for j in range(tex.width):
                x = i * tex.width + j
                index = (tex.data[x // 2] >> ((x % 2) << 2)) & 0x0f
                if index < len(palette):
                    pixels[j, i] = palette[index]
                else:
                    common.logWarning("Index", index, "is out of range", len(palette))
    # 256-color Palette
    elif tex.format == 4:
        for i in range(tex.height):
            for j in range(tex.width):
                x = i * tex.width + j
                index = tex.data[x]
                if index < len(palette):
                    pixels[j, i] = palette[index]
                else:
                    common.logWarning("Index", index, "is out of range", len(palette))
    # 4x4-Texel Compressed Texture
    elif tex.format == 5:
        w = tex.width // 4
        h = tex.height // 4
        for y in range(h):
            for x in range(w):
                index = y * w + x
                t = tex.data[index]
                d = tex.spdata[index]
                addr = d & 0x3fff
                pali = addr << 1
                mode = (d >> 14) & 3
                for r in range(4):
                    for c in range(4):
                        texel = (t >> ((r * 4 + c) * 2)) & 3
                        i = y * 4 + r
                        j = x * 4 + c
                        try:
                            if mode == 0:
                                if texel == 3:
                                    pixels[j, i] = (0xff, 0xff, 0xff, 0)
                                else:
                                    pixels[j, i] = palette[pali + texel]
                            elif mode == 2:
                                pixels[j, i] = palette[pali + texel]
                            elif mode == 1:
                                if texel == 0 or texel == 1:
                                    pixels[j, i] = palette[pali + texel]
                                elif texel == 2:
                                    pixels[j, i] = common.sumColors(palette[pali], palette[pali + 1])
                                elif texel == 3:
                                    pixels[j, i] = (0xff, 0xff, 0xff, 0)
                            elif mode == 3:
                                if texel == 0 or texel == 1:
                                    pixels[j, i] = palette[pali + texel]
                                elif texel == 2:
                                    pixels[j, i] = common.sumColors(palette[pali], palette[pali + 1], 5, 3, 8)
                                elif texel == 3:
                                    pixels[j, i] = common.sumColors(palette[pali], palette[pali + 1], 3, 5, 8)
                        except IndexError:
                            pixels[j, i] = (0x00, 0x00, 0x00, 0xff)
    # A5I3 Translucent Texture (5bit Alpha, 3bit Color Index)
    elif tex.format == 6:
        for i in range(tex.height):
            for j in range(tex.width):
                x = i * tex.width + j
                index = tex.data[x] & 0x7
                alpha = int((tex.data[x] >> 3) * 8)
                if index < len(palette):
                    pixels[j, i] = (palette[index][0], palette[index][1], palette[index][2], alpha)
                else:
                    common.logWarning("Index", index, "is out of range", len(palette))
    # Direct Color Texture
    elif tex.format == 7:
        for i in range(tex.height):
            for j in range(tex.width):
                x = i * tex.width + j
                p = tex.data[x * 2] + (tex.data[x * 2 + 1] << 8)
                pixels[j, i] = (((p >> 0) & 0x1f) << 3, ((p >> 5) & 0x1f) << 3, ((p >> 10) & 0x1f) << 3, 0xff if (p & 0x8000) else 0)
    # Draw palette
    if tex.format != 7:
        pixels = common.drawPalette(pixels, palette, tex.width)
    img.save(file, "PNG")


def writeNSBMD(file: str, nsbmd: NSBMD, texi: int, infile: str, fixtransp: bool = False, checkalpha: bool = False, zerotransp: bool = True, backwards: bool = False) -> None:
    """Write a png image back into a single NSBMD texture.

    The 4x4-texel (5) and direct color (7) formats are not supported.

    Args:
        file: Path of the model file to update.
        nsbmd: Structure returned by :func:`readNSBMD`.
        texi: Index of the texture to write.
        infile: Path of the png file to pack.
        fixtransp: Whether to skip the first palette color when matching.
        checkalpha: Whether the alpha channel counts when matching colors.
        zerotransp: Whether fully transparent colors match index 0.
        backwards: Whether to search the palette backwards.
    """
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    img = Image.open(infile)
    img = img.convert("RGBA")
    pixels = img.load()
    tex = nsbmd.textures[texi]
    with common.Stream(file, "r+b") as f:
        # Read palette
        if tex.format != 7:
            palette = nsbmd.palettes[texi]
            paldata = palette.data
        # Write new texture data
        f.seek(tex.offset)
        # A3I5 Translucent Texture (3bit Alpha, 5bit Color Index)
        if tex.format == 1:
            for i in range(tex.height):
                for j in range(tex.width):
                    index = common.getPaletteIndex(paldata, pixels[j, i], fixtransp=fixtransp, checkalpha=checkalpha, zerotransp=zerotransp, backwards=backwards)
                    alpha = (pixels[j, i][3] * 8) // 256
                    f.writeByte(index | (alpha << 5))
        # 4-color Palette
        elif tex.format == 2:
            for i in range(tex.height):
                for j in range(0, tex.width, 4):
                    index1 = common.getPaletteIndex(paldata, pixels[j, i], fixtransp=fixtransp, checkalpha=checkalpha, zerotransp=zerotransp, backwards=backwards)
                    index2 = common.getPaletteIndex(paldata, pixels[j + 1, i], fixtransp=fixtransp, checkalpha=checkalpha, zerotransp=zerotransp, backwards=backwards)
                    index3 = common.getPaletteIndex(paldata, pixels[j + 2, i], fixtransp=fixtransp, checkalpha=checkalpha, zerotransp=zerotransp, backwards=backwards)
                    index4 = common.getPaletteIndex(paldata, pixels[j + 3, i], fixtransp=fixtransp, checkalpha=checkalpha, zerotransp=zerotransp, backwards=backwards)
                    f.writeByte((index4 << 6) | (index3 << 4) | (index2 << 2) | index1)
        # 16/256-color Palette
        elif tex.format == 3 or tex.format == 4:
            for i in range(tex.height):
                for j in range(0, tex.width, 2):
                    index1 = common.getPaletteIndex(paldata, pixels[j, i], fixtransp=fixtransp, checkalpha=checkalpha, zerotransp=zerotransp, backwards=backwards)
                    index2 = common.getPaletteIndex(paldata, pixels[j + 1, i], fixtransp=fixtransp, checkalpha=checkalpha, zerotransp=zerotransp, backwards=backwards)
                    writeNCGRData(f, 4 if tex.format == 3 else 8, index1, index2)
        # 4x4-Texel Compressed Texture
        elif tex.format == 5:
            common.logError("Texture format 5 not implemented")
        # A5I3 Translucent Texture (5bit Alpha, 3bit Color Index)
        elif tex.format == 6:
            for i in range(tex.height):
                for j in range(tex.width):
                    index = common.getPaletteIndex(paldata, pixels[j, i], fixtransp=fixtransp, checkalpha=checkalpha, zerotransp=zerotransp, backwards=backwards)
                    alpha = (pixels[j, i][3] * 32) // 256
                    f.writeByte(index | (alpha << 3))
        # Direct Color Texture
        elif tex.format == 7:
            common.logError("Texture format 7 not implemented")


def readManualCells(manualcells: list) -> NCER:
    """Build an NCER structure from a manual cell description.

    Used for images that have cell data hardcoded in the game instead of
    an NCER file.

    Args:
        manualcells: List of bank dictionaries, each holding a "cells"
            list of {"width", "height", "x", "y"} dictionaries, and
            optional "pal" and "repeat" values.

    Returns:
        The built cell structure.
    """
    ncer = NCER()
    ncer.banknum = 0
    ncer.tbank = ncer.bankoffset = ncer.blocksize = ncer.partitionoffset = 0
    curroff = 0
    for manualbank in manualcells:
        repeat = int(manualbank["repeat"]) if "repeat" in manualbank else 1
        for i in range(repeat):
            bank = Bank()
            ncer.banks.append(bank)
            ncer.banknum += 1
    i = 0
    banki = 0
    while i < ncer.banknum:
        manualbank = manualcells[banki]
        repeat = int(manualbank["repeat"]) if "repeat" in manualbank else 1
        for r in range(repeat):
            bank = ncer.banks[i]
            bank.cellnum = len(manualbank["cells"])
            bank.layernum = 1
            bank.partitionoffset = bank.width = bank.height = 0
            for j in range(len(manualbank["cells"])):
                manualcell = manualbank["cells"][j]
                cell = Cell()
                cell.objoffset = cell.layer = cell.objmode = cell.priority = 0
                cell.mosaic = cell.depth = cell.xflip = cell.yflip = cell.rsflag = False
                cell.width = manualcell["width"]
                cell.height = manualcell["height"]
                cell.pal = manualbank["pal"] if "pal" in manualbank else 0
                cell.x = manualcell["x"] if "x" in manualcell else 0
                cell.y = manualcell["y"] if "y" in manualcell else 0
                if cell.x + cell.width > bank.width:
                    bank.width = cell.x + cell.width
                if cell.y + cell.height > bank.height:
                    bank.height = cell.y + cell.height
                cell.numcell = j
                cell.tileoffset = curroff
                curroff += ((cell.width * cell.height) // (8 * 8))
                bank.cells.append(cell)
            common.logDebug(vars(bank))
            for cell in bank.cells:
                common.logDebug(vars(cell))
            i += 1
        banki += 1
    return ncer


def readNitroGraphicNBFC(palettefile: str, tilefile: str, mapfile: str, lineal: bool = False, bpp: int = 0):
    """Read a raw NBFP/NBFC/NBFS graphic.

    Args:
        palettefile: Path of the NBFP palette file.
        tilefile: Path of the NBFC tile file.
        mapfile: Path of the NBFS map file, optional.
        lineal: Whether the tiles are stored in lineal order.
        bpp: Bits per pixel, or 0 to guess it from the palette size.

    Returns:
        A (palettes, nbfc, nbfs) tuple, with None for the files that
        weren't found.
    """
    if not os.path.isfile(palettefile):
        common.logError("Palette", palettefile, "not found")
        return [], None, None
    palettes = readNBFP(palettefile, bpp)
    # Read tiles
    nbfc = readNBFC(tilefile, palettes[0], lineal, bpp)
    # Read maps
    nbfs = None
    if os.path.isfile(mapfile):
        nbfs = readNBFS(mapfile)
        nbfc.width = nbfs.width
        nbfc.height = nbfs.height
    return palettes, nbfc, nbfs


def readNitroGraphicNTFT(palettefile: str, tilefile: str, lineal: bool = True):
    """Read a raw NTFP/NTFT graphic.

    Args:
        palettefile: Path of the NTFP palette file.
        tilefile: Path of the NTFT tile file.
        lineal: Whether the tiles are stored in lineal order.

    Returns:
        A (palettes, ntft) tuple, or ([], None) if the palette is missing.
    """
    if not os.path.isfile(palettefile):
        common.logError("Palette", palettefile, "not found")
        return [], None
    palettes = readNBFP(palettefile)
    # Read tiles
    ntft = readNBFC(tilefile, palettes[0], lineal)
    return palettes, ntft


def readNBFP(ntfpfile: str, bpp: int = 8) -> dict:
    """Read the palettes of a raw NBFP or NTFP file.

    Args:
        ntfpfile: Path of the palette file.
        bpp: Bits per pixel of the image the palette is for.

    Returns:
        A dictionary of palette index -> list of RGBA tuples.
    """
    indexedpalettes = {}
    palettes = []
    size = os.path.getsize(ntfpfile)
    with common.Stream(ntfpfile, "rb") as f:
        pallen = 0x200
        if size < pallen:
            pallen = size
        if bpp == 4:
            pallen = 32
        colornum = pallen // 2
        for i in range(size // pallen):
            palette = []
            for j in range(colornum):
                palette.append(common.readPalette(f.readUShort()))
            palettes.append(palette)
        indexedpalettes = {i: palettes[i] for i in range(0, len(palettes))}
    common.logDebug("Loaded", len(indexedpalettes), "palettes")
    return indexedpalettes


def readNBFC(ntftfile: str, palette: list, lineal: bool, bpp: int = 0) -> NCGR:
    """Read the tiles of a raw NBFC or NTFT file.

    The image size is guessed from the data length, assuming a square
    image when possible.

    Args:
        ntftfile: Path of the tile file.
        palette: Palette of the image, used to guess the bpp.
        lineal: Whether the tiles are stored in lineal order.
        bpp: Bits per pixel, or 0 to guess it from the palette size.

    Returns:
        The parsed tile structure.
    """
    nbfc = NCGR()
    if bpp == 0:
        nbfc.bpp = 4 if len(palette) <= 16 else 8
    else:
        nbfc.bpp = bpp
    nbfc.width = 0x0100
    nbfc.height = 0x00C0
    nbfc.lineal = lineal
    with common.Stream(ntftfile, "rb") as f:
        tiledata = f.read()
    tilelen = len(tiledata)
    for i in range(tilelen // (8 * nbfc.bpp)):
        singletile = []
        for j in range(nbfc.tilesize * nbfc.tilesize):
            x = i * (nbfc.tilesize * nbfc.tilesize) + j
            if nbfc.bpp == 4:
                index = (tiledata[x // 2] >> ((x % 2) << 2)) & 0x0f
            else:
                index = tiledata[x]
            singletile.append(index)
        nbfc.tiles.append(singletile)
    numpix = tilelen * 8 / nbfc.bpp
    root = int(math.sqrt(numpix))
    if math.pow(root, 2) == numpix:
        nbfc.width = nbfc.height = root
        common.logDebug("Assuming square size", nbfc.width)
    else:
        nbfc.width = numpix if numpix < 0x100 else 0x0100
        nbfc.height = int(numpix // nbfc.width)
        common.logDebug("Assuming size", nbfc.width, nbfc.height)
    common.logDebug("Loaded", len(nbfc.tiles), "tiles")
    return nbfc


def readNBFS(nscrfile: str) -> NSCR:
    """Read the map entries of a raw NBFS file.

    The map size is guessed from the data length, assuming a square image
    when possible.

    Args:
        nscrfile: Path of the map file.

    Returns:
        The parsed map structure.
    """
    nbfs = NSCR()
    with common.Stream(nscrfile, "rb") as f:
        mapdata = f.read()
    for i in range(0, len(mapdata), 2):
        data = struct.unpack("<h", mapdata[i:i+2])[0]
        map = readMapData(data)
        nbfs.maps.append(map)
    maplen = len(nbfs.maps)
    root = int(math.sqrt(maplen))
    if math.pow(root, 2) == maplen:
        nbfs.width = nbfs.height = root * 8
        common.logDebug("Assuming square size", nbfs.width)
    else:
        nbfs.width = 0x100 if (maplen * 8 >= 0x100) else (maplen * 8)
        nbfs.height = (maplen // (nbfs.width // 8)) * 8
        common.logDebug("Assuming size", nbfs.width, nbfs.height)
    common.logDebug("Loaded", len(nbfs.maps), "maps", nbfs.width, nbfs.height)
    return nbfs
