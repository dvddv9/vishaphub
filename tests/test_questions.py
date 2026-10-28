# -*- coding: utf-8 -*-
"""Questions: only for what the skeptic left open, at most five, answers move severity and are remembered."""
from pathlib import Path

import pytest

from src.tools import proof, questions, skeptic
from src.tools.static_scan import scan_material

BENCH = Path(__file__).parent / "bench" / "blind"
USER = (BENCH / "user_service.py").read_text(encoding="utf-8")
WALLET = (BENCH / "wallet_service.py").read_text(encoding="utf-8")


@pytest.fixture()
def user():
    scan = scan_material(USER, "u.py")
    proof.prove(USER, scan["findings"], force=True)
    return scan["findings"]


def _by(findings):
    return {skeptic.finding_id(f): f for f in findings}


def test_questions_are_few_structured_and_only_about_open_findings(user):
    qs = questions.ask(user, USER)["questions"]
    assert 3 <= len(qs) <= questions.MAX_QUESTIONS
    by = _by(user)
    for q in qs:
        assert set(q) >= {"question_id", "kind", "text", "options", "finding_ids"} and len(q["options"]) >= 3
        assert all(set(o) == {"key", "label", "impact"} for o in q["options"])
        assert all(by[fid]["skeptic"]["skeptic_verdict"] == "suspected" for fid in q["finding_ids"])   # never confirmed/dismissed ones


def test_the_strongest_open_finding_is_asked_about_first(user):
    qs = questions.ask(user, USER)["questions"]
    assert qs[0]["question_id"] == "exposure:get_user_profile" and qs[0]["top_severity"] == "critical"
    assert {q["kind"] for q in qs} >= {"exposure", "secret_kind"}


def test_a_low_value_question_is_not_asked(user):
    qs = questions.ask(user, USER, max_n=50)["questions"]
    assert all(q["top_severity"] != "low" or q["kind"] == "secret_kind" for q in qs)
    wallet = scan_material(WALLET, "w.py")["findings"]
    proof.prove(WALLET, wallet, force=True)
    assert [q["question_id"] for q in questions.ask(wallet, WALLET)["questions"]] == ["rowcount_consumer:create_order"]


def test_nothing_to_ask_when_everything_is_settled():
    code = "def add(a, b):\n    return a + b\n"
    assert questions.ask([], code) == {"applied": [], "questions": []}


def test_exposure_answers_move_severity_up_and_down(user):
    qs = questions.candidates(user, USER)
    by = _by(user)
    applied = questions.apply_answers(user, qs, {"exposure:get_user_profile": "c", "exposure:bulk_update_users": "a"})
    assert [a["impact"] for a in applied] == ["lower2", "raise"] or {a["impact"] for a in applied} == {"lower2", "raise"}
    assert by["sqli-fstring@64"]["severity"] == "medium" and by["sqli-fstring@64"]["severity_asked"]["from"] == "critical"
    assert by["sqli-fstring@120"]["severity"] == "critical"                      # cannot go above critical
    assert by["sql-star@64"]["severity"] == "low"                               # cannot go below low


def test_answers_are_idempotent_and_can_be_changed(user):
    qs = questions.candidates(user, USER)
    by = _by(user)
    questions.apply_answers(user, qs, {"exposure:get_user_profile": "b"})
    questions.apply_answers(user, qs, {"exposure:get_user_profile": "b"})
    assert by["sqli-fstring@64"]["severity"] == "high"                            # one step, not two
    questions.apply_answers(user, qs, {"exposure:get_user_profile": "d"})
    assert by["sqli-fstring@64"]["severity"] == "critical"                        # "I do not know" restores it


def test_an_example_value_is_dismissed_with_its_basis_and_a_real_key_stays_critical(user):
    qs = questions.candidates(user, USER)
    by = _by(user)
    questions.apply_answers(user, qs, {"secret_kind:API_KEY": "c"})
    assert by["secret-hardcoded@8"]["skeptic"] == {"skeptic_verdict": "false_positive", "basis": "answer",
                                                   "reason": "answered c) An example or placeholder, not a secret"}
    assert by["secret-hardcoded@8"] in skeptic.split(user)[1]
    questions.apply_answers(user, qs, {"secret_kind:API_KEY": "a"})
    assert by["secret-hardcoded@8"]["severity"] == "critical"


def test_an_answer_never_touches_a_probe_result(user):
    qs = questions.candidates(user, USER)
    confirmed = [f for f in user if f.get("status") == "CONFIRMED"]
    before = [(f["status"], f["proof"]["evidence"], f["severity"]) for f in confirmed]
    questions.apply_answers(user, qs, {q["question_id"]: "c" for q in qs})
    assert [(f["status"], f["proof"]["evidence"], f["severity"]) for f in confirmed] == before


def test_unknown_question_or_option_is_ignored(user):
    qs = questions.candidates(user, USER)
    assert questions.apply_answers(user, qs, {"nope:x": "a", "exposure:get_user_profile": "z"}) == []
    assert questions.apply_answers(user, qs, [{"question_id": "exposure:get_user_profile", "answer": "B"}])[0]["impact"] == "lower"


def test_answers_are_remembered_and_not_asked_again(user, tmp_path):
    store_path = tmp_path / ".vishap" / "answers.json"
    first = questions.ask(user, USER)
    qid = first["questions"][0]["question_id"]
    questions.save_store(store_path, {qid: "c", "secret_kind:API_KEY": {"answer": "c"}})
    fresh = scan_material(USER, "u.py")["findings"]
    proof.prove(USER, fresh, force=True)
    again = questions.ask(fresh, USER, store=questions.load_store(store_path))
    assert qid not in [q["question_id"] for q in again["questions"]]
    assert {a["question_id"] for a in again["applied"]} == {qid, "secret_kind:API_KEY"}
    assert _by(fresh)["sqli-fstring@64"]["severity"] == "medium"
    assert all(q["question_id"] not in (qid, "secret_kind:API_KEY") for q in again["questions"])


def test_broken_or_missing_store_is_an_empty_store(tmp_path):
    assert questions.load_store(tmp_path / "nope.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert questions.load_store(bad) == {}
    bad.write_text('["a"]', encoding="utf-8")
    assert questions.load_store(bad) == {}


def test_scope_keeps_files_apart(user):
    a = questions.candidates(user, USER, scope="a.py")
    assert a[0]["question_id"] == "a.py:exposure:get_user_profile"


def test_render_lists_options_and_affected_findings(user):
    md = questions.render_md(questions.ask(user, USER)["questions"])
    assert "**Q1** `exposure:get_user_profile`" in md and "- a) The public" in md and "affects: sqli-fstring@64" in md
    assert questions.render_md([]) == ""
