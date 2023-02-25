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


class CompressedBitInput:
    def __init__(self, data):
        from bitarray import bitarray
        self.b = bitarray()
        self.b.frombytes(data[::-1])
        self.pos = 0

    def read(self, length):
        data = self.b[self.pos:self.pos + length]
        self.pos += length
        return data

    def read01(self, length):
        return self.read(length).to01()

    def readnum(self, length):
        return int(self.read01(length), 2)

    def readbyte(self, length = 1):
        return self.read(length * 8).tobytes()

    def close(self):
        self.b = None


class CompressedBitOutput:
    def __init__(self):
        from bitarray import bitarray
        self.b = bitarray()
    # TODO


def decompressCRILAYLA(f, fileoffset):
    def deflatelevels():
        for v in [2, 3, 5, 8]:
            yield v
        while True:
            yield 8
    uncsize = f.readUInt()
    uncheaderoffset = f.readUInt()
    # common.logDebug("decompressCRILAYLA uncsize", uncsize, "uncheaderoffset", uncheaderoffset)
    with common.Stream() as decmp:
        cmp = CompressedBitInput(f.read(uncheaderoffset))
        while True:
            bit = cmp.read01(1)
            if bit == '':
                break
            if int(bit, 2):
                offset = cmp.readnum(13) + 3
                refc = 3

                for lv in deflatelevels():
                    bits = cmp.read(lv)
                    refc += int(bits.to01(), 2)
                    if not bits.all():
                        break

                while refc > 0:
                    decmp.seek(-offset, 1)
                    ref = decmp.read(refc)
                    decmp.seek(0, 2)
                    decmp.write(ref)
                    refc -= len(ref)
            else:
                b = cmp.readbyte()
                decmp.write(b)
        cmp.close()
        with common.Stream() as result:
            # Copy the uncompressed 0x100 header
            f.seek(fileoffset + 0x10 + uncheaderoffset)
            result.write(f.read(0x100))
            # Copy the uncompressed data, reversed
            decmp.seek(0)
            result.write(decmp.read()[:uncsize][::-1])
            result.seek(0)
            return result.read()


# Implementation by KenTse based on https://github.com/ConnorKrammer/cpk-tools/blob/master/LibCRIComp/LibCRIComp.cpp
def compressCRILAYLA(src):
    srclen = len(src)
    destlen = srclen
    dest = bytearray(destlen)
    n = srclen - 1
    m = destlen - 1
    T = d = p = q = i = j = k = 0
    while n >= 0x100:
        j = n + 3 + 0x2000
        if j > srclen:
            j = srclen
        i = n + 3
        p = 0
        while i < j:
            for k in range(n - 0x100 + 1):
                if src[n - k] != src[i - k]:
                    break
            if k > p:
                q = i - n - 3
                p = k
            i += 1
        if p < 3:
            d = (d << 9) | src[n]
            n -= 1
            T += 9
        else:
            d = (((d << 1) | 1) << 13) | q
            T += 14
            n -= p
            if p < 6:
                d = (d << 2) | (p - 3)
                T += 2
            elif p < 13:
                d = (((d << 2) | 3) << 3) | (p - 6)
                T += 5
            elif p < 44:
                d = (((d << 5) | 0x1f) << 5) | (p - 13)
                T += 10
            else:
                d = ((d << 10) | 0x3ff)
                T += 10
                p -= 44
                while True:
                    while T >= 8:
                        dest[m] = (d >> (T - 8)) & 0xff
                        m -= 1
                        T -= 8
                        d = d & ((1 << T) - 1)
                    if p < 255:
                        break
                    d = (d << 8) | 0xff
                    T += 8
                    p = p - 0xff
                d = (d << 8) | p
                T += 8
        while T >= 8:
            dest[m] = (d >> (T - 8)) & 0xff
            m -= 1
            T -= 8
            d = d & ((1 << T) - 1)
    if T != 0:
        dest[m] = d << (8 - T)
        m -= 1
    dest[m] = 0
    m -= 1
    dest[m] = 0
    while True:
        if ((destlen - m) & 3) == 0:
            break
        dest[m] = 0
        m -= 1
    destlen -= m
    dest = dest[m:]
    header = bytearray(4 * 4)
    l = [ 0x4c495243, 0x414c5941, srclen - 0x100, destlen ]
    for j in range(4):
        for i in range(4):
            header[i + j * 4] = l[j] & 0xff
            l[j] >>= 8
    dest += src[:0x100]
    return header + dest
