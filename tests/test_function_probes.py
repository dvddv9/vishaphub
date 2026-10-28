# -*- coding: utf-8 -*-
"""Function probes: a bug in a plain function is CONFIRMED by running it and breaking an invariant."""
from pathlib import Path

import pytest

from src.tools import probe_funcs as pf
from src.tools import proof
from src.tools.static_scan import scan_material

BLIND = (Path(__file__).parent / "bench" / "blind" / "user_service.py").read_text(encoding="utf-8")


def _run(code, spec=None):
    doc = pf.run(code, spec, force=True)          # our own test code: no containment needed
    assert not doc.get("error"), doc.get("error")
    return {r["id"]: r for r in doc["results"]}


# ---- what is generated (no process started) ----------------------------------------------------------------

def test_schema_is_read_from_the_sql_the_module_executes():
    spec = pf.generate(BLIND)
    tables = spec["tables"]
    assert {"users", "payments", "profiles", "subscriptions"} <= set(tables)
    assert {"id", "username", "email", "password", "balance"} <= set(tables["users"]["cols"])
    assert tables["users"]["seed"] is True and tables["payments"]["seed"] is False     # insert-only: starts empty
    assert any(s.startswith('CREATE TABLE IF NOT EXISTS "users"') and "INTEGER PRIMARY KEY" in s for s in spec["schema"])


def test_hypotheses_are_declarative_data_with_known_check_types():
    for h in pf.generate(BLIND)["hypotheses"]:
        assert {"id", "function", "kind", "args", "checks"} <= set(h)
        assert all(c["type"] in pf.CHECK_TYPES for c in h["checks"])
        assert all(s.split()[0] == "INSERT" for s in h["setup"])


def test_two_accounts_stay_two_accounts_when_one_argument_is_overridden():
    h = {h["id"]: h for h in pf.generate(BLIND)["hypotheses"]}["transfer_funds:race_overdraft"]
    assert h["args"][:2] == [1, 2] and h["args"][2] == 80
    assert h["interleave"]["after"] == "select balance"


def test_a_code_without_sql_gets_no_probes():
    spec = pf.generate("def add(a, b):\n    return a + b\n")
    assert spec["hypotheses"] == []
    assert pf.run("def add(a, b):\n    return a + b\n", force=True)["error"] == "no function probes apply"


def test_own_create_table_statements_win_over_the_inferred_schema():
    code = ('import sqlite3\nDDL = "CREATE TABLE users (id INTEGER PRIMARY KEY, balance REAL NOT NULL);"\n'
            'def f(uid):\n    return sqlite3.connect("x").execute("SELECT balance FROM users WHERE id = ?", (uid,)).fetchone()[0]\n')
    spec = pf.generate(code)
    assert spec["schema"][0].startswith("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, balance REAL NOT NULL)")
    assert len(spec["schema"]) == 1


# ---- the five findings the plan asked for, plus the rest, proven by running --------------------------------

@pytest.fixture(scope="module")
def blind():
    return _run(BLIND)


def test_negative_transfer_amount_is_refused_by_nobody(blind):
    r = blind["transfer_funds:negative_amount"]
    assert r["status"] == "CONFIRMED" and "-(1," in r["evidence"] and "+(1," in r["evidence"]


def test_race_between_check_and_debit_overdraws_the_account(blind):
    r = blind["transfer_funds:race_overdraft"]
    assert r["status"] == "CONFIRMED" and "got -60" in r["evidence"] and "injected" in r["evidence"]


def test_lost_update_in_update_balance(blind):
    r = blind["update_balance:lost_update"]
    assert r["status"] == "CONFIRMED" and "expected 160, got 110" in r["evidence"]


def test_nan_becomes_a_payment_row(blind):
    r = blind["process_payment:nan_amount"]
    assert r["status"] == "CONFIRMED" and "payments:" in r["evidence"]


def test_sql_injection_in_delete_user_wipes_the_table(blind):
    assert blind["delete_user:sqli:user_id"]["status"] == "CONFIRMED"
    r = blind["delete_user:sqli_data:user_id"]
    assert r["status"] == "CONFIRMED" and r["evidence"].count("-(") == 3      # all three users gone for a missing id


def test_hardcoded_token_authenticates_and_the_guarded_statement_is_reached(blind):
    assert blind["reset_password:hardcoded_credential:token"]["status"] == "CONFIRMED"
    r = blind["reset_password:sqli:new_password"]                              # needs the right token to get that far
    assert r["status"] == "CONFIRMED" and "SET password = 'VSHPQ" in r["evidence"]


def test_money_vanishes_when_the_recipient_does_not_exist(blind):
    assert "expected 300, got 290" in blind["transfer_funds:transfer_to_missing"]["evidence"]


def test_success_without_effect_and_crash_on_missing_row(blind):
    assert blind["delete_user:missing_target"]["status"] == "CONFIRMED"
    assert "NoneType" in blind["get_user:missing_row"]["evidence"]


def test_command_injection_reaches_the_recorded_shell_command(blind):
    r = blind["send_notification:cmdi:message"]
    assert r["status"] == "CONFIRMED" and "echo 'VSHPQ; echo pwned'" in r["evidence"]


def test_guarded_code_is_reported_as_not_reproduced_not_as_a_bug(blind):
    assert blind["process_payment:negative_amount"]["status"] == "NOT_REPRODUCED"     # `if amount <= 0` refuses it
    assert blind["transfer_funds:nan_amount"]["status"] == "NOT_REPRODUCED"           # balance >= nan is False
    assert blind["check_subscription:missing_row"]["status"] == "NOT_REPRODUCED"      # `if not row: return False`


def test_a_statement_that_was_never_reached_is_inconclusive_not_safe():
    code = ('import sqlite3\ndef f(token, q):\n    if token != "letmein-123":\n        return False\n'
            '    sqlite3.connect("x").execute(f"SELECT * FROM t WHERE a = \'{q}\'")\n')
    spec = pf.generate(code)
    spec["hypotheses"] = [h for h in spec["hypotheses"] if h["kind"] == "sqli"]
    for h in spec["hypotheses"]:
        h["args"] = ["wrong", pf.PAYLOAD]                                       # the guard stops the call first
    r = _run(code, spec)["f:sqli:q"]
    assert r["status"] == "INCONCLUSIVE" and "no SQL statement was executed" in r["evidence"]


# ---- the harness itself is safe and survives bad modules ---------------------------------------------------

def test_the_module_cannot_reach_the_network_or_write_files_or_start_processes(tmp_path):
    code = ('import os, socket, sqlite3, subprocess\n'
            'def f(x):\n'
            '    sqlite3.connect("x").execute(f"UPDATE t SET a = \'{x}\' WHERE id = 1")\n'
            f'    open({str(tmp_path / "leak.txt")!r}, "w").write("data")\n'
            '    subprocess.run("touch /tmp/vshp_should_not_exist", shell=True)\n'
            '    try:\n        socket.create_connection(("example.com", 80))\n    except OSError:\n        return "blocked"\n')
    r = _run(code)["f:sqli:x"]
    assert r["status"] == "CONFIRMED"
    assert not (tmp_path / "leak.txt").exists() and not Path("/tmp/vshp_should_not_exist").exists()


def test_missing_third_party_modules_are_stubbed_and_a_crashing_import_is_reported():
    code = 'import structlog_not_installed\nimport sqlite3\ndef f(x):\n    sqlite3.connect("x").execute(f"DELETE FROM t WHERE id = {x}")\n'
    doc = pf.run(code, force=True)
    assert not doc["error"] and any("structlog_not_installed" in n for n in doc["notes"])
    bad = pf.run('import sqlite3\nraise RuntimeError("boom")\ndef f(x):\n    sqlite3.connect("x").execute(f"DELETE FROM t WHERE id = {x}")\n', force=True)
    assert "boom" in bad["error"]


def test_an_endless_loop_is_cut_off_and_reported_inconclusive():
    code = 'import sqlite3\ndef f(x):\n    while x:\n        pass\n    sqlite3.connect("x").execute(f"DELETE FROM t WHERE id = {x}")\n'
    spec = pf.generate(code)
    spec["hypotheses"] = spec["hypotheses"][:1]
    r = list(_run(code, spec).values())[0]
    assert r["status"] == "INCONCLUSIVE" and "did not finish" in r["evidence"]


# ---- model-written hypotheses: structure in, bounded data out ----------------------------------------------

def _llm(items):
    return lambda code, ctx: {"hypotheses": items}


GOOD = {"function": "update_balance", "kind": "overdraft", "hypothesis": "a large negative amount drives the balance below zero",
        "invariant": "balance >= 0", "args": [1, -500],
        "checks": [{"type": "sql_min", "sql": "SELECT balance FROM users WHERE id = 1", "min": 0}]}


def test_a_model_hypothesis_is_validated_run_and_merged():
    base = pf.generate(BLIND)
    extra = pf.llm_hypotheses(BLIND, _llm([GOOD]), base=base)
    assert len(extra) == 1 and extra[0]["id"].startswith("LLM:") and extra[0]["setup"]
    r = _run(BLIND, {"schema": base["schema"], "hypotheses": extra})[extra[0]["id"]]
    assert r["status"] == "CONFIRMED" and "expected >= 0, got -400" in r["evidence"]


@pytest.mark.parametrize("bad", [
    {**GOOD, "function": "does_not_exist"},
    {**GOOD, "checks": [{"type": "exec_python", "code": "import os"}]},
    {**GOOD, "checks": [{"type": "sql_min", "sql": "DELETE FROM users", "min": 0}]},
    {**GOOD, "checks": [{"type": "sql_min", "sql": "SELECT 1; DROP TABLE users", "min": 0}]},
    {**GOOD, "setup": ["DROP TABLE users"]},
    {**GOOD, "interleave": {"after": "select", "sql": "ATTACH DATABASE 'x' AS y"}},
    {**GOOD, "checks": []},
    "not a dict",
])
def test_unsafe_or_malformed_model_hypotheses_are_dropped(bad):
    assert pf.llm_hypotheses(BLIND, _llm([bad])) == []


def test_a_failing_model_never_breaks_the_probes():
    def boom(code, ctx):
        raise RuntimeError("network down")
    assert pf.llm_hypotheses(BLIND, boom) == []
    assert pf.llm_hypotheses(BLIND, lambda c, x: "garbage") == []


def test_duplicates_of_generated_hypotheses_are_not_added_twice():
    base = pf.generate(BLIND)
    same = {"function": "update_balance", "kind": "negative_amount", "args": [1, -5],
            "checks": [{"type": "db_unchanged"}]}
    h = pf.generate(BLIND)["hypotheses"]
    same["kind"] = "negative_amount"
    assert pf.llm_hypotheses(BLIND, _llm([same]), base=base) == []


# ---- annotate: rule findings get the proof; unreported proven bugs become findings -------------------------

def test_rule_findings_get_proof_and_proven_bugs_without_a_rule_become_findings():
    scan = scan_material(BLIND, "user_service.py")
    doc = proof.prove(BLIND, scan["findings"], force=True)
    assert not doc.get("error") and doc["function_probes"]["results"]
    by = {}
    for f in scan["findings"]:
        by.setdefault(f["id"], []).append(f)
    assert any(f.get("status") == "CONFIRMED" for f in by["sqli-fstring"])
    assert any(f.get("status") == "CONFIRMED" and "lost update" in f["title"] for f in by["func-read-modify-write"])
    new = [f for f in scan["findings"] if f.get("source") == "probe"]
    assert new and all(f["status"] == "CONFIRMED" and f["proof"]["evidence"] for f in new)
    # a rule finding and its probe are one finding, not two: create_user's injection is the taint-flow finding
    kinds = {f["id"] for f in new}
    assert {"probe-hardcoded_credential", "probe-nan_amount", "probe-transfer_to_missing"} <= kinds
    assert "probe-sqli" not in kinds and "probe-cmdi" not in kinds
    # a rule that fires on guarded code is refuted by running it
    refuted = [f for f in scan["findings"] if f["id"] == "logic-fetchone-index" and f["status"] == "NOT_REPRODUCED"]
    assert [f["line"] for f in refuted] == [129]                    # check_subscription: `if not row: return False`


def test_prove_without_handlers_is_no_longer_an_error_when_functions_were_probed():
    doc = proof.prove(BLIND, None, force=True)
    assert not doc.get("error") and doc["handlers"] == 0 and doc["function_probes"]["results"]


# ---- verify_patch replays the same hypotheses against the patch --------------------------------------------

PATCHED = BLIND.replace(
    'cursor.execute(f"DELETE FROM users WHERE id = {user_id}")\n    db.commit()\n    return True',
    'cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))\n    db.commit()\n    return cursor.rowcount > 0')


def test_verify_patch_replays_function_probes_before_and_after():
    assert PATCHED != BLIND
    v = proof.verify_patch(BLIND, PATCHED, force=True)
    assert "delete_user:sqli:user_id" in v["closed"] and "delete_user:sqli_data:user_id" in v["closed"]
    assert "delete_user:missing_target" in v["closed"]
    assert "transfer_funds:negative_amount" in v["still_open"]
    assert v["verdict"] == "PARTIAL" and not v["regressions"]


def test_verify_patch_flags_a_patch_that_changes_nothing_and_one_that_removes_the_function():
    assert proof.verify_patch(BLIND, BLIND, force=True)["verdict"] == "NO_EFFECT"
    gone = BLIND.replace("def delete_user(", "def _removed(")
    v = proof.verify_patch(BLIND, gone, force=True)
    assert "delete_user" in v["removed_handlers"]
