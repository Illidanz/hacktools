from setuptools import setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="hacktools",
    version="0.13.9",
    author="Illidan",
    description="A set of utilities and tools for rom hacking and translations.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Illidanz/hacktools",
    packages=["hacktools"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    install_requires=[
        "click",
        "tqdm",
        "ndspy",
        "crcmod",
        "Pillow",
        "pycdlib",
        "psd-tools>=1.8,<1.9"
    ],
    python_requires=">=3.7",
)
