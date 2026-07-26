#ifndef __CEXT_INC__
#define __CEXT_INC__

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#define MALLOC_CHECK(var) if (var == NULL) { PyErr_NoMemory(); return NULL; }
#define ERROR_CHECK(cond, error) if (cond) { PyErr_SetString(PyExc_ValueError, error); return NULL; }
#define READ_32(buf, pos) (buf[pos] | (buf[pos + 1] << 8) | (buf[pos + 2] << 16) | (buf[pos + 3] << 24))
#define WRITE_32(buf, pos, val) buf[pos] = (unsigned char)((val) & 0xff); buf[pos + 1] = (unsigned char)(((val) >> 8) & 0xff); \
                                buf[pos + 2] = (unsigned char)(((val) >> 16) & 0xff); buf[pos + 3] = (unsigned char)(((val) >> 24) & 0xff);

// Create the module, declaring that it can run without the GIL on free-threaded builds.
// All the modules are stateless, only working on local buffers, so this is safe.
static inline PyObject* moduleCreate(struct PyModuleDef* def)
{
    PyObject* module = PyModule_Create(def);
#ifdef Py_GIL_DISABLED
    if (module != NULL)
        PyUnstable_Module_SetGIL(module, Py_MOD_GIL_NOT_USED);
#endif
    return module;
}

#endif
