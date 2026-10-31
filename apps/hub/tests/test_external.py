"""A scanner the hub did not run: its SARIF is a third reader. It joins where it agrees, stays where it stands alone,
raises the verdict and never lowers it, and the fingerprint knows it was there."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from hub import evidence, external
from hub.pipeline import run_plan
from hub.router import plan_for
from hub.server import Handler
from hub.verdicts import rank

GOOD = {"calc.py": "def add(a, b):\n    return a + b\n"}
SPEC = {"files": ["calc.py"], "tests": []}
SQLI = "cur.execute(\"select * from t where a = \" + x)\n"


def sarif(*results, tool="Semgrep", rules=None):
    return {"version": "2.1.0", "runs": [{"tool": {"driver": {"name": tool, "rules": rules or []}},
                                         "results": list(results)}]}


def result(rule="r1", line=3, uri="calc.py", text="a finding", level="error"):
    return {"ruleId": rule, "level": level, "message": {"text": text},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": uri}, "region": {"startLine": line}}}]}


def one(cwe="CWE-79", line=3, file="calc.py", severity="high"):
    return {"rule": "x", "cwe": cwe, "severity": severity, "message": "m", "line": line, "file": file,
            "source": "external", "tool": "Semgrep"}


# ---- reading SARIF ------------------------------------------------------

def test_a_cwe_tag_a_severity_score_and_a_file_uri_are_read():
    rules = [{"id": "r1", "properties": {"tags": ["external/cwe/cwe-089"], "security-severity": "9.1"}}]
    found, notes = external.parse_sarif(sarif(result(uri="file://app.py", line=12), rules=rules))
    assert notes == []
    assert found == [{"rule": "r1", "cwe": "CWE-89", "severity": "critical", "message": "a finding", "line": 12,
                      "file": "app.py", "source": "external", "tool": "Semgrep"}]


def test_without_a_score_the_level_decides_and_without_a_class_there_is_none():
    found, _ = external.parse_sarif(sarif(result(level="warning"), result(level="note")))
    assert [f["severity"] for f in found] == ["medium", "low"] and all(f["cwe"] == "" for f in found)


def test_something_that_is_not_sarif_is_refused_not_read_as_empty():
    for bad in (None, [], {"runs": "x"}, {"nope": 1}, "text"):
        with pytest.raises(ValueError):
            external.parse_sarif(bad)


def test_past_the_limit_results_are_counted_and_the_count_is_said():
    doc = sarif(*[result(line=i + 1) for i in range(external.MAX_EXTERNAL + 5)])
    found, notes = external.parse_sarif(doc)
    assert len(found) == external.MAX_EXTERNAL and "5 external result" in notes[0]


# ---- joining ------------------------------------------------------------

MINE = [{"rule": "sqli-fstring", "cwe": "CWE-89", "severity": "critical", "line": 10, "file": "app.py",
         "source": "material", "seen_by": ["rules"]}]


def test_the_same_class_near_the_same_line_is_one_finding_seen_by_one_more_reader():
    out, summary = external.attach(MINE, [one("CWE-89", line=11, file="app.py")])
    assert len(out) == 1 and out[0]["seen_by"] == ["rules", "external"] and out[0]["external_tool"] == "Semgrep"
    assert summary == {"received": 1, "paired": 1, "external_only": 0, "tools": ["Semgrep"]}


def test_nothing_is_dropped_and_what_does_not_pair_stands_alone():
    cases = [one("CWE-79", line=10, file="app.py"),        # another class
             one("CWE-89", line=40, file="app.py"),        # too far
             one("CWE-89", line=10, file="other.py"),      # another file
             one("", line=10, file="app.py"),              # no class to compare
             one("CWE-89", line=0, file="app.py")]         # no line to compare
    out, summary = external.attach(MINE, cases)
    assert len(out) == 1 + len(cases) and summary["paired"] == 0 and summary["external_only"] == len(cases)
    assert all(f["seen_by"] == ["external"] for f in out[1:])
    assert MINE[0]["seen_by"] == ["rules"]                  # the input is not changed


# ---- in a run -------------------------------------------------------------

def test_a_lone_external_finding_raises_the_verdict_and_never_lowers_it():
    base = run_plan(plan_for("validate"), files=GOOD, spec=SPEC)
    got = run_plan(plan_for("validate"), files=GOOD, spec=SPEC, external=[one()])
    assert rank(got.verdict) >= max(rank(base.verdict), rank("REQUIRES_REVIEW"))
    assert any(f["seen_by"] == ["external"] for f in got.findings)
    assert got.as_dict()["external"]["external_only"] == 1


def test_an_empty_scanner_changes_nothing_and_leaves_no_trace_in_the_result():
    base = run_plan(plan_for("analyse"), material=SQLI, files=GOOD)
    got = run_plan(plan_for("analyse"), material=SQLI, files=GOOD, external=[])
    assert got.verdict == base.verdict and got.fingerprint == base.fingerprint and "external" not in got.as_dict()


def test_the_fingerprint_knows_the_scanner_was_there():
    base = run_plan(plan_for("analyse"), material=SQLI, files=GOOD)
    got = run_plan(plan_for("analyse"), material=SQLI, files=GOOD, external=[one()])
    assert "external" not in base.fingerprint["body"]["evidence"]
    assert got.fingerprint["body"]["evidence"]["external"] == {
        "count": 1, "sha256": evidence.sha([one()])}
    assert got.fingerprint != base.fingerprint


# ---- over HTTP ---------------------------------------------------------------

@pytest.fixture()
def port():
    from hub import limits
    from hub import server as server_module
    saved = dict(server_module.LIMITERS)
    for kind in server_module.LIMITERS:
        server_module.LIMITERS[kind] = limits.RateLimiter(0)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()
    server_module.LIMITERS.update(saved)


def post(port, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/run", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_a_bad_sarif_is_a_400_that_says_so(port):
    status, body = post(port, {"material": SQLI, "intent": "analyse", "sarif": {"nope": 1}})
    assert status == 400 and body["error"].startswith("sarif:")


def test_a_good_sarif_comes_back_in_the_run(port):
    doc = sarif(result(rule="xss", line=40, uri="app.py"), rules=[{"id": "xss", "properties": {"tags": ["CWE-79"]}}])
    status, body = post(port, {"material": SQLI, "intent": "analyse", "sarif": doc})
    assert status == 200 and body["external"]["external_only"] == 1
    assert any(f["seen_by"] == ["external"] and f["cwe"] == "CWE-79" for f in body["findings"])