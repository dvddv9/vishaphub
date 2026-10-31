"""The installer chooses how submitted code is run; an unknown choice runs nothing."""
import json
import os
import sys
from pathlib import Path

import pytest

from hub import isolation, local

GOOD = Path(__file__).resolve().parents[2] / "validator" / "examples" / "good"
SPEC = {"language": "python", "files": ["calc/__init__.py", "test_calc.py"], "exports": ["add"],
        "entry": "calc", "tests": ["test_calc.py"]}


def _files():
    return {str(p.relative_to(GOOD)).replace("\\", "/"): p.read_text(encoding="utf-8")
            for p in GOOD.rglob("*.py") if "__pycache__" not in p.parts}


def test_default_is_auto(monkeypatch):
    monkeypatch.delenv("VISHAP_HUB_ISOLATION", raising=False)
    assert isolation.policy() == "auto"


@pytest.mark.parametrize("mode", ["docker", "auto", "host", " HOST "])
def test_known_modes(monkeypatch, mode):
    monkeypatch.setenv("VISHAP_HUB_ISOLATION", mode)
    assert isolation.policy() == mode.strip().lower()


def test_unknown_mode_runs_nothing(monkeypatch):
    monkeypatch.setenv("VISHAP_HUB_ISOLATION", "dokcer")
    r = local.validate_code({"a.py": "x = 1\n"}, {"language": "python", "files": ["a.py"]})
    assert r["ok"] is False and "dokcer" in r["error"]
    r = local.run_exploits({"a.py": "x = 1\n"}, [])
    assert r["ok"] is False and "dokcer" in r["error"]


def test_docker_without_image_runs_nothing(monkeypatch):
    monkeypatch.setenv("VISHAP_HUB_ISOLATION", "docker")
    monkeypatch.delenv("VISHAP_HUB_WORKER_IMAGE", raising=False)
    r = local.validate_code({"a.py": "x = 1\n"}, {"language": "python", "files": ["a.py"]})
    assert r["ok"] is False and "WORKER_IMAGE" in r["error"]


def test_docker_uses_worker_even_without_strictness(monkeypatch):
    monkeypatch.setenv("VISHAP_HUB_ISOLATION", "docker")
    monkeypatch.setenv("VISHAP_HUB_WORKER_IMAGE", "img")
    seen = []
    monkeypatch.setattr(local, "_validate_in_worker", lambda root, spec, image: seen.append(image) or {"ok": True})
    assert local.validate_code({"a.py": "x = 1\n"}, {"language": "python"}, require_netns=False)["ok"]
    assert seen == ["img"]


def test_host_skips_worker_and_says_so(monkeypatch):
    monkeypatch.setenv("VISHAP_HUB_ISOLATION", "host")
    monkeypatch.setenv("VISHAP_HUB_WORKER_IMAGE", "img")
    monkeypatch.setattr(local, "_validate_in_worker", lambda *a: pytest.fail("worker must not be used"))
    r = local.validate_code(_files(), SPEC)
    assert r["ok"] is True, r
    assert r["isolation"]["kind"] == "host" and r["isolation"]["confirmed"] is False
    assert r["report"]["verdict"] in ("PASS", "NEEDS_REVIEW")


def test_host_record_is_not_a_confirmation():
    rec = isolation.host_record("guard")
    assert rec["confirmed"] is False and rec["network"] == "guard"


def test_host_overrides_the_strict_variable(monkeypatch):
    # The hub image sets VISHAP_VALIDATOR_REQUIRE_NETNS=1; the installer's explicit choice must still hold.
    monkeypatch.setenv("VISHAP_HUB_ISOLATION", "host")
    monkeypatch.setenv("VISHAP_VALIDATOR_REQUIRE_NETNS", "1")
    monkeypatch.delenv("VISHAP_HUB_WORKER_IMAGE", raising=False)
    r = local.validate_code(_files(), SPEC)
    assert r["ok"] is True and r["report"]["verdict"] != "FAIL", r


def test_auto_keeps_the_strict_variable(monkeypatch):
    from validator import safe
    monkeypatch.setenv("VISHAP_VALIDATOR_REQUIRE_NETNS", "1")
    if safe.isolation() in ("netns", "container"):
        pytest.skip("this host has real isolation")
    assert safe.refusal() != "" and safe.refusal(host_ok=True) == ""
