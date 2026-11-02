"""A submitted file name may never put a file outside the directory it is written to, on any platform."""
import ntpath
import posixpath

import pytest

from hub import local, paths


@pytest.mark.parametrize("rel", ["D:evil.py", "C:..\\..\\x", "..\\..\\x", "../x", "a/../../x", "\\\\host\\share\\x", "", ".", "a\x00b"])
def test_windows_rules_refuse_what_leaves_the_root(rel):
    assert paths.contained("C:\\Temp\\hub-x", rel, ntpath) is None


@pytest.mark.parametrize("rel", ["../x", "a/../../x", "", ".", "a\x00b"])
def test_posix_rules_refuse_what_leaves_the_root(rel):
    assert paths.contained("/tmp/hub-x", rel, posixpath) is None


def test_ordinary_names_stay_inside():
    assert paths.contained("C:\\Temp\\hub-x", "pkg\\a.py", ntpath) == "C:\\Temp\\hub-x\\pkg\\a.py"
    assert paths.contained("/tmp/hub-x", "pkg/a.py", posixpath) == "/tmp/hub-x/pkg/a.py"
    assert paths.contained("/tmp/hub-x", "/etc/passwd", posixpath) == "/tmp/hub-x/etc/passwd"   # rooted at the temp dir
    assert paths.contained("/tmp/hub-x", "..hidden.py", posixpath) == "/tmp/hub-x/..hidden.py"


def test_materialize_writes_only_inside(tmp_path):
    root, written = local._materialize({"ok/a.py": "x = 1\n", "../escape.py": "x", "/abs.py": "y = 2\n"})
    import os
    names = sorted(os.path.relpath(os.path.join(d, f), root) for d, _, fs in os.walk(root) for f in fs)
    assert written == 2 and names == [os.path.join("abs.py"), os.path.join("ok", "a.py")]
    assert not os.path.exists(os.path.join(os.path.dirname(root), "escape.py"))
