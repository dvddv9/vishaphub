"""A patch is a claim; the patch check turns it into FIX_VERIFIED / PARTIAL / REJECTED / UNVERIFIED."""
import copy
import os
import shutil

import pytest

from hub import local, patchcheck, statuses

APP = (
    "def find(cur, name):\n"
    "    cur.execute(\"select id from users where name = '\" + name + \"'\")\n"
    "    return cur.fetchall()\n"
)
FIXED = (
    "def find(cur, name):\n"
    "    cur.execute(\"select id from users where name = ?\", (name,))\n"
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


_ORIGINAL_VALIDATE = local.validate_code     # captured before any test patches the hub's own name


def real_validate(files, spec):
    """The real validator, in-process (guard mode): this fixture is synthetic code of our own."""
    return _ORIGINAL_VALIDATE(files, spec, require_netns=False)


def fake_validate(verdict="PASS", ran=True, ok=True):
    def run(files, spec):
        if not ok:
            return {"ok": False, "error": "boom"}
        return {"ok": True, "report": {"verdict": verdict, "checks": [
            {"name": "behavior", "ok": True, "skipped": not ran, "findings": []}]}}
    return run


def status(**kw):
    kw.setdefault("spec", SPEC)
    kw.setdefault("validate", fake_validate())
    return patchcheck.check(SNAPSHOT, **kw)


# a real fix, a real run --------------------------------------------------------------------------

def test_a_real_fix_is_verified_by_the_real_tests_not_by_the_finding_disappearing():
    out = status(files={"app.py": FIXED}, validate=real_validate)
    assert out["status"] == "FIX_VERIFIED", out
    assert out["rules"]["after"] < out["rules"]["before"] and out["rules"]["new"] == []
    assert out["validator"]["tests_ran"] is True


def test_the_same_snapshot_and_patch_give_the_same_result_in_either_form():
    a = status(files={"app.py": FIXED}, validate=real_validate)
    b = status(files={"app.py": FIXED}, validate=real_validate)
    diff = patchcheck.diff_from_files(SNAPSHOT, {"app.py": FIXED})
    c = status(diff=diff, validate=real_validate)
    assert a == b == c


def test_gutting_the_function_removes_the_finding_but_the_real_tests_reject_it():
    out = status(files={"app.py": "def find(cur, name):\n    return []\n"}, validate=real_validate)
    assert out["status"] == "FIX_REJECTED" and "behavior" in out["reason"] and "fail after the patch" in out["reason"]


# what cannot buy a verification --------------------------------------------------------------------

def test_deleting_the_file_that_held_the_finding_is_not_a_fix():
    out = status(files={"app.py": None})
    assert out["status"] == "FIX_PARTIAL" and "app.py" in out["reason"] and "went away" in out["reason"]


def test_deleting_the_function_but_keeping_the_file_is_not_a_fix():
    out = status(files={"app.py": "X = 1\n"})
    assert out["status"] == "FIX_PARTIAL" and "app.py:find" in out["reason"]


@pytest.mark.parametrize("path", ["test_app.py", "conftest.py", "pytest.ini", "pyproject.toml",
                                  "tests/test_other.py", ".github/workflows/ci.yml", "sitecustomize.py"])
def test_a_patch_that_touches_a_trusted_check_is_rejected(path):
    snap = {**SNAPSHOT, path: "x = 1\n"}
    out = patchcheck.check(snap, files={path: "x = 2\n"}, spec=SPEC, validate=fake_validate())
    assert out["status"] == "FIX_REJECTED" and "trusted" in out["reason"]


def test_deleting_a_test_is_rejected():
    out = status(files={"test_app.py": None})
    assert out["status"] == "FIX_REJECTED" and "trusted" in out["reason"]


def test_a_patch_whose_tests_never_ran_is_partial_not_verified():
    out = status(files={"app.py": FIXED}, validate=fake_validate(ran=False))
    assert out["status"] == "FIX_PARTIAL" and "no test of the deliverable ran" in out["reason"]


def test_a_patch_that_introduces_a_finding_is_rejected():
    worse = FIXED + "import os\n\n\ndef run(x):\n    os.system('ls ' + x)\n"
    out = status(files={"app.py": worse})
    assert out["status"] == "FIX_REJECTED" and "introduces findings" in out["reason"]


def test_a_patch_that_does_not_parse_is_rejected():
    out = status(files={"app.py": "def find(:\n"})
    assert out["status"] == "FIX_REJECTED" and "does not parse" in out["reason"]


def test_a_patch_that_removes_nothing_the_rules_saw_is_partial():
    out = status(files={"app.py": APP + "\n\ndef extra():\n    return 1\n"})
    assert out["status"] == "FIX_PARTIAL" and "no finding that the patch removed" in out["reason"]


# bounds -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("diff,why", [
    ("--- a/../evil.py\n+++ b/../evil.py\n@@ -0,0 +1 @@\n+x\n", "climbs out"),
    ("--- /dev/null\n+++ b//etc/passwd\n@@ -0,0 +1 @@\n+x\n", "not a relative path"),
    ("--- /dev/null\n+++ b/C:/win.py\n@@ -0,0 +1 @@\n+x\n", "not a relative path"),
    ("--- a/app.py\n+++ b/app.py\n@@ -1,1 +1,1 @@\n-def nothing():\n+def other():\n", "does not match"),
    ("--- a/missing.py\n+++ b/missing.py\n@@ -1,1 +1,1 @@\n-x\n+y\n", "not in the snapshot"),
    ("--- /dev/null\n+++ b/app.py\n@@ -0,0 +1 @@\n+x\n", "already exists"),
    ("--- a/app.py\n+++ b/renamed.py\n@@ -1,1 +1,1 @@\n-def find(cur, name):\n+def find(cur, name):\n", "renames"),
    ("this is not a diff\n", "unexpected line"),
    ("", "changes nothing"),
])
def test_a_diff_outside_its_bounds_is_rejected_with_the_reason(diff, why):
    out = status(diff=diff)
    assert out["status"] == "FIX_REJECTED" and why in out["reason"] and out["applied"] is False


def test_too_many_files_or_too_large_a_diff_is_rejected():
    many = {f"m{i}.py": "x = 1\n" for i in range(patchcheck.MAX_FILES + 1)}
    out = patchcheck.check({}, files=many, spec=SPEC, validate=fake_validate())
    assert out["status"] == "FIX_REJECTED" and "more than" in out["reason"]
    big = {"app.py": APP + "x = 1\n" * 60000}
    assert "larger than" in status(files=big)["reason"]


def test_the_snapshot_is_never_modified():
    before = copy.deepcopy(SNAPSHOT)
    status(files={"app.py": FIXED})
    status(files={"app.py": None})
    assert SNAPSHOT == before


# when the checks could not run -------------------------------------------------------------------

def test_without_a_confirmed_isolation_the_fix_is_unverified_and_nothing_ran():
    def refused(files, spec):
        return {"ok": True, "report": {"verdict": "FAIL", "reason": "nothing was run", "checks": [
            {"name": "isolation", "ok": False, "skipped": False, "findings": []}]}}
    out = status(files={"app.py": FIXED}, validate=refused)
    assert out["status"] == "FIX_UNVERIFIED" and "isolation was not confirmed" in out["reason"]


def test_a_validator_that_fails_to_run_is_unverified_not_rejected():
    out = status(files={"app.py": FIXED}, validate=fake_validate(ok=False))
    assert out["status"] == "FIX_UNVERIFIED" and "could not run" in out["reason"]


def test_the_in_process_hub_without_a_namespace_gives_unverified_for_a_real_fix():
    out = patchcheck.check(SNAPSHOT, files={"app.py": FIXED}, spec=SPEC)     # default validator: strict
    assert out["status"] == "FIX_UNVERIFIED"


# exploit-test hook (trusted tests, kept apart from the patch) ---------------------------------------

def test_an_exploit_that_still_works_after_the_patch_rejects_it():
    hook = lambda before, after: [{"class": "sqli", "before": "reproduced", "after": "reproduced"}]
    out = status(files={"app.py": FIXED}, exploit=hook)
    assert out["status"] == "FIX_REJECTED" and "sqli" in out["reason"]


def test_an_exploit_that_never_reproduced_on_the_original_cannot_verify():
    hook = lambda b, a: [{"class": "sqli", "before": "not_reproduced", "after": "not_reproduced"}]
    out = status(files={"app.py": FIXED}, exploit=hook)
    assert out["status"] == "FIX_PARTIAL" and "no exploit test reproduced" in out["reason"]


def test_reproduced_before_and_blocked_after_verifies():
    hook = lambda b, a: [{"class": "sqli", "before": "reproduced", "after": "not_reproduced"}]
    assert status(files={"app.py": FIXED}, exploit=hook)["status"] == "FIX_VERIFIED"


# the status plugs into the three results ----------------------------------------------------------------

def test_the_fix_status_reaches_the_three_results_without_touching_the_verdict():
    out = status(files={"app.py": FIXED})
    st = statuses.compute(ok=True, verdict="FAIL", checks={}, plan={}, patch={"app.py": FIXED},
                          model_verdict="", not_checked=[], patch_check=out)
    assert st["fix"]["status"] == out["status"] and st["risk"]["verdict"] == "FAIL"


# the same check through a real worker container --------------------------------------------------------

IMAGE = os.getenv("VISHAP_TEST_WORKER_IMAGE", "")


@pytest.mark.skipif(not (IMAGE and shutil.which("docker")), reason="no Docker or VISHAP_TEST_WORKER_IMAGE")
def test_a_fix_is_verified_inside_a_real_worker_container(monkeypatch):
    monkeypatch.setenv("VISHAP_HUB_WORKER_IMAGE", IMAGE)
    out = patchcheck.check(SNAPSHOT, files={"app.py": FIXED}, spec=SPEC)
    assert out["status"] == "FIX_VERIFIED", out
    assert out["validator"]["isolation"]["kind"] == "container"
    assert out["validator"]["isolation"]["cleanup_confirmed"] is True

def test_a_test_that_already_failed_before_the_patch_cannot_be_blamed_on_it_nor_verify_it():
    broken = {"app.py": APP, "test_app.py": TEST.replace("[(1,)]", "[(2,)]")}      # fails on the original too
    out = patchcheck.check(broken, files={"app.py": FIXED}, spec=SPEC, validate=real_validate)
    assert out["status"] == "FIX_PARTIAL" and "already failing" in out["reason"]

# through the pipeline and the command line -----------------------------------------------------------------

def _model_proposing(monkeypatch, patch):
    from hub import proposal
    monkeypatch.setattr(proposal, "propose", lambda **k: {
        "ok": True, "model": "test-model", "verdict": "SAFE", "findings": [], "patch": patch,
        "questions": [], "proof": [], "summary": "fixed"})


def test_the_pipeline_checks_the_models_patch_only_when_asked(monkeypatch):
    from hub.pipeline import run_plan
    from hub.router import plan_for
    _model_proposing(monkeypatch, {"app.py": FIXED})
    monkeypatch.setattr(local, "validate_code", real_validate)
    off = run_plan(plan_for("review"), material=APP, files=SNAPSHOT, api_key="k")
    assert off.as_dict()["statuses"]["fix"]["status"] == "FIX_UNVERIFIED"
    on = run_plan(plan_for("review"), material=APP, files=SNAPSHOT, spec=SPEC, api_key="k", check_patch=True)
    data = on.as_dict()
    assert data["statuses"]["fix"]["status"] == "FIX_VERIFIED", data["statuses"]["fix"]
    assert data["statuses"]["risk"]["verdict"] == data["verdict"] != "SAFE"   # the fix does not soften the risk
    fc = data["fingerprint"]["body"]["evidence"]["fix_check"]
    assert fc["status"] == "FIX_VERIFIED" and fc["diff_sha256"] and fc["validator"]["tests_ran"] is True


def test_a_patch_that_deletes_the_finding_with_the_code_is_partial_in_the_run_too(monkeypatch):
    from hub.pipeline import run_plan
    from hub.router import plan_for
    _model_proposing(monkeypatch, {"app.py": None})
    monkeypatch.setattr(local, "validate_code", fake_validate())
    on = run_plan(plan_for("review"), material=APP, files=SNAPSHOT, spec=SPEC, api_key="k", check_patch=True)
    assert on.as_dict()["statuses"]["fix"]["status"] == "FIX_PARTIAL"


def test_the_command_line_gives_a_status_and_an_exit_code_without_a_model(tmp_path, monkeypatch, capsys):
    from hub import cli
    snap = tmp_path / "snap"
    snap.mkdir()
    for name, text in SNAPSHOT.items():
        (snap / name).write_text(text, encoding="utf-8")
    diff = patchcheck.diff_from_files(SNAPSHOT, {"app.py": FIXED})
    (tmp_path / "fix.diff").write_text(diff, encoding="utf-8")
    import json
    (tmp_path / "spec.json").write_text(json.dumps(SPEC), encoding="utf-8")
    argv = ["patch-check", "--snapshot", str(snap), "--diff", str(tmp_path / "fix.diff"),
            "--spec", str(tmp_path / "spec.json")]
    assert cli.main(argv) == 5                       # strict validator on this host: not verified, not rejected
    assert "FIX_UNVERIFIED" in capsys.readouterr().out
    monkeypatch.setattr(local, "validate_code", real_validate)
    assert cli.main(argv) == 0
    assert "FIX_VERIFIED" in capsys.readouterr().out
    (tmp_path / "evil.diff").write_text("--- a/../x.py\n+++ b/../x.py\n@@ -0,0 +1 @@\n+x\n", encoding="utf-8")
    assert cli.main(["patch-check", "--snapshot", str(snap), "--diff", str(tmp_path / "evil.diff"),
                     "--spec", str(tmp_path / "spec.json")]) == 4