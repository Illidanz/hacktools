import ctypes
from hacktools import common


# https://forum.xentax.com/viewtopic.php?p=30390#p30387
def getBits(n, f, blen, fbuf):
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


def decompressHuffman(rawdata, decomplength, numbits=8, little=True):
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
    children = []
    freqcount = 0
    code = 0
    score = 0

    def __init__(self, freqcount, code, children=[]):
        self.freqcount = freqcount
        self.code = code
        self.children = children

    def getHuffCodes(self, seed):
        if len(self.children) == 0:
            return [(self.code, seed)]
        ret = []
        for i in range(len(self.children)):
            childcodes = self.children[i].getHuffCodes(seed + str(i))
            for childcode in childcodes:
                ret.append(childcode)
        return ret


def compressHuffman(indata, numbits=8, little=True):
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
    lst = []
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


def decompressPRS(f, slen, dlen):
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
