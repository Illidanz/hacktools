import pytest
import os.path
from hacktools import cmp_lzss, cmp_cri

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
