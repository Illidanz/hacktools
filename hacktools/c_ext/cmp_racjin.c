#include "inc.h"

// https://github.com/Raw-man/Racjin-de-compression/blob/master/src/encode.cpp
static PyObject* compressRACJIN(PyObject* module, PyObject* args, PyObject* kwargs)
{
    static char *kwlist[] = { "indata", NULL };

    unsigned char* src;
    size_t srclen;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s#", kwlist, &src, &srclen))
        return NULL;

    unsigned char* compressed_buffer = PyMem_Malloc(srclen * 2);
    MALLOC_CHECK(compressed_buffer);
    unsigned int destlen = 0;

    unsigned int index = 0; //position of an element from the input buffer
    unsigned char last_enc_byte = 0;//last encoded byte
    unsigned char bit_shift = 0; //shift by bitShift (used to fold codes)
    unsigned char* frequencies = PyMem_Calloc(256, sizeof(unsigned char));
    MALLOC_CHECK(frequencies);
    for (int i = 0; i < 256; ++i)
        frequencies[i] = 0;
    unsigned int* seq_indices = PyMem_Calloc(8192, sizeof(unsigned int));
    MALLOC_CHECK(seq_indices);
    for (int i = 0; i < 8192; ++i)
        seq_indices[i] = 0;
    unsigned short* codes = PyMem_Calloc(srclen, sizeof(unsigned short));
    MALLOC_CHECK(codes);
    for (int i = 0; i < srclen; ++i)
        codes[i] = 0;
    unsigned int codeslen = 0;

    while (index < srclen)
    {
        unsigned char best_freq = 0;
        unsigned char best_match = 0;

        // To get the exact same compression for CDDATA.DIG files uncomment the following:
        if (frequencies[last_enc_byte] == 256)
            frequencies[last_enc_byte] = 0x00;

        unsigned char positions_to_check = frequencies[last_enc_byte] < 32 ? (frequencies[last_enc_byte] & 0x1F) : 32;
        unsigned int seq_index = index;

        for (unsigned char freq = 0; freq < positions_to_check; freq++)
        {
            unsigned short key = freq + last_enc_byte * 32; //0x1F + 0xFF*32 = 8191
            unsigned int src_index = seq_indices[key];
            unsigned char matched = 0;
            unsigned char max_length = index + 8 < srclen ? 8 : srclen - index;

            for (unsigned char offset = 0; offset < max_length; ++offset)
            {
                if (src[src_index + offset] == src[index + offset])
                    ++matched;
                else
                    break;
            }

            if (matched > best_match)
            {
                best_freq = freq;
                best_match = matched;
            }
        }

        unsigned short code = 0x00;
        if (best_match > 0) //found a better match?
        {
            code = code | (best_freq << 3); //f|ooooolll //f=0 (flag), o - occurrences/frequency, l -length
            code = code | (best_match - 1); //encode a reference
            index += best_match;
        }
        else //encode byte literal
        {
            code = 0x100 | src[index]; //f|bbbbbbbb //f=1
            ++index;
        }

        code = code << bit_shift; //prepare for folding
        codes[codeslen] = code;
        codeslen++;

        ++bit_shift;
        if (bit_shift == 8)
            bit_shift = 0;

        unsigned int key = (frequencies[last_enc_byte] & 0x1F) + last_enc_byte * 32; //0x1F + 0xFF*32 = 8191
        seq_indices[key] = seq_index;
        frequencies[last_enc_byte] = frequencies[last_enc_byte] + 1; //increase by 1 (up to 31)
        last_enc_byte = src[index - 1];
    }
    //Fold codes (8 codes, 16 bytes -> 8 codes, 9 bytes)
    for (unsigned int i = 0; i < codeslen; i = i + 8)
    {
        unsigned char group_size = i + 8 < codeslen ? 8 : codeslen - i;
        for (unsigned char s = 0; s <= group_size; s += 2)
        {
            unsigned short first = s > 0 ? codes[s + i - 1] : 0x00;
            unsigned short middle = s < group_size ? codes[s + i] : 0x00;
            unsigned short last = s < group_size - 1 ? codes[s + i + 1] : 0x00;
            unsigned short result = middle | (first >> 8) | (last << 8);
            compressed_buffer[destlen] = result & 0xFF;
            ++destlen;
            if (s < group_size)
            {
                compressed_buffer[destlen] = result >> 8;
                ++destlen;
            }
        }
    }

    PyObject *output = PyBytes_FromStringAndSize(compressed_buffer, destlen);
    PyMem_Free(compressed_buffer);
    PyMem_Free(frequencies);
    PyMem_Free(seq_indices);
    PyMem_Free(codes);
    return output;
}

// https://github.com/Raw-man/Racjin-de-compression/blob/master/src/decode.cpp
static PyObject* decompressRACJIN(PyObject* m, PyObject* args, PyObject* kwargs)
{
    static char *kwlist[] = { "indata", "decomplength", NULL };

    unsigned char* input_buffer;
    size_t input_size;
    unsigned int decomplength;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s#I", kwlist, &input_buffer, &input_size, &decomplength))
        return NULL;

    unsigned int index = 0; //position of a byte from the input buffer
    unsigned int dest_index = 0; //position (destination) of a decoded byte in the output buffer
    unsigned char last_dec_byte = 0; //last decoded byte of the previus decoding iteration
    unsigned char bit_shift = 0; //shift right by bitShift

    // Allocate buffers
    unsigned char* frequencies = PyMem_Malloc(256);
    MALLOC_CHECK(frequencies);
    for (int i = 0; i < 256; ++i)
        frequencies[i] = 0;
    unsigned int* seq_indices = PyMem_Calloc(8192, sizeof(unsigned int));
    MALLOC_CHECK(seq_indices);
    for (int i = 0; i < 8192; ++i)
        seq_indices[i] = 0;
    unsigned char* decompressed_buffer = PyMem_Malloc(decomplength);
    MALLOC_CHECK(decompressed_buffer);

    while (index < input_size)
    {
        unsigned short next_code = input_buffer[index + 1];  //next pair of bytes to decode from the input buffer
        next_code = next_code << 8;
        next_code = next_code | input_buffer[index];
        next_code = next_code >> bit_shift; //unfold 9 bit token

        //The result can be interpreted as follows:
        // iiiiiiif|ooooolll //f=0
        // iiiiiiif|bbbbbbbb //f=1
        //i - ignore
        //f - flag  (is literal or offset/length pair)
        //l - length (add 1 to get the real length)
        //o - occurrences/frequency
        //b - byte literal

        ++bit_shift;
        ++index;

        if (bit_shift == 8)
        {
            bit_shift = 0;
            ++index;
        }

        unsigned int seq_index = dest_index; //start of a byte sequence
        if ((next_code & 0x100) != 0) // bit flag: is nextToken a literal or a reference?
        {
            decompressed_buffer[dest_index] = (unsigned char)(next_code & 0xFF); //store the literal
            ++dest_index;
        }
        else
        {
            unsigned int key = ((next_code >> 3) & 0x1F) + last_dec_byte * 32; //0x1F + 0xFF*32 = 8191
            unsigned int src_index = seq_indices[key]; //get a reference to a previously decoded sequence

            for (unsigned char length = 0; length < (next_code & 0x07) + 1; ++length, ++dest_index, ++src_index)
            {
                decompressed_buffer[dest_index] = decompressed_buffer[src_index]; //copy a previously decoded byte sequence (up to 8)
            }
        }

        if (dest_index >= decomplength)
            break;

        unsigned int key = frequencies[last_dec_byte] + last_dec_byte * 32; //0x1F + 0xFF*32 = 8191
        seq_indices[key] = seq_index;
        frequencies[last_dec_byte] = (unsigned char)((frequencies[last_dec_byte] + 1) & 0x1F); //increase by 1 (up to 31)
        last_dec_byte = decompressed_buffer[dest_index - 1];
    }

    PyObject *output = PyBytes_FromStringAndSize(decompressed_buffer, decomplength);
    PyMem_Free(frequencies);
    PyMem_Free(seq_indices);
    PyMem_Free(decompressed_buffer);
    return output;
}

static PyMethodDef Cmp_racjinMethods[] = {
    {"compressRACJIN", (PyCFunction)compressRACJIN, METH_VARARGS | METH_KEYWORDS, "Compress RACJIN data."},
    {"decompressRACJIN", (PyCFunction)decompressRACJIN, METH_VARARGS | METH_KEYWORDS, "Decompress RACJIN data."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef cmp_racjinmodule = {
    PyModuleDef_HEAD_INIT,
    "cmp_racjin",
    "RACJIN functions.",
    -1,
    Cmp_racjinMethods
};

PyMODINIT_FUNC PyInit_cmp_racjin(void)
{
    return PyModule_Create(&cmp_racjinmodule);
}
