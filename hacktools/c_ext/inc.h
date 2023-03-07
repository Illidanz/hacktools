#ifndef __CEXT_INC__
#define __CEXT_INC__

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#define MALLOC_CHECK(var) if (var == NULL) { PyErr_NoMemory(); return NULL; }
#define ERROR_CHECK(cond, error) if (cond) { PyErr_SetString(PyExc_ValueError, error); return NULL; }
#define READ_32(buf, pos) (buf[pos] | (buf[pos + 1] << 8) | (buf[pos + 2] << 16) | (buf[pos + 3] << 24))

#endif
