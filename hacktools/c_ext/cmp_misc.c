#include "inc.h"

PyDoc_STRVAR(decompressRLE_doc,
"decompressRLE($module, /, data, decomplength)\n"
"--\n"
"\n"
"Decompress RLE-compressed data, as used by the GBA and NDS BIOS.\n"
"\n"
"Args:\n"
"    data (bytes): Compressed data to read, without the 4-byte header.\n"
"    decomplength (int): Length of the decompressed data.\n"
"\n"
"Returns:\n"
"    bytes: The decompressed data.");

static PyObject* decompressRLE(PyObject* m, PyObject* args, PyObject* kwargs)
{
    static char *kwlist[] = { "data", "decomplength", NULL };

    unsigned char* data;
    size_t datalength;
    unsigned int decomplength;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s#I", kwlist, &data, &datalength, &decomplength))
        return NULL;

    unsigned int complength = (unsigned int)datalength;
    unsigned char* out = PyMem_Malloc(decomplength);
    MALLOC_CHECK(out);

    unsigned int readbytes = 0;
    unsigned int writebytes = 0;
    while (writebytes < decomplength)
    {
        int flag = data[readbytes++];
        int length = flag & 0x7f;
        if ((flag & 0x80) > 0)
        {
            length += 3;
            unsigned char byte = data[readbytes++];
            for (int i = 0; i < length; ++i)
                out[writebytes++] = byte;
        }
        else
        {
            length += 1;
            for (int i = 0; i < length; ++i)
                out[writebytes++] = data[readbytes++];
        }
    }

    PyObject *output = PyBytes_FromStringAndSize(out, decomplength);
    PyMem_Free(out);
    return output;
}

// Write a pending raw block, if any, and return the updated output length
static unsigned int flushRawBlock(unsigned char* out, unsigned int compressedlength, unsigned char* rawblock, unsigned int rawlength)
{
    if (rawlength > 0)
    {
        out[compressedlength++] = (unsigned char)(rawlength - 1);
        for (unsigned int i = 0; i < rawlength; ++i)
            out[compressedlength++] = rawblock[i];
    }
    return compressedlength;
}

PyDoc_STRVAR(compressRLE_doc,
"compressRLE($module, /, indata)\n"
"--\n"
"\n"
"Compress data with the RLE scheme, as used by the GBA and NDS BIOS.\n"
"\n"
"Args:\n"
"    indata (bytes): Data to compress.\n"
"\n"
"Returns:\n"
"    bytes: The compressed data, without the 4-byte header.");

static PyObject* compressRLE(PyObject* m, PyObject* args, PyObject* kwargs)
{
    static char *kwlist[] = { "indata", NULL };

    unsigned char* indata;
    size_t inlength;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s#", kwlist, &indata, &inlength))
        return NULL;

    // Worst case: uncompressible data emits 1 flag byte per 128 raw bytes,
    // so output can reach inlength + ceil(inlength/128)
    size_t outcap = inlength + (inlength + 127) / 128 + 32;
    unsigned char* out = PyMem_Malloc(outcap);
    MALLOC_CHECK(out);

    unsigned int compressedlength = 0;
    // bytes that could not be compressed are buffered until the block is full
    // or until a run is found, as their amount is written before them
    unsigned char rawblock[0x80];
    unsigned int rawlength = 0;
    size_t readbytes = 0;
    while (readbytes < inlength)
    {
        // determine how many times the current byte is repeated,
        // a run is at most 0x7f + 3 bytes long
        unsigned char byte = indata[readbytes++];
        unsigned int repcount = 1;
        while (readbytes < inlength && repcount < 0x82 && indata[readbytes] == byte)
        {
            ++repcount;
            ++readbytes;
        }
        if (repcount >= 3)
        {
            // 3 or more repetitions are worth a compressed block,
            // which has to come after the raw bytes read until now
            compressedlength = flushRawBlock(out, compressedlength, rawblock, rawlength);
            rawlength = 0;
            out[compressedlength++] = (unsigned char)(0x80 | (repcount - 3));
            out[compressedlength++] = byte;
        }
        else
        {
            // less than 3, buffer them as raw bytes,
            // a raw block is at most 0x7f + 1 bytes long
            for (unsigned int i = 0; i < repcount; ++i)
            {
                rawblock[rawlength++] = byte;
                if (rawlength == 0x80)
                {
                    compressedlength = flushRawBlock(out, compressedlength, rawblock, rawlength);
                    rawlength = 0;
                }
            }
        }
    }
    // write the remaining raw bytes
    compressedlength = flushRawBlock(out, compressedlength, rawblock, rawlength);

    PyObject *output = PyBytes_FromStringAndSize(out, compressedlength);
    PyMem_Free(out);
    return output;
}

static PyMethodDef Cmp_miscMethods[] = {
    {"decompressRLE", (PyCFunction)decompressRLE, METH_VARARGS | METH_KEYWORDS, decompressRLE_doc},
    {"compressRLE", (PyCFunction)compressRLE, METH_VARARGS | METH_KEYWORDS, compressRLE_doc},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef cmp_miscmodule = {
    PyModuleDef_HEAD_INIT,
    "cmp_misc",
    "C implementations of miscellaneous compression schemes.",
    -1,
    Cmp_miscMethods
};

PyMODINIT_FUNC PyInit_cmp_misc(void)
{
    return moduleCreate(&cmp_miscmodule);
}
