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

static PyMethodDef Cmp_miscMethods[] = {
    {"decompressRLE", (PyCFunction)decompressRLE, METH_VARARGS | METH_KEYWORDS, decompressRLE_doc},
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
