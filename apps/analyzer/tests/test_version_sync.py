# -*- coding: utf-8 -*-
"""Version sync: src/version.py must match pyproject.toml."""
from pathlib import Path
import tomllib

from src.version import __version__


def test_version_matches_pyproject():
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    version = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    assert __version__ == version, f"src/version.py={__version__} != pyproject={version}"


def test_version_is_string():
    assert isinstance(__version__, str)
    assert __version__.count(".") == 2
