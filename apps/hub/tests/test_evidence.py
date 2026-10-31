"""The fingerprint carries what a claim about a fix rests on, and another reader can re-check it."""
import copy
import hashlib

from hub import evidence, fingerprint, local, proposal, templates
from hub.pipeline import run_plan
from hub.router import plan_for

GOOD = {"calc.py": "def add(a, b):\n    return a + b\n"}
SQLI = "cur.execute(\"select * from t where a = \" + x)\n"
PATCH = {"calc.py": "def add(a, b):\n    return a + b  # patched\n"}


def fake(**over):
    payload = {"ok": True, "model": "test-model", "verdict": "SAFE", "findings": [], "patch": {},
               "questions": [], "proof": [], "summary": "fine"}
    payload.update(over)
    return payload


def ev_of(result):
    return result.fingerprint["body"]["evidence"]


def test_a_run_records_the_snapshot_the_attempts_and_why_it_stopped():
    r = run_plan(plan_for("analyse"), material=SQLI, files=GOOD)
    ev = ev_of(r)
    assert ev["snapshot"]["files"] == {"calc.py": hashlib.sha256(GOOD["calc.py"].encode()).hexdigest()}
    assert ev["attempts"] == 1 and "ran to its end" in ev["stop_reason"]
    assert ev["patch"] == {"proposed": False, "diff_sha256": "", "files": {}}
    assert ev["cleanup"] == {"confirmed": None}                  # no container, nothing to confirm
    assert any(c["stage"] == "analyser" for c in ev["checks_run"])


def test_a_model_patch_is_recorded_by_hash_and_the_snapshot_is_the_input_not_the_patch(monkeypatch):
    monkeypatch.setattr(proposal, "propose", lambda **k: fake(patch=PATCH, verdict="REQUIRES_REVIEW"))
    monkeypatch.setattr(local, "validate_code", lambda files, spec: {
        "ok": True, "report": {"verdict": "PASS", "checks": []}})
    r = run_plan(plan_for("generate+validate+analyse"), material=SQLI, files=GOOD, spec="name: demo\n",
                 api_key="k")
    ev = ev_of(r)
    assert ev["snapshot"]["files"] == evidence.file_hashes(GOOD)         # what the client sent
    assert ev["patch"]["proposed"] is True
    assert ev["patch"]["files"] == evidence.file_hashes(PATCH)
    assert ev["patch"]["diff_sha256"] == evidence.sha(evidence.file_hashes(PATCH))
    assert r.fingerprint["body"]["files"] == evidence.file_hashes(GOOD)    # the client sent files: the validator ran on them
    assert ev["validator_ran_on"]["what"] == "supplied files"            # the patch was only read by the rules
    assert ev["validator_ran_on"]["files"] == evidence.file_hashes(GOOD)
    assert ev["analyser_read"]["patch_files"] == ["calc.py"]
    assert ev["model"]["consulted"] is True and ev["model"]["name"] == "test-model"


def test_a_worker_run_records_the_sandbox_profile_and_the_confirmed_cleanup(monkeypatch):
    monkeypatch.setattr(local, "validate_code", lambda files, spec: {
        "ok": True, "report": {"verdict": "PASS", "checks": [
            {"name": "behavior", "ok": True, "skipped": False, "findings": [],
             "note": "network: container (loopback only, outbound refused, root read-only, no secrets in env)"}]},
        "isolation": {"kind": "container", "image": "vishap-validator:worker",
                      "container": "vishap-worker-RANDOM", "cleanup_confirmed": True}})
    r = run_plan(plan_for("validate"), files=GOOD, spec={"files": ["calc.py"], "tests": []})
    ev = ev_of(r)
    prof = ev["versions"]["sandbox_profile"]
    assert prof["name"] == "worker-v1" and prof["network"] == "none" and len(prof["sha256"]) == 64
    assert ev["cleanup"] == {"confirmed": True}
    assert "RANDOM" not in str(r.fingerprint)                    # a random name must not enter the hash
    assert ev["checks_run"][0]["name"] == "behavior" and "container" in ev["checks_run"][0]["note"]


def test_the_same_run_gives_the_same_bytes():
    a = run_plan(plan_for("analyse"), material=SQLI, files=GOOD)
    b = run_plan(plan_for("analyse"), material=SQLI, files=GOOD)
    assert a.fingerprint["digest"] == b.fingerprint["digest"]
    assert evidence.canonical(ev_of(a)) == evidence.canonical(ev_of(b))


def test_another_reader_can_check_integrity_and_a_change_is_caught():
    r = run_plan(plan_for("analyse"), material=SQLI, files=GOOD)
    fp = r.fingerprint
    assert fingerprint.verify(fp) == (True, "intact")
    assert fingerprint.verify(fp, GOOD)[0] is True              # run on these files, and they match
    changed = copy.deepcopy(fp)
    changed["body"]["evidence"]["attempts"] = 9                 # edited after the fact
    ok, why = fingerprint.verify(changed)
    assert ok is False and "changed" in why
    assert fingerprint.verify(fp, {"calc.py": "x"})[0] is False
    renamed = copy.deepcopy(fp)
    renamed["id"] = "0" * 16
    assert fingerprint.verify(renamed)[0] is False
    assert fingerprint.verify({})[0] is False


def test_the_report_shows_who_found_what_and_what_is_left_unverified():
    r = run_plan(plan_for("analyse"), material=SQLI, files=GOOD)
    html = templates.report_page({"id": "abc", "result": r.as_dict(), "verdict": r.verdict})
    for word in ("Evidence", "record intact", "rules found", "model said", "not consulted",
                 "tests that really ran", "left unverified", "analyser"):
        assert word in html


def test_a_record_that_was_edited_is_flagged_on_the_page():
    r = run_plan(plan_for("analyse"), material=SQLI, files=GOOD)
    data = r.as_dict()
    data["fingerprint"]["body"]["evidence"]["attempts"] = 7
    html = templates.report_page({"id": "abc", "result": data, "verdict": r.verdict})
    assert "record NOT intact" in html


def test_runs_stored_before_the_evidence_existed_still_verify_and_render():
    r = run_plan(plan_for("analyse"), material=SQLI)
    old = copy.deepcopy(r.fingerprint)
    del old["body"]["evidence"]
    import hashlib as h
    old["digest"] = h.sha256(fingerprint.canonical(old["body"])).hexdigest()
    old["id"] = old["digest"][:16]
    assert fingerprint.verify(old)[0] is True
    data = r.as_dict()
    data["fingerprint"] = old
    assert "Evidence" not in templates.report_page({"id": old["id"], "result": data, "verdict": r.verdict})

def test_with_no_client_files_the_validator_runs_on_the_patch_and_the_evidence_says_so(monkeypatch):
    monkeypatch.setattr(proposal, "propose", lambda **k: fake(patch=PATCH))
    monkeypatch.setattr(local, "validate_code", lambda files, spec: {
        "ok": True, "report": {"verdict": "PASS", "checks": []}})
    r = run_plan(plan_for("generate+validate+analyse"), material=SQLI, spec="name: demo\n", api_key="k")
    ev = ev_of(r)
    assert ev["snapshot"]["files"] == {}
    assert ev["validator_ran_on"] == {"what": "model patch", "files": evidence.file_hashes(PATCH)}