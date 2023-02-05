import ctypes
import os
from hacktools import common


def runExternal(indata, fmt, compress):
    dsdecmp = common.bundledExecutable("DSDecmp.exe")
    if os.path.isfile(dsdecmp):
        tmpfile = "cmp.tmp"
        tmpfileout = "cmpout.tmp"
        with open(tmpfile, "wb") as f:
            f.write(indata)
        common.execute(dsdecmp + " {command} {fmt} {tmpfile} {tmpfileout}".format(command="-c" if compress else "-d", fmt=fmt, tmpfile=tmpfile, tmpfileout=tmpfileout), False)
        with open(tmpfileout, "rb") as f:
            f.seek(4)
            data = f.read()
        os.remove(tmpfile)
        os.remove(tmpfileout)
        return True, data
    return False, None


# Implementations based on Kurimuu's Kontract
# https://github.com/IcySon55/Kuriimu/tree/master/src/Kontract/Compression
def decompressLZ10(data, complength, decomplength, dispextra=1):
    with common.Stream() as out:
        readbytes = 0

        # the maximum 'DISP-1' is 0xFFF.
        bufferlength = 0x1000
        buffer = bytearray(bufferlength)
        bufferoffset = 0

        currentoutsize = 0
        flags = 0
        mask = 1
        while currentoutsize < decomplength:
            # Update the mask. If all flag bits have been read, get a new set.
            # the current mask is the mask used in the previous run. So if it masks the
            # last flag bit, get a new flags byte.
            if mask == 1:
                if readbytes >= complength:
                    raise Exception("Not enough data.")
                flags = data.readByte()
                readbytes += 1
                if flags < 0:
                    raise Exception("Stream too short!")
                mask = 0x80
            else:
                mask >>= 1
            # bit = 1 <=> compressed.
            if (flags & mask) > 0:
                # Get length and displacement('disp') values from next 2 bytes
                # there are < 2 bytes available when the end is at most 1 byte away
                if readbytes + 1 >= complength:
                    if readbytes < complength:
                        data.readbyte()
                        readbytes += 1
                    raise Exception("Not enough data.")
                byte1 = data.readByte()
                byte2 = data.readByte()
                readbytes += 2
                if byte2 < 0:
                    raise Exception("Stream too short!")
                # the number of bytes to copy
                length = byte1 >> 4
                length += 3
                # from where the bytes should be copied (relatively)
                disp = ((byte1 & 0x0F) << 8) | byte2
                disp += dispextra
                if disp > currentoutsize:
                    raise Exception("Cannot go back more than already written.")

                bufidx = bufferoffset + bufferlength - disp
                for i in range(length):
                    next = buffer[bufidx % bufferlength]
                    bufidx += 1
                    out.writeByte(next)
                    buffer[bufferoffset] = next
                    bufferoffset = (bufferoffset + 1) % bufferlength
                currentoutsize += length
            else:
                if readbytes >= complength:
                    raise Exception("Not enough data.")
                next = data.readByte()
                readbytes += 1
                if next < 0:
                    raise Exception("Stream too short!")
                currentoutsize += 1
                out.writeByte(next)
                buffer[bufferoffset] = next
                bufferoffset = (bufferoffset + 1) % bufferlength
        out.seek(0)
        return out.read(decomplength)


def compressLZ10(indata, mindisp=1):
    external, data = runExternal(indata, "lz10", True)
    if external:
        return data
    with common.Stream() as out:
        inlength = len(indata)
        compressedlength = 0
        instart = 0
        # we do need to buffer the output, as the first byte indicates which blocks are compressed.
        # this version does not use a look-ahead, so we do not need to buffer more than 8 blocks at a time.
        outbuffer = bytearray(8 * 2 + 1)
        outbuffer[0] = 0
        bufferlength = 1
        bufferedblocks = 0
        readbytes = 0
        while readbytes < inlength:
            # If 8 blocks are buffered, write them and reset the buffer
            # we can only buffer 8 blocks at a time.
            if bufferedblocks == 8:
                out.write(outbuffer[:bufferlength])
                compressedlength += bufferlength
                # reset the buffer
                outbuffer[0] = 0
                bufferlength = 1
                bufferedblocks = 0
            # determine if we're dealing with a compressed or raw block.
            # it is a compressed block when the next 3 or more bytes can be copied from
            # somewhere in the set of already compressed bytes.
            oldlength = min(readbytes, 0x1000)
            length, disp = getOccurrenceLength(indata, instart + readbytes, min(inlength - readbytes, 0x12), instart + readbytes - oldlength, oldlength, mindisp)
            # length not 3 or more? next byte is raw data
            if length < 3:
                outbuffer[bufferlength] = indata[instart + readbytes]
                bufferlength += 1
                readbytes += 1
            else:
                # 3 or more bytes can be copied? next (length) bytes will be compressed into 2 bytes
                readbytes += length
                # mark the next block as compressed
                outbuffer[0] |= (1 << (7 - bufferedblocks))
                outbuffer[bufferlength] = ((length - 3) << 4) & 0xF0
                outbuffer[bufferlength] |= ((disp - 1) >> 8) & 0x0F
                bufferlength += 1
                outbuffer[bufferlength] = (disp - 1) & 0xFF
                bufferlength += 1
            bufferedblocks += 1
        # copy the remaining blocks to the output
        if bufferedblocks > 0:
            out.write(outbuffer[:bufferlength])
            compressedlength += bufferlength
        out.seek(0)
        return out.read()


def decompressLZ11(data, complength, decomplength):
    result = bytearray(decomplength)
    dstoffset = 0
    while True:
        header = data.readByte()
        for i in range(8):
            if (header & 0x80) == 0:
                result[dstoffset] = data.readByte()
                dstoffset += 1
            else:
                a = data.readByte()
                b = data.readByte()
                offset = 0
                length2 = 0
                if (a >> 4) == 0:
                    c = data.readByte()
                    length2 = (((a & 0xF) << 4) | (b >> 4)) + 0x11
                    offset = (((b & 0xF) << 8) | c) + 1
                elif (a >> 4) == 1:
                    c = data.readByte()
                    d = data.readByte()
                    length2 = (((a & 0xF) << 12) | (b << 4) | (c >> 4)) + 0x111
                    offset = (((c & 0xF) << 8) | d) + 1
                else:
                    length2 = (a >> 4) + 1
                    offset = (((a & 0xF) << 8) | b) + 1
                for j in range(length2):
                    result[dstoffset] = result[dstoffset - offset]
                    dstoffset += 1
            if dstoffset >= decomplength:
                return result
            header <<= 1


def compressLZ11(indata, mindisp=1):
    external, data = runExternal(indata, "lz11", True)
    if external:
        return data
    with common.Stream() as out:
        inlength = len(indata)
        compressedlength = 0
        instart = 0
        # we do need to buffer the output, as the first byte indicates which blocks are compressed.
        # this version does not use a look-ahead, so we do not need to buffer more than 8 blocks at a time.
        # (a block is at most 4 bytes long)
        outbuffer = bytearray(8 * 4 + 1)
        outbuffer[0] = 0
        bufferlength = 1
        bufferedblocks = 0
        readbytes = 0
        while readbytes < inlength:
            # If 8 blocks are buffered, write them and reset the buffer
            # we can only buffer 8 blocks at a time.
            if bufferedblocks == 8:
                out.write(outbuffer[:bufferlength])
                compressedlength += bufferlength
                # reset the buffer
                outbuffer[0] = 0
                bufferlength = 1
                bufferedblocks = 0
            # determine if we're dealing with a compressed or raw block.
            # it is a compressed block when the next 3 or more bytes can be copied from
            # somewhere in the set of already compressed bytes.
            oldlength = min(readbytes, 0x1000)
            length, disp = getOccurrenceLength(indata, instart + readbytes, min(inlength - readbytes, 0x10110), instart + readbytes - oldlength, oldlength, mindisp)
            # length not 3 or more? next byte is raw data
            if length < 3:
                outbuffer[bufferlength] = indata[instart + readbytes]
                bufferlength += 1
                readbytes += 1
            else:
                # 3 or more bytes can be copied? next (length) bytes will be compressed into 2 bytes
                readbytes += length
                # mark the next block as compressed
                outbuffer[0] |= (1 << (7 - bufferedblocks))
                if length >= 0x110:
                    # case 1: 1(B CD E)(F GH) + (0x111)(0x1) = (LEN)(DISP)
                    outbuffer[bufferlength] = 0x10
                    outbuffer[bufferlength] |= ((length - 0x111) >> 12) & 0x0F
                    bufferlength += 1
                    outbuffer[bufferlength] = ((length - 0x111) >> 4) & 0xFF
                    bufferlength += 1
                    outbuffer[bufferlength] = ((length - 0x111) << 4) & 0xF0
                elif length > 0x10:
                    # case 0; 0(B C)(D EF) + (0x11)(0x1) = (LEN)(DISP)
                    outbuffer[bufferlength] = 0x00
                    outbuffer[bufferlength] |= ((length - 0x11) >> 4) & 0x0F
                    bufferlength += 1
                    outbuffer[bufferlength] = ((length - 0x11) << 4) & 0xF0
                else:
                    # case > 1: (A)(B CD) + (0x1)(0x1) = (LEN)(DISP)
                    outbuffer[bufferlength] = ((length - 1) << 4) & 0xF0
                # the last 1.5 bytes are always the disp
                outbuffer[bufferlength] |= ((disp - 1) >> 8) & 0x0F
                bufferlength += 1
                outbuffer[bufferlength] = (disp - 1) & 0xFF
                bufferlength += 1
            bufferedblocks += 1
        # copy the remaining blocks to the output
        if bufferedblocks > 0:
            out.write(outbuffer[:bufferlength])
            compressedlength += bufferlength
        out.seek(0)
        return out.read()


def getOccurrenceLength(indata, newptr, newlength, oldptr, oldlength, mindisp=1):
    disp = 0
    if newlength == 0:
        return 0
    maxlength = 0
    # try every possible 'disp' value (disp = oldLength - i)
    for i in range(oldlength - mindisp):
        # work from the start of the old data to the end, to mimic the original implementation's behaviour
        # (and going from start to end or from end to start does not influence the compression ratio anyway)
        currentoldstart = oldptr + i
        currentlength = 0
        # determine the length we can copy if we go back (oldLength - i) bytes
        # always check the next 'newLength' bytes, and not just the available 'old' bytes,
        # as the copied data can also originate from what we're currently trying to compress.
        for j in range(newlength):
            # stop when the bytes are no longer the same
            if indata[currentoldstart + j] != indata[newptr + j]:
                break
            currentlength += 1
        # update the optimal value
        if currentlength > maxlength:
            maxlength = currentlength
            disp = oldlength - i
            # if we cannot do better anyway, stop trying.
            if maxlength == newlength:
                break
    return maxlength, disp


def decompressRLE(data, complength, decomplength):
    with common.Stream() as out:
        while out.tell() < decomplength:
            flag = data.readByte()
            compressed = (flag & 0x80) > 0
            length = flag & 0x7f
            if compressed:
                length += 3
                byte = data.readByte()
                for i in range(length):
                    out.writeByte(byte)
            else:
                length += 1
                out.write(data.read(length))
        out.seek(0)
        return out.read()


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


def decompressHuffman(data, complength, decomplength, numbits=8, little=True):
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
    len = 0
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
                len, blen, fbuf = getBits(2, f, blen, fbuf)
                len += 2
                data = f.readSByte()
                # Use ctypes to correctly handle int overflow
                pos = ctypes.c_int(data | 0xffffff00).value
            else:
                pos = ctypes.c_int((f.readSByte() << 8) | 0xffff0000).value
                pos |= f.readSByte() & 0xff
                len = pos & 0x07
                pos >>= 3
                if len == 0:
                    len = (f.readSByte() & 0xff) + 1
                else:
                    len += 2
            pos += dptr
            for i in range(len):
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
