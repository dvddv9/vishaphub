# -*- coding: utf-8 -*-
"""Route checklist, exploit probes, report trimming, fingerprints/diff, repo/diff scan, OSV audit, benchmark."""
import json
import shutil
from pathlib import Path

import pytest

from src.tools import proof
from src.tools.findings_diff import assign_fingerprints, diff_findings, load_baseline, save_baseline
from src.tools.repo_scan import (check_osv, parse_diff, parse_package_lock, parse_requirements, scan_cli,
                                 scan_dependencies, scan_diff, scan_repo)
from src.tools.report_trim import has_substance, trim_noise
from src.tools.route_checklist import checklist
from src.tools.sarif import to_sarif
from src.tools.static_scan import scan_material, to_rules_view
from tests.bench.score import load_truth, score_engine, score_report

BENCH = Path(__file__).parent / "bench"
PLANTED = (BENCH / "planted_app.py").read_text(encoding="utf-8")
FIXED = (BENCH / "fixed_app.py").read_text(encoding="utf-8")

needs_bwrap = pytest.mark.skipif(proof.isolation_level() != "bwrap", reason="bubblewrap not available")


def _ids(findings):
    return {f["id"] for f in findings}


# --- route checklist ----------------------------------------------------------------------------

def test_checklist_flags_unauthenticated_money_route():
    res = checklist(PLANTED, "python")
    ids = _ids(res["findings"])
    assert {"route-no-auth", "route-check-then-act", "route-unchecked-rowcount",
            "route-amount-no-bounds", "route-unvalidated-json"} <= ids
    assert {r["route"] for r in res["routes"]} >= {"/user", "/download", "/login", "/items", "/transfer"}


def test_checklist_is_quiet_on_the_fixed_app():
    assert checklist(FIXED, "python")["findings"] == []


def test_login_required_decorator_counts_as_auth():
    code = ("from flask import Flask\napp = Flask(__name__)\n"
            "@app.get('/a')\n@login_required\ndef a():\n    return 'x'\n")
    assert "route-no-auth" not in _ids(checklist(code, "python")["findings"])


def test_handler_that_checks_an_api_key_header_is_not_flagged_as_unauthenticated():
    code = ("from flask import Flask, request\napp = Flask(__name__)\n"
            "@app.post('/internal')\ndef internal():\n"
            "    if request.headers.get('X-Api-Key') != KEY:\n        return 'no', 403\n    return 'ok'\n"
            "@app.post('/open')\ndef open_():\n    return request.headers.get('User-Agent', '')\n")
    flagged = {f["line"] for f in checklist(code, "python")["findings"] if f["id"] == "route-no-auth"}
    assert 4 not in flagged and 9 in flagged


def test_checklist_never_raises_on_broken_code():
    assert checklist("def (:\n", "python")["findings"] == []
    assert checklist("", "javascript")["findings"] == []


# --- fingerprints and diff ----------------------------------------------------------------------

def test_fingerprint_survives_line_shift_but_not_a_changed_snippet():
    a = scan_material(PLANTED, "a.py")["findings"]
    b = scan_material("# one\n# two\n" + PLANTED, "a.py")["findings"]
    assert {f["fingerprint"] for f in a} == {f["fingerprint"] for f in b}
    c = scan_material(PLANTED.replace("shop.db", "other.db").replace("md5", "md5 "), "a.py")["findings"]
    assert len({f["fingerprint"] for f in c}) == len(c)


def test_fingerprints_are_unique_within_one_run():
    fps = [f["fingerprint"] for f in scan_material(PLANTED, "a.py")["findings"]]
    assert len(fps) == len(set(fps))


def test_same_code_in_two_files_gets_two_identities():
    f1 = assign_fingerprints([{"id": "x", "snippet": "eval(a)", "line": 1}], "a.py")[0]["fingerprint"]
    f2 = assign_fingerprints([{"id": "x", "snippet": "eval(a)", "line": 1}], "b.py")[0]["fingerprint"]
    assert f1 != f2


def test_baseline_round_trip_and_diff(tmp_path):
    before = scan_material(PLANTED, "a.py")["findings"]
    path = tmp_path / "base.json"
    assert save_baseline(before, str(path), "a.py") == len(before)
    after = scan_material(PLANTED + '\nimport os\nos.system("ls " + input())\n', "a.py")["findings"]
    d = diff_findings(load_baseline(str(path)), after)
    assert len(d["new"]) >= 1 and d["fixed"] == [] and len(d["unchanged"]) == len(before)
    d2 = diff_findings(load_baseline(str(path)), scan_material(FIXED, "a.py")["findings"])
    assert len(d2["fixed"]) == len(before) and d2["new"] == []


def test_load_baseline_tolerates_missing_and_corrupt_files(tmp_path):
    assert load_baseline(str(tmp_path / "nope.json")) == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_baseline(str(bad)) == []


def test_sarif_has_one_stable_fingerprint_per_result():
    findings = scan_material(PLANTED, "planted_app.py")["findings"]
    doc = to_sarif({}, sast_result={"vishap_rules": {"available": True, "findings": to_rules_view(findings)}},
                   source_file="planted_app.py")
    results = doc["runs"][0]["results"]
    fps = [r["partialFingerprints"]["vishapFingerprint/v1"] for r in results]
    assert len(results) == len(findings) and len(set(fps)) == len(fps)


# --- report trimming ----------------------------------------------------------------------------

def test_trim_drops_placeholder_only_lines_and_keeps_real_ones():
    md = ("ECONOMICS: NOT_SET\nSLO IMPACT: не вычислим\nCLOUD COST: $120 per month\n"
          "ON-CALL: runbook does not exist; VERIFY\nSome other line\n")
    out = trim_noise(md)
    assert "$120" in out and "runbook does not exist" in out and "Some other line" in out
    assert "NOT_SET" not in out and "не вычислим" not in out
    assert "No data for" in out


def test_trim_leaves_a_clean_report_untouched():
    md = "# Report\n\nECONOMICS: 3 hours of downtime cost about 900 USD\n"
    assert trim_noise(md) == md
    assert trim_noise("") == ""


def test_has_substance():
    assert has_substance("12 hours")
    assert not has_substance("NOT_SET")
    assert not has_substance("N/A")


def test_trim_can_be_switched_off():
    from src.tools.report_trim import trim_enabled
    import os
    os.environ["VISHAP_TRIM_REPORT"] = "0"
    try:
        assert not trim_enabled()
    finally:
        os.environ.pop("VISHAP_TRIM_REPORT", None)
    assert trim_enabled()


# --- proofs -------------------------------------------------------------------------------------

def test_proof_is_off_by_default():
    import os
    os.environ.pop("VISHAP_PROVE", None)
    ok, why = proof.proof_allowed()
    assert not ok and "VISHAP_PROVE" in why
    doc = proof.prove(PLANTED)
    assert doc["enabled"] is False and "proof is off" in doc["error"]


@needs_bwrap
def test_probes_confirm_planted_bugs_in_isolation():
    import os
    os.environ["VISHAP_PROVE"] = "1"
    try:
        findings = scan_material(PLANTED, "planted_app.py")["findings"]
        doc = proof.prove(PLANTED, findings)
    finally:
        os.environ.pop("VISHAP_PROVE", None)
    assert not doc.get("error"), doc.get("error")
    assert doc["isolation"] == "bwrap"
    confirmed = {(r["function"], r["check"]) for r in doc["results"] if r["status"] == "CONFIRMED"}
    assert {("get_user", "sqli"), ("download", "traversal"), ("transfer", "auth"), ("transfer", "amount")} <= confirmed
    by_id = {(f["id"], f["line"]): f.get("status") for f in findings}
    assert by_id[("sqli-fstring", 17)] == "CONFIRMED"


@needs_bwrap
def test_fixed_app_has_no_confirmed_exploit_and_patch_is_verified():
    import os
    os.environ["VISHAP_PROVE"] = "1"
    try:
        doc = proof.prove(FIXED)
        verdict = proof.verify_patch(PLANTED, FIXED)
        noop = proof.verify_patch(PLANTED, PLANTED)
    finally:
        os.environ.pop("VISHAP_PROVE", None)
    assert not doc.get("error"), doc.get("error")
    assert not [r for r in doc["results"] if r["status"] == "CONFIRMED"]
    assert verdict["verdict"] == "CLOSES_EXPLOITS" and not verdict["regressions"], verdict
    assert noop["verdict"] == "NO_EFFECT", noop


def test_verify_patch_rejects_code_that_does_not_parse():
    v = proof.verify_patch(PLANTED, "def broken(:\n")
    assert v["verdict"] == "REJECTED"


def test_a_handler_whose_file_needs_an_unset_env_var_is_still_probed():
    code = ("import os\nfrom flask import Flask, request\napp = Flask(__name__)\nK = os.environ['NOPE_NOT_SET']\n"
            "@app.get('/x')\ndef x():\n    return 'ok'\n")
    if proof.isolation_level() != "bwrap":
        pytest.skip("bubblewrap not available")
    import os
    os.environ["VISHAP_PROVE"] = "1"
    try:
        doc = proof.prove(code)
    finally:
        os.environ.pop("VISHAP_PROVE", None)
    assert not doc.get("error"), doc.get("error")
    assert doc["handlers"] == 1


# --- repo and diff scan -------------------------------------------------------------------------

def _repo(tmp_path):
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "node_modules" / "x").mkdir(parents=True)
    (root / "pkg" / "app.py").write_text(PLANTED, encoding="utf-8")
    (root / "pkg" / "ok.py").write_text(FIXED, encoding="utf-8")
    (root / "node_modules" / "x" / "bad.js").write_text("eval(req.query.x)\n", encoding="utf-8")
    (root / "README.md").write_text("eval(x)\n", encoding="utf-8")
    return root


def test_scan_repo_skips_vendored_dirs_and_non_code(tmp_path):
    res = scan_repo(str(_repo(tmp_path)))
    assert res["files_scanned"] == 2
    assert {f["file"] for f in res["findings"]} == {"pkg/app.py"}
    assert res["total_findings"] == 20 and res["logic_findings"] == 10


def test_scan_repo_does_not_follow_symlinks(tmp_path):
    root = _repo(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("eval(x)\n", encoding="utf-8")
    try:
        (root / "link.py").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks not supported")
    res = scan_repo(str(root))
    assert "link.py" not in {f["file"] for f in res["findings"]}
    assert {"file": "link.py", "reason": "symlink"} in res["files_skipped"]


def test_scan_repo_respects_size_limit_and_exclude(tmp_path):
    root = _repo(tmp_path)
    assert scan_repo(str(root), max_file_bytes=10)["files_scanned"] == 0
    assert scan_repo(str(root), exclude=(r"^pkg/",))["files_scanned"] == 0


DIFF = """diff --git a/pkg/ok.py b/pkg/ok.py
--- a/pkg/ok.py
+++ b/pkg/ok.py
@@ -1,2 +1,4 @@
 import hmac
+import os
+os.system("ping " + input())
 import hashlib
"""


def test_parse_diff_gives_added_line_numbers():
    assert parse_diff(DIFF) == {"pkg/ok.py": {2, 3}}
    assert parse_diff("") == {}


def test_scan_diff_reports_only_what_the_diff_added(tmp_path):
    root = _repo(tmp_path)
    ok = root / "pkg" / "ok.py"
    ok.write_text("".join(FIXED.splitlines(True)[:1]) + 'import os\nos.system("ping " + input())\n' + "".join(FIXED.splitlines(True)[1:]), encoding="utf-8")
    res = scan_diff(str(root), DIFF)
    assert [(f["file"], f["line"], f["id"]) for f in res["findings"]] == [("pkg/ok.py", 3, "cmd-injection-py")]


def test_scan_cli_baseline_and_gate(tmp_path):
    root = _repo(tmp_path)
    base = tmp_path / "base.json"
    assert scan_cli(str(root), save_baseline_path=str(base), output=str(tmp_path / "r1.md")) == 0
    assert scan_cli(str(root), baseline=str(base), fail_on="low", output=str(tmp_path / "r2.md")) == 0
    (root / "pkg" / "new.py").write_text('import os\nos.system("ls " + input())\n', encoding="utf-8")
    assert scan_cli(str(root), baseline=str(base), fail_on="high", output=str(tmp_path / "r3.md")) == 1
    assert scan_cli(str(root), fail_on="critical", output=str(tmp_path / "r4.md")) == 1
    assert scan_cli(str(tmp_path / "missing")) == 2


def test_scan_cli_sarif_has_a_location_per_file(tmp_path):
    root = _repo(tmp_path)
    (root / "pkg" / "new.py").write_text('import os\nos.system("ls " + input())\n', encoding="utf-8")
    out = tmp_path / "scan.sarif"
    assert scan_cli(str(root), sarif=str(out), output=str(tmp_path / "r.md")) == 0
    uris = {r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
            for r in json.loads(out.read_text(encoding="utf-8"))["runs"][0]["results"]}
    assert {"pkg/app.py", "pkg/new.py"} <= uris


# --- dependencies (OSV, mocked: the tests never touch the network) ------------------------------

def test_parse_requirements_pinned_and_loose():
    pinned, loose = parse_requirements("flask==2.0.0\nrequests>=2\n# c\nnumpy==1.2 ; python_version<'3.9'\n-r o.txt\nfoo[x]==1.0\n")
    assert pinned == [("flask", "2.0.0", 1), ("numpy", "1.2", 4), ("foo", "1.0", 6)]
    assert [x[0] for x in loose] == ["requests"]


def test_parse_package_lock_v2_and_v1():
    v2 = json.dumps({"packages": {"": {}, "node_modules/lodash": {"version": "4.17.20"}}})
    v1 = json.dumps({"dependencies": {"lodash": {"version": "4.17.20"}}})
    assert parse_package_lock(v2) == [("lodash", "4.17.20", 1)]
    assert parse_package_lock(v1) == [("lodash", "4.17.20", 1)]
    assert parse_package_lock("not json") == []


def test_osv_results_become_findings_with_fix_versions(tmp_path):
    (tmp_path / "requirements.txt").write_text("flask==2.0.0\nrequests>=2\n", encoding="utf-8")
    post = lambda url, payload: {"results": [{"vulns": [{"id": "GHSA-test"}]}]}  # noqa: E731
    get = lambda url: {"summary": "Test advisory", "database_specific": {"severity": "CRITICAL"},  # noqa: E731
                       "affected": [{"ranges": [{"events": [{"introduced": "0"}, {"fixed": "2.2.5"}]}]}]}
    res = scan_dependencies(str(tmp_path), post=post, get=get)
    vuln = [f for f in res["findings"] if f["id"] == "dep-vuln"][0]
    assert vuln["severity"] == "critical" and "2.2.5" in vuln["fix"] and vuln["file"] == "requirements.txt"
    assert any(f["id"] == "dep-unpinned" for f in res["findings"])


def test_osv_outage_fails_open_and_says_so(tmp_path):
    (tmp_path / "requirements.txt").write_text("flask==2.0.0\n", encoding="utf-8")

    def boom(url, payload):
        raise OSError("no network")
    res = scan_dependencies(str(tmp_path), post=boom)
    assert res["available"] is False and "no network" in res["errors"][0]
    assert [f for f in res["findings"] if f["id"] == "dep-vuln"] == []
    assert check_osv([], "PyPI")["available"] is True


# --- benchmark ----------------------------------------------------------------------------------

def test_engine_finds_every_planted_bug():
    res = score_engine(scan_material(PLANTED, "planted_app.py")["findings"])
    assert res["missed"] == [], res


def test_engine_is_silent_on_the_fixed_app():
    assert scan_material(FIXED, "fixed_app.py")["findings"] == []


def test_ground_truth_lines_point_at_real_code():
    lines = PLANTED.splitlines()
    for bug in load_truth()["bugs"]:
        for n in bug["lines"]:
            assert 1 <= n <= len(lines) and lines[n - 1].strip(), bug


def test_report_scoring_counts_keywords():
    res = score_report("There is SQL injection in /user and MD5 is used; debug mode is on.")
    assert {"B01", "B04", "B15"} <= set(res["found"]) and "B03" in res["missed"]


# --- blind benchmark ------------------------------------------------------------------------------

def _blind():
    truth = load_truth("blind")
    files = {f: (BENCH / truth["dir"] / f).read_text(encoding="utf-8") for f in truth["files"]}
    return truth, files


def test_blind_files_carry_no_hint_that_they_are_vulnerable():
    _, files = _blind()
    for name, code in files.items():
        low = code.lower()
        assert "vulnerab" not in low and "ground truth" not in low and "never deploy" not in low, name


def test_blind_ground_truth_lines_point_at_real_code():
    truth, files = _blind()
    for bug in truth["bugs"]:
        lines = files[bug["file"]].splitlines()
        for n in bug["lines"]:
            assert 1 <= n <= len(lines) and lines[n - 1].strip(), bug


def test_blind_shop_is_the_planted_shop_without_its_header():
    _, files = _blind()
    assert files["shop_service.py"].splitlines() == PLANTED.splitlines()[2:]


def test_engine_finds_what_the_blind_ground_truth_says_it_should():
    truth, files = _blind()
    for name, code in files.items():
        res = score_engine(scan_material(code, name)["findings"], truth, file=name)
        expected = [b["id"] for b in truth["bugs"] if b["file"] == name and b["rules"]]
        assert set(expected) <= set(res["found"]), (name, res)


def test_blind_orders_has_bugs_the_rule_engine_cannot_see():
    truth, files = _blind()
    res = score_engine(scan_material(files["orders_service.py"], "orders_service.py")["findings"], truth,
                       file="orders_service.py")
    assert res["recall"] < 0.6   # the point of this file: the rest has to come from a model


def test_handler_with_its_own_api_key_check_is_not_reported_unauthenticated_in_orders():
    _, files = _blind()
    flagged = {f["line"] for f in scan_material(files["orders_service.py"], "o.py")["findings"] if f["id"] == "route-no-auth"}
    assert 133 not in flagged


def test_money_in_float_is_a_logic_finding_and_decimal_is_not():
    def ids(code, name="m.py"):
        return [f["id"] for f in scan_material(code, name)["findings"]]
    assert "logic-money-float" in ids("unit_price = float(data['price'])\n")
    assert "logic-money-float" in ids("total = round(qty * unit_price * 1.2, 2)\n")
    assert "logic-js-money-float" in ids("const amount = parseFloat(req.body.amount);\n", "m.js")
    assert "logic-money-float" not in ids("price = Decimal(data['price'])\n")
    assert "logic-money-float" not in ids("score = float(row['score'])\nratio = float(n) / d\n")
