# -*- coding: utf-8 -*-
"""Test that conftest.py isolates VISHAP_DATA_DIR (# v6.0.2-fix).

Regression: tests used to write audit files to ~/.vishap/data (outside workspace),
which is blocked by Windows Defender / file locks / sandbox.
"""
import os
from pathlib import Path


def test_vishap_data_dir_is_set():
    """VISHAP_DATA_DIR must be set by conftest during test session."""
    data_dir = os.environ.get("VISHAP_DATA_DIR")
    assert data_dir, "VISHAP_DATA_DIR not set -- conftest failed"


def test_vishap_data_dir_is_not_in_user_profile():
    """VISHAP_DATA_DIR must NOT point into the user home profile."""
    data_dir = Path(os.environ["VISHAP_DATA_DIR"]).resolve()
    home_vishap = (Path.home() / ".vishap").resolve()
    assert home_vishap not in data_dir.parents, (
        f"VISHAP_DATA_DIR points into user profile: {data_dir}"
    )


def test_vishap_data_dir_exists():
    """VISHAP_DATA_DIR must exist (created by conftest)."""
    data_dir = Path(os.environ["VISHAP_DATA_DIR"])
    assert data_dir.exists(), f"VISHAP_DATA_DIR does not exist: {data_dir}"


def test_vishap_data_dir_inside_project_or_temp():
    """VISHAP_DATA_DIR must be inside project or system temp (isolated)."""
    data_dir = Path(os.environ["VISHAP_DATA_DIR"]).resolve()
    project_root = Path(__file__).parent.parent.resolve()
    import tempfile
    tmp_root = Path(tempfile.gettempdir()).resolve()
    inside_project = project_root in data_dir.parents or data_dir == project_root
    inside_temp = tmp_root in data_dir.parents or data_dir == tmp_root
    assert inside_project or inside_temp, (
        f"VISHAP_DATA_DIR not isolated: {data_dir}"
    )
