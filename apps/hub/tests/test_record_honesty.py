"""The record says what decided a run: the model's words and the client's question are in the fingerprint,
a run with no files does not show the hash of nothing as a snapshot, and the report does not claim a
validator ran when none did."""
import hashlib
from pathlib import Path

from hub import fingerprint, proposal, server, templates
from hub.pipeline import run_plan
from hub.router import plan_for

SQLI = "cur.execute(\"select * from t where a = \" + x)\n"
GOOD = {"calc.py": "def add(a, b):\n    return a + b\n"}
HASH_OF_NOTHING = "44136fa355b3678a"             # sha256 of "{}": what an empty snapshot hashes to


def fake(**over):
    payload = {"ok": True, "model": "test-model", "verdict": "SAFE", "findings": [], "patch": {},
               "questions": [], "proof": [], "summary": "fine"}
    payload.update(over)
    return payload


def _review(monkeypatch, question="", findings=None):
    monkeypatch.setattr(proposal, "propose", lambda **kw: fake(findings=findings or []))
    return run_plan(plan_for("review"), material=SQLI, question=question, api_key="k")


def _model(result):
    return result.fingerprint["body"]["evidence"]["model"]


def test_two_answers_with_the_same_number_of_findings_do_not_share_a_fingerprint(monkeypatch):
    a = _review(monkeypatch, findings=[{"severity": "high", "rule": "CWE-755", "message": "x", "line": 1}])
    b = _review(monkeypatch, findings=[{"severity": "high", "rule": "CWE-400", "message": "y", "line": 2}])
    assert _model(a)["findings"] == _model(b)["findings"] == 1
    assert a.fingerprint["digest"] != b.fingerprint["digest"]
    assert a.fingerprint["id"] != b.fingerprint["id"]
    assert fingerprint.verify(a.fingerprint)[0] and fingerprint.verify(b.fingerprint)[0]


def test_the_question_is_part_of_the_record(monkeypatch):
    asked = _review(monkeypatch, question="is this safe?")
    other = _review(monkeypatch, question="fix it")
    nothing = _review(monkeypatch)
    assert _model(asked)["question_sha256"] == hashlib.sha256(b"is this safe?").hexdigest()
    assert asked.fingerprint["digest"] != other.fingerprint["digest"]
    assert "question_sha256" not in _model(nothing) and "findings_sha256" not in _model(nothing)


def test_a_question_nobody_put_to_a_model_is_not_recorded_as_asked():
    r = run_plan(plan_for("analyse"), material=SQLI, question="is this safe?")
    assert "question_sha256" not in _model(r)


def test_a_run_with_no_files_does_not_show_the_hash_of_nothing_as_a_snapshot():
    html = templates._evidence_block(run_plan(plan_for("analyse"), material=SQLI).fingerprint)
    assert "none (no files were sent)" in html and HASH_OF_NOTHING not in html


def test_a_run_with_files_still_shows_their_snapshot():
    html = templates._evidence_block(run_plan(plan_for("analyse"), material=SQLI, files=GOOD).fingerprint)
    assert "none (no files were sent)" not in html and "snapshot <code>" in html


def test_the_report_does_not_say_a_validator_ran_when_none_did():
    html = templates._evidence_block(run_plan(plan_for("analyse"), material=SQLI).fingerprint)
    assert "did not run: nothing for it to check" in html and "<td>nothing (0 file(s))" not in html


def test_a_key_alone_never_turns_the_model_on_but_a_question_does(monkeypatch):
    monkeypatch.setattr(server, "_model_key_available", lambda body: True)
    assert server._intent_for({"api_key": "k"}, SQLI, "") == "analyse"
    assert server._intent_for({}, SQLI, "") == "analyse"
    assert server._intent_for({"question": "q"}, SQLI, "") == "review"


def test_the_review_is_always_the_base_task_and_the_question_is_added(monkeypatch):
    seen = {}
    real = proposal.llm.request_parts

    def spy(current, key, system, messages, limit):
        seen["text"] = messages[0]["content"]
        return real(current, key, system, messages, limit)

    def refuse(*args, **kwargs):
        raise proposal.urllib.error.URLError("offline")

    monkeypatch.setattr(proposal.llm, "request_parts", spy)
    monkeypatch.setattr(proposal.urllib.request, "urlopen", refuse)
    proposal._call("k", "", SQLI, "", "fix it", "")
    text = seen["text"]
    assert proposal.REVIEW_TASK in text and "Client question:\nfix it" in text
    assert text.index(proposal.REVIEW_TASK) < text.index("Client question:")
    seen.clear()
    proposal._call("k", "", "", "build a thing", "", "")           # a spec alone: no review forced on it
    assert proposal.REVIEW_TASK not in seen["text"]
    seen.clear()
    proposal._call("k", "", SQLI, "", proposal.REVIEW_TASK, "")    # the default question is not sent twice
    assert seen["text"].count(proposal.REVIEW_TASK) == 1


def test_the_server_and_the_model_share_one_review_wording():
    assert server.DEFAULT_REVIEW_QUESTION == proposal.REVIEW_TASK

def test_the_key_hint_says_a_question_is_needed_for_the_model_to_read():
    # a saved key is sent with every run, and a key alone does not turn the model on (see ReviewRoutingTests),
    # so the page must not promise that it does
    web = Path(server.__file__).parent / "web"
    page, script = (web / "index.html").read_text(encoding="utf-8"), (web / "app.js").read_text(encoding="utf-8")
    assert "with your key and a question the model reads the code" in page
    assert "with your key and a question the model reads the code" in script
    assert "с твоим ключом и вопросом код читает ещё и модель" in script
    assert "with your key the model reads the code as well" not in page + script
