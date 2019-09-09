from hacktools import common


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


def getOccurrenceLength(indata, newptr, newlength, oldptr, oldlength, mindisp=1):
    disp = 0
    if newlength == 0:
        return 0
    maxlength = 0
    disp = 0
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


def compressLZ10(indata):
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
            # If 8 blocks are bufferd, write them and reset the buffer
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
            length, disp = getOccurrenceLength(indata, instart + readbytes, min(inlength - readbytes, 0x12), instart + readbytes - oldlength, oldlength)
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
    # TODO
    return bytes()


def compressLZ11(indata):
    # TODO
    return bytes()
