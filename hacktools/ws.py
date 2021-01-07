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
    common.logMessage("Repacking", banknum, "banks ...")
    with common.Stream(rompatch, "wb") as fout:
        for i in range(banknum):
            bankname = "bank_"
            if i < 0x10:
                bankname += "0"
            bankname += format(i, 'x')
            with common.Stream(workfolder + bankname + ".bin", "rb") as f:
                fout.write(f.read())
    # Calculate and write the checksum
    with common.Stream(rompatch, "rb+") as fout:
        checksum = sum(fout.read(filesize - 2))
        fout.writeUShort(checksum & 0xffff)
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


def readPalette(f, num=16):
    palettes = []
    for i in range(num):
        c1 = f.readHalf() * 0x11
        c2 = f.readHalf() * 0x11
        c3 = f.readHalf() * 0x11
        c4 = f.readHalf() * 0x11
        palettes.append([(c1, c1, c1, 0xff), (c2, c2, c2, 0xff), (c3, c3, c3, 0xff), (c4, c4, c4, 0xff)])
    return palettes


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
    common.logDebug("Map data ended at", common.toHex(f.tell()))
    return maps


def extractMappedImage(f, outfile, tilestart, mapstart, num=1, readpal=False, printnum=False):
    common.logDebug("Extracting", outfile)
    if printnum:
        from PIL import ImageFont, ImageDraw
        fnt = ImageFont.truetype("m3x6.ttf", 16)
    maps = readMappedImage(f, outfile, tilestart, mapstart, num)
    maxtile = 0
    if readpal:
        f.seek(mapstart - 32)
        palettes = readPalette(f)
    else:
        palettes = bwpalette
    common.logDebug(palettes)
    for i in range(num):
        mapdata = maps[i]
        img = Image.new("RGB", (mapdata.width * 8, mapdata.height * 8), (0x0, 0x0, 0x0))
        pixels = img.load()
        x = y = 0
        for map in mapdata.map:
            if map.tile > maxtile:
                maxtile = map.tile
            f.seek(tilestart + map.tile * 16)
            readTile(f, pixels, x * 8, y * 8, palettes[map.pal] if map.pal < len(palettes) else palettes[0], map.hflip, map.vflip)
            if printnum:
                d = ImageDraw.Draw(img)
                d.text((x * 8, y * 8 - 5), str(map.pal), font=fnt, spacing=1, fill='red')
            x += 1
            if x == mapdata.width:
                y += 1
                x = 0
        img.save(mapdata.name, "PNG")
    common.logDebug("Tile data ended at", common.toHex(tilestart + maxtile * 16 + 16))


def repackMappedImage(f, infile, tilestart, mapstart, num=1, readpal=False, writepal=False):
    common.logDebug("Repacking", infile)
    maps = readMappedImage(f, infile, tilestart, mapstart, num)
    tiles = {}
    if readpal:
        f.seek(mapstart - 32)
        palettes = readPalette(f)
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
                        writeTile(f, pixels, x * 8, y * 8, palettes[pal])
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
