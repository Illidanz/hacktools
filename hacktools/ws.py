import os
from PIL import Image
from hacktools import common


def extractRom(romfile, extractfolder, workfolder=""):
    common.logMessage("Extracting ROM", romfile, "...")
    common.makeFolder(extractfolder)
    filesize = os.path.getsize(romfile)
    banknum = filesize // 0x10000
    common.logMessage("Extracting", banknum, "banks ...")
    with common.Stream(romfile, "rb") as f:
        for i in range(banknum):
            bankname = "bank_"
            if i < 0x10:
                bankname += "0"
            bankname += format(i, 'x')
            with common.Stream(extractfolder + bankname + ".bin", "wb") as fout:
                fout.write(f.read(0x10000))
    if workfolder != "":
        common.copyFolder(extractfolder, workfolder)
    common.logMessage("Done!")


def repackRom(romfile, rompatch, workfolder, patchfile=""):
    common.logMessage("Repacking ROM", rompatch, "...")
    filesize = os.path.getsize(romfile)
    banknum = filesize // 0x10000
    common.logMessage("Extracting", banknum, "banks ...")
    with common.Stream(rompatch, "wb") as fout:
        for i in range(banknum):
            bankname = "bank_"
            if i < 0x10:
                bankname += "0"
            bankname += format(i, 'x')
            with common.Stream(workfolder + bankname + ".bin", "rb") as f:
                fout.write(f.read())
    common.logMessage("Done!")
    # Create xdelta patch
    if patchfile != "":
        common.xdeltaPatch(patchfile, romfile, rompatch)


def readTile(f, pixels, x, y, palette):
    for y2 in range(8):
        b1 = f.readByte()
        b2 = f.readByte()
        for x2 in range(8):
            hi = (b2 >> (7 - x2)) & 1
            lo = (b1 >> (7 - x2)) & 1
            pixels[x + x2, y + y2] = palette[(hi << 1) | lo]


def writeTile(f, pixels, x, y, palette):
    for y2 in range(8):
        b1 = b2 = 0
        for x2 in range(8):
            index = common.getPaletteIndex(palette, pixels[x + x2, y + y2], zerotransp=False)
            lo = index & 1
            hi = (index >> 1) & 1
            b2 |= (hi << (7 - x2))
            b1 |= (lo << (7 - x2))
        f.writeByte(b1)
        f.writeByte(b2)


bwpalette = [(0x0, 0x0, 0x0, 0xff), (0x50, 0x50, 0x50, 0xff), (0xb0, 0xb0, 0xb0, 0xff), (0xf0, 0xf0, 0xf0, 0xff)]


def extractImage(f, outfile, width, height, palette=bwpalette):
    # Example image used is 8x8 tiles, arranged as
    # 1 3 5 8
    # 2 4 6 7
    img = Image.new("RGB", (width, height), palette[0])
    pixels = img.load()
    for y in range(height // 16):
        for x in range(width // 16):
            readTile(f, pixels, x * 16, y * 16, palette)
            readTile(f, pixels, x * 16, y * 16 + 8, palette)
            readTile(f, pixels, x * 16 + 8, y * 16, palette)
            readTile(f, pixels, x * 16 + 8, y * 16 + 8, palette)
    img.save(outfile, "PNG")


def repackImage(f, infile, width, height, palette=bwpalette):
    img = Image.open(infile)
    img = img.convert("RGBA")
    pixels = img.load()
    for y in range(height // 16):
        for x in range(width // 16):
            writeTile(f, pixels, x * 16, y * 16, palette)
            writeTile(f, pixels, x * 16, y * 16 + 8, palette)
            writeTile(f, pixels, x * 16 + 8, y * 16, palette)
            writeTile(f, pixels, x * 16 + 8, y * 16 + 8, palette)
