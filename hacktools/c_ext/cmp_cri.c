#include "inc.h"

// https://github.com/ConnorKrammer/cpk-tools/blob/master/LibCRIComp/LibCRIComp.cpp
static PyObject* compressCRILAYLA(PyObject* module, PyObject* args, PyObject* kwargs)
{
    static char *kwlist[] = { "indata", NULL };

    unsigned char* src;
    size_t srclen;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s#", kwlist, &src, &srclen))
        return NULL;

    unsigned int destlen = (unsigned int)srclen;
    unsigned char* dest = PyMem_Malloc(destlen);
    MALLOC_CHECK(dest);

    int n = (int)srclen - 1;
    int m = destlen - 1;
    int T = 0, d = 0, p = 0, q = 0, i = 0, j = 0, k = 0;
    unsigned char* odest = dest;
    unsigned char* retdest = dest;
    for (; n >= 0x100;)
    {
        j = n + 3 + 0x2000;
        if (j > srclen)
            j = (int)srclen;
        for (i = n + 3, p = 0; i < j; i++)
        {
            for (k = 0; k <= n - 0x100; k++)
            {
                if (*(src + n - k) != *(src + i - k))
                    break;
            }
            if (k>p)
            {
                q = i - n - 3;
                p = k;
            }
        }
        if (p < 3)
        {
            d = (d << 9) | (*(src + n--));
            T += 9;
        }
        else
        {
            d = (((d << 1) | 1) << 13) | q;
            T += 14;
            n -= p;
            if (p < 6)
            {
                d = (d << 2) | (p - 3);
                T += 2;
            }
            else if (p < 13)
            {
                d = (((d << 2) | 3) << 3) | (p - 6);
                T += 5;
            }
            else if (p < 44)
            {
                d = (((d << 5) | 0x1f) << 5) | (p - 13);
                T += 10;
            }
            else
            {
                d = ((d << 10) | 0x3ff);
                T += 10;
                p -= 44;
                for (;;)
                {
                    for (; T >= 8;)
                    {
                        *(dest + m--) = (d >> (T - 8)) & 0xff;
                        T -= 8;
                        d = d & ((1 << T) - 1);
                    }
                    if (p < 255)
                        break;
                    d = (d << 8) | 0xff;
                    T += 8;
                    p = p - 0xff;
                }
                d = (d << 8) | p;
                T += 8;
            }
        }
        for (; T >= 8;)
        {
            *(dest + m--) = (d >> (T - 8)) & 0xff;
            T -= 8;
            d = d & ((1 << T) - 1);
        }
    }
    if (T != 0)
    {
        *(dest + m--) = d << (8 - T);
    }
    *(dest + m--) = 0;
    *(dest + m) = 0;
    for (;;)
    {
        if (((destlen - m) & 3) == 0)
            break;
        *(dest + m--) = 0;
    }
    destlen = destlen - m;
    dest += m;
    int l[] = { 0x4c495243, 0x414c5941, (int)srclen - 0x100, (int)destlen };
    for (j = 0; j < 4; j++)
    {
        for (i = 0; i < 4; i++)
        {
            *(odest + i + j * 4) = l[j] & 0xff;
            l[j] >>= 8;
        }
    }
    for (j = 0, odest += 0x10; j < (int)destlen; j++)
    {
        *(odest++) = *(dest + j);
    }
    for (j = 0; j < 0x100; j++)
    {
        *(odest++) = *(src + j);
    }
    destlen += 0x110;

    PyObject *output = PyBytes_FromStringAndSize(retdest, destlen);
    PyMem_Free(retdest);
    return output;
}

static inline uint16_t get_next_bits(unsigned char* input_buffer, long* const offset_p, uint8_t* const bit_pool_p, int* const bits_left_p, const int bit_count)
{
    uint16_t out_bits = 0;
    int num_bits_produced = 0;
    while (num_bits_produced < bit_count)
    {
        if (0 == *bits_left_p)
        {
            *bit_pool_p = input_buffer[*offset_p];
            *bits_left_p = 8;
            --*offset_p;
        }

        int bits_this_round;
        if (*bits_left_p > (bit_count - num_bits_produced))
            bits_this_round = bit_count - num_bits_produced;
        else
            bits_this_round = *bits_left_p;

        out_bits <<= bits_this_round;
        out_bits |= (*bit_pool_p >> (*bits_left_p - bits_this_round)) & ((1 << bits_this_round) - 1);

        *bits_left_p -= bits_this_round;
        num_bits_produced += bits_this_round;
    }

    return out_bits;
}

// https://github.com/hcs64/vgm_ripping/blob/master/multi/utf_tab/cpk_uncompress.c
static PyObject* decompressCRILAYLA(PyObject* m, PyObject* args, PyObject* kwargs)
{
    static char *kwlist[] = { "indata", NULL };

    unsigned char* input_buffer;
    size_t input_size;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s#", kwlist, &input_buffer, &input_size))
        return NULL;

    // check signature
    unsigned char* signature = "CRILAYLA";
    int i = 0;
    for (i = 0; i < 8; ++i)
    {
        ERROR_CHECK(input_buffer[i] != signature[i], "No CRILAYLA signature.");
    }
    // read header
    long uncompressed_size = READ_32(input_buffer, 0x8);
    long uncompressed_header_offset = READ_32(input_buffer, 0xc) + 0x10;
    // allocate buffer and copy uncompressed header
    unsigned char* output_buffer = PyMem_Malloc(uncompressed_size + 0x100);
    MALLOC_CHECK(output_buffer);
    for (i = 0; i < 0x100; ++i)
        output_buffer[i] = input_buffer[uncompressed_header_offset + i];
    // setup
    const long input_end = (long)input_size - 0x100 - 1;
    long input_offset = input_end;
    const long output_end = 0x100 + uncompressed_size - 1;
    uint8_t bit_pool = 0;
    int bits_left = 0;
    long bytes_output = 0;
    int vle_lens[4] = { 2, 3, 5, 8 };
    // decompress
    while (bytes_output < uncompressed_size)
    {
        if (get_next_bits(input_buffer, &input_offset, &bit_pool, &bits_left, 1))
        {
            long backreference_offset = output_end - bytes_output + get_next_bits(input_buffer, &input_offset, &bit_pool, &bits_left, 13) + 3;
            long backreference_length = 3;

            // decode variable length coding for length
            int vle_level;
            for (vle_level = 0; vle_level < 4; ++vle_level)
            {
                int this_level = get_next_bits(input_buffer, &input_offset, &bit_pool, &bits_left, vle_lens[vle_level]);
                backreference_length += this_level;
                if (this_level != ((1 << vle_lens[vle_level]) - 1))
                    break;
            }
            if (vle_level == 4)
            {
                int this_level;
                do
                {
                    this_level = get_next_bits(input_buffer, &input_offset, &bit_pool, &bits_left, 8);
                    backreference_length += this_level;
                }
                while (this_level == 255);
            }

            //printf("0x%08lx backreference to 0x%lx, length 0x%lx\n", output_end-bytes_output, backreference_offset, backreference_length);
            for (int i = 0; i < backreference_length; ++i)
            {
                output_buffer[output_end-bytes_output] = output_buffer[backreference_offset--];
                bytes_output++;
            }
        }
        else
        {
            // verbatim byte
            output_buffer[output_end-bytes_output] = (unsigned char)get_next_bits(input_buffer, &input_offset, &bit_pool, &bits_left, 8);
            //printf("0x%08lx verbatim byte\n", output_end-bytes_output);
            bytes_output++;
        }
    }

    PyObject *output = PyBytes_FromStringAndSize(output_buffer, uncompressed_size + 0x100);
    PyMem_Free(output_buffer);
    return output;
}

static PyMethodDef Cmp_criMethods[] = {
    {"compressCRILAYLA", (PyCFunction)compressCRILAYLA, METH_VARARGS | METH_KEYWORDS, "Compress CRILAYLA data."},
    {"decompressCRILAYLA", (PyCFunction)decompressCRILAYLA, METH_VARARGS | METH_KEYWORDS, "Decompress CRILAYLA data."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef cmp_crimodule = {
    PyModuleDef_HEAD_INIT,
    "cmp_cri",
    "CRILAYLA functions.",
    -1,
    Cmp_criMethods
};

PyMODINIT_FUNC PyInit_cmp_cri(void)
{
    return PyModule_Create(&cmp_crimodule);
}
