"""Local adapters: the analyser's rules must read the report, not its keys - and SAFE must mean what it says.

SAFE is not "the rules found nothing". It is issued only for a language whose rules passed the gates registered
before the blind measurement (tests/bench/blind_public/CRITERION.md), for a text the scan could read in full, with
nothing found. Every other outcome is REQUIRES_REVIEW, with the reason.
"""
import json
from pathlib import Path
from unittest import mock

from hub import local
from hub.pipeline import run_plan
from hub.router import plan_for

ALLOWED = {"languages": {"python": {"safe_allowed": True, "dangerous": 40, "safe": 40,
                                    "false_safe_upper_95": 0.1, "why": "passed G1 and G2"}}}


PYTHON = "def add(a, b):\n    return a + b\n"


def with_quality(quality):
    return mock.patch("src.tools.safe_gate.load_quality", lambda path=None: quality)


def test_clean_material_is_not_safe_while_its_language_is_unmeasured():
    result = local.analyse_static("x = 1\n")
    assert result["ok"] is True
    assert result["verdict"] == "REQUIRES_REVIEW"
    assert result["findings"] == []
    assert result["reason"].startswith("unknown coverage")
    assert "not a claim that the code has no vulnerabilities" in result["meaning"]


def test_nothing_found_is_safe_only_for_a_language_that_passed_its_gates():
    with with_quality(ALLOWED):
        result = local.analyse_static(PYTHON)
    assert result["verdict"] == "SAFE"
    assert "measured on 40 dangerous and 40 safe independent examples" in result["reason"]
    with with_quality(ALLOWED):                       # one line of nothing in particular is not recognised as Python
        assert local.analyse_static("x = 1\n")["verdict"] == "REQUIRES_REVIEW"


def test_a_passing_language_is_still_not_safe_when_the_scan_could_not_read_all_of_it():
    with with_quality(ALLOWED):
        result = local.analyse_static("x = 1\n" + "a" * 700 + "\n")
    assert result["verdict"] == "REQUIRES_REVIEW"
    assert "cut before matching" in result["reason"]
    assert result["coverage"]["complete"] is False


def test_an_unrecognised_language_is_never_safe_whatever_the_table_says():
    everything = {"languages": {"unknown": {"safe_allowed": True}, "python": ALLOWED["languages"]["python"]}}
    with with_quality(everything):
        result = local.analyse_static("foo bar baz\n")
    assert result["verdict"] == "REQUIRES_REVIEW" and "not recognised" in result["reason"]


def test_a_missing_quality_file_fails_closed(tmp_path):
    from src.tools import safe_gate
    assert safe_gate.load_quality(tmp_path / "nope.json") == {"languages": {}}
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    assert safe_gate.load_quality(tmp_path / "bad.json") == {"languages": {}}
    with with_quality({"languages": {}}):
        assert local.analyse_static("x = 1\n")["verdict"] == "REQUIRES_REVIEW"


def test_a_finding_is_review_even_for_a_language_that_passed():
    with with_quality(ALLOWED):
        result = local.analyse_static("result = eval(user_text)\n")
    assert result["verdict"] == "REQUIRES_REVIEW"
    assert result["raw"]["critical"] is True and "critical" in result["reason"]


def test_sql_injection_is_found():
    result = local.analyse_static('cur.execute("select * from t where a = " + x)\n')
    assert result["ok"] is True
    assert result["verdict"] == "REQUIRES_REVIEW"
    assert result["findings"], "the rules should name at least one finding"
    rules = {f["rule"] for f in result["findings"]}
    assert any("sqli" in r or "concat" in r for r in rules)


def test_report_keys_are_not_mistaken_for_findings():
    # scan_material returns a report; iterating it used to yield its keys ("engine",
    # "language", :) and a clean file looked like a file full of findings.
    result = local.analyse_static("def add(a, b):\n    return a + b\n")
    assert result["findings"] == [], result["findings"]
    with with_quality(ALLOWED):
        assert local.analyse_static("def add(a, b):\n    return a + b\n")["verdict"] == "SAFE"


def test_the_shipped_quality_table_is_what_the_registered_gates_say():
    from src.tools import safe_gate
    criterion_path = (Path(safe_gate.__file__).resolve().parents[2] / "tests" / "bench" / "blind_public" / "criterion.json")
    criterion = json.loads(criterion_path.read_text(encoding="utf-8"))
    table = safe_gate.load_quality()["languages"]
    for lang, entry in table.items():
        gate = safe_gate.evaluate_gates(entry, criterion)
        assert entry["safe_allowed"] == gate["safe_allowed"], lang
        assert not entry["safe_allowed"] or (entry["measured"] and entry["critical_false_safe"] == 0), lang
    assert not {"", "unknown", "log"} & set(table)


def test_the_pipeline_carries_the_reason_and_the_meaning_to_the_report():
    result = run_plan(plan=plan_for("analyse", 1), material="x = 1\n").as_dict()
    assert result["verdict"] == "REQUIRES_REVIEW"
    assert "unknown coverage" in result["steps"][-1]["detail"]
    with with_quality(ALLOWED):
        safe = run_plan(plan=plan_for("analyse", 1), material=PYTHON).as_dict()
    assert safe["verdict"] == "SAFE" and safe["checks"]["analyser"]["meaning"]


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