# -*- coding: utf-8 -*-
"""Pytest configuration for Vishap (# v6.0.2-fix-v2: pytest_configure).

Runs BEFORE collection (pytest_configure), so src.config picks up the tmp dir
when it is first imported. Fixes PermissionError on Windows for tests that
write audit files (previous fixture-based approach was too late).

v6.0.3-fallback: tempfile.mkdtemp() creates a 0o700 dir that some sandboxed
environments (DSH) cannot create subdirectories in; on failure we fall back to
a workspace-local .tmp_data dir instead.
"""
import os
import shutil
import tempfile
from pathlib import Path

import pytest


_TMP_ROOT = None


def pytest_configure(config):
    """Prepare the environment before any test module is imported.

    Two things must happen here rather than in a fixture, because
    ``src.config`` reads the environment at import time:

    * ``VISHAP_DATA_DIR`` points at a throwaway directory;
    * the job store and tenant-key lookup are pinned to the in-memory backend.

    The second one is not cosmetic. ``get_store()`` builds a single
    ``PostgresJobStore`` per process, and its asyncpg engine is bound to the
    event loop that first used it. pytest gives each test a fresh loop, so with
    ``JOB_STORE=postgres`` inherited from ``.env`` the second test in a module
    fails with ``asyncpg.InterfaceError: cannot perform operation: another
    operation is in progress``. Tests must not depend on a developer's ``.env``.

    Set ``VISHAP_TEST_POSTGRES=1`` to opt back in (for a live-database run).
    """
    _configure_data_dir()
    _configure_store()


def _configure_store():
    """Pin the suite to the in-memory backends unless explicitly opted out."""
    if os.environ.get("VISHAP_TEST_POSTGRES"):
        return
    os.environ["JOB_STORE"] = "memory"
    # Tenant-key lookups hit ``tenants``; without a database they would raise.
    os.environ["VISHAP_TENANT_KEYS"] = "false"


def _configure_data_dir():
    """Point VISHAP_DATA_DIR at a throwaway directory."""
    # v6.0.3-fallback: mkdtemp fails in DSH sandbox (0o700 ACL)
    global _TMP_ROOT
    if os.environ.get("VISHAP_DATA_DIR"):
        return  # respect explicit override
    try:
        _TMP_ROOT = Path(tempfile.mkdtemp(prefix="vishap-tests-"))
        data_dir = _TMP_ROOT / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        # Sandboxed env (e.g. DSH): mkdtemp's 0o700 dir can't host subdirs.
        _TMP_ROOT = Path(__file__).parent.parent / ".tmp_data"
        _TMP_ROOT.mkdir(parents=True, exist_ok=True)
        data_dir = _TMP_ROOT / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["VISHAP_DATA_DIR"] = str(data_dir)


def pytest_unconfigure(config):
    """Cleanup tmp dir after session (best-effort)."""
    if _TMP_ROOT is not None:
        shutil.rmtree(_TMP_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
def _api_key_pepper(monkeypatch):
    """Give every test a deterministic API key pepper.

    ``hash_api_key`` refuses to run without one (v6.5, P0), and applying the
    pepper everywhere keeps the suite independent of the developer's ``.env``.
    Tests that assert the *absence* of the pepper delete it themselves.
    """
    if not os.environ.get("API_KEY_PEPPER"):
        monkeypatch.setenv("API_KEY_PEPPER", "test-pepper")
