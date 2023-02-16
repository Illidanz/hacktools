#ifndef __CEXT_INC__
#define __CEXT_INC__

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#define MALLOC_CHECK(var) if (var == NULL) { PyErr_NoMemory(); return NULL; }
#define ERROR_CHECK(cond, error) if (cond) { PyErr_SetString(PyExc_ValueError, error); return NULL; }

#endif
