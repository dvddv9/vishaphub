"""A patch is a claim; the patch check turns it into FIX_VERIFIED / PARTIAL / REJECTED / UNVERIFIED."""
import copy
import os
import shutil

import pytest
from validator import exploits as vexploits

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
SQLI_TARGET = {"class": "sqli", "entry": "app:find", "args": ["$cursor", "$payload"]}
SPEC_X = {**SPEC, "exploit_targets": [SQLI_TARGET]}      # trusted exploit tests come from the spec, never the patch


_ORIGINAL_VALIDATE = local.validate_code     # captured before any test patches the hub's own name


def real_validate(files, spec):
    """The real validator, in-process (guard mode): this fixture is synthetic code of our own."""
    return _ORIGINAL_VALIDATE(files, spec, require_netns=False)


def real_exploits(files, targets, **kw):
    """The trusted probes on synthetic code of our own, in-process (the hub itself runs them only in isolation)."""
    root, _ = local._materialize(files)
    try:
        return {"ok": True, "exploits": vexploits.run_targets(root, targets)}
    finally:
        shutil.rmtree(root, ignore_errors=True)


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

def test_a_real_fix_is_verified_by_the_real_tests_and_the_exploit_not_by_the_finding_disappearing(monkeypatch):
    monkeypatch.setattr(local, "run_exploits", real_exploits)
    out = status(files={"app.py": FIXED}, validate=real_validate, spec=SPEC_X)
    assert out["status"] == "FIX_VERIFIED", out
    assert [(r["class"], r["before"], r["after"]) for r in out["exploit"]] == [("sqli", "reproduced", "not_reproduced")]
    assert out["rules"]["after"] < out["rules"]["before"] and out["rules"]["new"] == []
    assert out["validator"]["tests_ran"] is True


def test_the_same_snapshot_and_patch_give_the_same_result_in_either_form(monkeypatch):
    monkeypatch.setattr(local, "run_exploits", real_exploits)
    a = status(files={"app.py": FIXED}, validate=real_validate, spec=SPEC_X)
    b = status(files={"app.py": FIXED}, validate=real_validate, spec=SPEC_X)
    diff = patchcheck.diff_from_files(SNAPSHOT, {"app.py": FIXED})
    c = status(diff=diff, validate=real_validate, spec=SPEC_X)
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
    assert out["status"] == "FIX_PARTIAL" and "did not reproduce the problem on the original" in out["reason"]


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
    out = patchcheck.check(SNAPSHOT, files={"app.py": FIXED}, spec=SPEC_X)      # tests AND exploit probes in containers
    assert out["status"] == "FIX_VERIFIED", out
    assert out["exploit"][0]["before"] == "reproduced" and out["exploit"][0]["after"] == "not_reproduced"
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
    monkeypatch.setattr(local, "run_exploits", real_exploits)
    on = run_plan(plan_for("review"), material=APP, files=SNAPSHOT, spec=SPEC_X, api_key="k", check_patch=True)
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
    (tmp_path / "spec.json").write_text(json.dumps(SPEC_X), encoding="utf-8")
    argv = ["patch-check", "--snapshot", str(snap), "--diff", str(tmp_path / "fix.diff"),
            "--spec", str(tmp_path / "spec.json")]
    assert cli.main(argv) == 5                       # strict validator on this host: not verified, not rejected
    assert "FIX_UNVERIFIED" in capsys.readouterr().out
    monkeypatch.setattr(local, "validate_code", real_validate)
    monkeypatch.setattr(local, "run_exploits", real_exploits)
    assert cli.main(argv) == 0
    assert "FIX_VERIFIED" in capsys.readouterr().out
    (tmp_path / "evil.diff").write_text("--- a/../x.py\n+++ b/../x.py\n@@ -0,0 +1 @@\n+x\n", encoding="utf-8")
    assert cli.main(["patch-check", "--snapshot", str(snap), "--diff", str(tmp_path / "evil.diff"),
                     "--spec", str(tmp_path / "spec.json")]) == 4

# exploit tests: the trusted probes decide, the rules only point -------------------------------------------

def test_a_fix_for_an_attack_class_with_no_exploit_test_is_not_verified_by_a_test():
    out = status(files={"app.py": FIXED})
    assert out["status"] == "FIX_PARTIAL" and "no exploit test for SQL injection" in out["reason"]
    assert out["exploit_untested"] == ["sqli"]


def test_a_rewrite_the_rules_cannot_see_through_is_caught_by_the_exploit_test(monkeypatch):
    """`+=` builds the same injectable query, and the rules report nothing: the finding 'disappears'."""
    sneaky = (
        "def find(cur, name):\n"
        "    sql = \"select id from users where name = '\"\n"
        "    sql += name\n"
        "    sql += \"'\"\n"
        "    cur.execute(sql)\n"
        "    return cur.fetchall()\n"
    )
    monkeypatch.setattr(local, "run_exploits", real_exploits)
    rules_only = status(files={"app.py": sneaky}, validate=real_validate)
    assert rules_only["rules"]["after"] < rules_only["rules"]["before"]          # the rules say: fixed
    out = status(files={"app.py": sneaky}, validate=real_validate, spec=SPEC_X)
    assert out["status"] == "FIX_REJECTED" and "exploit still works" in out["reason"] and "sqli" in out["reason"]


def test_exploit_tests_that_cannot_run_leave_the_fix_unverified_not_verified(monkeypatch):
    monkeypatch.setattr(local, "run_exploits", lambda files, targets, **kw: {"ok": False, "error": "no confirmed isolation"})
    out = status(files={"app.py": FIXED}, spec=SPEC_X)
    assert out["status"] == "FIX_UNVERIFIED" and "exploit tests could not run" in out["reason"]


def test_a_patch_cannot_carry_its_own_exploit_targets():
    """Targets come from the caller's spec. A patch file named like a target changes nothing."""
    planted = {"app.py": FIXED, "exploit_targets.json": "[]"}
    out = status(files=planted)
    assert out["status"] == "FIX_PARTIAL" and "no exploit test for SQL injection" in out["reason"]


PATH_VULN = "import os\n\n\ndef read(base, name):\n    with open(os.path.join(base, name), encoding='utf-8') as fh:\n        return fh.read()\n"
PATH_FIXED = (
    "import os\n\n\ndef read(base, name):\n"
    "    root = os.path.realpath(base)\n    full = os.path.realpath(os.path.join(base, name))\n"
    "    if os.path.commonpath([root, full]) != root:\n        raise ValueError('outside')\n"
    "    with open(full, encoding='utf-8') as fh:\n        return fh.read()\n"
)
PATH_TARGET = {"class": "path_traversal", "entry": "app:read", "args": ["$base", "$payload"]}


def test_path_traversal_is_verified_by_its_exploit_test_when_the_rules_still_flag_the_fixed_code(monkeypatch):
    monkeypatch.setattr(local, "run_exploits", real_exploits)
    spec = {"entry": "app", "files": ["app.py"], "tests": [], "exploit_targets": [PATH_TARGET]}
    out = patchcheck.check({"app.py": PATH_VULN}, files={"app.py": PATH_FIXED}, spec=spec,
                           validate=fake_validate())
    assert out["rules"]["remaining_critical_or_high"] == []          # taint-flow is discharged by the proven test
    assert out["status"] == "FIX_VERIFIED", out
    assert patchcheck.check({"app.py": PATH_VULN}, files={"app.py": PATH_VULN + "\n"}, spec=spec,
                            validate=fake_validate())["status"] == "FIX_REJECTED"       # still readable outside


def test_an_exploit_test_discharges_only_its_own_class(monkeypatch):
    """A proven SQL fix does not wave through an unrelated high finding that is still there."""
    monkeypatch.setattr(local, "run_exploits", real_exploits)
    both = FIXED + "import os\n\n\ndef run(x):\n    os.system('ls ' + x)\n"
    snap = {"app.py": APP + "import os\n\n\ndef run(x):\n    os.system('ls ' + x)\n", "test_app.py": TEST}
    out = patchcheck.check(snap, files={"app.py": both}, spec=SPEC_X, validate=fake_validate())
    assert out["status"] == "FIX_PARTIAL" and "cmd-injection-py" in out["reason"]


@pytest.mark.skipif(not (IMAGE and shutil.which("docker")), reason="no Docker or VISHAP_TEST_WORKER_IMAGE")
def test_all_three_attack_classes_are_reproduced_and_gone_inside_the_worker_container(monkeypatch):
    monkeypatch.setenv("VISHAP_HUB_WORKER_IMAGE", IMAGE)
    cmd_vuln = "import os\n\n\ndef echo(text):\n    os.system('echo ' + text)\n"
    cmd_fixed = "import subprocess\n\n\ndef echo(text):\n    subprocess.run(['echo', text], check=False)\n"
    targets = [SQLI_TARGET, {"class": "path_traversal", "entry": "p:read", "args": ["$base", "$payload"]},
               {"class": "command_injection", "entry": "c:echo", "args": ["$payload"]}]
    vuln = local.run_exploits({"app.py": APP, "p.py": PATH_VULN, "c.py": cmd_vuln}, targets)
    assert vuln["ok"], vuln
    assert [r["result"] for r in vuln["exploits"]] == ["reproduced"] * 3
    assert vuln["isolation"]["kind"] == "container" and vuln["isolation"]["cleanup_confirmed"] is True
    fixed = local.run_exploits({"app.py": FIXED, "p.py": PATH_FIXED, "c.py": cmd_fixed}, targets)
    assert [r["result"] for r in fixed["exploits"]] == ["not_reproduced"] * 3
