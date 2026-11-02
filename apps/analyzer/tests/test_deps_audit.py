# -*- coding: utf-8 -*-
"""Dependency manifest audit (src/tools/deps_audit.py): offline rules, opt-in online checks with a fake network."""
import json

from src.tools import deps_audit
from src.tools.static_scan import scan_material

REQ = (
    "requests==2.19.0\n"
    "flaskk>=2\n"
    "numpy\n"
    "--index-url http://pypi.internal/simple\n"
    "--extra-index-url https://x.example/simple\n"
    "--trusted-host pypi.internal\n"
    "git+https://github.com/a/b.git#egg=b\n"
)


def _ids(result):
    return [f["id"] for f in result["findings"]]


def test_requirements_offline_findings():
    a = deps_audit.audit("requirements.txt", REQ, online=False)
    ids = {f["id"] for f in a["findings"]}
    assert {"deps-index-http", "deps-extra-index", "deps-trusted-host", "deps-direct-url",
            "deps-typosquat", "deps-unpinned"} <= ids
    assert next(f for f in a["findings"] if f["id"] == "deps-index-http")["severity"] == "high"
    assert next(f for f in a["findings"] if f["id"] == "deps-typosquat")["line"] == 2
    assert any("online checks are off" in d for d in a["degraded"])


def test_popular_names_are_not_typosquats():
    a = deps_audit.audit("requirements.txt", "flask==3.0.0\nrequests==2.31.0\nsix==1.16.0\n", online=False)
    assert "deps-typosquat" not in {f["id"] for f in a["findings"]}
    assert "deps-unpinned" not in {f["id"] for f in a["findings"]}


def test_package_json_and_pyproject():
    pj = json.dumps({"dependencies": {"lodahs": "^4.0.0", "express": "4.18.2", "mylib": "github:a/b"}})
    a = deps_audit.audit("package.json", pj, online=False)
    assert {"deps-typosquat", "deps-direct-url", "deps-unpinned"} <= {f["id"] for f in a["findings"]}
    toml = '[project]\nname = "x"\ndependencies = ["requets>=2", "pytest==8.0.0"]\n'
    b = deps_audit.audit("pyproject.toml", toml, online=False)
    assert "deps-typosquat" in {f["id"] for f in b["findings"]}
    assert b["deps"] == 2


def test_code_and_prose_are_not_manifests():
    assert deps_audit.audit("", "import os\nx = 1\n", online=False) is None
    assert deps_audit.audit("", "hello\nworld\nthis is prose\n", online=False) is None
    assert deps_audit.audit("app.py", "requests==2.0\nflask==1\n", online=False) is None


def test_assignments_and_comparisons_are_not_requirements():
    for code in ("x = 1\ny = 2\n", "x = 1\n" + "a" * 700 + "\n", "a >= 3\nb <= 4\nc == 5\n", "name = 'x'\nlevel = 3\n"):
        r = scan_material(code)
        assert not any(f["id"].startswith("deps-") for f in r["findings"]), code


def test_sniffing_without_a_filename():
    a = deps_audit.audit("", "requests==2.31.0\nnumpy>=1.26\n", online=False)
    assert a and a["kind"] == "requirements" and a["deps"] == 2


def test_online_missing_package_and_advisories():
    seen = []

    def fake(url, payload=None):
        seen.append(url)
        if "pypi.org/pypi/ghostpkg" in url:
            return 404, None
        if "pypi.org" in url:
            return 200, {}
        assert url == "https://api.osv.dev/v1/querybatch"
        assert payload["queries"] == [{"package": {"name": "requests", "ecosystem": "PyPI"}, "version": "2.19.0"}]
        return 200, {"results": [{"vulns": [{"id": "GHSA-x"}, {"id": "PYSEC-1"}]}]}

    a = deps_audit.audit("requirements.txt", "requests==2.19.0\nghostpkg\n", online=True, fetch=fake)
    ids = _ids(a)
    assert "deps-missing" in ids and "deps-vulnerable" in ids
    hit = next(f for f in a["findings"] if f["id"] == "deps-vulnerable")
    assert "GHSA-x" in hit["snippet"] and hit["severity"] == "high"
    assert not any("OSV" in d for d in a["degraded"])


def test_online_failures_are_reported_not_silent():
    a = deps_audit.audit("requirements.txt", "requests==2.19.0\n", online=True, fetch=lambda url, payload=None: (0, None))
    assert any("OSV" in d for d in a["degraded"])
    assert any("lookups failed" in d for d in a["degraded"])
    assert "deps-missing" not in _ids(a)


def test_online_sends_only_names_and_versions():
    sent = []

    def fake(url, payload=None):
        sent.append((url, payload))
        return 200, {"results": [{}]} if payload else {}

    deps_audit.audit("requirements.txt", "requests==2.19.0\n", online=True, fetch=fake)
    blob = json.dumps(sent)
    assert "requests" in blob and "2.19.0" in blob
    assert "Authorization" not in blob and "password" not in blob


def test_env_switch(monkeypatch):
    monkeypatch.delenv("VISHAP_DEPS_ONLINE", raising=False)
    assert deps_audit.online_enabled() is False
    monkeypatch.setenv("VISHAP_DEPS_ONLINE", "1")
    assert deps_audit.online_enabled() is True


def test_scan_material_carries_manifest_findings_and_never_says_safe():
    r = scan_material("requests==2.31.0\nnumpy==1.26.0\n", "requirements.txt")
    assert r["coverage"]["complete"] is False
    assert any("online checks are off" in g for g in r["coverage"]["gaps"])
    r2 = scan_material(REQ, "requirements.txt")
    assert {"deps-index-http", "deps-typosquat"} <= {f["id"] for f in r2["findings"]}