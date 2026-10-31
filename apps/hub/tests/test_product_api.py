"""What a pipeline and a reader get: the CI contract, the exports, the integrity re-check, honest lists."""
import json
import secrets

import pytest
from test_service import ServerCase

from hub import ci, cli, export, server, templates
from hub.pipeline import run_plan
from hub.router import plan_for

SQLI = "cur.execute('select ' + name)\n"
CLEAN = "x = 1\n"
STORE_MARKER = "ZZ-material-marker-4242"          # something only the material says, to prove it is not exported


def result(verdict="REQUIRES_REVIEW", ok=True, verification="PARTIAL", ran=("analyser",), not_run=("validator",)):
    return {"ok": ok, "verdict": verdict, "reason": "" if ok else "boom",
            "statuses": {"fix": {"status": "NO_PATCH"},
                         "verification": {"status": verification, "ran": list(ran), "not_run": list(not_run)}}}


# the contract ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("verdict,fail_on,code", [
    ("PASS", "fail", 0), ("SAFE", "emergency", 0), ("REQUIRES_REVIEW", "fail", 0), ("REQUIRES_REVIEW", "review", 1),
    ("NEEDS_REVIEW", "review", 1), ("FAIL", "fail", 1), ("FAIL", "emergency", 0), ("EMERGENCY", "emergency", 1),
    ("EMERGENCY", "fail", 1), ("ERROR", "emergency", 1), ("", "fail", 1), ("NONSENSE", "emergency", 1),
])
def test_the_verdict_against_the_failing_level_gives_the_exit_code(verdict, fail_on, code):
    out = ci.decide(result(verdict), fail_on)
    assert out["exit_code"] == code and out["pass"] is (code == 0) and out["schema"] == "vishap.run/1"
    assert bool(out["reasons"]) is (code != 0)


def test_a_run_that_did_not_pass_its_own_gates_fails_whatever_the_level():
    out = ci.decide(result("ERROR", ok=False), "emergency")
    assert out["exit_code"] == 1 and "did not pass its own gates" in out["reasons"][0]


def test_an_incomplete_run_passes_by_default_but_never_with_require_complete():
    inc = result("PASS", verification="PARTIAL")
    assert ci.decide(inc)["exit_code"] == 0 and ci.decide(inc)["complete"] is False       # visible either way
    strict = ci.decide(inc, require_complete=True)
    assert strict["exit_code"] == 3 and not strict["pass"]
    assert "PARTIAL" in strict["reasons"][0] and "not run validator" in strict["reasons"][0]
    assert ci.decide(result("PASS", verification="NOT_RUN", ran=(), not_run=()), require_complete=True)["exit_code"] == 3
    assert ci.decide(result("PASS", verification="COMPLETE", ran=("analyser", "validator"), not_run=()),
                     require_complete=True)["exit_code"] == 0


def test_a_failing_verdict_wins_over_incompleteness():
    assert ci.decide(result("FAIL", verification="PARTIAL"), "fail", True)["exit_code"] == 1


def test_a_run_without_statuses_is_incomplete_not_complete():
    out = ci.decide({"ok": True, "verdict": "PASS"}, require_complete=True)
    assert out["exit_code"] == 3 and out["complete"] is False


def test_an_unknown_failing_level_is_refused():
    with pytest.raises(ValueError):
        ci.decide(result(), "whenever")


# over HTTP --------------------------------------------------------------------------------------------

class ApiTests(ServerCase):
    def run_json(self, material, cookie=None, **extra):
        status, headers, raw = self.post("/run", {"material": material, "intent": "analyse", **extra}, cookie=cookie)
        return status, headers, json.loads(raw)

    def test_a_run_carries_the_schema_and_the_decision_but_the_stored_record_does_not(self):
        status, _h, data = self.run_json(SQLI)
        assert status == 200 and data["schema"] == "vishap.run/1" and data["ci"]["schema"] == "vishap.run/1"
        stored = server.RUNS.get(data["fingerprint"]["id"])
        assert "ci" not in stored and "ci" not in stored["result"]

    def test_the_options_are_per_request(self):
        _s, _h, lenient = self.run_json(SQLI)
        _s, _h, strict = self.run_json(SQLI, fail_on="review")
        _s, _h, complete = self.run_json(CLEAN, require_complete=True)
        assert lenient["ci"]["exit_code"] in (0, 1)
        assert strict["ci"]["fail_on"] == "review" and strict["ci"]["exit_code"] == 1
        assert complete["ci"]["exit_code"] == 3 and complete["ci"]["verification"] == "PARTIAL"

    def test_a_bad_failing_level_is_a_400_and_nothing_runs(self):
        from unittest import mock
        with mock.patch.object(server, "run_plan", side_effect=AssertionError("ran")):
            status, _h, raw = self.post("/run", {"material": SQLI, "fail_on": "maybe"})
        assert status == 400 and "fail_on must be one of" in json.loads(raw)["error"]

    def test_the_stream_ends_with_the_decision_too(self):
        status, _h, body = self.post("/run/stream", {"material": SQLI, "intent": "analyse", "require_complete": True})
        done = json.loads(body.decode().split("event: done\ndata: ", 1)[1].split("\n", 1)[0])
        assert status == 200 and done["ci"]["exit_code"] == 3

    # exports --------------------------------------------------------------------------------------

    def test_the_markdown_export_is_for_the_owner_only_and_never_holds_the_material(self):
        _s, headers, data = self.run_json(f"{SQLI}# {STORE_MARKER}\n")
        run_id, cookie = data["fingerprint"]["id"], self.cookie_of(headers)
        status, response_headers, raw = self.get_with_headers(f"/api/runs/{run_id}.md", cookie)
        text = raw.decode()
        assert status == 200 and response_headers["content-type"].startswith("text/markdown")
        for word in ("Risk verdict", "Fix status", "Verification", "Findings", "Not checked", "Evidence", "intact"):
            assert word in text
        assert run_id in text and STORE_MARKER not in text
        assert self.get(f"/api/runs/{run_id}.md")[0] == 404                                  # a stranger
        _s, other, _data = self.run_json("y = 2\n")
        assert self.get(f"/api/runs/{run_id}.md", self.cookie_of(other))[0] == 404            # another owner

    def test_the_markdown_survives_a_finding_with_a_pipe_and_a_newline(self):
        record = {"id": "abc", "result": {"verdict": "FAIL", "findings": [
            {"severity": "high", "rule": "r", "line": 1, "message": "a | b\nc"}], "statuses": {}}}
        text = export.markdown(record)
        assert "a \\| b c" in text and "| high | r | 1 |" in text

    def test_the_report_page_offers_the_exports_and_the_integrity_check(self):
        _s, headers, data = self.run_json(SQLI)
        run_id = data["fingerprint"]["id"]
        _status, page = self.get(f"/r/{run_id}", self.cookie_of(headers))
        for link in (f"/api/runs/{run_id}.json", f"/api/runs/{run_id}.sarif", f"/api/runs/{run_id}.md",
                     f"/api/verify/{run_id}"):
            assert link in page.decode()

    # integrity ------------------------------------------------------------------------------------

    def test_a_stored_record_can_be_re_checked_and_an_edit_is_caught(self):
        files = {"calc.py": "def add(a, b):\n    return a + b\n"}
        _s, headers, data = self.run_json(SQLI, files=files)
        run_id, cookie = data["fingerprint"]["id"], self.cookie_of(headers)
        status, raw = self.get(f"/api/verify/{run_id}", cookie)
        assert status == 200 and json.loads(raw)["intact"] is True and json.loads(raw)["files_checked"] is False
        _s, _h, ok = self.post(f"/api/verify/{run_id}", {"files": files}, cookie)
        assert json.loads(ok)["intact"] is True and json.loads(ok)["files_checked"] is True
        _s, _h, bad = self.post(f"/api/verify/{run_id}", {"files": {"calc.py": "x"}}, cookie)
        assert json.loads(bad)["intact"] is False and "files" in json.loads(bad)["reason"]
        server.RUNS._runs[run_id]["result"]["fingerprint"]["body"]["evidence"]["attempts"] = 9      # edited later
        again = json.loads(self.get(f"/api/verify/{run_id}", cookie)[1])
        assert again["intact"] is False and "changed" in again["reason"]

    def test_the_integrity_check_is_as_private_as_the_run_and_wants_files_to_compare(self):
        _s, headers, data = self.run_json(SQLI)
        run_id, cookie = data["fingerprint"]["id"], self.cookie_of(headers)
        assert self.get(f"/api/verify/{run_id}")[0] == 404
        assert self.post(f"/api/verify/{run_id}", {"files": {"a": "b"}})[0] == 404
        assert self.post(f"/api/verify/{run_id}", {}, cookie)[0] == 400
        assert self.post(f"/api/verify/{run_id}", {"files": {"a": 1}}, cookie)[0] == 400
        assert self.get(f"/api/verify/{secrets.token_hex(8)}", cookie)[0] == 404

    # lists ----------------------------------------------------------------------------------------

    def test_the_list_says_a_run_was_only_partly_checked(self):
        _s, headers, _data = self.run_json(CLEAN)
        cookie = self.cookie_of(headers)
        row = json.loads(self.get("/api/runs", cookie)[1])["runs"][0]
        assert row["verification"] == "PARTIAL" and row["fix"] == "NO_PATCH"
        assert "partial" in self.get("/runs", cookie)[1].decode()


def test_an_incomplete_run_is_marked_in_the_list_and_a_complete_one_is_not():
    assert "partial" in templates._status_chips({"verification": "PARTIAL"})
    assert "not run" in templates._status_chips({"verification": "NOT_RUN"})
    assert templates._status_chips({"verification": "COMPLETE", "fix": "NO_PATCH"}) == ""
    assert "fix unverified" in templates._status_chips({"verification": "COMPLETE", "fix": "FIX_UNVERIFIED"})
    assert templates._status_chips({}) == ""                                  # a run stored before the statuses


# the command line -----------------------------------------------------------------------------------------

@pytest.fixture()
def material_file(tmp_path):
    def make(text):
        path = tmp_path / "m.py"
        path.write_text(text, encoding="utf-8")
        return str(path)
    return make


def test_the_cli_exit_codes_are_the_contract(material_file, capsys):
    base = ["run", "--intent", "analyse"]
    assert cli.main([*base, "--material", material_file(CLEAN)]) == 0
    assert cli.main([*base, "--material", material_file(CLEAN), "--fail-on", "review"]) == 1
    assert cli.main([*base, "--material", material_file(CLEAN), "--require-complete"]) == 3
    out = capsys.readouterr().out
    assert "ci:      FAIL (exit 3)" in out and "PARTIAL" in out


def test_the_cli_json_carries_the_decision(material_file, capsys):
    code = cli.main(["run", "--intent", "analyse", "--material", material_file(CLEAN), "--json",
                     "--require-complete"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 3 and payload["ci"]["exit_code"] == 3 and payload["result"]["schema"] == "vishap.run/1"


def test_run_plan_names_its_schema():
    assert run_plan(plan_for("analyse"), material=CLEAN).as_dict()["schema"] == "vishap.run/1"
