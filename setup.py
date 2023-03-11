from setuptools import setup, Extension

with open("README.md", "r") as fh:
    long_description = fh.read()

extras_nds=["ndspy"]
extras_armips=["pyarmips"]
extras_xdelta=["pyxdelta"]
extras_iso=["pymkpsxiso"]
extras_psp=["pycdlib", "pyeboot"]
extras_ips=["ips_util"]
extras_graphics=["Pillow"]
extras_cli=["click", "tqdm"]

setup(
    name="hacktools",
    version="0.31.0",
    author="Illidan",
    description="A set of utilities and tools for rom hacking and translations.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Illidanz/hacktools",
    packages=["hacktools"],
    ext_modules=[
        Extension("hacktools.cmp_lzss", sources=["hacktools/c_ext/cmp_lzss.c"]),
        Extension("hacktools.cmp_cri",  sources=["hacktools/c_ext/cmp_cri.c"]),
        Extension("hacktools.cmp_misc", sources=["hacktools/c_ext/cmp_misc.c"]),
    ],
    classifiers=[
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    extras_require = {
        "nds": extras_nds,
        "armips": extras_armips,
        "xdelta": extras_xdelta,
        "iso": extras_iso,
        "psp": extras_psp,
        "ips": extras_ips,
        "graphics": extras_graphics,
        "cli": extras_cli,
        "all": extras_nds + extras_armips + extras_xdelta + extras_iso + extras_psp + extras_ips + extras_graphics + extras_cli,
    },
    python_requires=">=3.7",
)
