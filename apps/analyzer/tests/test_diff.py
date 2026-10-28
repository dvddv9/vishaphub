# -*- coding: utf-8 -*-
"""Tests for diff-aware scan (P0-2)."""
from unittest.mock import patch, MagicMock

from src.tools.diff import (
    get_changed_files,
    get_uncommitted_files,
    get_changed_files_pr,
    is_changed,
    _normalize,
)


def _mock_run(stdout="", returncode=0):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    return m


def test_normalize_backslash():
    assert _normalize("src\\main.py") == "src/main.py"


def test_normalize_leading_dot_slash():
    assert _normalize("./src/main.py") == "src/main.py"


def test_normalize_empty():
    assert _normalize("") == ""
    assert _normalize("  ") == ""


def test_get_changed_files_basic():
    with patch("src.tools.diff.subprocess.run", return_value=_mock_run("a.py\nb.py\nc.py\n")):
        assert get_changed_files("main") == ["a.py", "b.py", "c.py"]


def test_get_changed_files_empty_ref():
    assert get_changed_files("") == []


def test_get_changed_files_git_error():
    with patch("src.tools.diff.subprocess.run", return_value=_mock_run("", returncode=128)):
        assert get_changed_files("nonexistent") == []


def test_get_changed_files_git_not_found():
    with patch("src.tools.diff.subprocess.run", side_effect=FileNotFoundError()):
        assert get_changed_files("main") == []


def test_get_uncommitted_combined():
    calls = [
        _mock_run("a.py\n"),      # diff HEAD
        _mock_run("b.py\n"),      # diff --cached
        _mock_run("c.py\n"),      # ls-files others
    ]
    with patch("src.tools.diff.subprocess.run", side_effect=calls):
        result = get_uncommitted_files()
    assert set(result) == {"a.py", "b.py", "c.py"}


def test_get_changed_files_pr_env():
    with patch.dict("os.environ", {"GITHUB_BASE_REF": "develop"}):
        with patch("src.tools.diff.subprocess.run", return_value=_mock_run("x.py\n")):
            assert get_changed_files_pr() == ["x.py"]


def test_get_changed_files_pr_default_main():
    with patch.dict("os.environ", {}, clear=True):
        with patch("src.tools.diff.subprocess.run", return_value=_mock_run("y.py\n")):
            # Should query origin/main
            assert get_changed_files_pr() == ["y.py"]


def test_is_changed_exact():
    assert is_changed("src/a.py", ["src/a.py", "src/b.py"]) is True


def test_is_changed_not_present():
    assert is_changed("src/z.py", ["src/a.py", "src/b.py"]) is False


def test_is_changed_empty_changed():
    assert is_changed("a.py", []) is False


def test_is_changed_basename():
    assert is_changed("full/path/input.txt", ["input.txt"]) is True


def test_is_changed_normalized_backslash():
    assert is_changed("src\\main.py", ["src/main.py"]) is True
