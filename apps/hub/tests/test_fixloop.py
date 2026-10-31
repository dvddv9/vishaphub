"""The checking loop: three attempts at most, the check decides, a refusal is sent back with its reason."""
import os
import shutil

import pytest

from hub import fixloop, local, patchcheck, proposal, statuses
from hub.pipeline import run_plan
from hub.router import plan_for

APP = (
    "def find(cur, name):\n"
    "    cur.execute(\"select id from users where name = '\" + name + \"'\")\n"
    "    return cur.fetchall()\n"
)
FIXED = (
    "def find(cur, name):\n"
    "    cur.execute('select id from users where name = ?', (name,))\n"
    "    return cur.fetchall()\n"
)
TEST = (
    "import sqlite3\n\nfrom app import find\n\n\n"
    "def test_find_returns_rows():\n"
    "    con = sqlite3.connect(':memory:')\n"
    "    cur = con.cursor()\n"
    "    cur.execute('create table users (id integer, name text)')\n"
    "    cur.execute(\"insert into users values (1, 'ann')\")\n"
    "    assert find(cur, 'ann') == [(1,)]\n"
)
SNAPSHOT = {"app.py": APP, "test_app.py": TEST}
SPEC = {"entry": "app", "files": ["app.py", "test_app.py"], "exports": ["find"], "tests": ["test_app.py"]}
SQLI = {"class": "sqli", "entry": "app:find", "args": ["$cursor", "$payload"]}

WEAK = {"app.py": APP.replace("name + ", "name.strip() + ")}            # still injectable and still flagged
PARTIAL_PATCH = {"app.py": FIXED + "\n\ndef gone():\n    return 1\n"}   # fixes it but no exploit test is given


def scripted(*statuses_and_patches):
    """A fake check that returns the scripted results in order, and records what it was asked."""
    seen = []
    queue = list(statuses_and_patches)

    def check(snapshot, *, files=None, spec=None, **kw):
        seen.append(files)
        status, reason = queue.pop(0)
        return {"status": status, "reason": reason, "applied": True, "diff_sha256": patchcheck.sha(files or {})}
    check.seen = seen
    return check


def asker(*answers):
    """A fake model: returns the answers in order and records the feedback it was sent."""
    sent = []
    queue = list(answers)

    def ask(text):
        sent.append(text)
        return queue.pop(0)
    ask.sent = sent
    return ask


def ok(patch):
    return {"ok": True, "patch": patch}


V, P, R, U = (statuses.FIX_VERIFIED, statuses.FIX_PARTIAL, statuses.FIX_REJECTED, statuses.FIX_UNVERIFIED)


def test_a_patch_that_verifies_at_once_costs_no_model_call():
    out = fixloop.run(SNAPSHOT, SPEC, {"app.py": FIXED}, asker(), check=scripted((V, "fine")))
    assert out["status"] == V and out["model_calls"] == 0 and len(out["attempts"]) == 1
    assert out["stop_reason"] == "FIX_VERIFIED on attempt 1"


def test_a_rejection_goes_back_with_its_reason_and_the_patch_it_was_about():
    ask = asker(ok({"app.py": FIXED}))
    out = fixloop.run(SNAPSHOT, SPEC, WEAK, ask, check=scripted((R, "the exploit still works after the patch: sqli"), (V, "fine")))
    assert out["status"] == V and out["model_calls"] == 1 and out["stop_reason"] == "FIX_VERIFIED on attempt 2"
    text = ask.sent[0]
    assert "the exploit still works after the patch: sqli" in text and "FIX_REJECTED" in text
    assert "name.strip()" in text and "attempt 1 of 3" in text
    assert "Do not change test files" in text
    assert [a["status"] for a in out["attempts"]] == [R, V] and out["attempts"][1]["source"] == "retry"


def test_three_failures_end_the_loop_with_the_best_status_not_a_promise():
    ask = asker(ok({"app.py": "x = 2\n"}), ok({"app.py": "x = 3\n"}))
    check = scripted((R, "r1"), (P, "p2"), (R, "r3"))
    out = fixloop.run(SNAPSHOT, SPEC, {"app.py": "x = 1\n"}, ask, check=check)
    assert out["model_calls"] == 2 and len(out["attempts"]) == 3          # never more than three attempts
    assert out["status"] == P and out["reason"] == "p2"                   # the best one: partial beats rejected
    assert out["patch"] == {"app.py": "x = 2\n"}
    assert out["stop_reason"] == "3 attempt(s) used; best result FIX_PARTIAL"


def test_the_limit_cannot_be_raised_above_three():
    ask = asker(*[ok({"app.py": f"x = {i}\n"}) for i in range(2, 10)])
    out = fixloop.run(SNAPSHOT, SPEC, {"app.py": "x = 1\n"}, ask, max_attempts=99,
                      check=scripted(*[(R, "no")] * 10))
    assert len(out["attempts"]) == 3 and out["model_calls"] == 2


def test_when_the_checks_cannot_run_the_model_is_not_asked_again():
    ask = asker()
    out = fixloop.run(SNAPSHOT, SPEC, {"app.py": FIXED}, ask, check=scripted((U, "the isolation was not confirmed")))
    assert out["status"] == U and out["model_calls"] == 0 and ask.sent == []
    assert "no retry" in out["stop_reason"] and "isolation was not confirmed" in out["stop_reason"]


@pytest.mark.parametrize("answer,why", [
    ({"ok": False, "error": "HTTP 529 overloaded"}, "could not answer on attempt 2: HTTP 529 overloaded"),
    (ok({}), "proposed no patch on attempt 2"),
    (ok({"app.py": "x = 1\n"}), "repeated the same patch on attempt 2"),
])
def test_a_model_that_fails_repeats_itself_or_proposes_nothing_ends_the_loop_with_that_reason(answer, why):
    out = fixloop.run(SNAPSHOT, SPEC, {"app.py": "x = 1\n"}, asker(answer), check=scripted((P, "partly")))
    assert why in out["stop_reason"] and out["status"] == P and len(out["attempts"]) == 1


def test_the_model_cannot_delete_a_trusted_test_to_get_a_pass():
    """Real patch check, real refusal: the loop forwards the reason, and the tests stay what they were."""
    kill_test = {"test_app.py": None, "app.py": FIXED}
    ask = asker(ok(kill_test), ok(kill_test | {"app.py": FIXED + "\n"}))
    out = fixloop.run(SNAPSHOT, SPEC, kill_test, ask,
                      check=lambda snap, **kw: patchcheck.check(snap, validate=lambda f, s: {"ok": True, "report": {
                          "verdict": "PASS", "checks": []}}, **kw))
    assert out["status"] == R and "trusted" in out["reason"]
    assert "belongs to the trusted checks" in ask.sent[0]
    assert SNAPSHOT["test_app.py"] == TEST                                  # the snapshot is never modified


def test_a_patch_that_fixes_the_finding_but_proves_nothing_is_partial_and_the_reason_says_what_to_add():
    real = lambda snap, **kw: patchcheck.check(snap, validate=lambda f, s: {"ok": True, "report": {
        "verdict": "PASS", "checks": [{"name": "behavior", "ok": True, "skipped": False, "findings": []}]}}, **kw)
    ask = asker(ok(PARTIAL_PATCH))
    out = fixloop.run(SNAPSHOT, SPEC, {"app.py": FIXED + "\n"}, ask, max_attempts=2, check=real)
    assert out["status"] == P and "no exploit test for SQL injection" in out["reason"]
    assert "no exploit test for SQL injection" in ask.sent[0]               # the model is told what is missing


# through the pipeline ---------------------------------------------------------------------------------------

def _model(monkeypatch, *patches):
    calls = []
    queue = list(patches)

    def propose(**kw):
        calls.append(kw["question"])
        patch = queue.pop(0)
        return {"ok": True, "model": "test-model", "verdict": "SAFE", "findings": [], "patch": patch,
                "questions": [], "proof": [], "summary": "I fixed it"}

    monkeypatch.setattr(proposal, "propose", propose)
    return calls


def _validate(monkeypatch):
    original = local.validate_code
    monkeypatch.setattr(local, "validate_code", lambda files, spec: original(files, spec, require_netns=False))


def test_the_loop_in_a_run_retries_once_then_verifies_and_the_risk_verdict_stays_the_rules(monkeypatch):
    import shutil

    from validator import exploits as vexploits

    def real_exploits(files, targets, **kw):
        root, _ = local._materialize(files)
        try:
            return {"ok": True, "exploits": vexploits.run_targets(root, targets)}
        finally:
            shutil.rmtree(root, ignore_errors=True)

    monkeypatch.setattr(local, "run_exploits", real_exploits)
    _validate(monkeypatch)
    calls = _model(monkeypatch, WEAK, {"app.py": FIXED})
    spec = {**SPEC, "exploit_targets": [SQLI]}
    r = run_plan(plan_for("review"), material=APP, files=SNAPSHOT, spec=spec, api_key="k", fix_loop=True)
    data = r.as_dict()
    # the first proposal comes from the generator stage; the loop asked once more, with the reason
    assert len(calls) == 2 and "Fix check, attempt 1 of 3" in calls[1]
    assert data["statuses"]["fix"]["status"] == V
    assert data["patch"] == {"app.py": FIXED}                               # the patch that was verified
    assert data["statuses"]["risk"]["verdict"] == data["verdict"] != "SAFE"  # "I fixed it" did not lower the risk
    ev = data["fingerprint"]["body"]["evidence"]
    assert [a["status"] for a in ev["fix_attempts"]] != [] and ev["fix_attempts"][-1]["status"] == V
    assert "fix loop: FIX_VERIFIED on attempt 2" in ev["stop_reason"]
    from hub import fingerprint
    assert fingerprint.verify(data["fingerprint"]) == (True, "intact")


def test_without_the_flag_the_model_is_called_once_and_the_patch_stays_unverified(monkeypatch):
    calls = _model(monkeypatch, WEAK)
    r = run_plan(plan_for("review"), material=APP, files=SNAPSHOT, api_key="k")
    assert len(calls) == 1 and r.as_dict()["statuses"]["fix"]["status"] == "FIX_UNVERIFIED"


def test_with_no_confirmed_isolation_the_loop_stops_at_once_and_spends_nothing_more(monkeypatch):
    calls = _model(monkeypatch, WEAK)
    r = run_plan(plan_for("review"), material=APP, files=SNAPSHOT, spec=SPEC, api_key="k", fix_loop=True)
    assert len(calls) == 1                                  # the strict validator cannot run here: no retry
    assert r.as_dict()["statuses"]["fix"]["status"] == "FIX_UNVERIFIED"
    assert "no retry" in r.fingerprint["body"]["evidence"]["stop_reason"]


def test_the_server_turns_the_opt_in_field_into_the_loop_flag():
    from hub import server

    class Stub:
        def _send(self, *a, **k):
            raise AssertionError("the request was refused")

    on = server.Handler._run_args(Stub(), {"material": APP, "verify_fix": True})
    off = server.Handler._run_args(Stub(), {"material": APP})
    assert on["fix_loop"] is True and off["fix_loop"] is False

IMAGE = os.getenv("VISHAP_TEST_WORKER_IMAGE", "")


@pytest.mark.skipif(not (IMAGE and shutil.which("docker")), reason="no Docker or VISHAP_TEST_WORKER_IMAGE")
def test_the_whole_loop_runs_inside_real_worker_containers(monkeypatch):
    """A weak first patch is refused by the exploit probe in a container; the retry is verified in another."""
    monkeypatch.setenv("VISHAP_HUB_WORKER_IMAGE", IMAGE)
    ask = asker(ok({"app.py": FIXED}))
    out = fixloop.run(SNAPSHOT, {**SPEC, "exploit_targets": [SQLI]}, WEAK, ask)
    assert [a["status"] for a in out["attempts"]] == [R, V], out["attempts"]
    assert "the exploit still works after the patch: sqli" in ask.sent[0]
    assert out["patch_check"]["validator"]["isolation"]["kind"] == "container"
    assert out["patch_check"]["validator"]["isolation"]["cleanup_confirmed"] is True