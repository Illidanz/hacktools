"""Support for Wii ISOs, archives, textures and fonts.

ISO, ARC, TPL and BREFT files are handled with the wit, wszst and wimgt
tools from Wiimms ISO/SZS Tools, which need to be installed separately.
BRFNT fonts are converted by calling the brfnt2tpl executable externally.
"""
import codecs
import math
import os
from hacktools import common


# Generic extract/repack functions
def extractARC(infolder: str, outfolder: str) -> None:
    """Extract all the .arc files in a folder with wszst.

    Args:
        infolder: Path of the folder to scan.
        outfolder: Path of the folder to extract to.
    """
    common.makeFolder(outfolder)
    common.logMessage("Extracting ARC to", outfolder, "...")
    files = common.getFiles(infolder, ".arc")
    for file in common.showProgress(files):
        common.logDebug("Processing", file, "...")
        common.execute("wszst EXTRACT " + infolder + file + " -D " + outfolder + file, False)
    common.logMessage("Done! Extracted", len(files), "files")


def extractTPL(infolder: str, outfolder: str, splitName: bool = True, flatten: bool = False) -> None:
    """Extract all the .tpl files in a folder to png with wimgt.

    Args:
        infolder: Path of the folder to scan.
        outfolder: Path of the folder to extract to.
        splitName: Whether to name the output subfolder after the first
            component of each file path, instead of mirroring the whole path.
        flatten: Whether to extract the files inside a .arc folder directly
            in it, instead of mirroring its inner folder structure.
    """
    common.makeFolder(outfolder)
    common.logMessage("Extracting TPL to", outfolder, "...")
    files = common.getFiles(infolder, ".tpl")
    for file in common.showProgress(files):
        common.logDebug("Processing", file, "...")
        if splitName:
            filename = file.split("/")[0] + "/" + os.path.basename(file).replace(".tpl", ".png")
        elif flatten and ".arc/" in file:
            filename = file[:file.index(".arc/") + 4] + "/" + os.path.basename(file).replace(".tpl", ".png")
        else:
            filename = file.replace(".tpl", ".png")
        common.execute("wimgt DECODE " + infolder + file + " -D " + outfolder + filename, False)
    common.logMessage("Done! Extracted", len(files), "files")


def repackTPL(infolder: str, workfolder: str, outfolder: str) -> None:
    """Repack modified pngs into the .arc folders extracted by extractARC.

    For each png in workfolder that matches a .tpl file in infolder, the
    containing .arc folder is copied to outfolder, then the png is encoded
    over the tpl with wimgt, keeping the original image and palette formats.

    Args:
        infolder: Path of the folder extracted by :func:`extractARC`.
        workfolder: Path of the folder with the modified pngs.
        outfolder: Path of the folder the .arc folders are copied to.
    """
    common.makeFolder(outfolder)
    common.logMessage("Repacking TPL from", workfolder, "...")
    files = common.getFiles(workfolder, ".png")
    arcs = []
    repacked = 0
    for file in common.showProgress(files):
        tplfile = file.replace(".png", ".tpl")
        if not os.path.isfile(infolder + tplfile):
            # Search the .arc folder for pngs that were extracted with flatten
            if ".arc/" not in file:
                continue
            arcname = file[:file.index(".arc/") + 4]
            matches = [tpl for tpl in common.getFiles(infolder + arcname, ".tpl") if os.path.basename(tpl) == os.path.basename(tplfile)]
            if len(matches) == 0:
                common.logError("Work file", file, "does not match any file in", arcname)
                continue
            tplfile = arcname + matches[0]
        common.logDebug("Processing", file, "...")
        if ".arc/" in tplfile:
            arcname = tplfile[:tplfile.index(".arc/") + 4]
            if arcname not in arcs:
                common.copyFolder(infolder + arcname, outfolder + arcname)
                arcs.append(arcname)
        transform = getTPLTransform(infolder + tplfile)
        common.execute("wimgt ENCODE " + workfolder + file + " -D " + outfolder + tplfile + " --n-mipmaps 0 --transform " + transform + " --overwrite", False)
        repacked += 1
    common.logMessage("Done! Repacked", repacked, "files in", len(arcs), "ARC folders")


def repackARC(workfolder: str, outfolder: str) -> None:
    """Repack all the .arc folders in a folder with wszst.

    Args:
        workfolder: Path of the folder to scan.
        outfolder: Path of the folder the .arc files are created in.
    """
    common.logMessage("Repacking ARC to", outfolder, "...")
    arcs = []
    for (root, dirs, files) in os.walk(workfolder):
        for dir in sorted(dirs):
            if dir.endswith(".arc"):
                arcs.append(os.path.join(root, dir).replace("\\", "/").replace(workfolder, ""))
    for arc in common.showProgress(arcs):
        common.logDebug("Processing", arc, "...")
        common.execute("wszst CREATE " + workfolder + arc + " -D " + outfolder + arc + " --overwrite", False)
    common.logMessage("Done! Repacked", len(arcs), "files")


def extractBREFT(infolder: str, tempfolder: str, outfolder: str) -> None:
    """Extract all the .breft files in a folder to png.

    The files are first extracted with wszst to the temp folder, then every
    texture found in them is decoded with wimgt.

    Args:
        infolder: Path of the folder to scan.
        tempfolder: Path of the folder holding the extracted archives.
        outfolder: Path of the folder the textures are decoded to.
    """
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


def extractBRTEX(infolder: str, tempfolder: str, outfolder: str) -> None:
    """Extract all the .brtex files in a folder to png.

    The files are extracted with wszst to the temp folder, alongside the
    paired .brplt files when they exist, then every texture is converted
    to a temporary TPL and decoded with wimgt.

    Args:
        infolder: Path of the folder to scan.
        tempfolder: Path of the folder holding the extracted archives.
        outfolder: Path of the folder the textures are decoded to.
    """
    common.makeFolder(tempfolder)
    common.makeFolders(outfolder)
    common.logMessage("Extracting BRTEX to", outfolder, "...")
    files = common.getFiles(infolder, ".brtex")
    extracted = 0
    for file in common.showProgress(files):
        common.logDebug("Processing", file, "...")
        common.execute("wszst EXTRACT " + infolder + file + " -D " + tempfolder + file, False)
        pltfile = file.replace(".brtex", ".brplt")
        if os.path.isfile(infolder + pltfile):
            common.execute("wszst EXTRACT " + infolder + pltfile + " -D " + tempfolder + pltfile, False)
        texfolder = tempfolder + file + "/Textures(NW4R)/"
        if not os.path.isdir(texfolder):
            continue
        for texname in sorted(os.listdir(texfolder)):
            palfile = tempfolder + pltfile + "/Palettes(NW4R)/" + texname
            if not os.path.isfile(palfile):
                palfile = None
            tplfile = tempfolder + file + "/" + texname + ".tpl"
            texToTPL(texfolder + texname, tplfile, palfile)
            common.execute("wimgt DECODE " + tplfile + " -D " + outfolder + file + "/" + texname + ".png --overwrite", False)
            os.remove(tplfile)
            extracted += 1
    common.logMessage("Done! Extracted", extracted, "textures")


def repackBRTEX(infolder: str, tempfolder: str, workfolder: str, outfolder: str) -> None:
    """Repack modified pngs into .brtex and .brplt files.

    For each folder in workfolder that matches a .brtex file in infolder, the
    file is extracted with wszst to the temp folder, alongside the paired
    .brplt file when it exists. Every png is encoded to a temporary TPL with
    wimgt, keeping the original image and palette formats, and the data is
    copied back into the TEX0 and PLT0 textures. The files are then rebuilt
    with wszst into outfolder.

    Args:
        infolder: Path of the folder to scan.
        tempfolder: Path of the folder holding the extracted archives.
        workfolder: Path of the folder with the modified pngs.
        outfolder: Path of the folder the files are created in.
    """
    common.makeFolder(tempfolder)
    common.logMessage("Repacking BRTEX from", workfolder, "...")
    files = common.getFiles(infolder, ".brtex")
    repacked = 0
    textures = 0
    for file in common.showProgress(files):
        workdir = workfolder + file + "/"
        if not os.path.isdir(workdir):
            continue
        common.logDebug("Processing", file, "...")
        common.execute("wszst EXTRACT " + infolder + file + " -D " + tempfolder + file, False)
        pltfile = file.replace(".brtex", ".brplt")
        if os.path.isfile(infolder + pltfile):
            common.execute("wszst EXTRACT " + infolder + pltfile + " -D " + tempfolder + pltfile, False)
        modified = pltmodified = False
        for pngname in sorted(os.listdir(workdir)):
            if not pngname.endswith(".png"):
                continue
            texname = pngname.replace(".png", "")
            texfile = tempfolder + file + "/Textures(NW4R)/" + texname
            if not os.path.isfile(texfile):
                common.logError("Work file", pngname, "does not match any texture in", file)
                continue
            palfile = tempfolder + pltfile + "/Palettes(NW4R)/" + texname
            if not os.path.isfile(palfile):
                palfile = None
            tplfile = tempfolder + file + "/" + texname + ".tpl"
            transform = getTexTransform(texfile, palfile)
            common.execute("wimgt ENCODE " + workdir + pngname + " -D " + tplfile + " --n-mipmaps 0 --transform " + transform + " --overwrite", False)
            tplToTex(tplfile, texfile, palfile)
            os.remove(tplfile)
            textures += 1
            modified = True
            if palfile is not None:
                pltmodified = True
        if modified:
            common.execute("wszst CREATE " + tempfolder + file + " -D " + outfolder + file + " --overwrite", False)
            repacked += 1
        if pltmodified:
            common.execute("wszst CREATE " + tempfolder + pltfile + " -D " + outfolder + pltfile + " --overwrite", False)
    common.logMessage("Done!", textures, "textures repacked in", repacked, "BRTEX files")


def extractBRFNT(infile: str, outfile: str) -> None:
    """Extract a BRFNT font to png, with brfnt2tpl and wimgt.

    Args:
        infile: Path of the BRFNT file.
        outfile: Path of the output png file.
    """
    brfnt2tpl = common.bundledExecutable("brfnt2tpl.exe")
    if not os.path.isfile(brfnt2tpl):
        common.logError("brfnt2tpl not found")
        return
    common.execute(brfnt2tpl + " {file}".format(file=infile), False)
    common.execute("wimgt DECODE " + infile.replace(".brfnt", ".tpl") + " -D " + outfile, False)
    os.remove(infile.replace(".brfnt", ".tpl"))
    os.remove(infile.replace(".brfnt", ".vbfta"))


def repackBRFNT(outfile: str, workfile: str) -> None:
    """Repack a png into a BRFNT font, with brfnt2tpl.

    Args:
        outfile: Path of the BRFNT file to update.
        workfile: Path of the png file to pack.
    """
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


def extractIso(isofile: str, extractfolder: str, workfolder: str = "") -> None:
    """Extract an ISO with wit.

    Args:
        isofile: Path of the ISO file.
        extractfolder: Path of the folder to extract to.
        workfolder: Optional path of a work folder the extracted files are
            copied to.
    """
    common.logMessage("Extracting ISO", isofile, "...")
    common.makeFolder(extractfolder)
    common.execute("wit EXTRACT -o {iso} {folder}".format(iso=isofile, folder=extractfolder), False)
    if workfolder != "":
        common.copyFolder(extractfolder, workfolder)
    common.logMessage("Done!")


def repackIso(isofile: str, isopatch: str, workfolder: str, patchfile: str = "") -> None:
    """Repack an ISO with wit.

    Args:
        isofile: Path of the original ISO file, unused.
        isopatch: Path of the output ISO file.
        workfolder: Path of the folder to repack.
        patchfile: Unused.
    """
    common.logMessage("Repacking ISO", isopatch, "...")
    if os.path.isfile(isopatch):
        os.remove(isopatch)
    common.execute("wit COPY {folder} {iso}".format(folder=workfolder, iso=isopatch), False)
    common.logMessage("Done!")


# TPL files
# wimgt name, bits per pixel and block size for every GX image format
TEXFORMATS = {
    0x00: ("I4", 4, 8, 8),
    0x01: ("I8", 8, 8, 4),
    0x02: ("IA4", 8, 8, 4),
    0x03: ("IA8", 16, 4, 4),
    0x04: ("RGB565", 16, 4, 4),
    0x05: ("RGB5A3", 16, 4, 4),
    0x06: ("RGBA32", 32, 4, 4),
    0x08: ("C4", 4, 8, 8),
    0x09: ("C8", 8, 8, 4),
    0x0a: ("C14X2", 16, 4, 4),
    0x0e: ("CMPR", 4, 8, 8),
}
TEXPALFORMATS = {0x00: "PIA8", 0x01: "PRGB565", 0x02: "PRGB5A3"}


def getTexDataSize(width: int, height: int, format: int) -> int:
    """Calculate the data size of an image in the given GX format.

    Args:
        width: Width of the image.
        height: Height of the image.
        format: Format of the image data.

    Returns:
        The size of the block-aligned image data.
    """
    bpp, tilewidth, tileheight = TEXFORMATS[format][1:]
    blockwidth = math.ceil(width / tilewidth) * tilewidth
    blockheight = math.ceil(height / tileheight) * tileheight
    return blockwidth * blockheight * bpp // 8


def getTPLTransform(file: str) -> str:
    """Read the image and palette formats of a TPL file.

    Args:
        file: Path of the TPL file.

    Returns:
        The formats as a wimgt transform string, like TPL.C8.PRGB5A3.
    """
    with common.Stream(file, "rb", False) as f:
        f.seek(f.readUIntAt(8))
        imgoff = f.readUInt()
        paloff = f.readUInt()
        transform = "TPL." + TEXFORMATS[f.readUIntAt(imgoff + 4)][0]
        if paloff > 0:
            transform += "." + TEXPALFORMATS[f.readUIntAt(paloff + 4)]
    return transform


def getTexTransform(texfile: str, palfile: str | None = None) -> str:
    """Read the image and palette formats of a TEX0 texture.

    Args:
        texfile: Path of the TEX0 file.
        palfile: Optional path of the paired PLT0 file.

    Returns:
        The formats as a wimgt transform string, like TPL.C8.PRGB5A3.
    """
    with common.Stream(texfile, "rb", False) as f:
        transform = "TPL." + TEXFORMATS[f.readUIntAt(0x20)][0]
    if palfile is not None:
        with common.Stream(palfile, "rb", False) as f:
            transform += "." + TEXPALFORMATS[f.readUIntAt(0x18)]
    return transform


def texToTPL(texfile: str, tplfile: str, palfile: str | None = None) -> None:
    """Convert a TEX0 texture and its optional PLT0 palette to a TPL file.

    Args:
        texfile: Path of the TEX0 file.
        tplfile: Path of the output TPL file.
        palfile: Optional path of the paired PLT0 file.
    """
    with common.Stream(texfile, "rb", False) as f:
        dataoff = f.readUIntAt(0x10)
        f.seek(0x1c)
        width = f.readUShort()
        height = f.readUShort()
        format = f.readUInt()
        f.seek(dataoff)
        data = f.read(getTexDataSize(width, height, format))
    paldata = b""
    palformat = 0
    if palfile is not None:
        with common.Stream(palfile, "rb", False) as f:
            paldataoff = f.readUIntAt(0x10)
            palformat = f.readUIntAt(0x18)
            palcount = f.readUShortAt(0x1c)
            f.seek(paldataoff)
            paldata = f.read(palcount * 2)
    with common.Stream(tplfile, "wb", False) as f:
        f.writeUInt(0x0020af30)  # Header
        f.writeUInt(1)     # Image number
        f.writeUInt(0xc)   # Table offset
        f.writeUInt(0x14)  # Image header offset
        f.writeUInt(0x38 if len(paldata) > 0 else 0)  # Palette header offset
        f.writeUShort(height)
        f.writeUShort(width)
        f.writeUInt(format)
        f.writeUInt(0)  # Data offset, written later
        f.writeUInt(0)  # WrapS
        f.writeUInt(0)  # WrapT
        f.writeUInt(1)  # MinFilter
        f.writeUInt(1)  # MagFilter
        f.writeUInt(0)  # LODBias
        f.writeUInt(0)  # EdgeLODEnable, MinLOD, MaxLOD, Unpacked
        if len(paldata) > 0:
            f.writeUShort(len(paldata) // 2)
            f.writeUShort(0)  # Unpacked + padding
            f.writeUInt(palformat)
            f.writeUInt(0x60)  # Palette data offset
            f.writeZero(0x60 - f.tell())
            f.write(paldata)
        imgdataoff = f.tell() + (-f.tell() % 32)
        f.writeZero(imgdataoff - f.tell())
        f.write(data)
        f.writeUIntAt(0x1c, imgdataoff)


def tplToTex(tplfile: str, texfile: str, palfile: str | None = None) -> None:
    """Copy the image and palette data of a TPL back into TEX0/PLT0 files.

    The palette is padded to the original color count when possible, so the
    PLT0 file layout is unchanged.

    Args:
        tplfile: Path of the TPL file.
        texfile: Path of the TEX0 file to update.
        palfile: Optional path of the paired PLT0 file to update.
    """
    with common.Stream(tplfile, "rb", False) as f:
        f.seek(f.readUIntAt(8))
        imgoff = f.readUInt()
        paloff = f.readUInt()
        f.seek(imgoff)
        height = f.readUShort()
        width = f.readUShort()
        format = f.readUInt()
        dataoff = f.readUInt()
        f.seek(dataoff)
        data = f.read(getTexDataSize(width, height, format))
        paldata = b""
        if paloff > 0:
            f.seek(paloff)
            palcount = f.readUShort()
            paldataoff = f.readUIntAt(paloff + 8)
            f.seek(paldataoff)
            paldata = f.read(palcount * 2)
    with common.Stream(texfile, "rb+", False) as f:
        texdataoff = f.readUIntAt(0x10)
        f.seek(0x1c)
        f.writeUShort(width)
        f.writeUShort(height)
        f.seek(texdataoff)
        f.write(data)
        f.truncate()
        f.writeUIntAt(0x4, texdataoff + len(data))
    if palfile is not None and len(paldata) > 0:
        with common.Stream(palfile, "rb+", False) as f:
            paldataoff = f.readUIntAt(0x10)
            origcount = f.readUShortAt(0x1c)
            if len(paldata) // 2 < origcount:
                paldata += bytes(2 * (origcount - len(paldata) // 2))
            f.writeUShortAt(0x1c, len(paldata) // 2)
            f.seek(paldataoff)
            f.write(paldata)
            f.truncate()
            f.writeUIntAt(0x4, paldataoff + len(paldata))


class TPL:
    """Structure of a TPL texture file.

    Format reference: http://wiki.tockdom.com/wiki/TPL_(File_Format)

    Attributes:
        imgnum: Number of images in the file.
        tableoff: Offset of the image table.
        images: List of images in the file.
    """
    def __init__(self):
        self.imgnum: int = 0
        self.tableoff: int = 0
        self.images: list[TPLImage] = []


class TPLImage:
    """Structure of a single image in a TPL file.

    Attributes:
        imgoff: Offset of the image header.
        paloff: Offset of the palette header, 0 if the image has no palette.
        palformat: Format of the palette colors, only 0x02 (RGB5A3) is supported.
        paldataoff: Offset of the palette data.
        palette: Palette colors, as a list of RGBA tuples.
        width: Width of the image.
        height: Height of the image.
        format: Format of the image data, only 0x02 (IA8), 0x08 (C4) and
            0x09 (C8) are supported.
        dataoff: Offset of the image data.
        tilewidth: Width of a single tile.
        tileheight: Height of a single tile.
        blockwidth: Width rounded up to a multiple of the tile width.
        blockheight: Height rounded up to a multiple of the tile height.
    """
    def __init__(self):
        self.imgoff: int = 0
        self.paloff: int = 0
        self.palformat: int = 0x02
        self.paldataoff: int = 0
        self.palette: list = []
        self.width: int = 0
        self.height: int = 0
        self.format: int = 0x09
        self.dataoff: int = 0
        self.tilewidth: int = 8
        self.tileheight: int = 8
        self.blockwidth: int = 0
        self.blockheight: int = 0


def readTPL(file: str) -> TPL:
    """Read the image table and palettes of a TPL file.

    Args:
        file: Path of the TPL file.

    Returns:
        The parsed TPL structure.
    """
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


def writeTPL(file: str, tpl: TPL, infile: str) -> None:
    """Write png images back into a TPL file.

    The first image is read from infile, the following ones from .mmN.png
    files next to it, with N being the image number. If an image size
    changed, the new size is written in the header.

    Args:
        file: Path of the TPL file to update.
        tpl: TPL structure returned by :func:`readTPL`.
        infile: Path of the png file to pack.
    """
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
def getFontGlyphs(file: str, encoding: str = "shift_jis") -> dict:
    """Read the glyph information of a BRFNT font.

    The glyph widths are read from the HDWC section, and matched with the
    character codes from the PAMC sections.

    Args:
        file: Path of the font file.
        encoding: Encoding of the character codes.

    Returns:
        A dictionary of character -> FontGlyph.
    """
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
                    c = common.codeToChar(firstchar + i, encoding, little=False)
                    glyphs[c] = common.FontGlyph(hdwc[firstcode + i][0], hdwc[firstcode + i][1], hdwc[firstcode + i][2], c, firstchar + i, firstcode + i)
            elif sectiontype == 1:
                for i in range(lastchar - firstchar + 1):
                    charcode = f.readUShort()
                    if charcode == 0xffff or charcode >= len(hdwc):
                        continue
                    c = common.codeToChar(firstchar + i, encoding, little=False)
                    glyphs[c] = common.FontGlyph(hdwc[charcode][0], hdwc[charcode][1], hdwc[charcode][2], c, firstchar + i, charcode)
            else:
                common.logWarning("Unknown section type", sectiontype)
    return glyphs


def extractFontData(file: str, outfile: str) -> None:
    """Extract the glyph data of a font to a text file.

    Each line has the char=start,width,length format, with "=" characters
    written as <3D>.

    Args:
        file: Path of the font file.
        outfile: Path of the output text file.
    """
    common.logMessage("Extracting font data to", outfile, "...")
    glyphs = getFontGlyphs(file)
    with codecs.open(outfile, "w", "utf-8") as f:
        for glyph in glyphs.values():
            char = glyph.char if glyph.char != "=" else "<3D>"
            f.write(char + "=" + str(glyph.start) + "," + str(glyph.width) + "," + str(glyph.length) + "\n")
    common.logMessage("Done!")


def repackFontData(infile: str, outfile: str, datafile: str) -> None:
    """Repack the glyph data of a font from a text file.

    Args:
        infile: Path of the original font file.
        outfile: Path of the output font file.
        datafile: Path of the text file, in the format written by
            :func:`extractFontData`.
    """
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
