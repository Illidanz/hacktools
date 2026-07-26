"""Support for PS2 GS texture swizzling."""

# GS memory layout tables, from the GS manual / rwlib
# PSMT4 and PSMCT16 share the same block arrangement,
# pages are 32 blocks of 256 bytes split in 4 columns.
gsblock4 = [
    0,  2,  8, 10,
    1,  3,  9, 11,
    4,  6, 12, 14,
    5,  7, 13, 15,
    16, 18, 24, 26,
    17, 19, 25, 27,
    20, 22, 28, 30,
    21, 23, 29, 31
]
gscoleven = [0, 1, 4, 5, 8, 9, 12, 13, 2, 3, 6, 7, 10, 11, 14, 15]
gscolodd = [8, 9, 12, 13, 0, 1, 4, 5, 10, 11, 14, 15, 2, 3, 6, 7]


swizzle4maps: dict[tuple[int, int], list[tuple[int, int]]] = {}


def unswizzle4(pixels, w: int, h: int) -> bytearray:
    """Unswizzle a 4bpp texture uploaded to GS memory as PSMCT16.

    Simulates a GS memory transfer: the data was sent as a PSMCT16 image of
    w/2 x h/2 pixels and gets sampled as PSMT4, w x h pixels.
    The map from output pixel to input byte/nibble is cached for each size.

    Args:
        pixels: Swizzled 4bpp texture data.
        w: Width of the texture.
        h: Height of the texture.

    Returns:
        A bytearray of w * h palette indexes, one per byte.
    """
    if (w, h) not in swizzle4maps:
        dbw = max(1, w // 128)
        mem = [0] * (dbw * max(1, (h + 127) // 128) * 8192)
        # Write as PSMCT16 (page 64x64, block 16x8, column 16x2)
        i = 0
        for y in range(h // 2):
            pagey = (y >> 6) * dbw
            py = y & 0x3f
            blocky = (py >> 3) * 4
            column = (py & 0x7) >> 1
            coloff = gscoleven[(py & 1) * 8:]
            for x in range(w // 2):
                px = x & 0x3f
                block = gsblock4[(px >> 4) + blocky]
                cx = px & 0xf
                addr = ((x >> 6) + pagey) * 8192 + block * 256 + column * 64 + coloff[cx & 7] * 4 + (cx >> 3) * 2
                mem[addr] = i
                mem[addr + 1] = i + 1
                i += 2
        # Read as PSMT4 (page 128x128, block 32x16, column 32x4)
        posmap = []
        for y in range(h):
            pagey = (y >> 7) * dbw
            py = y & 0x7f
            blocky = (py >> 4) * 4
            by = py & 0xf
            column = by >> 2
            cy = by & 3
            pattern = gscolodd if ((cy >> 1) ^ (column & 1)) != 0 else gscoleven
            coloff = pattern[(cy & 1) * 8:]
            for x in range(w):
                px = x & 0x7f
                block = gsblock4[(px >> 5) + blocky]
                cx = px & 0x1f
                nib = (cy >> 1) + (cx >> 3) * 2
                addr = ((x >> 7) + pagey) * 8192 + block * 256 + column * 64 + coloff[cx & 7] * 4 + (nib >> 1)
                posmap.append((mem[addr], (nib & 1) * 4))
        swizzle4maps[(w, h)] = posmap
    return bytearray((pixels[addr] >> shift) & 0xf for addr, shift in swizzle4maps[(w, h)])


def swizzle4(pixels, w: int, h: int) -> bytearray:
    """Swizzle a 4bpp texture, inverse of :func:`unswizzle4`.

    Args:
        pixels: Sequence of w * h palette indexes, one per byte.
        w: Width of the texture.
        h: Height of the texture.

    Returns:
        A bytearray of the swizzled 4bpp texture data, two indexes per byte.
    """
    if (w, h) not in swizzle4maps:
        unswizzle4(bytes(w * h // 2), w, h)
    outpixels = bytearray(w * h // 2)
    for i, (addr, shift) in enumerate(swizzle4maps[(w, h)]):
        outpixels[addr] = (outpixels[addr] & (0xf0 >> shift)) | ((pixels[i] & 0xf) << shift)
    return outpixels


# Swizzle code from: https://github.com/neko68k/rtftool/blob/master/RTFTool/rtfview/p6t_v2.cpp
def coord4(x: int, y: int, w: int, h: int) -> int:
    pageX = x & (~0x7f)
    pageY = y & (~0x7f)
    pages_horz = (w + 127) // 128
    pages_vert = (h + 127) // 128
    page_number = (pageY // 128) * pages_horz + (pageX // 128)
    page32Y = (page_number // pages_vert) * 32
    page32X = (page_number % pages_vert) * 64
    page_location = page32Y * h * 2 + page32X * 4
    locX = x & 0x7f
    locY = y & 0x7f
    block_location = ((locX & (~0x1f)) >> 1) * h + (locY & (~0xf)) * 2
    swap_selector = (((y + 2) >> 2) & 0x1) * 4
    posY = (((y & (~3)) >> 1) + (y & 1)) & 0x7
    column_location = posY * h * 2 + ((x + swap_selector) & 0x7) * 4
    byte_num = (x >> 3) & 3
    return page_location + block_location + column_location + byte_num


def unswizzleP6T4(pixels, w: int, h: int) -> bytearray:
    """Unswizzle a 4bpp P6T texture, returning one index per byte."""
    outpixels = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            index = (y * w) + x
            coord = coord4(x, y, w, h)
            entry = pixels[coord]
            entry = ((entry >> (((y >> 1) & 0x01) * 4)) & 0x0f) & 0xff
            outpixels[index] = entry
    return outpixels


def swizzleP6T4(pixels, w: int, h: int, size: int) -> bytearray:
    """Swizzle a 4bpp P6T texture from one index per byte into a size bytes buffer."""
    outpixels = bytearray(size)
    for y in range(h):
        for x in range(w):
            index = (y * w) + x
            coord = coord4(x, y, w, h)
            entry = outpixels[coord]
            color = pixels[index]
            entry |= ((color & 0xff) & 0xf) << (((y >> 1) & 0x01) * 4)
            outpixels[coord] = entry
    return outpixels


def coord8(x: int, y: int, w: int, h: int) -> int:
    block_location = (y & (~0xf)) * w + (x & (~0xf)) * 2
    swap_selector = (((y + 2) >> 2) & 0x1) * 4
    positionY = (((y & (~3)) >> 1) + (y & 1)) & 0x7
    column_location = positionY * w * 2 + ((x + swap_selector) & 0x7) * 4
    byte_number = ((y >> 1) & 1) + ((x >> 2) & 2)
    return block_location + column_location + byte_number


swizzle8maps: dict[tuple[int, int], list[int]] = {}


def getSwizzle8Map(w: int, h: int):
    if (w, h) not in swizzle8maps:
        swizzle8maps[(w, h)] = [coord8(x, y, w, h) for y in range(h) for x in range(w)]
    return swizzle8maps[(w, h)]


def unswizzle8(pixels, w: int, h: int, default=0) -> list:
    """Unswizzle an 8bpp texture, works on any sequence (indexes or colors).

    Args:
        pixels: Swizzled sequence of w * h pixels.
        w: Width of the texture.
        h: Height of the texture.
        default: Value used for out of bounds pixels.

    Returns:
        The unswizzled list of pixels.
    """
    length = len(pixels)
    return [pixels[coord] if coord < length else default for coord in getSwizzle8Map(w, h)]


def swizzle8(pixels, w: int, h: int, default=0) -> list:
    """Swizzle an 8bpp texture, works on any sequence (indexes or colors)."""
    outpixels = [default] * len(pixels)
    length = len(pixels)
    for index, coord in enumerate(getSwizzle8Map(w, h)):
        if coord < length:
            outpixels[coord] = pixels[index]
    return outpixels


def unswizzlePalette(swizzled: list) -> list:
    """Unswizzle a CSM1 256 colors palette by swapping the middle 8 colors of each 32 colors block."""
    unswizzled = [0] * 256
    j = 0
    for i in range(0, 256, 32):
        unswizzled[i:i + 8] = swizzled[j:j + 8]
        unswizzled[i + 16:i + 24] = swizzled[j + 8:j + 16]
        unswizzled[i + 8:i + 16] = swizzled[j + 16:j + 24]
        unswizzled[i + 24:i + 32] = swizzled[j + 24:j + 32]
        j += 32
    return unswizzled


def swizzlePalette(unswizzled: list) -> list:
    """Swizzle a CSM1 256 colors palette, inverse of :func:`unswizzlePalette`."""
    return unswizzlePalette(unswizzled)
