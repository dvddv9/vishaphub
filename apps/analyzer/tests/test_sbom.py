# -*- coding: utf-8 -*-
"""Tests for SBOM generation (P0-3)."""
import json
from unittest.mock import patch, MagicMock

from src.tools.sbom import (
    generate_sbom,
    parse_sbom,
    is_cyclonedx_available,
)


def _mock_run(stdout="", returncode=0):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    return m


SAMPLE_SBOM = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.6",
    "serialNumber": "urn:uuid:abc-123",
    "components": [
        {"name": "requests", "version": "2.32.0"},
        {"name": "fastapi", "version": "0.115.0"},
        {"name": "pydantic", "version": "2.9.0"},
    ],
}


def test_parse_sbom_full():
    info = parse_sbom(SAMPLE_SBOM)
    assert info["count"] == 3
    assert info["spec_version"] == "1.6"
    assert info["bom_format"] == "CycloneDX"
    assert info["serial_number"] == "urn:uuid:abc-123"


def test_parse_sbom_empty():
    info = parse_sbom({})
    assert info["count"] == 0
    assert info["spec_version"] == ""


def test_parse_sbom_not_dict():
    info = parse_sbom("not a dict")
    assert info["count"] == 0


def test_parse_sbom_components_not_list():
    info = parse_sbom({"components": "broken"})
    assert info["count"] == 0


def test_parse_sbom_missing_components():
    info = parse_sbom({"bomFormat": "CycloneDX"})
    assert info["count"] == 0
    assert info["bom_format"] == "CycloneDX"


def test_generate_sbom_success():
    with patch("src.tools.sbom.subprocess.run", return_value=_mock_run(json.dumps(SAMPLE_SBOM))):
        sbom = generate_sbom()
    assert sbom["bomFormat"] == "CycloneDX"
    assert len(sbom["components"]) == 3


def test_generate_sbom_cli_error():
    with patch("src.tools.sbom.subprocess.run", return_value=_mock_run("", returncode=1)):
        assert generate_sbom() == {}


def test_generate_sbom_cli_not_found():
    with patch("src.tools.sbom.subprocess.run", side_effect=FileNotFoundError()):
        assert generate_sbom() == {}


def test_generate_sbom_bad_json():
    with patch("src.tools.sbom.subprocess.run", return_value=_mock_run("not json {")):
        assert generate_sbom() == {}


def test_generate_sbom_writes_file(tmp_path):
    out = tmp_path / "sbom.json"
    with patch("src.tools.sbom.subprocess.run", return_value=_mock_run(json.dumps(SAMPLE_SBOM))):
        sbom = generate_sbom(output_path=str(out))
    assert sbom["bomFormat"] == "CycloneDX"
    assert out.exists()
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["specVersion"] == "1.6"


def test_generate_sbom_write_error_silent(tmp_path):
    out = tmp_path / "nested" / "sbom.json"
    with patch("src.tools.sbom.subprocess.run", return_value=_mock_run(json.dumps(SAMPLE_SBOM))):
        sbom = generate_sbom(output_path=str(out))
    assert sbom["bomFormat"] == "CycloneDX"
    assert out.exists()


def test_is_cyclonedx_available_true():
    with patch("src.tools.sbom.subprocess.run", return_value=_mock_run("7.5.0")):
        assert is_cyclonedx_available() is True


def test_is_cyclonedx_available_false():
    with patch("src.tools.sbom.subprocess.run", side_effect=FileNotFoundError()):
        assert is_cyclonedx_available() is False


def test_is_cyclonedx_available_returncode():
    with patch("src.tools.sbom.subprocess.run", return_value=_mock_run("", returncode=2)):
        assert is_cyclonedx_available() is False
