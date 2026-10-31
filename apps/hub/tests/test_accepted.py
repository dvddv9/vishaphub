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