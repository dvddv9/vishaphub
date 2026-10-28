# -*- coding: utf-8 -*-
"""Skeptic: one structured verdict per finding; only proof confirms, only proof/quote/dead code dismisses."""
from pathlib import Path

import pytest

from src.tools import callgraph, proof, skeptic
from src.tools.static_scan import scan_material

BENCH = Path(__file__).parent / "bench" / "blind"
USER = (BENCH / "user_service.py").read_text(encoding="utf-8")

APP = '''import sqlite3
from flask import Flask
app = Flask(__name__)


def _old_export(uid):
    return sqlite3.connect("x").execute(f"SELECT * FROM t WHERE id = {uid}").fetchall()


def _helper(uid):
    return sqlite3.connect("x").execute(f"SELECT * FROM t WHERE id = {uid}").fetchall()


def lookup(uid):
    return _helper(uid)


@app.route("/a")
def a():
    return lookup(1)


def cli():
    return a()


if __name__ == "__main__":
    cli()
'''


# ---- call graph -------------------------------------------------------------------------------------------

def test_callgraph_knows_callers_entries_and_dead_functions():
    g = callgraph.build(APP)["functions"]
    assert g["a"]["entry"] == "http" and g["lookup"]["callers"] == ["a"] and g["_helper"]["callers"] == ["lookup"]
    assert g["_old_export"]["callers"] == [] and not g["_old_export"]["referenced"] and g["_old_export"]["entry"] is None
    assert callgraph.reaches(callgraph.build(APP), "_helper") == "public"      # via lookup (public), which a() calls
    assert callgraph.reaches(callgraph.build(APP), "_old_export") is None
    assert callgraph.build(APP)["main_calls"] == ["cli"]


def test_a_function_mentioned_as_a_value_is_alive():
    code = "def _cb(x):\n    return x\nHANDLERS = {'a': _cb}\n"
    g = callgraph.build(code)
    assert g["functions"]["_cb"]["referenced"] and callgraph.reaches(g, "_cb") == "referenced"


def test_unparsable_code_gives_an_empty_graph():
    assert callgraph.build("def (:")["functions"] == {}


# ---- deterministic verdicts -------------------------------------------------------------------------------

def _review(code, **kw):
    scan = scan_material(code, "a.py")
    out = skeptic.review(scan["findings"], code, **kw)
    return scan["findings"], {v["finding_id"]: v for v in out}


def test_dead_private_code_is_dismissed_and_called_private_code_is_not():
    findings, by = _review(APP)
    sq = [f for f in findings if f["id"] == "sqli-fstring"]
    dead = next(f for f in sq if f["line"] == 7)
    live = next(f for f in sq if f["line"] == 11)
    assert by[skeptic.finding_id(dead)]["skeptic_verdict"] == "false_positive" and "dead code" in by[skeptic.finding_id(dead)]["reason"]
    assert by[skeptic.finding_id(live)]["skeptic_verdict"] == "suspected"          # reached from an HTTP handler
    assert live["skeptic"]["skeptic_verdict"] == "suspected"                        # applied in place


def test_public_functions_and_module_level_code_stay_suspected_not_dismissed():
    findings, by = _review(USER)
    assert by["sqli-fstring@64"]["skeptic_verdict"] == "suspected" and "public" in by["sqli-fstring@64"]["reason"]
    assert by["secret-hardcoded@8"]["skeptic_verdict"] == "suspected" and "module level" in by["secret-hardcoded@8"]["reason"]


def test_verdict_has_the_structure_the_plan_asks_for():
    _, by = _review(USER)
    for fid, v in by.items():
        assert set(v) >= {"finding_id", "skeptic_verdict", "reason", "basis"} and v["skeptic_verdict"] in skeptic.VERDICTS
        assert v["reason"] and v["finding_id"] == fid


# ---- proof decides ----------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def proved():
    scan = scan_material(USER, "u.py")
    proof.prove(USER, scan["findings"], force=True)         # also runs the skeptic
    return scan["findings"]


def test_prove_attaches_verdicts_and_proof_decides_both_ways(proved):
    by = {skeptic.finding_id(f): f for f in proved}
    assert by["logic-fetchone-index@129"]["skeptic"]["skeptic_verdict"] == "false_positive"
    assert by["logic-fetchone-index@129"]["skeptic"]["basis"] == "proof"
    assert by["sqli-fstring@111"]["skeptic"]["skeptic_verdict"] == "confirmed"
    kept, dismissed = skeptic.split(proved)
    assert [skeptic.finding_id(f) for f in dismissed] == ["logic-fetchone-index@129"] and len(kept) == len(proved) - 1


def test_verified_block_does_not_list_the_same_refutation_twice(proved):
    md = proof.render_verified_md(proved, {"isolation": "test"})
    assert md.count("logic-fetchone-index") <= 1 and "Dismissed by the skeptic" not in md


def test_dismissed_block_lists_dead_code_with_its_reason():
    findings, _ = _review(APP)
    md = skeptic.render_md(findings)
    assert "Dismissed by the skeptic" in md and "dead code" in md and "sqli-fstring@7" in md


# ---- a model may argue, with a quote, never confirm, never overrule a probe -------------------------------

GUARDED = '''def refund(order_id, amount):
    if amount <= 0 or amount > 500:
        raise ValueError("bad amount")
    return db.execute("UPDATE wallets SET balance = balance + ? WHERE id = ?", (amount, order_id))
'''


def _runner(answer):
    seen = []

    def run(text, ctx):
        seen.append((text, ctx))
        return answer
    run.seen = seen
    return run


def _one(code, answer):
    findings = [{"id": "func-amount-no-bounds", "title": "x", "severity": "medium", "cwe": "CWE-20", "line": 4,
                 "snippet": "", "fix": ""}]
    r = _runner(answer)
    out = skeptic.review(findings, code, runner=r)
    return out[0], r, findings[0]


def test_a_quoted_guard_dismisses_the_finding():
    v, r, f = _one(GUARDED, {"finding_id": "x", "skeptic_verdict": "false_positive", "reason": "amount is bounded first",
                             "quote": "if amount <= 0 or amount > 500:"})
    assert v["skeptic_verdict"] == "false_positive" and v["basis"] == "llm+quote" and f["skeptic"]["skeptic_verdict"] == "false_positive"
    text, ctx = r.seen[0]
    assert "    2|     if amount <= 0" in text and ctx["function"] == "refund" and len(ctx["questions"]) == 3


@pytest.mark.parametrize("answer", [
    {"skeptic_verdict": "false_positive", "reason": "validated elsewhere", "quote": ""},
    {"skeptic_verdict": "false_positive", "reason": "validated", "quote": "if amount > 10_000_000:"},   # not in the code
    {"skeptic_verdict": "false_positive", "reason": "validated", "quote": "if x:"},                     # too short to mean anything
    {"skeptic_verdict": "false_positive", "reason": ""},
    {"skeptic_verdict": "banana", "reason": "x"},
    "not a dict",
])
def test_an_unquoted_or_invented_guard_leaves_the_finding_suspected(answer):
    v, _, _ = _one(GUARDED, answer)
    assert v["skeptic_verdict"] == "suspected"


def test_a_model_cannot_confirm_a_finding():
    v, _, _ = _one(GUARDED, {"skeptic_verdict": "confirmed", "reason": "looks real"})
    assert v["skeptic_verdict"] == "suspected" and "only running the code can confirm" in v["reason"]


def test_a_model_is_not_asked_about_what_a_probe_already_settled():
    findings = [{"id": "sqli-fstring", "title": "x", "severity": "high", "cwe": "CWE-89", "line": 4, "status": "CONFIRMED",
                 "proof": {"status": "CONFIRMED", "evidence": "payload reached the SQL text"}}]
    r = _runner({"skeptic_verdict": "false_positive", "reason": "no", "quote": "if amount <= 0 or amount > 500:"})
    out = skeptic.review(findings, GUARDED, runner=r)
    assert out[0]["skeptic_verdict"] == "confirmed" and out[0]["basis"] == "proof" and not r.seen


def test_a_failing_model_keeps_the_deterministic_verdict():
    def boom(text, ctx):
        raise RuntimeError("down")
    findings = [{"id": "func-amount-no-bounds", "title": "x", "severity": "medium", "line": 4}]
    assert skeptic.review(findings, GUARDED, runner=boom)[0]["skeptic_verdict"] == "suspected"
