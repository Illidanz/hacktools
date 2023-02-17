#include "inc.h"

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
    {"decompressRLE", (PyCFunction)decompressRLE, METH_VARARGS | METH_KEYWORDS, "Decompress RLE data."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef cmp_miscmodule = {
    PyModuleDef_HEAD_INIT,
    "cmp_misc",
    "Misc functions.",
    -1,
    Cmp_miscMethods
};

PyMODINIT_FUNC PyInit_cmp_misc(void)
{
    return PyModule_Create(&cmp_miscmodule);
}
