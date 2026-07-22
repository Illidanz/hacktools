"""Generic implementations of compression algorithms.

Includes the Huffman coding scheme used by the GBA and NDS BIOS and the
PRS scheme, an LZ77 variant used by several SEGA games.
"""
import ctypes
from hacktools import common


# https://forum.xentax.com/viewtopic.php?p=30390#p30387
def getBits(n: int, f: common.Stream, blen: int, fbuf: int) -> tuple[int, int, int]:
    """Read bits from a stream, most significant first, through a byte buffer.

    Args:
        n: Number of bits to read.
        f: Stream to read from.
        blen: Number of bits still available in fbuf, 0 on the first call.
        fbuf: Buffer with the current partially consumed byte, 0 on the first call.

    Returns:
        A tuple (value, blen, fbuf) with the bits that were read and the
        updated buffer state to pass to the next call.
    """
    retv = 0
    while n > 0:
        retv = retv << 1
        if blen == 0:
            fbuf = f.readSByte()
            blen = 8
        if fbuf & 0x80:
            retv |= 1
        fbuf = fbuf << 1
        blen -= 1
        n -= 1
    return retv, blen, fbuf


def decompressHuffman(rawdata: bytes, decomplength: int, numbits: int = 8, little: bool = True) -> bytes:
    """Decompress Huffman-coded data, as used by the GBA and NDS BIOS.

    The data is expected to start with the tree size and the tree itself,
    followed by the 32-bit codeword stream, without the 4-byte header with
    compression type and length.

    Args:
        rawdata: Compressed data to read.
        decomplength: Length of the decompressed data.
        numbits: Data size in bits, 8 or 4.
        little: Whether nibbles are ordered low-first when numbits is 4.

    Returns:
        The decompressed data.
    """
    with common.Stream() as data:
        data.write(rawdata)
        data.seek(0)
        with common.Stream() as out:
            treesize = data.readByte()
            treeroot = data.readByte()
            treebuffer = data.read(treesize * 2)
            i = code = next = 0
            pos = treeroot
            code = data.readUInt()
            while True:
                if i == 32:
                    code = data.readUInt()
                    i = 0
                next += (pos & 0x3f) * 2 + 2
                direction = (code >> (31 - i)) % 2 == 0 and 2 or 1
                leaf = ((pos >> 5) >> direction) % 2 != 0
                pos = treebuffer[next - direction]
                if leaf:
                    out.writeByte(pos & 0xff)
                    pos = treeroot
                    next = 0
                if out.tell() == decomplength * (8 / numbits):
                    break
                i += 1
            out.seek(0)
            if numbits == 8:
                return out.read(decomplength)
            with common.Stream() as out4:
                for j in range(decomplength):
                    b1 = out.readByteAt(2 * j + 1)
                    b2 = out.readByteAt(2 * j)
                    if little:
                        out4.writeByte(b1 * 16 + b2)
                    else:
                        out4.writeByte(b2 * 16 + b1)
                out4.seek(0)
                return out4.read(decomplength)


class HuffmanNode:
    """Node of the binary tree built by :func:`compressHuffman`.

    Attributes:
        freqcount: Number of occurrences of code in the input data.
        code: Byte value for leaf nodes, label for branch nodes.
        children: The two child nodes, empty for leaf nodes.
        score: Temporary score used while labeling nodes.
    """
    children: list["HuffmanNode"] = []
    freqcount = 0
    code = 0
    score = 0

    def __init__(self, freqcount, code, children=[]):
        self.freqcount: int = freqcount
        self.code: int = code
        self.children: list[HuffmanNode] = children

    def getHuffCodes(self, seed: str) -> list[tuple[int, str]]:
        """Get the Huffman codes for all the leaf nodes under this node.

        Args:
            seed: Bit string prefix accumulated so far, "" for the root.

        Returns:
            A list of (code, bits) tuples, where bits is the string of "0"
            and "1" characters that encodes the code byte value.
        """
        if len(self.children) == 0:
            return [(self.code, seed)]
        ret = []
        for i in range(len(self.children)):
            childcodes = self.children[i].getHuffCodes(seed + str(i))
            for childcode in childcodes:
                ret.append(childcode)
        return ret


def compressHuffman(indata: bytes, numbits: int = 8, little: bool = True) -> bytes:
    """Compress data with Huffman coding, as used by the GBA and NDS BIOS.

    The output starts with the tree size and the tree itself, followed by
    the 32-bit codeword stream. The 4-byte header with compression type and
    length is not included and should be written separately.

    Args:
        indata: Data to compress.
        numbits: Data size in bits, 8 or 4.
        little: Whether nibbles are ordered low-first when numbits is 4.

    Returns:
        The compressed data.
    """
    # Read indata as nibbles if numbits is 4
    if numbits == 4:
        with common.Stream() as in4:
            for i in range(len(indata)):
                b1 = indata[i] % 16
                b2 = indata[i] // 16
                if little:
                    in4.writeByte(b1)
                    in4.writeByte(b2)
                else:
                    in4.writeByte(b2)
                    in4.writeByte(b1)
            in4.seek(0)
            indata = in4.read()

    # Get frequencies
    freq = []
    for i in range(256):
        count = indata.count(i)
        if count > 0:
            freq.append(HuffmanNode(count, i))

    # Add a stub entry in the special case that there's only one item
    if len(freq) == 1:
        freq.append(HuffmanNode(0, indata[0] + 1))

    # Sort and create the tree
    while len(freq) > 1:
        freq.sort(key=lambda x: x.freqcount)
        children = [freq.pop(0), freq.pop(0)]
        freq.append(HuffmanNode(children[0].freqcount + children[1].freqcount, 0, children))

    # Label nodes to keep bandwidth small
    lst: list[HuffmanNode] = []
    while len(freq) > 0:
        scorelst = []
        for i in range(len(freq)):
            freq[i].score = freq[i].code - i
            scorelst.append(freq[i])
        scorelst.sort(key=lambda x: x.score)
        node = scorelst[0]
        freq.remove(node)
        node.code = (len(lst) - node.code) & 0xff
        lst.append(node)
        if len(node.children) > 0:
            for child in reversed(node.children):
                if len(child.children) > 0:
                    child.code = len(lst) & 0xff
                    freq.append(child)

    # Convert our list of nodes to a dictionary of bytes -> huffman codes
    huffcodes = lst[0].getHuffCodes("")
    codes = {}
    for huffcode in huffcodes:
        codes[huffcode[0]] = huffcode[1]

    # Write data
    with common.Stream() as out:
        # Write header
        out.writeByte(len(lst) & 0xff)

        # Write Huffman tree
        tree = [lst[0]]
        for node in lst:
            if len(node.children) > 0:
                for children in node.children:
                    tree.append(children)
        for node in tree:
            if len(node.children) > 0:
                childsum = 0
                for i in range(len(node.children)):
                    if len(node.children[i].children) == 0:
                        childsum += ((0x80 >> i) & 0xff)
                node.code |= (childsum & 0xff)
            out.writeByte(node.code)

        # Write bits to stream
        data = setbits = 0
        for datavalue in indata:
            bits = codes[datavalue]
            for bit in bits:
                data = data * 2 + int(bit)
                setbits += 1
                if setbits % 32 == 0:
                    out.writeUInt(data)
                    data = 0
        if setbits % 32 != 0:
            out.writeUInt(data << (32 - (setbits % 32)))

        # Return data
        out.seek(0)
        return out.read()


def decompressPRS(f: common.Stream, slen: int, dlen: int) -> bytearray:
    """Decompress PRS data, an LZ77 variant.

    Args:
        f: Stream to read from, seeked to the start of the compressed data.
        slen: Length of the compressed data.
        dlen: Length of the decompressed data.

    Returns:
        The decompressed data.
    """
    dbuf = bytearray(dlen)
    startpos = f.tell()
    blen = 0
    fbuf = 0
    dptr = 0
    plen = 0
    pos = 0
    while f.tell() < startpos + slen:
        flag, blen, fbuf = getBits(1, f, blen, fbuf)
        if flag == 1:
            if dptr < dlen:
                dbuf[dptr] = f.readByte()
                dptr += 1
        else:
            flag, blen, fbuf = getBits(1, f, blen, fbuf)
            if flag == 0:
                plen, blen, fbuf = getBits(2, f, blen, fbuf)
                plen += 2
                data = f.readSByte()
                # Use ctypes to correctly handle int overflow
                pos = ctypes.c_int(data | 0xffffff00).value
            else:
                pos = ctypes.c_int((f.readSByte() << 8) | 0xffff0000).value
                pos |= f.readSByte() & 0xff
                plen = pos & 0x07
                pos >>= 3
                if plen == 0:
                    plen = (f.readSByte() & 0xff) + 1
                else:
                    plen += 2
            pos += dptr
            for _ in range(plen):
                if dptr < dlen:
                    dbuf[dptr] = dbuf[pos]
                    dptr += 1
                    pos += 1
    return dbuf
