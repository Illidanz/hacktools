#include "inc.h"

// Implementations based on Kurimuu's Kontract
// https://github.com/IcySon55/Kuriimu/tree/master/src/Kontract/Compression

static PyObject* decompressLZ10(PyObject* m, PyObject* args, PyObject* kwargs)
{
    static char *kwlist[] = { "data", "decomplength", "dispextra", NULL };

    unsigned char* data;
    size_t datalength;
    unsigned int decomplength;
    int dispextra;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s#Ii", kwlist, &data, &datalength, &decomplength, &dispextra))
        return NULL;

    unsigned int complength = (unsigned int)datalength;
    unsigned char* out = PyMem_Malloc(decomplength);
    MALLOC_CHECK(out);

    unsigned int readbytes = 0;
    unsigned int bufferlength = 0x1000;
    unsigned int bufferoffset = 0;
    unsigned char* buffer = PyMem_Malloc(bufferlength);
    for (int i = 0; i < bufferlength; ++i)
        buffer[i] = 0;
    MALLOC_CHECK(buffer);

    unsigned int currentoutsize = 0;
    int flags = 0;
    int mask = 1;
    while (currentoutsize < decomplength)
    {
        // Update the mask. If all flag bits have been read, get a new set.
        // the current mask is the mask used in the previous run. So if it masks the
        // last flag bit, get a new flags byte.
        if (mask == 1)
        {
            ERROR_CHECK(readbytes >= complength, "Not enough data.");
            flags = data[readbytes++];
            ERROR_CHECK(flags < 0, "Stream too short.");
            mask = 0x80;
        }
        else
        {
            mask >>= 1;
        }
        // bit = 1 <=> compressed.
        if ((flags & mask) > 0)
        {
            // Get length and displacement('disp') values from next 2 bytes
            // there are < 2 bytes available when the end is at most 1 byte away
            ERROR_CHECK(readbytes + 1 >= complength, "Not enough data.");
            int byte1 = data[readbytes++];
            int byte2 = data[readbytes++];
            ERROR_CHECK(byte2 < 0, "Stream too short.");
            // the number of bytes to copy
            int length = byte1 >> 4;
            length += 3;
            // from where the bytes should be copied (relatively)
            int disp = ((byte1 & 0x0f) << 8) | byte2;
            disp += dispextra;
            ERROR_CHECK(disp > (int)currentoutsize, "Cannot go back more than already written.");

            int bufidx = bufferoffset + bufferlength - disp;
            for (int i = 0; i < length; ++i)
            {
                unsigned char next = buffer[bufidx % bufferlength];
                ++bufidx;
                out[currentoutsize + i] = next;
                buffer[bufferoffset] = next;
                bufferoffset = (bufferoffset + 1) % bufferlength;
            }
            currentoutsize += length;
        }
        else
        {
            ERROR_CHECK(readbytes >= complength, "Not enough data.");
            int next = data[readbytes++];
            ERROR_CHECK(next < 0, "Stream too short.");
            out[currentoutsize++] = (unsigned char)next;
            buffer[bufferoffset] = (unsigned char)next;
            bufferoffset = (bufferoffset + 1) % bufferlength;
        }
    }

    PyObject *output = PyBytes_FromStringAndSize(out, decomplength);
    PyMem_Free(out);
    PyMem_Free(buffer);
    return output;
}

static PyObject* decompressLZ11(PyObject* m, PyObject* args, PyObject* kwargs)
{
    static char *kwlist[] = { "data", "decomplength", "dispextra", NULL };

    unsigned char* data;
    size_t datalength;
    unsigned int decomplength;
    int dispextra;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s#Ii", kwlist, &data, &datalength, &decomplength, &dispextra))
        return NULL;

    unsigned int complength = (unsigned int)datalength;
    unsigned char* out = PyMem_Malloc(decomplength);
    MALLOC_CHECK(out);
    unsigned int currentoutsize = 0;
    unsigned int readbytes = 0;

    while (currentoutsize < decomplength)
    {
        unsigned char mask = data[readbytes++];
        for (int i = 0; i < 8; ++i)
        {
            if ((mask & 0x80) == 0)
            {
                out[currentoutsize++] = data[readbytes++];
            }
            else
            {
                unsigned char a = data[readbytes++];
                unsigned char b = data[readbytes++];
                int offset = 0;
                int length2 = 0;
                if ((a >> 4) == 0)
                {
                    unsigned char c = data[readbytes++];
                    length2 = (((a & 0xf) << 4) | (b >> 4)) + 0x11;
                    offset = ((b & 0xf) << 8) | c;
                }
                else if ((a >> 4) == 1)
                {
                    unsigned char c = data[readbytes++];
                    unsigned char d = data[readbytes++];
                    length2 = (((a & 0xf) << 12) | (b << 4) | (c >> 4)) + 0x111;
                    offset = ((c & 0xf) << 8) | d;
                }
                else
                {
                    length2 = (a >> 4) + 1;
                    offset = ((a & 0xf) << 8) | b;
                }
                offset += dispextra;
                for (int j = 0; j < length2; ++j)
                {
                    out[currentoutsize] = out[currentoutsize - offset];
                    ++currentoutsize;
                    if (currentoutsize >= decomplength)
                        break;
                }
            }
            if (currentoutsize >= decomplength)
                break;
            mask <<= 1;
        }
    }

    PyObject *output = PyBytes_FromStringAndSize(out, decomplength);
    PyMem_Free(out);
    return output;
}

static int getOccurrenceLength(unsigned char* newptr, int newlength, unsigned char* oldptr, int oldlength, int* outdisp, int mindisp)
{
    int disp = 0;
    if (newlength == 0)
        return 0;
    int maxlength = 0;
    // try every possible 'disp' value (disp = oldLength - i)
    for (int i = 0; i < oldlength - mindisp; ++i)
    {
        // work from the start of the old data to the end, to mimic the original implementation's behaviour
        // (and going from start to end or from end to start does not influence the compression ratio anyway)
        unsigned char* currentoldstart = oldptr + i;
        int currentlength = 0;
        // determine the length we can copy if we go back (oldLength - i) bytes
        // always check the next 'newLength' bytes, and not just the available 'old' bytes,
        // as the copied data can also originate from what we're currently trying to compress.
        for (int j = 0; j < newlength; ++j)
        {
            // stop when the bytes are no longer the same
            if (*(currentoldstart + j) != *(newptr + j))
                break;
            ++currentlength;
        }
        // update the optimal value
        if (currentlength > maxlength)
        {
            maxlength = currentlength;
            disp = oldlength - i;
            // if we cannot do better anyway, stop trying.
            if (maxlength == newlength)
                break;
        }
    }
    *outdisp = disp;
    return maxlength;
}

static PyObject* compressLZ10(PyObject* m, PyObject* args, PyObject* kwargs)
{
    static char *kwlist[] = { "indata", "mindisp", NULL };

    unsigned char* indata;
    size_t inlength;
    int mindisp;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s#i", kwlist, &indata, &inlength, &mindisp))
        return NULL;

    unsigned char* out = PyMem_Malloc(inlength);
    MALLOC_CHECK(out);

    unsigned int compressedlength = 0;
    unsigned char* instart = &indata[0];
    // we do need to buffer the output, as the first byte indicates which blocks are compressed.
    // this version does not use a look-ahead, so we do not need to buffer more than 8 blocks at a time.
    // (a block is at most 4 bytes long)
    unsigned char* outbuffer = PyMem_Malloc(8 * 4 + 1);
    MALLOC_CHECK(outbuffer);
    for (int i = 0; i < 8 * 4 + 1; ++i)
        outbuffer[i] = 0;
    int bufferlength = 1;
    int bufferedblocks = 0;
    int readbytes = 0;
    while (readbytes < inlength)
    {
        // If 8 blocks are buffered, write them and reset the buffer
        // we can only buffer 8 blocks at a time.
        if (bufferedblocks == 8)
        {
            for (int i = 0; i < bufferlength; ++i)
                out[compressedlength++] = outbuffer[i];
            // reset the buffer
            outbuffer[0] = 0;
            bufferlength = 1;
            bufferedblocks = 0;
        }
        // determine if we're dealing with a compressed or raw block.
        // it is a compressed block when the next 3 or more bytes can be copied from
        // somewhere in the set of already compressed bytes.
        int disp;
        int oldlength = readbytes < 0x1000 ? readbytes : 0x1000;
        int newlength = (int)inlength - readbytes;
        if (newlength > 0x12)
            newlength = 0x12;
        int length = getOccurrenceLength(instart + readbytes, newlength, instart + readbytes - oldlength, oldlength, &disp, mindisp);
        // length not 3 or more? next byte is raw data
        if (length < 3)
        {
            outbuffer[bufferlength++] = *(instart + (readbytes++));
        }
        else
        {
            // 3 or more bytes can be copied? next (length) bytes will be compressed into 2 bytes
            readbytes += length;
            // mark the next block as compressed
            outbuffer[0] |= (unsigned char)(1 << (7 - bufferedblocks));
            outbuffer[bufferlength] = (unsigned char)(((length - 3) << 4) & 0xf0);
            outbuffer[bufferlength] |= (unsigned char)(((disp - 1) >> 8) & 0x0f);
            ++bufferlength;
            outbuffer[bufferlength] = (unsigned char)((disp - 1) & 0xff);
            ++bufferlength;
        }
        ++bufferedblocks;
    }
    // copy the remaining blocks to the output
    if (bufferedblocks > 0)
        for (int i = 0; i < bufferlength; ++i)
            out[compressedlength++] = outbuffer[i];

    PyObject *output = PyBytes_FromStringAndSize(out, compressedlength);
    PyMem_Free(outbuffer);
    PyMem_Free(out);
    return output;
}

static PyObject* compressLZ11(PyObject* m, PyObject* args, PyObject* kwargs)
{
    static char *kwlist[] = { "indata", "mindisp", NULL };

    unsigned char* indata;
    size_t inlength;
    int mindisp;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s#i", kwlist, &indata, &inlength, &mindisp))
        return NULL;

    unsigned char* out = PyMem_Malloc(inlength);
    MALLOC_CHECK(out);

    unsigned int compressedlength = 0;
    unsigned char* instart = &indata[0];
    // we do need to buffer the output, as the first byte indicates which blocks are compressed.
    // this version does not use a look-ahead, so we do not need to buffer more than 8 blocks at a time.
    // (a block is at most 4 bytes long)
    unsigned char* outbuffer = PyMem_Malloc(8 * 4 + 1);
    MALLOC_CHECK(outbuffer);
    for (int i = 0; i < 8 * 4 + 1; ++i)
        outbuffer[i] = 0;
    int bufferlength = 1;
    int bufferedblocks = 0;
    int readbytes = 0;
    while (readbytes < inlength)
    {
        // If 8 blocks are buffered, write them and reset the buffer
        // we can only buffer 8 blocks at a time.
        if (bufferedblocks == 8)
        {
            for (int i = 0; i < bufferlength; ++i)
                out[compressedlength++] = outbuffer[i];
            // reset the buffer
            outbuffer[0] = 0;
            bufferlength = 1;
            bufferedblocks = 0;
        }
        // determine if we're dealing with a compressed or raw block.
        // it is a compressed block when the next 3 or more bytes can be copied from
        // somewhere in the set of already compressed bytes.
        int disp;
        int oldlength = readbytes < 0x1000 ? readbytes : 0x1000;
        int newlength = (int)inlength - readbytes;
        if (newlength > 0x10110)
            newlength = 0x10110;
        int length = getOccurrenceLength(instart + readbytes, newlength, instart + readbytes - oldlength, oldlength, &disp, mindisp);
        // length not 3 or more? next byte is raw data
        if (length < 3)
        {
            outbuffer[bufferlength++] = *(instart + (readbytes++));
        }
        else
        {
            // 3 or more bytes can be copied? next (length) bytes will be compressed into 2 bytes
            readbytes += length;
            // mark the next block as compressed
            outbuffer[0] |= (unsigned char)(1 << (7 - bufferedblocks));
            if (length >= 0x110)
            {
                // case 1: 1(B CD E)(F GH) + (0x111)(0x1) = (LEN)(DISP)
                outbuffer[bufferlength] = 0x10;
                outbuffer[bufferlength] |= (unsigned char)(((length - 0x111) >> 12) & 0x0f);
                ++bufferlength;
                outbuffer[bufferlength] = (unsigned char)(((length - 0x111) >> 4) & 0xff);
                ++bufferlength;
                outbuffer[bufferlength] = (unsigned char)(((length - 0x111) << 4) & 0xf0);
            }
            else if (length > 0x10)
            {
                // case 0; 0(B C)(D EF) + (0x11)(0x1) = (LEN)(DISP)
                outbuffer[bufferlength] = 0x00;
                outbuffer[bufferlength] |= (unsigned char)(((length - 0x11) >> 4) & 0x0f);
                ++bufferlength;
                outbuffer[bufferlength] = (unsigned char)(((length - 0x11) << 4) & 0xf0);
            }
            else
            {
                // case > 1: (A)(B CD) + (0x1)(0x1) = (LEN)(DISP)
                outbuffer[bufferlength] = (unsigned char)(((length - 1) << 4) & 0xf0);
            }
            // the last 1.5 bytes are always the disp
            outbuffer[bufferlength] |= (unsigned char)(((disp - 1) >> 8) & 0x0f);
            ++bufferlength;
            outbuffer[bufferlength] = (unsigned char)((disp - 1) & 0xff);
            ++bufferlength;
        }
        ++bufferedblocks;
    }
    // copy the remaining blocks to the output
    if (bufferedblocks > 0)
        for (int i = 0; i < bufferlength; ++i)
            out[compressedlength++] = outbuffer[i];

    PyObject *output = PyBytes_FromStringAndSize(out, compressedlength);
    PyMem_Free(outbuffer);
    PyMem_Free(out);
    return output;
}

static PyMethodDef Cmp_lzssMethods[] = {
    {"decompressLZ10", (PyCFunction)decompressLZ10, METH_VARARGS | METH_KEYWORDS, "Decompress lz10 data."},
    {"compressLZ10", (PyCFunction)compressLZ10, METH_VARARGS | METH_KEYWORDS, "Compress lz10 data."},
    {"decompressLZ11", (PyCFunction)decompressLZ11, METH_VARARGS | METH_KEYWORDS, "Decompress lz11 data."},
    {"compressLZ11", (PyCFunction)compressLZ11, METH_VARARGS | METH_KEYWORDS, "Compress lz11 data."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef cmp_lzssmodule = {
    PyModuleDef_HEAD_INIT,
    "cmp_lzss",
    "LZSS functions.",
    -1,
    Cmp_lzssMethods
};

PyMODINIT_FUNC PyInit_cmp_lzss(void)
{
    return PyModule_Create(&cmp_lzssmodule);
}
