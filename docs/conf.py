# Configuration file for the Sphinx documentation builder.
# https://www.sphinx-doc.org/en/master/usage/configuration.html
import os
import sys

sys.path.insert(0, os.path.abspath(".."))


def getversion(rel_path):
    here = os.path.abspath(os.path.dirname(__file__))
    with open(os.path.join(here, rel_path), "r") as f:
        for line in f.read().splitlines():
            if line.startswith("__version__"):
                delim = '"' if '"' in line else "'"
                return line.split(delim)[1]
    raise RuntimeError("Unable to find version string.")


project = "hacktools"
author = "Illidan"
release = getversion("../hacktools/__init__.py")

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "myst_parser",
]

# Merge type hints from signatures into the parameter descriptions
autodoc_typehints = "description"
autodoc_member_order = "bysource"
# Mock the gui dependencies so they don't need to be installed.
# The compiled C extensions are documented from their real docstrings,
# so they need to be built in-place with: python setup.py build_ext --inplace
autodoc_mock_imports = [
    "customtkinter",
    "tqdm",
]

# The README is included with its H1 title skipped, so its headings start at H2
suppress_warnings = ["myst.header"]

# Stdlib types can't be cross-referenced without intersphinx
nitpick_ignore = [
    ("py:class", "collections.abc.Callable"),
    ("py:class", "logging.LogRecord"),
]

napoleon_google_docstring = True
napoleon_numpy_docstring = False

templates_path = []
exclude_patterns = ["_build"]

html_theme = "furo"
