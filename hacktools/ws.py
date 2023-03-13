import os
import struct
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
            bankname += format(i, "x")
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
            bankname += format(i, "x")
            with common.Stream(workfolder + bankname + ".bin", "rb") as f:
                fout.write(f.read())
    # Calculate and write the checksum
    with common.Stream(rompatch, "rb+") as fout:
        checksum = sum(fout.read(filesize - 2))
        fout.writeUShort(checksum & 0xffff)
    common.logMessage("Done!")
    # Create patch
    if patchfile != "":
        common.xdeltaPatch(patchfile, romfile, rompatch)
        common.ipsPatch(patchfile.replace(".xdelta", ".ips"), romfile, rompatch)


# rom0 = 0xc2, rom1 = 0xc3, rom2 = 0xc0, sram = 0xc1
def memoryToBank(segment, address, rom0, rom1, rom2, sram=0, nbanks=64, justbank=False):
    j = (rom2 << 4) & 0xf0
    rommap = [0] * 0x100
    for i in range(nbanks):
        rommap[0x100 - nbanks + i] = i
    pages = []
    for i in range(0xf + 1):
        pages.append(rommap[i | j])
    pages[0] = rommap[0xff]
    pages[1] = rommap[sram]
    pages[2] = rommap[rom0]
    pages[3] = rommap[rom1]
    ptr = (segment << 4) + address
    ptrbank = (ptr >> 16) & 0xf
    if justbank:
        return pages[ptrbank]
    return (pages[ptrbank] * 0x10000) + ptr & 0xffff


def readPointer(f, bankoff=0):
    address = f.readUShort()
    segment = f.readUShort()
    return (segment << 4) + address - bankoff


def readTile(f, pixels, x, y, palette, hflip=False, vflip=False, bpp=2):
    for y2 in range(8):
        if bpp == 2:
            b1 = f.readByte()
            b2 = f.readByte()
            for x2 in range(8):
                hi = (b2 >> (7 - x2)) & 1
                lo = (b1 >> (7 - x2)) & 1
                posx = x2 if not hflip else 7 - x2
                posy = y2 if not vflip else 7 - y2
                index = ((hi << 1) | lo)
                pixels[x + posx, y + posy] = palette[index]
        else:
            b1 = f.readByte()
            b2 = f.readByte()
            b3 = f.readByte()
            b4 = f.readByte()
            for x2 in range(8):
                hi2 = (b4 >> (7 - x2)) & 1
                hi = (b3 >> (7 - x2)) & 1
                lo2 = (b2 >> (7 - x2)) & 1
                lo = (b1 >> (7 - x2)) & 1
                posx = x2 if not hflip else 7 - x2
                posy = y2 if not vflip else 7 - y2
                index = ((hi2 << 3) | (hi << 2) | (lo2 << 1) | lo)
                pixels[x + posx, y + posy] = palette[index]


def writeTile(f, pixels, x, y, palette, bpp=2):
    for y2 in range(8):
        if bpp == 2:
            b1 = b2 = 0
            for x2 in range(8):
                index = common.getPaletteIndex(palette, pixels[x + x2, y + y2], zerotransp=False)
                lo = index & 1
                hi = (index >> 1) & 1
                b2 |= (hi << (7 - x2))
                b1 |= (lo << (7 - x2))
            f.writeByte(b1)
            f.writeByte(b2)
        else:
            b1 = b2 = b3 = b4 = 0
            for x2 in range(8):
                index = common.getPaletteIndex(palette, pixels[x + x2, y + y2], zerotransp=False)
                lo = index & 1
                lo2 = (index >> 1) & 1
                hi = (index >> 2) & 1
                hi2 = (index >> 3) & 1
                b4 |= (hi2 << (7 - x2))
                b3 |= (hi << (7 - x2))
                b2 |= (lo2 << (7 - x2))
                b1 |= (lo << (7 - x2))
            f.writeByte(b1)
            f.writeByte(b2)
            f.writeByte(b3)
            f.writeByte(b4)


bwpalette = [[(0x0, 0x0, 0x0, 0xff), (0x50, 0x50, 0x50, 0xff), (0xb0, 0xb0, 0xb0, 0xff), (0xf0, 0xf0, 0xf0, 0xff)]]
colpalette = [[(0x0,  0x0,  0x0,  0xff), (0x1f, 0x1f, 0x1f, 0xff), (0x2f, 0x2f, 0x2f, 0xff), (0x3f, 0x3f, 0x3f, 0xff),
               (0x4f, 0x4f, 0x4f, 0xff), (0x5f, 0x5f, 0x5f, 0xff), (0x6f, 0x6f, 0x6f, 0xff), (0x7f, 0x7f, 0x7f, 0xff),
               (0x8f, 0x8f, 0x8f, 0xff), (0x9f, 0x9f, 0x9f, 0xff), (0xaf, 0xaf, 0xaf, 0xff), (0xbf, 0xbf, 0xbf, 0xff),
               (0xcf, 0xcf, 0xcf, 0xff), (0xdf, 0xdf, 0xdf, 0xff), (0xef, 0xef, 0xef, 0xff), (0xff, 0xff, 0xff, 0xff)]]


def extractImage(f, outfile, width, height, palette=None, bpp=2):
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    if palette is None:
        palette = bwpalette[0] if bpp == 2 else colpalette[0]
    img = Image.new("RGB", (width, height), palette[0])
    pixels = img.load()
    for y in range(height // 8):
        for x in range(width // 8):
            try:
                readTile(f, pixels, x * 8, y * 8, palette, bpp=bpp)
            except struct.error:
                pass
    img.save(outfile, "PNG")


def repackImage(f, infile, width, height, palette=None, bpp=2):
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    if palette is None:
        palette = bwpalette[0] if bpp == 2 else colpalette[0]
    img = Image.open(infile)
    img = img.convert("RGBA")
    pixels = img.load()
    for y in range(height // 8):
        for x in range(width // 8):
            writeTile(f, pixels, x * 8, y * 8, palette, bpp=bpp)


def extractTiledImage(f, outfile, width, height, palette=None, bpp=2):
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    if palette is None:
        palette = bwpalette[0] if bpp == 2 else colpalette[0]
    # Example image used is 8x8 tiles, arranged as
    # 1 3 5 7
    # 2 4 6 8
    img = Image.new("RGB", (width, height), palette[0])
    pixels = img.load()
    for y in range(height // 16):
        for x in range(width // 16):
            try:
                readTile(f, pixels, x * 16, y * 16, palette, bpp=bpp)
                readTile(f, pixels, x * 16, y * 16 + 8, palette, bpp=bpp)
                readTile(f, pixels, x * 16 + 8, y * 16, palette, bpp=bpp)
                readTile(f, pixels, x * 16 + 8, y * 16 + 8, palette, bpp=bpp)
            except struct.error:
                pass
    img.save(outfile, "PNG")


def repackTiledImage(f, infile, width, height, palette=None, bpp=2):
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    if palette is None:
        palette = bwpalette[0] if bpp == 2 else colpalette[0]
    img = Image.open(infile)
    img = img.convert("RGBA")
    pixels = img.load()
    for y in range(height // 16):
        for x in range(width // 16):
            writeTile(f, pixels, x * 16, y * 16, palette, bpp=bpp)
            writeTile(f, pixels, x * 16, y * 16 + 8, palette, bpp=bpp)
            writeTile(f, pixels, x * 16 + 8, y * 16, palette, bpp=bpp)
            writeTile(f, pixels, x * 16 + 8, y * 16 + 8, palette, bpp=bpp)


class TileMap:
    def __init__(self):
        self.name = ""
        self.offset = 0
        self.width = 0
        self.height = 0
        self.map = []
        self.bpp = 2


class TileData:
    def __init__(self, tile=0, pal=0, hflip=False, vflip=False):
        self.tile = tile
        self.data = 0
        self.pal = pal
        self.bank = 0
        self.hflip = hflip
        self.vflip = vflip


class SpriteData:
    def __init__(self):
        self.tile = 0
        self.data = 0
        self.pal = 0
        self.hflip = False
        self.vflip = False
        self.xpos = 0
        self.ypos = 0


def readPalette(f, bpp=2, num=16):
    palettes = []
    for i in range(num):
        if bpp == 2:
            c1 = f.readHalf() * 0x11
            c2 = f.readHalf() * 0x11
            c3 = f.readHalf() * 0x11
            c4 = f.readHalf() * 0x11
            palettes.append([(c1, c1, c1, 0xff), (c2, c2, c2, 0xff), (c3, c3, c3, 0xff), (c4, c4, c4, 0xff)])
        else:
            palette = []
            for j in range(16):
                col = f.readUShort()
                b = (col & 0xf) * 0x11
                g = ((col >> 4) & 0xf) * 0x11
                r = ((col >> 8) & 0xf) * 0x11
                palette.append((r, g, b, 0xff))
            palettes.append(palette)
    return palettes


def writePalette(f, palettes, bpp=2):
    for palette in palettes:
        for color in palette:
            if bpp == 2:
                f.writeHalf(color[0] // 0x11)
            else:
                col = (color[2] // 0x11)
                col |= ((color[1] // 0x11) << 4)
                col |= ((color[0] // 0x11) << 8)
                f.writeUShort(col)


def readMappedImage(f, outfile, mapstart=0, num=1, bpp=2, width=0, height=0):
    f.seek(mapstart)
    maps = []
    for j in range(num):
        map = TileMap()
        if num > 1:
            map.name = outfile.replace(".png", "_" + str(j + 1).zfill(2) + ".png")
        else:
            map.name = outfile
        map.offset = f.tell()
        map.width = width
        if map.width == 0:
            map.width = f.readByte()
        map.height = height
        if map.height == 0:
            map.height = f.readByte()
        map.bpp = bpp
        common.logDebug(" ", mapstart, vars(map))
        for i in range(map.width * map.height):
            tilemap = TileMap()
            tilemap.data = f.readUShort()
            tilemap.tile = tilemap.data & 0x1ff
            tilemap.pal = (tilemap.data >> 9) & 0xf
            tilemap.bank = (tilemap.data >> 13) & 1
            if tilemap.bank != 0 and bpp == 2:
                common.logError("Bank is not 0")
            tilemap.hflip = ((tilemap.data >> 14) & 1) == 1
            tilemap.vflip = ((tilemap.data >> 15) & 1) == 1
            map.map.append(tilemap)
        maps.append(map)
    common.logDebug("Map data ended at", common.toHex(f.tell()))
    return maps


# Sprite format:
# 24-31 X position
# 16-23 Y position
# 15    Vertical flip
# 14    Horizontal flip
# 13    SCR2 priority
# 12    Window clip mode (0=Display Outside, 1=Inside)
# 9-11  Palette
# 0-8   Tile
def readSprite(f, spritelen, outfile, spritestart=0, bpp=2, width=0, height=0, ignorepal=False):
    f.seek(spritestart)
    xmax = ymax = 0
    tiles = []
    for i in range(spritelen):
        spritemap = SpriteData()
        spritemap.data = f.readUInt()
        spritemap.tile = spritemap.data & 0x1ff
        spritemap.pal = (spritemap.data >> 9) & 0x7
        spritemap.hflip = ((spritemap.data >> 14) & 1) == 1
        spritemap.vflip = ((spritemap.data >> 15) & 1) == 1
        spritemap.ypos = (spritemap.data >> 16) & 0xff
        if spritemap.ypos % 8 != 0:
            common.logError("Sprite ypos is not a multiple of 8", spritemap.ypos)
        spritemap.xpos = (spritemap.data >> 24) & 0xff
        if spritemap.xpos % 8 != 0:
            common.logError("Sprite xpos is not a multiple of 8", spritemap.xpos)
        if spritemap.ypos > ymax:
            ymax = spritemap.ypos
        if spritemap.xpos > xmax:
            xmax = spritemap.xpos
        tiles.append(spritemap)
    # Convert this to map data
    map = TileMap()
    map.name = outfile
    map.offset = spritestart
    map.width = (xmax + 8) // 8
    map.height = (ymax + 8) // 8
    map.bpp = bpp
    for y in range(map.height):
        for x in range(map.width):
            data = TileData(0)
            # Search for a sprite with these coordinates
            for i in range(len(tiles)):
                if tiles[i].ypos == y * 8 and tiles[i].xpos == x * 8:
                    data.tile = tiles[i].tile
                    if not ignorepal:
                        data.pal = tiles[i].pal
                    data.hflip = tiles[i].hflip
                    data.vflip = tiles[i].vflip
                    break
            map.map.append(data)
    return [map]


def extractMappedImage(f, outfile, tilestart, mapstart, num=1, readpal=False, bpp=2, forcewidth=0, forceheight=0):
    common.logDebug("Extracting", outfile)
    maps = readMappedImage(f, outfile, mapstart, num, bpp, forcewidth, forceheight)
    if readpal:
        f.seek(mapstart - 32)
        palettes = readPalette(f, maps[0].bpp)
    else:
        palettes = bwpalette
    writeMappedImage(f, tilestart, maps, palettes, num)


def writeMappedImage(f, tilestart, maps, palettes, num=1, skipzero=False):
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    maxtile = tilesize = 0
    for i in range(num):
        mapdata = maps[i]
        if mapdata.width == 0:
            common.logError("Width is 0")
            continue
        if mapdata.height == 0:
            common.logError("Height is 0")
            continue
        imgwidth = mapdata.width * 8
        imgheight = mapdata.height * 8
        pali = 0
        if mapdata.bpp == 4 and palettes != colpalette:
            imgwidth += 40
            for palette in palettes:
                if palette.count((0x0, 0x0, 0x0, 0xff)) == 16:
                    break
                pali += 1
            imgheight = max(imgheight, pali * 10)
        img = Image.new("RGB", (imgwidth, imgheight), (0x0, 0x0, 0x0))
        pixels = img.load()
        x = y = 0
        for map in mapdata.map:
            tilesize = (16 if mapdata.bpp == 2 else 32)
            if map.tile > maxtile:
                maxtile = map.tile
            if (map.tile > 0 or not skipzero) and (mapdata.bpp != 2 or map.bank == 0):
                f.seek(tilestart + map.bank * 0x4000 + map.tile * tilesize)
                try:
                    readTile(f, pixels, x * 8, y * 8, palettes[map.pal] if map.pal < len(palettes) else palettes[0], map.hflip, map.vflip, mapdata.bpp)
                except struct.error:
                    pass
                except IndexError:
                    pass
            x += 1
            if x == mapdata.width:
                y += 1
                x = 0
        if pali > 0:
            palstart = 0
            for i in range(pali):
                pixels = common.drawPalette(pixels, palettes[i], imgwidth - 40, palstart * 10)
                palstart += 1
        img.save(mapdata.name, "PNG")
    common.logDebug("Tile data ended at", common.toHex(tilestart + maxtile * tilesize + tilesize))


def repackMappedImage(f, infile, tilestart, mapstart, num=1, readpal=False, writepal=False):
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    common.logDebug("Repacking", infile)
    maps = readMappedImage(f, infile, mapstart, num)
    tiles = {}
    if readpal:
        f.seek(mapstart - 32)
        palettes = readPalette(f, maps[0].bpp)
    else:
        palettes = bwpalette
    common.logDebug(palettes)
    # Figure out how many tiles we can include
    maxtile = 0
    mintile = 9999
    for i in range(num):
        for map in maps[i].map:
            if map.tile < mintile:
                mintile = map.tile
            if map.tile > maxtile:
                maxtile = map.tile
    currtile = mintile
    for i in range(num):
        mapdata = maps[i]
        imgname = mapdata.name
        if not os.path.isfile(mapdata.name):
            imgname = imgname.replace("work_IMG", "out_IMG")
        if not os.path.isfile(imgname):
            common.logError("Image", imgname, "not found")
            continue
        common.logDebug(" Processing", imgname)
        img = Image.open(imgname)
        img = img.convert("RGB")
        pixels = img.load()
        # Loop the tiles in the PNG
        currmap = 0
        x = y = 0
        common.logDebug(mapdata.width, mapdata.height)
        while y < mapdata.height:
            hflip = vflip = False
            tilecolors = []
            # Convert the PNG tile to indexes
            for y2 in range(8):
                for x2 in range(8):
                    tilecolors.append(pixels[x * 8 + x2, y * 8 + y2])
            pal = 0
            if writepal:
                pal = common.findBestPalette(palettes, tilecolors)
            elif readpal:
                pal = mapdata.map[currmap].pal
            tile = []
            for tilecolor in tilecolors:
                tile.append(common.getPaletteIndex(palettes[pal], tilecolor, zerotransp=False))
            tile = tuple(tile)
            # Check if we already have added this file
            if tile in tiles:
                maptile = tiles[tile]
            else:
                # Look for inverted tiles
                hflipped = tuple(common.flipTile(tile, True, False))
                vflipped = tuple(common.flipTile(tile, False, True))
                hvflipped = tuple(common.flipTile(tile, True, True))
                if hflipped in tiles:
                    maptile = tiles[hflipped]
                    hflip = True
                elif vflipped in tiles:
                    maptile = tiles[vflipped]
                    vflip = True
                elif hvflipped in tiles:
                    maptile = tiles[hvflipped]
                    hflip = vflip = True
                else:
                    # Check for space
                    if currtile > maxtile:
                        common.logError("Not enough space for tile", (str(currtile) + "/" + str(maxtile)), "in", mapdata.name)
                        currtile += 1
                        maptile = mintile
                    else:
                        # Add the new tile
                        maptile = currtile
                        currtile += 1
                        tiles[tile] = maptile
                        f.seek(tilestart + (maptile * 16))
                        writeTile(f, pixels, x * 8, y * 8, palettes[pal], mapdata.bpp)
            # Write the map data
            f.seek(mapdata.offset + 2 + currmap * 2)
            originalmap = mapdata.map[currmap]
            mapbytes = maptile
            if writepal:
                mapbytes |= (pal << 9)
            else:
                mapbytes |= (originalmap.pal << 9)
            mapbytes |= (originalmap.bank << 13)
            mapbytes |= ((1 if hflip else 0) << 14)
            mapbytes |= ((1 if vflip else 0) << 15)
            f.writeUShort(mapbytes)
            x += 1
            currmap += 1
            if x == mapdata.width:
                y += 1
                x = 0


def repackMappedTiles(f, tilestart, mapdata, palettes):
    try:
        from PIL import Image
    except ImportError:
        common.logError("PIL not found")
        return
    imgname = mapdata.name
    if not os.path.isfile(mapdata.name):
        imgname = imgname.replace("work_IMG", "out_IMG")
    if not os.path.isfile(imgname):
        common.logError("Image", imgname, "not found")
        return
    img = Image.open(imgname)
    img = img.convert("RGB")
    pixels = img.load()
    x = y = 0
    for tiledata in mapdata.map:
        if not tiledata.hflip and not tiledata.vflip:
            f.seek(tilestart + (tiledata.tile * 16))
            writeTile(f, pixels, x * 8, y * 8, palettes[0], mapdata.bpp)
        x += 1
        if x == mapdata.width:
            y += 1
            x = 0
