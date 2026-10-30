# -*- coding: utf-8 -*-
"""Secrets are read from a file outside the project tree, and a secret file inside it is refused.

An agent that opens this repository as a project can read every file in it, ignored or not. A `.env` in the tree is a
readable file, not a secret.
"""
import subprocess
from pathlib import Path

import pytest

from src import env_file


def test_the_file_comes_from_the_environment_variable_first(monkeypatch, tmp_path):
    chosen = tmp_path / "elsewhere.env"
    monkeypatch.setenv("VISHAP_ENV_FILE", str(chosen))
    assert env_file.env_file_path() == chosen


def test_then_from_the_users_home_and_nowhere_else(monkeypatch, tmp_path):
    monkeypatch.delenv("VISHAP_ENV_FILE", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert env_file.env_file_path() is None
    (tmp_path / ".vishap").mkdir()
    (tmp_path / ".vishap" / "analyzer.env").write_text("X=1\n", encoding="utf-8")
    assert env_file.env_file_path() == tmp_path / ".vishap" / "analyzer.env"


def test_the_file_is_loaded_into_the_environment(monkeypatch, tmp_path):
    secrets = tmp_path / "analyzer.env"
    secrets.write_text("VISHAP_TEST_SECRET=from-the-outside-file\n", encoding="utf-8")
    monkeypatch.setenv("VISHAP_ENV_FILE", str(secrets))
    monkeypatch.delenv("VISHAP_TEST_SECRET", raising=False)
    monkeypatch.setattr(env_file, "stray_files", lambda root=None: [])
    assert env_file.load() == secrets
    import os
    assert os.environ["VISHAP_TEST_SECRET"] == "from-the-outside-file"
    monkeypatch.delenv("VISHAP_TEST_SECRET", raising=False)


def test_a_secret_file_inside_the_tree_is_refused_and_not_loaded(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("VISHAP_TEST_SECRET=in-the-tree\n", encoding="utf-8")
    monkeypatch.setattr(env_file, "APP_ROOT", tmp_path)
    monkeypatch.delenv("VISHAP_TEST_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="inside the project tree"):
        env_file.load()
    import os
    assert "VISHAP_TEST_SECRET" not in os.environ


def test_an_example_file_is_not_a_secret_file(tmp_path):
    (tmp_path / ".env.example").write_text("API_KEY=placeholder\n", encoding="utf-8")
    assert env_file.stray_files(tmp_path) == []
    (tmp_path / ".env.production").write_text("API_KEY=real\n", encoding="utf-8")
    assert [p.name for p in env_file.stray_files(tmp_path)] == [".env.production"]


def test_this_working_tree_has_no_secret_file_in_it():
    assert env_file.stray_files() == [], "move it outside the repository (see src/env_file.py)"


def test_no_secret_file_is_tracked_by_git():
    root = Path(__file__).resolve().parents[3]
    try:
        tracked = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    bad = [f for f in tracked if Path(f).name in env_file.STRAY_NAMES]
    assert bad == [], bad
