# -*- coding: utf-8 -*-
"""Focused logic pass: chunking, merge without duplicates, concurrency, never-raise (no network: fake model)."""
import asyncio

from src.pipeline import multipass
from src.tools.chunker import split_code

CODE = '''import os
import sqlite3

DB = os.environ.get("DB_PATH", "app.db")


def update_balance(user_id, amount):
    cur = db.cursor()
    cur.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    bal = cur.fetchone()[0]
    cur.execute("UPDATE users SET balance = ? WHERE id = ?", (bal + amount, user_id))


def transfer_funds(a, b, amount):
    cur = db.cursor()
    cur.execute("SELECT balance FROM users WHERE id = ?", (a,))
    if cur.fetchone()[0] >= amount:
        cur.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (amount, a))
        cur.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, b))


def check_subscription(uid):
    row = db.execute("SELECT expires_at FROM subscriptions WHERE user_id = ?", (uid,)).fetchone()
    return datetime.fromisoformat(row[0]) > datetime.now()
'''


# ---- chunker ------------------------------------------------------------------

def test_one_chunk_when_the_file_is_small_and_lines_keep_their_original_numbers():
    chunks = split_code(CODE, "python")
    assert len(chunks) == 1
    text = chunks[0]["text"]
    assert "    7| def update_balance" in text and "   14| def transfer_funds" in text
    assert chunks[0]["functions"] == ["update_balance", "transfer_funds", "check_subscription"]


def test_big_files_split_by_function_and_every_chunk_repeats_the_header():
    chunks = split_code(CODE, "python", max_chars=330)
    assert len(chunks) >= 2
    for c in chunks:
        assert "import sqlite3" in c["text"]          # header context in every chunk
    seen = [f for c in chunks for f in c["functions"]]
    assert seen == ["update_balance", "transfer_funds", "check_subscription"]   # nothing lost or doubled


def test_chunk_count_is_capped_and_the_tail_is_merged_not_dropped():
    many = "\n\n".join(f"def f{i}(x):\n    return db.execute('SELECT {i}')\n" for i in range(40))
    chunks = split_code(many, "python", max_chars=200, max_chunks=4)
    assert len(chunks) == 4
    assert [f for c in chunks for f in c["functions"]] == [f"f{i}" for i in range(40)]


def test_unparsable_python_falls_back_to_line_chunks():
    broken = "def a(:\n    pass\n\n" * 200
    assert split_code(broken, "python", max_chars=500)


def test_empty_material_gives_no_chunks():
    assert split_code("", "python") == []


# ---- merge --------------------------------------------------------------------

def _f(title, loc, cwe=None, issue=""):
    return {"title": title, "issue": issue, "priority": "важно", "cwe": cwe, "location": loc, "kind": "logic"}


def test_a_known_finding_is_not_added_again():
    existing = [{"id": "SEC-3", "title": "Race condition in transfer_funds", "issue": "balance checked then written",
                 "cwe": "CWE-362", "location": "transfer_funds, line 18"}]
    new = [multipass._norm(_f("transfer_funds: race between check and update", "transfer_funds, line 18-20",
                              "CWE-362"), 1)]
    assert multipass.merge_findings(existing, new) == []


def test_distinct_findings_in_the_same_function_are_both_kept():
    new = [multipass._norm(_f("negative amount reverses the transfer", "transfer_funds, line 15", "CWE-20"), 1),
           multipass._norm(_f("race between balance check and update", "transfer_funds, line 18", "CWE-362"), 2)]
    assert len(multipass.merge_findings([], new)) == 2


def test_the_same_claim_reported_by_two_chunks_is_merged():
    a = multipass._norm(_f("update_balance lost update", "update_balance, line 11", "CWE-362"), 1)
    b = multipass._norm(_f("lost update in update_balance", "update_balance line 11-12", "CWE-362"), 2)
    assert len(multipass.merge_findings([], [a, b])) == 1


def test_priority_is_normalised_and_bad_cwe_is_dropped():
    n = multipass._norm({"title": "x bug", "priority": "high", "cwe": "injection", "location": ["f", 3]}, 1)
    assert n["priority"] == "критично" and n["cwe"] is None and n["location"] == "f, 3"
    assert multipass._norm({"issue": "no title"}, 1) is None


# ---- running ------------------------------------------------------------------

def _runner(calls):
    def run(text, ctx):
        calls.append(ctx)
        return {"findings": [_f("negative amount reverses the transfer", "transfer_funds, line 15", "CWE-20")],
                "_meta": {"tokens_in": 100, "tokens_out": 20, "cost_usd": 0.001}}
    return run


def test_run_logic_passes_collects_findings_cost_and_ids():
    calls = []
    added, info = multipass.run_logic_passes(CODE, "python", _runner(calls))
    assert [f["id"] for f in added] == ["LOG-1"]
    assert info["passes"] == 1 and info["added"] == 1 and info["tokens_in"] == 100
    assert calls[0]["functions"][0] == "update_balance"


def test_each_chunk_gets_only_the_static_findings_from_its_own_lines():
    hint = {"findings": [{"id": "x", "line": 11, "title": "t", "severity": "low"},
                         {"id": "y", "line": 23, "title": "u", "severity": "low"}]}
    calls = []
    multipass.run_logic_passes(CODE, "python", _runner(calls), hint=hint)
    assert len(calls[0]["static_checklist"]["findings"]) == 2          # one chunk covers both lines
    calls.clear()
    from src.tools import chunker
    old = chunker.MAX_CHARS
    try:
        multipass.split_code = lambda m, l: chunker.split_code(m, l, max_chars=330)
        multipass.run_logic_passes(CODE, "python", _runner(calls), hint=hint)
    finally:
        multipass.split_code = chunker.split_code
        chunker.MAX_CHARS = old
    assert len(calls) >= 2
    assert sum(len(c.get("static_checklist", {}).get("findings", [])) for c in calls) == 2


def test_a_failing_chunk_does_not_lose_the_others():
    state = {"n": 0}

    def flaky(text, ctx):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("boom")
        return {"findings": [_f("lost update in update_balance", "update_balance, line 11", "CWE-362")]}

    multipass.split_code = lambda m, l: __import__("src.tools.chunker", fromlist=["x"]).split_code(m, l, max_chars=330)
    try:
        added, info = multipass.run_logic_passes(CODE, "python", flaky)
    finally:
        from src.tools import chunker
        multipass.split_code = chunker.split_code
    assert info["errors"] and len(added) == 1


def test_non_code_and_disabled_do_nothing(monkeypatch):
    assert multipass.run_logic_passes("hello world", "other", _runner([]))[1]["passes"] == 0
    monkeypatch.setenv("VISHAP_MULTIPASS", "0")
    assert multipass.run_logic_passes(CODE, "python", _runner([]))[1]["passes"] == 0


def test_async_twin_gives_the_same_result():
    async def arun(text, ctx):
        return {"findings": [_f("negative amount reverses the transfer", "transfer_funds, line 15", "CWE-20")]}

    added, info = asyncio.run(multipass.arun_logic_passes(CODE, "python", arun))
    assert [f["title"] for f in added] == ["negative amount reverses the transfer"]
    assert info["passes"] == 1


def test_apply_to_stage2_appends_findings_and_adds_cost():
    stage2 = {"security": {"findings": [{"id": "SEC-1", "title": "x"}]},
              "_meta": {"tokens_in": 10, "tokens_out": 5, "cost_usd": 0.01}}
    added = [{"id": "LOG-1", "title": "t", "issue": "", "priority": "важно", "cwe": None, "location": "f", "kind": "logic"}]
    multipass.apply_to_stage2(stage2, added, {"tokens_in": 100, "tokens_out": 20, "cost_usd": 0.002, "passes": 1})
    assert [f["id"] for f in stage2["security"]["findings"]] == ["SEC-1", "LOG-1"]
    assert stage2["_meta"]["tokens_in"] == 110 and abs(stage2["_meta"]["cost_usd"] - 0.012) < 1e-9
    assert stage2["_multipass"]["passes"] == 1


def test_apply_to_stage2_creates_the_security_section_when_missing():
    stage2 = {}
    multipass.apply_to_stage2(stage2, [{"id": "LOG-1", "title": "t"}], {})
    assert stage2["security"]["findings"][0]["id"] == "LOG-1"
