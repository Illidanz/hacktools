#include "inc.h"

// Free the buffer before raising, as the checks happen after allocating it
#define ERROR_CHECK_FREE(cond, error, ptr) if (cond) { PyMem_Free(ptr); PyErr_SetString(PyExc_ValueError, error); return NULL; }

// A tree can hold at most 256 leaves, one per possible value, plus the 255 branches joining them
#define MAX_NODES 512
// With at most 256 leaves the tree is at most 255 levels deep, so codes are at most 255 bits long
#define MAX_CODE_BITS 256

PyDoc_STRVAR(decompressHuffman_doc,
"decompressHuffman($module, /, rawdata, decomplength, numbits=8, little=True)\n"
"--\n"
"\n"
"Decompress Huffman-coded data, as used by the GBA and NDS BIOS.\n"
"\n"
"The data is expected to start with the tree size and the tree itself,\n"
"followed by the 32-bit codeword stream, without the 4-byte header with\n"
"compression type and length.\n"
"\n"
"Args:\n"
"    rawdata (bytes): Compressed data to read.\n"
"    decomplength (int): Length of the decompressed data.\n"
"    numbits (int): Data size in bits, 8 or 4.\n"
"    little (bool): Whether nibbles are ordered low-first when numbits is 4.\n"
"\n"
"Returns:\n"
"    bytes: The decompressed data.");

static PyObject* decompressHuffman(PyObject* m, PyObject* args, PyObject* kwargs)
{
    static char *kwlist[] = { "rawdata", "decomplength", "numbits", "little", NULL };

    unsigned char* rawdata;
    size_t datalength;
    unsigned int decomplength;
    int numbits = 8;
    int little = 1;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s#I|ip", kwlist, &rawdata, &datalength, &decomplength, &numbits, &little))
        return NULL;
    ERROR_CHECK(numbits != 8 && numbits != 4, "Data size must be 8 or 4 bits.");
    ERROR_CHECK(datalength < 2, "Not enough data.");

    unsigned int treesize = rawdata[0];
    unsigned int treeroot = rawdata[1];
    unsigned char* treebuffer = rawdata + 2;
    size_t treelength = (size_t)treesize * 2;
    ERROR_CHECK(datalength < 2 + treelength, "Not enough data.");

    // Every written byte holds numbits bits of the decompressed data
    size_t outlength = (size_t)decomplength * (8 / numbits);
    unsigned char* out = PyMem_Malloc(outlength > 0 ? outlength : 1);
    MALLOC_CHECK(out);

    size_t readbytes = 2 + treelength;
    ERROR_CHECK_FREE(readbytes + 4 > datalength, "Not enough data.", out);
    unsigned int code = READ_32(rawdata, readbytes);
    readbytes += 4;

    size_t writebytes = 0;
    unsigned int i = 0;
    unsigned int next = 0;
    unsigned int pos = treeroot;
    while (writebytes < outlength)
    {
        // All the bits of the current codeword have been read, get a new one
        if (i == 32)
        {
            ERROR_CHECK_FREE(readbytes + 4 > datalength, "Not enough data.", out);
            code = READ_32(rawdata, readbytes);
            readbytes += 4;
            i = 0;
        }
        next += (pos & 0x3f) * 2 + 2;
        unsigned int direction = ((code >> (31 - i)) & 1) == 0 ? 2 : 1;
        int leaf = (((pos >> 5) >> direction) & 1) != 0;
        ERROR_CHECK_FREE(next - direction >= treelength, "Tree offset out of range.", out);
        pos = treebuffer[next - direction];
        if (leaf)
        {
            out[writebytes++] = (unsigned char)(pos & 0xff);
            pos = treeroot;
            next = 0;
        }
        ++i;
    }

    // Pack the nibbles back into bytes
    if (numbits == 4)
    {
        for (unsigned int j = 0; j < decomplength; ++j)
        {
            unsigned char b1 = out[2 * j + 1];
            unsigned char b2 = out[2 * j];
            if (little)
                out[j] = (unsigned char)((b1 * 16 + b2) & 0xff);
            else
                out[j] = (unsigned char)((b2 * 16 + b1) & 0xff);
        }
    }

    PyObject *output = PyBytes_FromStringAndSize(out, decomplength);
    PyMem_Free(out);
    return output;
}

// Node of the binary tree built by compressHuffman
typedef struct HuffNode
{
    unsigned int freqcount;
    int code;
    int score;
    int haschildren;
    struct HuffNode* children[2];
} HuffNode;

// Sort the nodes by frequency, keeping the order of equal elements.
// The list is always sorted except for the node appended by the last iteration,
// so the insertion sort only has to move that one back into place.
static void sortByFreq(HuffNode** freq, int freqlen)
{
    for (int i = 1; i < freqlen; ++i)
    {
        HuffNode* node = freq[i];
        int j = i - 1;
        while (j >= 0 && freq[j]->freqcount > node->freqcount)
        {
            freq[j + 1] = freq[j];
            --j;
        }
        freq[j + 1] = node;
    }
}

// Store the code of every leaf node under this node as a string of 0 and 1 bits
static void getHuffCodes(HuffNode* node, unsigned char* seed, int seedlen, unsigned char* codebits, int* codelengths)
{
    if (!node->haschildren)
    {
        for (int i = 0; i < seedlen; ++i)
            codebits[node->code * MAX_CODE_BITS + i] = seed[i];
        codelengths[node->code] = seedlen;
        return;
    }
    for (int i = 0; i < 2; ++i)
    {
        seed[seedlen] = (unsigned char)i;
        getHuffCodes(node->children[i], seed, seedlen + 1, codebits, codelengths);
    }
}

PyDoc_STRVAR(compressHuffman_doc,
"compressHuffman($module, /, indata, numbits=8, little=True)\n"
"--\n"
"\n"
"Compress data with Huffman coding, as used by the GBA and NDS BIOS.\n"
"\n"
"The output starts with the tree size and the tree itself, followed by\n"
"the 32-bit codeword stream. The 4-byte header with compression type and\n"
"length is not included and should be written separately.\n"
"\n"
"Args:\n"
"    indata (bytes): Data to compress.\n"
"    numbits (int): Data size in bits, 8 or 4.\n"
"    little (bool): Whether nibbles are ordered low-first when numbits is 4.\n"
"\n"
"Returns:\n"
"    bytes: The compressed data.");

static PyObject* compressHuffman(PyObject* m, PyObject* args, PyObject* kwargs)
{
    static char *kwlist[] = { "indata", "numbits", "little", NULL };

    unsigned char* indata;
    size_t inlength;
    int numbits = 8;
    int little = 1;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s#|ip", kwlist, &indata, &inlength, &numbits, &little))
        return NULL;
    ERROR_CHECK(numbits != 8 && numbits != 4, "Data size must be 8 or 4 bits.");
    ERROR_CHECK(inlength == 0, "No data to compress.");

    // Read indata as nibbles if numbits is 4
    unsigned char* workdata = indata;
    size_t worklength = inlength;
    unsigned char* nibbles = NULL;
    if (numbits == 4)
    {
        nibbles = PyMem_Malloc(inlength * 2);
        MALLOC_CHECK(nibbles);
        for (size_t i = 0; i < inlength; ++i)
        {
            unsigned char b1 = indata[i] % 16;
            unsigned char b2 = indata[i] / 16;
            nibbles[2 * i] = little ? b1 : b2;
            nibbles[2 * i + 1] = little ? b2 : b1;
        }
        workdata = nibbles;
        worklength = inlength * 2;
    }

    // Get frequencies
    unsigned int freqcount[256] = { 0 };
    for (size_t i = 0; i < worklength; ++i)
        ++freqcount[workdata[i]];

    HuffNode* nodes = PyMem_Malloc(MAX_NODES * sizeof(HuffNode));
    HuffNode** freq = PyMem_Malloc(MAX_NODES * sizeof(HuffNode*));
    HuffNode** lst = PyMem_Malloc(MAX_NODES * sizeof(HuffNode*));
    unsigned char* codebits = PyMem_Malloc(256 * MAX_CODE_BITS);
    if (nodes == NULL || freq == NULL || lst == NULL || codebits == NULL)
    {
        PyMem_Free(nibbles);
        PyMem_Free(nodes);
        PyMem_Free(freq);
        PyMem_Free(lst);
        PyMem_Free(codebits);
        return PyErr_NoMemory();
    }
    int nodecount = 0;
    int freqlen = 0;
    for (int i = 0; i < 256; ++i)
    {
        if (freqcount[i] > 0)
        {
            HuffNode* node = &nodes[nodecount++];
            node->freqcount = freqcount[i];
            node->code = i;
            node->score = 0;
            node->haschildren = 0;
            freq[freqlen++] = node;
        }
    }

    // Add a stub entry in the special case that there's only one item
    if (freqlen == 1)
    {
        HuffNode* node = &nodes[nodecount++];
        node->freqcount = 0;
        node->code = (workdata[0] + 1) & 0xff;
        node->score = 0;
        node->haschildren = 0;
        freq[freqlen++] = node;
    }

    // Sort and create the tree
    while (freqlen > 1)
    {
        sortByFreq(freq, freqlen);
        HuffNode* node = &nodes[nodecount++];
        node->freqcount = freq[0]->freqcount + freq[1]->freqcount;
        node->code = 0;
        node->score = 0;
        node->haschildren = 1;
        node->children[0] = freq[0];
        node->children[1] = freq[1];
        for (int i = 2; i < freqlen; ++i)
            freq[i - 2] = freq[i];
        freqlen -= 2;
        freq[freqlen++] = node;
    }

    // Label nodes to keep bandwidth small
    int lstlen = 0;
    while (freqlen > 0)
    {
        // Take the node with the lowest score, the first one if there are ties
        int best = 0;
        for (int i = 0; i < freqlen; ++i)
        {
            freq[i]->score = freq[i]->code - i;
            if (freq[i]->score < freq[best]->score)
                best = i;
        }
        HuffNode* node = freq[best];
        for (int i = best; i < freqlen - 1; ++i)
            freq[i] = freq[i + 1];
        --freqlen;
        node->code = (lstlen - node->code) & 0xff;
        lst[lstlen++] = node;
        if (node->haschildren)
        {
            for (int i = 1; i >= 0; --i)
            {
                if (node->children[i]->haschildren)
                {
                    node->children[i]->code = lstlen & 0xff;
                    freq[freqlen++] = node->children[i];
                }
            }
        }
    }

    // Convert our list of nodes to a table of bytes -> huffman codes
    int codelengths[256] = { 0 };
    unsigned char seed[MAX_CODE_BITS];
    getHuffCodes(lst[0], seed, 0, codebits, codelengths);

    // The output holds the tree, then the codes padded to a multiple of 32 bits
    size_t totalbits = 0;
    for (int i = 0; i < 256; ++i)
        totalbits += (size_t)freqcount[i] * codelengths[i];
    size_t outcap = 2 + 2 * (size_t)lstlen + 2 + (totalbits + 31) / 32 * 4 + 4;
    unsigned char* out = PyMem_Malloc(outcap);
    if (out == NULL)
    {
        PyMem_Free(nibbles);
        PyMem_Free(nodes);
        PyMem_Free(freq);
        PyMem_Free(lst);
        PyMem_Free(codebits);
        return PyErr_NoMemory();
    }
    size_t outlength = 0;

    // Write header
    out[outlength++] = (unsigned char)(lstlen & 0xff);

    // Write Huffman tree, reusing the now empty freq list to hold it
    HuffNode** tree = freq;
    int treelen = 0;
    tree[treelen++] = lst[0];
    for (int i = 0; i < lstlen; ++i)
    {
        if (lst[i]->haschildren)
            for (int j = 0; j < 2; ++j)
                tree[treelen++] = lst[i]->children[j];
    }
    for (int i = 0; i < treelen; ++i)
    {
        HuffNode* node = tree[i];
        if (node->haschildren)
        {
            int childsum = 0;
            for (int j = 0; j < 2; ++j)
                if (!node->children[j]->haschildren)
                    childsum += (0x80 >> j) & 0xff;
            node->code |= childsum & 0xff;
        }
        out[outlength++] = (unsigned char)(node->code & 0xff);
    }

    // Ensure nodes are word-aligned
    if (lstlen % 2 == 0)
    {
        out[outlength++] = 0;
        out[outlength++] = 0;
        out[0] = (unsigned char)((lstlen + 1) & 0xff);
    }

    // Write bits to stream
    unsigned int data = 0;
    size_t setbits = 0;
    for (size_t i = 0; i < worklength; ++i)
    {
        unsigned char* bits = codebits + workdata[i] * MAX_CODE_BITS;
        int bitslength = codelengths[workdata[i]];
        for (int j = 0; j < bitslength; ++j)
        {
            data = data * 2 + bits[j];
            ++setbits;
            if (setbits % 32 == 0)
            {
                WRITE_32(out, outlength, data);
                outlength += 4;
                data = 0;
            }
        }
    }
    if (setbits % 32 != 0)
    {
        WRITE_32(out, outlength, data << (32 - (setbits % 32)));
        outlength += 4;
    }

    PyObject *output = PyBytes_FromStringAndSize(out, outlength);
    PyMem_Free(out);
    PyMem_Free(nibbles);
    PyMem_Free(nodes);
    PyMem_Free(freq);
    PyMem_Free(lst);
    PyMem_Free(codebits);
    return output;
}

static PyMethodDef Cmp_huffMethods[] = {
    {"decompressHuffman", (PyCFunction)decompressHuffman, METH_VARARGS | METH_KEYWORDS, decompressHuffman_doc},
    {"compressHuffman", (PyCFunction)compressHuffman, METH_VARARGS | METH_KEYWORDS, compressHuffman_doc},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef cmp_huffmodule = {
    PyModuleDef_HEAD_INIT,
    "cmp_huff",
    "C implementation of the Huffman coding scheme used by the GBA and NDS BIOS.",
    -1,
    Cmp_huffMethods
};

PyMODINIT_FUNC PyInit_cmp_huff(void)
{
    return moduleCreate(&cmp_huffmodule);
}
