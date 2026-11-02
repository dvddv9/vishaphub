import ntpath
import posixpath

import pytest

from validator.paths import contained


@pytest.mark.parametrize("rel", ["D:evil.py", "C:..\\..\\x", "..\\..\\x", "../x", "", "."])
def test_windows_rules_refuse_what_leaves_the_root(rel):
    assert contained("C:\\Temp\\v", rel, ntpath) is None


def test_posix_rules_and_ordinary_names():
    assert contained("/tmp/v", "../x", posixpath) is None
    assert contained("/tmp/v", "pkg/a.py", posixpath) == "/tmp/v/pkg/a.py"
