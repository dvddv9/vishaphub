"""Local adapters: the analyser's rules must read the report, not its keys."""
from hub import local


def test_clean_material_is_safe():
    result = local.analyse_static("x = 1\n")
    assert result["ok"] is True
    assert result["verdict"] == "SAFE"
    assert result["findings"] == []


def test_sql_injection_is_found():
    result = local.analyse_static('cur.execute("select * from t where a = " + x)\n')
    assert result["ok"] is True
    assert result["verdict"] == "REQUIRES_REVIEW"
    assert result["findings"], "the rules should name at least one finding"
    rules = {f["rule"] for f in result["findings"]}
    assert any("sqli" in r or "concat" in r for r in rules)


def test_report_keys_are_not_mistaken_for_findings():
    # scan_material returns a report; iterating it used to yield its keys ("engine",
    # "language", …) and a clean file looked like a file full of findings.
    result = local.analyse_static("def add(a, b):\n    return a + b\n")
    assert result["verdict"] == "SAFE", result["findings"]
    assert all(isinstance(f, dict) and f.get("message") is not None for f in result["findings"])


def test_empty_material_is_refused():
    result = local.analyse_static("   ")
    assert result["ok"] is False


def test_validator_runs_in_process(tmp_path):
    files = {
        "calc/__init__.py": "def add(a, b):\n    return a + b\n",
        "test_calc.py": "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
    }
    spec = {"entry": "calc", "files": list(files), "exports": ["add"], "tests": ["test_calc.py"]}
    result = local.validate_code(files, spec)
    assert result["ok"] is True
    assert result["report"]["verdict"] == "PASS"
    assert len(result["report"]["checks"]) == 6


def test_a_path_escape_leaves_nothing_to_check():
    # The escape is dropped, and with it everything the caller sent: an empty
    # deliverable must not come back as PASS.
    result = local.validate_code({"../../etc/passwd": "x"}, {"files": []})
    assert result["ok"] is False
    assert "no usable files" in result["error"]
