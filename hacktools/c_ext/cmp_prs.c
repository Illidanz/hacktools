#include "inc.h"

// PRS scheme, an LZ77 variant used by several SEGA games.
// Control bits are read most significant first, refilling the control byte inline.

// Reads n control bits, most significant first, refilling the buffer from the stream when empty.
// Returns -1 when the stream runs out of data.
static int getBits(int n, unsigned char* data, unsigned int slen, unsigned int* readbytes, int* blen, unsigned char* fbuf)
{
    int retv = 0;
    while (n > 0)
    {
        retv <<= 1;
        if (*blen == 0)
        {
            if (*readbytes >= slen)
                return -1;
            *fbuf = data[(*readbytes)++];
            *blen = 8;
        }
        if (*fbuf & 0x80)
            retv |= 1;
        *fbuf <<= 1;
        --(*blen);
        --n;
    }
    return retv;
}

PyDoc_STRVAR(decompressPRS_doc,
"decompressPRS($module, /, data, decomplength)\n"
"--\n"
"\n"
"Decompress PRS data, an LZ77 variant.\n"
"\n"
"Args:\n"
"    data (bytes): Compressed data to read.\n"
"    decomplength (int): Length of the decompressed data.\n"
"\n"
"Returns:\n"
"    bytes: The decompressed data.");

static PyObject* decompressPRS(PyObject* m, PyObject* args, PyObject* kwargs)
{
    static char *kwlist[] = { "data", "decomplength", NULL };

    unsigned char* data;
    size_t datalength;
    unsigned int decomplength;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s#I", kwlist, &data, &datalength, &decomplength))
        return NULL;

    unsigned int slen = (unsigned int)datalength;
    unsigned char* dbuf = PyMem_Malloc(decomplength > 0 ? decomplength : 1);
    MALLOC_CHECK(dbuf);
    // Zero-fill so streams that end before decomplength give deterministic output
    memset(dbuf, 0, decomplength > 0 ? decomplength : 1);

    unsigned int readbytes = 0;
    unsigned int dptr = 0;
    int blen = 0;
    unsigned char fbuf = 0;
    while (readbytes < slen && dptr < decomplength)
    {
        int flag = getBits(1, data, slen, &readbytes, &blen, &fbuf);
        ERROR_CHECK(flag < 0, "Not enough data.");
        if (flag == 1)
        {
            // Literal byte
            if (dptr < decomplength)
            {
                ERROR_CHECK(readbytes >= slen, "Not enough data.");
                dbuf[dptr++] = data[readbytes++];
            }
        }
        else
        {
            int plen = 0;
            int pos = 0;
            flag = getBits(1, data, slen, &readbytes, &blen, &fbuf);
            ERROR_CHECK(flag < 0, "Not enough data.");
            if (flag == 0)
            {
                // Short copy: 2 length bits and a 1-byte offset
                plen = getBits(2, data, slen, &readbytes, &blen, &fbuf);
                ERROR_CHECK(plen < 0, "Not enough data.");
                plen += 2;
                ERROR_CHECK(readbytes >= slen, "Not enough data.");
                // The offset is negative, in the [-256, -1] range
                pos = (int)data[readbytes++] - 0x100;
            }
            else
            {
                // Long copy: 13-bit offset and 3-bit length, followed by a length byte when the length bits are 0
                ERROR_CHECK(readbytes + 1 >= slen, "Not enough data.");
                // The offset is negative, in the [-8192, -1] range
                pos = ((data[readbytes] << 8) | data[readbytes + 1]) - 0x10000;
                readbytes += 2;
                // A zero offset word encodes both the end-of-stream marker and a copy from
                // exactly -8192 with the length bits at 0 (8ing's Wii FPK encoder emits the
                // latter). Treat it as a copy when the distance is reachable.
                if (pos == -0x10000 && dptr < 8192)
                    break;
                plen = pos & 0x07;
                pos >>= 3;
                if (plen == 0)
                {
                    ERROR_CHECK(readbytes >= slen, "Not enough data.");
                    plen = data[readbytes++] + 1;
                }
                else
                    plen += 2;
            }
            pos += (int)dptr;
            // Some encoders reference data before the stream start, expecting a zero-filled buffer
            for (int i = 0; i < plen; ++i)
            {
                if (dptr < decomplength)
                    dbuf[dptr++] = pos < 0 ? 0 : dbuf[pos];
                ++pos;
            }
        }
    }

    PyObject *output = PyBytes_FromStringAndSize(dbuf, decomplength);
    PyMem_Free(dbuf);
    return output;
}

// Output writer that buffers the current control byte and the data bytes that belong to it,
// so that the decompressor finds a new control byte in the stream exactly when it needs one.
typedef struct
{
    unsigned char* out;
    unsigned int outlen;
    unsigned char ctrl;
    int bits;
    unsigned char pending[32];
    int pendinglen;
} PRSWriter;

static void prsFlush(PRSWriter* w)
{
    w->out[w->outlen++] = (unsigned char)(w->ctrl << (8 - w->bits));
    for (int i = 0; i < w->pendinglen; ++i)
        w->out[w->outlen++] = w->pending[i];
    w->ctrl = 0;
    w->bits = 0;
    w->pendinglen = 0;
}

// Flush when the control byte is full. Called after every control bit, except that the last
// bit of an operation is only saved after its data bytes so they are flushed together.
static void prsSave(PRSWriter* w)
{
    if (w->bits == 8)
        prsFlush(w);
}

static void prsPutBitNoSave(PRSWriter* w, int bit)
{
    w->ctrl = (unsigned char)((w->ctrl << 1) | (bit & 1));
    ++w->bits;
}

static void prsPutBit(PRSWriter* w, int bit)
{
    prsPutBitNoSave(w, bit);
    prsSave(w);
}

static void prsPutData(PRSWriter* w, unsigned char byte)
{
    w->pending[w->pendinglen++] = byte;
}

// Hash chains linking every position that shares a 3-byte prefix, newest first,
// so the matcher only visits candidates that can actually match 3+ bytes.
#define PRS_HASH_BITS 16
#define PRS_HASH_SIZE (1 << PRS_HASH_BITS)

typedef struct
{
    int* head;
    int* prev;
} PRSMatcher;

static unsigned int prsHash(unsigned char* p)
{
    unsigned int x = ((unsigned int)p[0] << 16) | ((unsigned int)p[1] << 8) | p[2];
    return (x * 2654435761u) >> (32 - PRS_HASH_BITS);
}

static void prsInsert(PRSMatcher* mt, unsigned char* src, unsigned int srclen, unsigned int pos)
{
    if (pos + 2 < srclen)
    {
        unsigned int h = prsHash(src + pos);
        mt->prev[pos] = mt->head[h];
        mt->head[h] = (int)pos;
    }
}

// Find the longest match for src[pos] in the previous 8191 bytes, preferring the closest one.
static int findMatch(PRSMatcher* mt, unsigned char* src, unsigned int srclen, unsigned int pos, int* outdisp)
{
    int maxlen = srclen - pos < 256 ? (int)(srclen - pos) : 256;
    int bestlen = 0;
    int bestdisp = 0;
    // Chains are newest first, so candidates are visited in increasing displacement
    // order and the closest of the longest matches wins, like with a linear scan
    if (pos + 2 < srclen)
    {
        // Displacement 8192 would encode as a zero offset word, which decompressors
        // can read as the end-of-stream marker, so only go back up to 8191 bytes
        for (int cand = mt->head[prsHash(src + pos)]; cand >= 0 && pos - cand <= 8191; cand = mt->prev[cand])
        {
            unsigned char* old = src + cand;
            int length = 0;
            // The copy can overlap with the data being compressed, so always check up to maxlen bytes
            while (length < maxlen && old[length] == src[pos + length])
                ++length;
            if (length >= 3 && length > bestlen)
            {
                bestlen = length;
                bestdisp = (int)(pos - cand);
                // If we cannot do better anyway, stop trying
                if (bestlen == maxlen)
                    break;
            }
        }
    }
    // The chains cannot find 2-byte matches, look for one in the short copy range
    if (bestlen < 3 && maxlen >= 2)
    {
        int maxdisp = pos < 256 ? (int)pos : 256;
        for (int disp = 1; disp <= maxdisp; ++disp)
        {
            if (src[pos - disp] == src[pos] && src[pos - disp + 1] == src[pos + 1])
            {
                bestlen = 2;
                bestdisp = disp;
                break;
            }
        }
    }
    *outdisp = bestdisp;
    return bestlen;
}

PyDoc_STRVAR(compressPRS_doc,
"compressPRS($module, /, indata)\n"
"--\n"
"\n"
"Compress data with the PRS scheme, an LZ77 variant.\n"
"\n"
"Args:\n"
"    indata (bytes): Data to compress.\n"
"\n"
"Returns:\n"
"    bytes: The compressed data.");

static PyObject* compressPRS(PyObject* m, PyObject* args, PyObject* kwargs)
{
    static char *kwlist[] = { "indata", NULL };

    unsigned char* src;
    size_t srclen;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s#", kwlist, &src, &srclen))
        return NULL;

    // Worst case: uncompressible data emits 1 control byte per 8 literal bytes
    size_t outcap = srclen + srclen / 8 + 16;
    unsigned char* out = PyMem_Malloc(outcap);
    MALLOC_CHECK(out);

    PRSMatcher mt;
    mt.head = PyMem_Malloc(PRS_HASH_SIZE * sizeof(int));
    mt.prev = PyMem_Malloc((srclen > 0 ? srclen : 1) * sizeof(int));
    if (mt.head == NULL || mt.prev == NULL)
    {
        PyMem_Free(mt.head);
        PyMem_Free(mt.prev);
        PyMem_Free(out);
        PyErr_NoMemory();
        return NULL;
    }
    for (int i = 0; i < PRS_HASH_SIZE; ++i)
        mt.head[i] = -1;

    PRSWriter w = { out, 0, 0, 0, { 0 }, 0 };
    unsigned int pos = 0;
    while (pos < srclen)
    {
        int disp;
        int length = findMatch(&mt, src, (unsigned int)srclen, pos, &disp);
        int step = 1;
        if (length >= 3 || (length == 2 && disp <= 256))
        {
            if (disp <= 256 && length <= 5)
            {
                // Short copy: flag bits 0 0, 2 length bits, 1-byte offset
                prsPutBit(&w, 0);
                prsPutBit(&w, 0);
                prsPutBit(&w, ((length - 2) >> 1) & 1);
                prsPutBitNoSave(&w, (length - 2) & 1);
                prsPutData(&w, (unsigned char)(-disp & 0xff));
            }
            else
            {
                // Long copy: flag bits 0 1, 13-bit offset and 3-bit length,
                // followed by a length byte when the length does not fit in 3 bits
                prsPutBit(&w, 0);
                prsPutBitNoSave(&w, 1);
                int value = ((-disp & 0x1fff) << 3) | (length <= 9 ? length - 2 : 0);
                prsPutData(&w, (unsigned char)(value >> 8));
                prsPutData(&w, (unsigned char)(value & 0xff));
                if (length > 9)
                    prsPutData(&w, (unsigned char)(length - 1));
            }
            prsSave(&w);
            step = length;
        }
        else
        {
            // Literal byte: flag bit 1
            prsPutBitNoSave(&w, 1);
            prsPutData(&w, src[pos]);
            prsSave(&w);
        }
        // Add the consumed positions to the hash chains
        for (int i = 0; i < step; ++i)
            prsInsert(&mt, src, (unsigned int)srclen, pos + i);
        pos += step;
    }
    // End-of-stream marker: a long copy with a zero offset word
    prsPutBit(&w, 0);
    prsPutBitNoSave(&w, 1);
    prsPutData(&w, 0);
    prsPutData(&w, 0);
    // Flush the last partial control byte along with its data
    prsFlush(&w);

    PyObject *output = PyBytes_FromStringAndSize(out, w.outlen);
    PyMem_Free(mt.head);
    PyMem_Free(mt.prev);
    PyMem_Free(out);
    return output;
}

static PyMethodDef Cmp_prsMethods[] = {
    {"compressPRS", (PyCFunction)compressPRS, METH_VARARGS | METH_KEYWORDS, compressPRS_doc},
    {"decompressPRS", (PyCFunction)decompressPRS, METH_VARARGS | METH_KEYWORDS, decompressPRS_doc},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef cmp_prsmodule = {
    PyModuleDef_HEAD_INIT,
    "cmp_prs",
    "C implementation of the PRS compression scheme, an LZ77 variant.",
    -1,
    Cmp_prsMethods
};

PyMODINIT_FUNC PyInit_cmp_prs(void)
{
    return moduleCreate(&cmp_prsmodule);
}
