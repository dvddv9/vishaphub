"""A person's note on a finding: accepted, and why. It is a note beside the finding, never a verdict."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from hub import accepted, access, store, templates
from hub import server as server_module
from hub.server import Handler

FINDING = {"rule": "sqli-fstring", "cwe": "CWE-89", "severity": "critical", "line": 10, "file": "app.py",
           "message": "SQL query built with an f-string", "seen_by": ["rules"]}
OTHER = {"rule": "route-no-auth", "cwe": "CWE-862", "severity": "medium", "line": 20, "file": "app.py",
         "message": "GET /user: no authentication", "seen_by": ["rules"]}
KEY = accepted.key_of(FINDING)
TOKEN = "own" + "x" * 30                     # a token the server accepts: 24 to 128 of [A-Za-z0-9_-]
STRANGER = "str" + "y" * 30


def result(**over):
    base = {"ok": True, "verdict": "REQUIRES_REVIEW", "findings": [dict(FINDING), dict(OTHER)]}
    base.update(over)
    return base


def record(owner="tok", **over):
    base = {"id": "run1", "at": "2026-10-31T10:00:00", "verdict": "REQUIRES_REVIEW", "ok": True, "plan": {},
            "summary": "", "result": result(), "owners": [store.owner_key(owner)]}
    base.update(over)
    return base


# ---- the note ---------------------------------------------------------------

def test_a_mark_has_a_reason_a_finding_to_stand_beside_and_a_limit():
    for bad in ("", "   ", None, 5):
        with pytest.raises(ValueError, match="reason is required"):
            accepted.mark(result(), KEY, bad, "me", "t")
    with pytest.raises(ValueError, match="no such finding"):
        accepted.mark(result(), "000000000000", "fine", "me", "t")
    with pytest.raises(ValueError, match="longer than"):
        accepted.mark(result(), KEY, "x" * (accepted.MAX_REASON + 1), "me", "t")


def test_a_mark_changes_nothing_but_the_note_and_the_input_is_left_alone():
    before = result()
    after = accepted.mark(before, KEY, "  test fixture only  ", "owner", "2026-10-31T10:00:00")
    assert after["accepted"] == {KEY: {"reason": "test fixture only", "by": "owner", "at": "2026-10-31T10:00:00"}}
    assert {k: v for k, v in after.items() if k != "accepted"} == before and "accepted" not in before


def test_a_mark_can_be_taken_back_and_only_if_it_was_there():
    marked = accepted.mark(result(), KEY, "fine", "me", "t")
    assert "accepted" in marked and accepted.unmark(marked, KEY)["accepted"] == {}
    with pytest.raises(ValueError, match="not marked"):
        accepted.unmark(result(), KEY)


def test_a_shown_result_gives_every_finding_its_key_and_its_note_and_keeps_the_verdict():
    shown = accepted.decorate(accepted.mark(result(), KEY, "fine", "me", "t"))
    assert [f["key"] for f in shown["findings"]] == [KEY, accepted.key_of(OTHER)]
    assert shown["findings"][0]["accepted"]["reason"] == "fine" and "accepted" not in shown["findings"][1]
    assert shown["verdict"] == "REQUIRES_REVIEW"


# ---- the store ---------------------------------------------------------------

def test_only_the_owner_can_annotate_and_a_stranger_gets_the_answer_for_a_missing_run():
    runs = store.RunStore()
    runs.save(record())
    change = lambda r: accepted.mark(r, KEY, "fine", "owner", "t")
    assert runs.annotate("run1", store.owner_key("someone else"), change) == ("missing", "")
    assert runs.annotate("nope", store.owner_key("tok"), change) == ("missing", "")
    assert runs.annotate("run1", store.owner_key("tok"), change) == ("ok", "")
    assert runs.get_for("run1", store.owner_key("tok"))["result"]["findings"][0]["accepted"]["reason"] == "fine"


def test_a_refused_change_is_invalid_and_leaves_the_run_as_it_was():
    runs = store.RunStore()
    runs.save(record())
    status, why = runs.annotate("run1", store.owner_key("tok"), lambda r: accepted.mark(r, KEY, "", "o", "t"))
    assert status == "invalid" and "reason" in why
    assert "accepted" not in runs.get("run1")["result"]


def test_the_same_run_again_keeps_its_notes():
    runs = store.RunStore()
    runs.save(record())
    runs.annotate("run1", store.owner_key("tok"), lambda r: accepted.mark(r, KEY, "fine", "o", "t"))
    runs.save(record(owner="another visitor"))                 # same material, same id, a second visitor
    assert runs.get("run1")["result"]["accepted"][KEY]["reason"] == "fine"


# ---- the report -----------------------------------------------------------------

def test_the_report_shows_the_note_escaped_and_says_the_verdict_is_not_the_note():
    page = templates.report_page(accepted.shown(record(result=accepted.mark(
        result(), KEY, "<b>fixture</b>", "owner", "t"))))
    assert "accepted: &lt;b&gt;fixture&lt;/b&gt;" in page and "<b>fixture</b>" not in page
    assert "not this note" in page


def test_the_report_names_every_reader_that_saw_a_finding():
    seen = dict(FINDING, seen_by=["rules", "external"])
    page = templates.report_page(record(result=result(findings=[seen])))
    assert "(rules + external)" in page


# ---- who may -----------------------------------------------------------------------

def test_a_viewer_may_not_mark_a_member_only_their_own_and_an_owner_any():
    assert not access.PERMISSIONS["viewer"] & {"run.accept.own", "run.accept.any"}
    assert "run.accept.own" in access.PERMISSIONS["member"] and "run.accept.any" not in access.PERMISSIONS["member"]
    assert {"run.accept.own", "run.accept.any"} <= access.PERMISSIONS["owner"]


# ---- over HTTP ------------------------------------------------------------------------

@pytest.fixture()
def port(monkeypatch):
    runs = store.RunStore()
    runs.save(record(owner=TOKEN))
    monkeypatch.setattr(server_module, "RUNS", runs)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def call(port, path, body=None, token=TOKEN):
    headers = {"content-type": "application/json"}
    if token:
        headers[server_module.OWNER_HEADER] = token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers,
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_accept_then_read_then_take_it_back_and_the_verdict_never_moves(port):
    status, body = call(port, "/api/runs/run1/accept", {"key": KEY, "reason": "only in the test fixtures"})
    assert status == 200 and body == {"ok": True, "key": KEY, "accepted": True}
    status, run = call(port, "/api/runs/run1")
    assert status == 200 and run["verdict"] == "REQUIRES_REVIEW" and run["result"]["verdict"] == "REQUIRES_REVIEW"
    assert run["result"]["findings"][0]["accepted"]["reason"] == "only in the test fixtures"
    assert call(port, "/api/runs/run1/unaccept", {"key": KEY})[0] == 200
    assert "accepted" not in call(port, "/api/runs/run1")[1]["result"]["findings"][0]


def test_the_refusals_say_what_is_wrong(port):
    assert call(port, "/api/runs/run1/accept", {"key": KEY, "reason": ""})[0] == 400
    assert call(port, "/api/runs/run1/accept", {"key": "0" * 12, "reason": "x"})[0] == 400
    assert call(port, "/api/runs/run1/accept", {"key": KEY, "reason": "x"}, token="")[0] == 403
    assert call(port, "/api/runs/run1/accept", {"key": KEY, "reason": "x"}, token=STRANGER)[0] == 404
    assert call(port, "/api/runs/nope/accept", {"key": KEY, "reason": "x"})[0] == 404


# ---- standing rules -----------------------------------------------------------------

def test_a_rule_names_what_it_matches_and_why_and_a_rule_that_matches_everything_is_refused():
    assert accepted.parse_rules([{"cwe": "89", "reason": " fixtures "}, {"file": "tests/*", "reason": "tests"}]) == [
        {"reason": "fixtures", "cwe": "89"}, {"reason": "tests", "file": "tests/*"}]
    bad = [None, {}, [5], [{"reason": "x"}], [{"cwe": "CWE-89"}], [{"cwe": "banana", "reason": "x"}],
           [{"cwe": "CWE-89", "reason": "x", "severity": "low"}], [{"rule": "", "reason": "x"}],
           [{"file": "*", "reason": "x" * (accepted.MAX_REASON + 1)}], [{"cwe": "1", "reason": "x"}] * (accepted.MAX_RULES + 1)]
    for raw in bad:
        with pytest.raises(ValueError):
            accepted.parse_rules(raw)


def test_a_rule_matches_by_class_rule_name_and_file_and_the_first_matching_rule_names_itself():
    findings = [dict(FINDING), dict(OTHER), dict(FINDING, line=30, in_patch=True)]
    rules = accepted.parse_rules([{"cwe": "CWE-862", "reason": "no auth on purpose"},
                                  {"cwe": "89", "file": "APP.PY", "reason": "fixture"},
                                  {"cwe": "89", "reason": "never reached"}])
    marks = accepted.standing(findings, rules, "t")
    assert marks == {accepted.key_of(OTHER): {"reason": "no auth on purpose", "by": "rule:1", "at": "t"},
                     KEY: {"reason": "fixture", "by": "rule:2", "at": "t"}}          # the patch's finding is not matched
    assert accepted.standing(findings, accepted.parse_rules([{"rule": "other", "reason": "x"}]), "t") == {}
    assert accepted.standing(findings, accepted.parse_rules([{"file": "nope.py", "reason": "x"}]), "t") == {}


def test_standing_rules_in_a_run_note_the_findings_and_leave_the_verdict_alone():
    from hub.pipeline import run_plan
    from hub.router import plan_for
    material = "cur.execute(\"select * from t where a = \" + x)\n"
    base = run_plan(plan_for("analyse"), material=material, files={"calc.py": "x = 1\n"})
    rules = accepted.parse_rules([{"cwe": "CWE-89", "reason": "fixture"}])
    got = run_plan(plan_for("analyse"), material=material, files={"calc.py": "x = 1\n"}, accept_rules=rules)
    assert got.verdict == base.verdict and got.findings == base.findings
    assert got.accepted and all(note["by"] == "rule:1" and note["reason"] == "fixture" for note in got.accepted.values())
    assert "accepted" not in base.as_dict() and got.as_dict()["accepted"] == got.accepted


@pytest.fixture()
def run_port(monkeypatch):
    from hub import limits
    saved = dict(server_module.LIMITERS)
    for kind in server_module.LIMITERS:
        server_module.LIMITERS[kind] = limits.RateLimiter(0)
    monkeypatch.setattr(server_module, "RUNS", store.RunStore())
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()
    server_module.LIMITERS.update(saved)


def test_a_run_over_http_takes_standing_rules_and_bad_ones_are_a_400(run_port):
    material = "cur.execute(\"select * from t where a = \" + x)\n"
    status, body = call(run_port, "/run", {"material": material, "intent": "analyse",
                                           "accept_rules": [{"cwe": "CWE-89", "reason": "fixture"}]})
    assert status == 200 and body["accepted"] and all(n["reason"] == "fixture" for n in body["accepted"].values())
    status, body = call(run_port, "/run", {"material": material, "intent": "analyse", "accept_rules": [{"cwe": "89"}]})
    assert status == 400 and body["error"].startswith("accept_rules:") and "reason" in body["error"]