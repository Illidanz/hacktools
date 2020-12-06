import os
from PIL import Image, ImageDraw
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
    common.logMessage("Repacking", banknum, "banks ...")
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


def readTile(f, pixels, x, y, palette, hflip=False, vflip=False):
    for y2 in range(8):
        b1 = f.readByte()
        b2 = f.readByte()
        for x2 in range(8):
            hi = (b2 >> (7 - x2)) & 1
            lo = (b1 >> (7 - x2)) & 1
            posx = x2 if not hflip else 7 - x2
            posy = y2 if not vflip else 7 - y2
            index = ((hi << 1) | lo)
            pixels[x + posx, y + posy] = palette[index]


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


bwpalette = [[(0x0, 0x0, 0x0, 0xff), (0x50, 0x50, 0x50, 0xff), (0xb0, 0xb0, 0xb0, 0xff), (0xf0, 0xf0, 0xf0, 0xff)]]


def extractImage(f, outfile, width, height, palette=bwpalette[0]):
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


def repackImage(f, infile, width, height, palette=bwpalette[0]):
    img = Image.open(infile)
    img = img.convert("RGBA")
    pixels = img.load()
    for y in range(height // 16):
        for x in range(width // 16):
            writeTile(f, pixels, x * 16, y * 16, palette)
            writeTile(f, pixels, x * 16, y * 16 + 8, palette)
            writeTile(f, pixels, x * 16 + 8, y * 16, palette)
            writeTile(f, pixels, x * 16 + 8, y * 16 + 8, palette)


class TileMap:
    name = ""
    offset = 0
    width = 0
    height = 0
    map = []


class TileData:
    tile = 0
    data = 0
    pal = 0
    bank = 0
    hflip = False
    vflip = False


def readMappedImage(f, outfile, tilestart, mapstart, num=1):
    f.seek(mapstart)
    maps = []
    for j in range(num):
        map = TileMap()
        if num > 1:
            map.name = outfile.replace(".png", "_" + str(j + 1).zfill(2) + ".png")
        else:
            map.name = outfile
        map.offset = f.tell()
        map.width = f.readByte()
        map.height = f.readByte()
        common.logDebug(" ", mapstart, vars(map))
        map.map = []
        for i in range(map.width * map.height):
            tilemap = TileMap()
            tilemap.data = f.readUShort()
            tilemap.tile = tilemap.data & 0x1ff
            tilemap.pal = (tilemap.data >> 9) & 0xf
            tilemap.bank = (tilemap.data >> 13) & 1
            if tilemap.bank != 0:
                common.logError("Bank is not 0")
            tilemap.hflip = ((tilemap.data >> 14) & 1) == 1
            tilemap.vflip = ((tilemap.data >> 15) & 1) == 1
            map.map.append(tilemap)
        maps.append(map)
    common.logDebug("Map data ended at", f.tell())
    return maps


def extractMappedImage(f, outfile, tilestart, mapstart, num=1, printnum=False):
    common.logDebug("Extracting", outfile)
    if printnum:
        from PIL import ImageFont
        fnt = ImageFont.truetype("m3x6.ttf", 16)
    maps = readMappedImage(f, outfile, tilestart, mapstart, num)
    for i in range(num):
        mapdata = maps[i]
        img = Image.new("RGB", (mapdata.width * 8, mapdata.height * 8), (0x0, 0x0, 0x0))
        pixels = img.load()
        x = y = 0
        for map in mapdata.map:
            f.seek(tilestart + map.tile * 16)
            readTile(f, pixels, x * 8, y * 8, bwpalette[map.pal] if map.pal in bwpalette else bwpalette[0], map.hflip, map.vflip)
            if printnum:
                d = ImageDraw.Draw(img)
                d.text((x * 8, y * 8 - 5), str(map.tile), font=fnt, spacing=1, fill='red')
            x += 1
            if x == mapdata.width:
                y += 1
                x = 0
        img.save(mapdata.name, "PNG")
    common.logDebug("Tile data ended at", f.tell())
