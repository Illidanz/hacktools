import pytest
import os.path
from hacktools import cmp_lzss, cmp_cri, cmp_huff, cmp_misc, cmp_prs, cmp_racjin

@pytest.fixture
def data():
    with open(os.path.dirname(__file__) + "/../README.md", "rb") as f:
        testdata = f.read()
    return testdata


def test_cmp_lz10(data):
    cmp = cmp_lzss.compressLZ10(data, 1)
    decmp = cmp_lzss.decompressLZ10(cmp, len(data), 1)
    assert len(data) == len(decmp)
    assert data == decmp


def test_cmp_lz11(data):
    cmp = cmp_lzss.compressLZ11(data, 1)
    decmp = cmp_lzss.decompressLZ11(cmp, len(data), 1)
    assert len(data) == len(decmp)
    assert data == decmp


def test_cmp_cri(data):
    cmp = cmp_cri.compressCRILAYLA(data)
    decmp = cmp_cri.decompressCRILAYLA(cmp)
    assert len(data) == len(decmp)
    assert data == decmp


def test_cmp_prs(data):
    cmp = cmp_prs.compressPRS(data)
    decmp = cmp_prs.decompressPRS(cmp, len(data))
    assert len(data) == len(decmp)
    assert data == decmp


@pytest.mark.parametrize("numbits", [8, 4])
@pytest.mark.parametrize("little", [True, False])
def test_cmp_huffman(data, numbits, little):
    cmp = cmp_huff.compressHuffman(data, numbits, little)
    decmp = cmp_huff.decompressHuffman(cmp, len(data), numbits, little)
    assert len(data) == len(decmp)
    assert data == decmp


@pytest.mark.parametrize("numbits", [8, 4])
def test_cmp_huffman_alignment(data, numbits):
    for extra in (b"", b"\xf0"):
        indata = data + extra
        cmp = cmp_huff.compressHuffman(indata, numbits)
        assert (2 + cmp[0] * 2) % 4 == 0
        assert len(cmp) % 4 == 0
        assert cmp_huff.decompressHuffman(cmp, len(indata), numbits) == indata


def test_cmp_huffman_single_value():
    # A single distinct value needs a stub entry to build the tree with
    single = b"\xff" * 50
    cmp = cmp_huff.compressHuffman(single)
    assert cmp_huff.decompressHuffman(cmp, len(single)) == single


def test_cmp_rle(data):
    cmp = cmp_misc.compressRLE(data)
    decmp = cmp_misc.decompressRLE(cmp, len(data))
    assert len(data) == len(decmp)
    assert data == decmp


def test_cmp_rle_runs(data):
    # Add runs longer than the maximum block lengths of 0x82 and 0x80
    rundata = b"\x00" * 300 + data[:500] + b"\xff" * 130 + b"\xaa\xaa" + data[:200]
    cmp = cmp_misc.compressRLE(rundata)
    decmp = cmp_misc.decompressRLE(cmp, len(rundata))
    assert len(cmp) < len(rundata)
    assert rundata == decmp


def test_cmp_racjin(data):
    cmp = cmp_racjin.compressRACJIN(data)
    decmp = cmp_racjin.decompressRACJIN(cmp, len(data))
    assert len(data) == len(decmp)
    assert data == decmp
