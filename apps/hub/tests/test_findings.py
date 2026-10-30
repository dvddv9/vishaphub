"""Findings from two readers: joined where they agree, never dropped, each saying who saw it."""
from hub import findings, templates

# The run a person actually reported: the model's four findings and the rules' five (two of them about the patch).
MODEL = [
    {"severity": "critical", "rule": "CWE-89", "message": "name is interpolated into the SQL string", "line": 10},
    {"severity": "critical", "rule": "CWE-22", "message": "file escapes the reports directory", "line": 15},
    {"severity": "medium", "rule": "CWE-306", "message": "no authentication on either route", "line": 6},
    {"severity": "low", "rule": "CWE-772", "message": "the connection is never closed", "line": 9},
]
RULES = [
    {"rule": "sqli-fstring", "severity": "critical", "message": "SQL query built with an f-string", "line": 10,
     "cwe": "CWE-89", "fix": "Pass user data as bound parameters.", "source": "material"},
    {"rule": "route-no-auth", "severity": "medium", "message": "GET /user: no authentication", "line": 7,
     "cwe": "CWE-862", "fix": "Require an authenticated caller.", "source": "material"},
    {"rule": "route-no-auth", "severity": "medium", "message": "GET /report: no authentication", "line": 14,
     "cwe": "CWE-862", "fix": "Require an authenticated caller.", "source": "material"},
    {"rule": "route-no-auth", "severity": "medium", "message": "", "line": 15, "cwe": "CWE-862", "source": "patch:app.py"},
    {"rule": "route-no-auth", "severity": "medium", "message": "", "line": 25, "cwe": "CWE-862", "source": "patch:app.py"},
]


def test_the_same_injection_seen_twice_is_one_finding_that_both_readers_saw():
    merged, _ = findings.merge(MODEL, RULES)
    sqli = [f for f in merged if f.get("cwe") == "CWE-89"]
    assert len(sqli) == 1 and sqli[0]["seen_by"] == ["rules", "model"]
    assert sqli[0]["rule"] == "sqli-fstring" and sqli[0]["model_rule"] == "CWE-89"
    assert sqli[0]["message"] == "name is interpolated into the SQL string"          # the model explains
    assert sqli[0]["rules_message"] == "SQL query built with an f-string"            # the rules' own words are kept
    assert sqli[0]["fix"] == "Pass user data as bound parameters."


def test_nothing_is_dropped_and_the_overlap_adds_up():
    merged, overlap = findings.merge(MODEL, RULES)
    assert overlap == {"both": 2, "model_only": 2, "rules_only": 1, "in_patch": 2}
    assert len(merged) == len(MODEL) + len(RULES) - overlap["both"] == 7
    only_model = {f["rule"] for f in merged if f["seen_by"] == ["model"]}
    assert only_model == {"CWE-22", "CWE-772"}                      # the traversal the rules missed is still there
    assert all(f["source"] == "model" for f in merged if f["seen_by"] == ["model"])


def test_the_authorization_findings_are_the_same_open_door_under_two_cwe_numbers():
    merged, _ = findings.merge(MODEL, RULES)
    auth = [f for f in merged if f["seen_by"] == ["rules", "model"] and f["rule"] == "route-no-auth"]
    assert len(auth) == 1 and auth[0]["model_rule"] == "CWE-306" and auth[0]["line"] == 7
    unpaired = [f for f in merged if f["rule"] == "route-no-auth" and f["seen_by"] == ["rules"] and f["source"] == "material"]
    assert [f["line"] for f in unpaired] == [14]                    # the second route, which the model named once for both


def test_the_findings_about_the_models_own_patch_are_never_paired_with_its_review():
    merged, _ = findings.merge(MODEL, RULES)
    in_patch = [f for f in merged if str(f.get("source", "")).startswith("patch:")]
    assert [f["line"] for f in in_patch] == [15, 25] and all(f["seen_by"] == ["rules"] for f in in_patch)


def test_the_worst_comes_first_and_what_two_readers_saw_before_what_one_did():
    merged, _ = findings.merge(MODEL, RULES)
    assert [f["severity"] for f in merged][:2] == ["critical", "critical"]
    assert merged[0]["seen_by"] == ["rules", "model"]                 # both saw it, so it leads among the criticals
    assert merged[-1]["severity"] == "low"


def test_the_stricter_severity_wins_when_two_readers_disagree():
    merged, _ = findings.merge([{"severity": "high", "rule": "CWE-89", "line": 5}],
                               [{"rule": "x", "severity": "medium", "cwe": "CWE-89", "line": 5, "source": "material"}])
    assert merged[0]["severity"] == "high"


def test_the_same_class_far_away_is_a_different_finding():
    merged, overlap = findings.merge([{"severity": "high", "rule": "CWE-89", "line": 80}],
                                     [{"rule": "x", "severity": "high", "cwe": "CWE-89", "line": 10, "source": "material"}])
    assert overlap["both"] == 0 and len(merged) == 2


def test_one_model_finding_pairs_with_one_rules_finding_not_two():
    merged, overlap = findings.merge(
        [{"severity": "high", "rule": "CWE-89", "line": 10}],
        [{"rule": "a", "severity": "high", "cwe": "CWE-89", "line": 10, "source": "material"},
         {"rule": "b", "severity": "high", "cwe": "CWE-89", "line": 11, "source": "material"}])
    assert overlap == {"both": 1, "model_only": 0, "rules_only": 1, "in_patch": 0} and len(merged) == 2


def test_a_finding_with_no_cwe_is_never_guessed_into_a_pair():
    merged, overlap = findings.merge([{"severity": "high", "rule": "bad-idea", "line": 3}],
                                     [{"rule": "other", "severity": "high", "line": 3, "source": "material"}])
    assert overlap["both"] == 0 and len(merged) == 2


def test_a_model_alone_is_listed_as_the_model_and_garbage_is_ignored():
    merged, overlap = findings.merge([{"severity": "low", "rule": "CWE-1", "line": "x"}, "not a finding", None], [])
    assert len(merged) == 1 and merged[0]["seen_by"] == ["model"] and merged[0]["source"] == "model"
    assert overlap["both"] == 0


def test_the_report_page_shows_who_saw_what_and_how_to_fix_it():
    merged, overlap = findings.merge(MODEL, RULES)
    page = templates.report_page({"id": "r1", "result": {"verdict": "REQUIRES_REVIEW", "ok": True, "findings": merged,
                                                         "agreement": overlap, "plan": {"stages": ["generator", "analyser"]}}})
    assert "rules + model" in page and "fix: Pass user data as bound parameters." in page
    assert "seen by both readers: 2" in page and "model only: 2" in page and "rules only: 1" in page
    assert "(model)" in page                                          # the traversal, seen by the model alone