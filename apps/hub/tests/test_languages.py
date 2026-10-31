"""Language support is a measured claim: counts from a labelled benchmark, never a list somebody typed."""
import importlib.util
import json
import os

import pytest
from test_service import ServerCase

from hub import ci, cli, export, languages, templates
from hub.pipeline import run_plan
from hub.router import plan_for

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCRIPT = os.path.join(ROOT, "apps", "hub", "scripts", "language_evidence.py")
PY = "import os\n\n\ndef run(name):\n    os.system('echo ' + name)\n"
GO = 'package main\n\nimport "os/exec"\n\nfunc main() {\n\texec.Command("sh", "-c", "ls")\n}\n'
JS = 'const { exec } = require("child_process");\nfunction run(dir) {\n  exec("ls " + dir);\n}\n'


def generator():
    spec = importlib.util.spec_from_file_location("language_evidence_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# the gate: no rules without data -----------------------------------------------------------------------

def test_the_committed_evidence_is_the_benchmarks_current_counts():
    """If the benchmark changed, the copy must be regenerated: `python apps/hub/scripts/language_evidence.py --write`."""
    gen = generator()
    assert os.path.isfile(os.path.join(gen.BENCH, "RESULTS.json")), "the labelled benchmark is missing"
    assert generator().main(["--check"]) == 0


def test_every_language_the_engine_has_rules_for_has_labelled_data_or_a_visible_exemption():
    from src.tools.static_scan import RULES
    with_rules = {lang for rule in RULES if rule.langs for lang in rule.langs}
    labelled = set(languages.data()["languages"])
    missing = sorted(with_rules - labelled - set(languages.EXEMPT))
    assert not missing, (f"rules exist for {missing} but no labelled example does, and no exemption says why: "
                         "add labelled examples (dangerous and safe) to tests/bench/labelled, or name the language "
                         "in hub.languages.EXEMPT with the reason")


def test_an_exemption_is_a_reason_and_goes_stale_the_day_data_arrives():
    for lang, why in languages.EXEMPT.items():
        assert len(why) >= 20, lang
        assert lang not in languages.data()["languages"], f"{lang} now has labelled data: remove the exemption"


def test_a_labelled_language_has_both_dangerous_and_safe_examples():
    """Without safe examples nothing can say how often the rules cry wolf."""
    for lang, row in languages.data()["languages"].items():
        for mode in ("named", "pasted"):
            assert row[mode]["dangerous_examples"] >= 1 and row[mode]["safe_examples"] >= 1, (lang, mode)


# the adequacy ----------------------------------------------------------------------------------------------

@pytest.fixture()
def fake_data(monkeypatch):
    def make(dangerous, safe, expected=10, hit=7):
        row = {"pasted": {"dangerous_examples": dangerous, "safe_examples": safe, "expected_findings": expected,
                          "hit_findings": hit, "dangerous_got_safe": 1, "critical_got_safe": 0, "safe_flagged": 1,
                          "wrong_line_only": 0, "fp_findings": 1}, "named": {}, "not_independent_examples": 2}
        monkeypatch.setattr(languages, "_CACHE", {"languages": {"xx": row}, "source": {}})
        return languages.evidence_for("xx")
    return make


@pytest.mark.parametrize("dangerous,safe,adequacy", [
    (10, 5, "measured"), (9, 5, "thin"), (10, 4, "thin"), (100, 4, "thin"), (3, 2, "thin"), (0, 0, "thin")])
def test_the_thresholds_decide_the_adequacy_not_an_opinion(fake_data, dangerous, safe, adequacy):
    assert fake_data(dangerous, safe)["adequacy"] == adequacy


def test_a_language_with_no_labelled_example_is_none_and_says_nothing_is_known():
    ev = languages.evidence_for("brainfuck")
    assert ev["adequacy"] == "none" and "nothing is known" in languages.sentence(ev)
    assert languages.evidence_for("")["language"] == "unknown"


def test_a_thin_set_is_shown_as_counts_not_as_a_rate(fake_data):
    text = languages.sentence(fake_data(4, 2))
    assert "thin evidence" in text and "counts, not rates" in text and "4 dangerous and 2 safe" in text


def test_the_numbers_for_the_languages_the_hub_has_today():
    py, go, docker = (languages.evidence_for(x) for x in ("python", "go", "dockerfile"))
    assert py["adequacy"] == "measured" and py["dangerous_examples"] >= 10 and py["safe_examples"] >= 5
    assert go["adequacy"] == "thin" and docker["adequacy"] == "thin"
    assert languages.evidence_for("log")["adequacy"] == "none"
    assert py["critical_got_safe"] == 0                  # the benchmark's own release blocker
    table = languages.table()
    assert table["schema"] == "vishap.languages/1" and {x["language"] for x in table["languages"]} >= {"python", "go", "log"}


# in a run, in the contract, in the exports ---------------------------------------------------------------

def analyse(material):
    return run_plan(plan_for("analyse"), material=material)


def test_a_run_records_how_well_the_rules_are_measured_for_what_it_read():
    r = analyse(PY)
    row = r.checks["analyser"]["languages"]
    assert [x["language"] for x in row] == ["python"] and row[0]["adequacy"] == "measured"
    assert r.fingerprint["body"]["evidence"]["languages"] == row                  # inside the hashed evidence
    assert analyse(PY).fingerprint["digest"] == r.fingerprint["digest"]           # and deterministic


def test_another_language_is_read_as_thin():
    js = analyse(JS).checks["analyser"]["languages"][0]
    assert js["language"] == "javascript" and js["adequacy"] == "thin" and js["dangerous_examples"] < 10


def test_a_language_the_text_alone_does_not_reveal_is_unknown_and_says_why():
    """Go, PHP and Dockerfile are recognised by file name; the hub sends text. Measured, and said."""
    ev = analyse(GO).checks["analyser"]["languages"][0]
    assert ev["language"] == "unknown" and ev["adequacy"] == "none" and "without a file name" in ev["reason"]


def result_of(languages_row, verdict="REQUIRES_REVIEW", ok=True):
    return {"ok": ok, "verdict": verdict, "checks": {"analyser": {"languages": languages_row}},
            "statuses": {"verification": {"status": "COMPLETE", "ran": ["analyser"], "not_run": []}}}


def test_require_measured_refuses_a_green_the_benchmark_cannot_back():
    thin = {"language": "javascript", "adequacy": "thin", "dangerous_examples": 9, "safe_examples": 4}
    good = {"language": "python", "adequacy": "measured", "dangerous_examples": 19, "safe_examples": 6}
    assert ci.decide(result_of([thin]))["exit_code"] == 0                         # off by default
    out = ci.decide(result_of([thin]), require_measured=True)
    assert out["exit_code"] == 3 and "javascript (thin: 9 dangerous, 4 safe labelled examples)" in out["reasons"][0]
    assert out["languages"] == {"javascript": "thin"} and out["require_measured"] is True
    assert ci.decide(result_of([good]), require_measured=True)["exit_code"] == 0
    assert ci.decide(result_of([good, thin]), require_measured=True)["exit_code"] == 3
    assert ci.decide({"ok": True, "verdict": "PASS", "checks": {}}, require_measured=True)["exit_code"] == 0
    assert ci.decide(result_of([thin], verdict="FAIL"), require_measured=True)["exit_code"] == 1   # a failure wins


def test_the_cli_has_the_flag(tmp_path, capsys):
    path = tmp_path / "m.js"
    path.write_text(JS, encoding="utf-8")
    assert cli.main(["run", "--intent", "analyse", "--material", str(path)]) == 0
    assert cli.main(["run", "--intent", "analyse", "--material", str(path), "--require-measured"]) == 3
    assert "not measured well enough" in capsys.readouterr().out


def test_the_report_and_the_export_say_it():
    r = analyse(JS)
    data = r.as_dict()
    html = templates.report_page({"id": "abc", "result": data, "verdict": r.verdict})
    assert "language evidence" in html and "thin evidence" in html
    assert "Language evidence: javascript: thin evidence" in export.markdown({"id": "abc", "result": data})


class Doors(ServerCase):
    def test_the_languages_door_is_public_data_with_its_thresholds(self):
        status, raw = self.get("/api/languages")
        data = json.loads(raw)
        assert status == 200 and data["thresholds"] == {"measured_needs_dangerous": 10, "measured_needs_safe": 5}
        by = {x["language"]: x["adequacy"] for x in data["languages"]}
        assert by["python"] == "measured" and by["go"] == "thin" and by["log"] == "none" and by["unknown"] == "none"

    def test_a_run_can_ask_for_measured_languages_only(self):
        status, _h, raw = self.post("/run", {"material": JS, "intent": "analyse", "require_measured": True})
        data = json.loads(raw)
        assert status == 200 and data["ci"]["exit_code"] == 3 and data["ci"]["languages"] == {"javascript": "thin"}