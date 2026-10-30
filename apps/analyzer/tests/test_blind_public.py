# -*- coding: utf-8 -*-
"""The blind set as a test: it stays frozen, the gates mean what they were registered to mean, and the table the hub
reads is what the rules actually do.

Nothing here uses a model. The re-run needs the example files, which are downloaded from pinned URLs and checked
against the manifest's SHA-256: from the cache if it is full, from the network if BLIND_FETCH=1 (CI sets it).
"""
import contextlib
import json
import os

import pytest

from src.tools import safe_gate
from tests.bench.blind_public import blind_score as bs
from tests.bench.blind_public import model_eval as me

CRITERION = bs.load_criterion()


@pytest.fixture(scope="module")
def manifest():
    return bs.load_manifest()


# the set stays frozen and the criterion stays as registered ----------------------

def test_the_frozen_ids_are_the_ids_that_were_hashed_before_the_first_run(manifest):
    recorded = (bs.HERE / "frozen_ids.sha256").read_text(encoding="utf-8").strip()
    assert bs.frozen_ids_hash(manifest) == recorded, (
        "an example was added or removed from the frozen set; additions must carry post_run: true, removals are not allowed")


def test_the_criterion_is_the_one_the_results_were_computed_with():
    recorded = json.loads((bs.HERE / "RESULTS.json").read_text(encoding="utf-8"))
    assert recorded["criterion_sha256"] == bs.file_sha(bs.HERE / "criterion.json"), (
        "criterion.json changed after the results were recorded: a criterion is changed in a commit that says why, "
        "before new data, and never after seeing results")
    assert safe_gate.load_quality()["criterion_sha256"] == recorded["criterion_sha256"]
    first = json.loads((bs.HERE / "RESULTS.first-run.json").read_text(encoding="utf-8"))
    assert first["criterion_sha256"] == recorded["criterion_sha256"] or "version" in CRITERION


def test_every_example_has_an_independent_source_a_pin_and_a_reason(manifest):
    pins = manifest["sources"]
    seen = set()
    for e in manifest["examples"]:
        assert e["id"] not in seen
        seen.add(e["id"])
        assert e["source"] in pins and pins[e["source"]]["sha"] in e["url"], e["id"]
        assert len(e["sha256"]) == 64 and e["bytes"] >= 0, e["id"]
        assert e["label"] in ("dangerous", "safe") and isinstance(e["post_run"], bool), e["id"]
        if e["label"] == "safe":
            assert e["criticality"] == "none" and e["expected"] == [], e["id"]
        else:
            assert e["criticality"] in bs.CRITICALITIES and e["expected"], e["id"]
            assert all(x.get("why") for x in e["expected"]), e["id"]
    assert manifest["left_out"] is not None


def test_an_empty_example_is_a_named_flaw_not_a_silent_one(manifest):
    empty = [e["id"] for e in manifest["examples"] if e["bytes"] == 0]
    assert empty == ["dvwa:javascript/impossible"], "a new empty example appeared: decide, and say so in RESULTS.md"
    assert all(i in (bs.HERE / "RESULTS.md").read_text(encoding="utf-8") for i in empty)


def test_examples_added_after_the_first_run_are_never_counted_in_a_gate():
    per = {"a": {"post_run": True, "detected": "java", "label": "dangerous", "criticality": "critical", "raw_safe": True},
           "b": {"post_run": False, "detected": "java", "label": "dangerous", "criticality": "high", "raw_safe": False}}
    stats = bs.language_stats(per)["java"]
    assert (stats["dangerous"], stats["false_safe"], stats["critical_false_safe"]) == (1, 0, 0)


# the gates ----------------------------------------------------------------------

def test_the_wilson_bound_is_what_the_criterion_quotes():
    assert round(safe_gate.wilson_upper(0, 20), 3) == 0.161
    assert round(safe_gate.wilson_upper(1, 20), 3) == 0.236
    assert safe_gate.wilson_upper(0, 0) == 1.0


def stats(dangerous, safe, false_safe, critical_false_safe=0):
    return {"dangerous": dangerous, "safe": safe, "false_safe": false_safe, "critical_false_safe": critical_false_safe}


def test_a_language_passes_only_when_measured_and_g1_and_g2():
    assert safe_gate.evaluate_gates(stats(20, 20, 0), CRITERION)["safe_allowed"] is True
    assert safe_gate.evaluate_gates(stats(20, 20, 1), CRITERION)["safe_allowed"] is False                 # G2: 23.6% > 20%
    assert safe_gate.evaluate_gates(stats(200, 200, 10, 1), CRITERION)["safe_allowed"] is False           # G1: one critical
    assert safe_gate.evaluate_gates(stats(200, 200, 10), CRITERION)["safe_allowed"] is True               # 5% of 200
    assert safe_gate.evaluate_gates(stats(19, 40, 0), CRITERION)["safe_allowed"] is False                 # unmeasured
    assert safe_gate.evaluate_gates(stats(40, 19, 0), CRITERION)["safe_allowed"] is False
    assert "unmeasured" in safe_gate.evaluate_gates(stats(5, 5, 0), CRITERION)["why"]


def test_a_small_set_cannot_pass_by_luck():
    assert not safe_gate.evaluate_gates(stats(20, 20, 1), CRITERION)["g2"]
    assert safe_gate.evaluate_gates(stats(20, 20, 0), CRITERION)["g2"]


def test_a_language_the_engine_did_not_recognise_is_not_a_language_that_can_pass():
    results = {"pasted": {"x": {"post_run": False, "detected": "unknown", "label": "safe", "criticality": "none",
                                "raw_safe": False, "language": "java", "source": "s", "category": None}}}
    assert "unknown" not in bs.quality_from(results, CRITERION, {"examples": []})["languages"]


def test_the_decision_names_its_reason_and_fails_closed():
    covered = {"findings": [], "coverage": {"language": "java", "complete": True, "gaps": []}}
    table = {"languages": {"java": {"safe_allowed": True, "dangerous": 50, "safe": 50, "false_safe_upper_95": 0.07}}}
    assert safe_gate.decide(covered, table)["verdict"] == "SAFE"
    assert safe_gate.decide(covered, {"languages": {}})["verdict"] == "REQUIRES_REVIEW"
    assert safe_gate.decide({"findings": [], "coverage": {"language": "java", "complete": False, "gaps": ["g"]}},
                            table)["verdict"] == "REQUIRES_REVIEW"
    assert safe_gate.decide({"findings": [], "language": "java"}, table)["verdict"] == "REQUIRES_REVIEW"   # no coverage block
    flagged = safe_gate.decide({"findings": [{"severity": "critical"}], "coverage": covered["coverage"]}, table)
    assert flagged["verdict"] == "REQUIRES_REVIEW" and flagged["critical"] and "critical" in flagged["reason"]


# the table the hub reads is what the rules do ----------------------------------------

def test_a_tampered_file_is_refused(tmp_path, manifest, monkeypatch):
    entry = manifest["examples"][0]
    monkeypatch.setattr(bs, "CACHE", tmp_path)
    target = bs.cached_path(entry)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"not the pinned file")
    with pytest.raises(RuntimeError, match="sha256 differs"):
        bs.get_code(entry)


def test_the_recorded_table_and_results_are_what_the_rules_do_today(manifest):
    if not (bs.have_all_files(manifest) or os.getenv("BLIND_FETCH")):
        pytest.skip("the example files are not cached; run with BLIND_FETCH=1 to download them from the pinned URLs")
    results = bs.run(manifest)
    recorded = json.loads((bs.HERE / "RESULTS.json").read_text(encoding="utf-8"))["per_example"]
    worse = [f"{mode}: {i} was flagged and is now raw SAFE"
             for mode, per in recorded.items() for i, old in per.items()
             if manifest_label(manifest, i) == "dangerous" and not old["raw_safe"] and results[mode][i]["raw_safe"]]
    assert not worse, "a dangerous example the rules used to flag is now called SAFE:\n  " + "\n  ".join(worse)
    now = bs.quality_from(results, CRITERION, manifest)
    shipped = safe_gate.load_quality()
    assert now["languages"] == shipped["languages"], (
        "src/tools/quality.json is not what the rules produce now: run python -m tests.bench.blind_public.blind_score --write")
    for lang, q in shipped["languages"].items():
        assert not q["safe_allowed"] or (q["measured"] and q["critical_false_safe"] == 0), lang


def manifest_label(manifest, ident):
    return next(e["label"] for e in manifest["examples"] if e["id"] == ident)

# model mode: the harness, without a model ----------------------------------------------

def fake_example(ident, label, criticality="none", language="python"):
    return {"id": ident, "language": language, "label": label, "criticality": criticality, "bytes": 100,
            "post_run": False, "expected": [], "source": "s", "path": ident, "sha256": "0" * 64, "url": "u"}


class FakeMeter:
    def __init__(self, tokens):
        self.tokens = tokens

    def measured(self):
        return self.tokens


def fake_metering(tokens=None):
    @contextlib.contextmanager
    def metering():
        yield FakeMeter(tokens)
    return metering


def clean_python():
    return "def add(a, b):\n    return a + b\n"


def test_the_model_sample_is_deterministic_and_leaves_out_post_run_examples(manifest):
    a, b = me.sample(manifest, 5), me.sample(manifest, 5)
    assert [e["id"] for e in a] == [e["id"] for e in b]
    assert not any(e.get("post_run") for e in a)
    groups = {}
    for e in a:
        groups[(e["language"], e["label"])] = groups.get((e["language"], e["label"]), 0) + 1
    assert max(groups.values()) <= 5
    extra = [dict(e) for e in manifest["examples"][:3]]
    for e in extra:
        e["post_run"] = True
    assert not {e["id"] for e in extra} & {e["id"] for e in me.sample({"examples": extra}, 99)}


def test_the_estimate_is_labelled_and_gives_no_price(manifest):
    est = me.estimate(me.sample(manifest, 2), 3, 1000, 5000)
    assert est["calls"] == est["examples"] * 3 and "price" in est["basis"] and "estimate" in est["basis"]
    assert "usd" not in json.dumps(est).lower() and "$" not in json.dumps(est)


def run_stub(monkeypatch, examples, verdict, runs=2, tokens=None, ok=True):
    monkeypatch.setattr(bs, "get_code", lambda e: clean_python() if e["id"].startswith("clean") else "x = eval(user)\n")
    calls = []

    def caller(**kw):
        calls.append(kw)
        return {"ok": ok, "verdict": verdict}
    return me.evaluate(examples, runs, caller, metering=fake_metering(tokens)), calls


def test_a_candidate_safe_needs_the_rules_the_scan_and_the_model_to_agree(monkeypatch):
    examples = [fake_example("clean-1", "dangerous", "critical"), fake_example("flagged-1", "dangerous", "critical")]
    per, calls = run_stub(monkeypatch, examples, "SAFE")
    assert per["clean-1"]["candidate_safe_runs"] == 2        # nothing found, complete scan, model said SAFE
    assert per["flagged-1"]["candidate_safe_runs"] == 0      # the rules found eval: the model cannot lower that
    assert len(calls) == 4 and all(c["question"] == me.QUESTION for c in calls)


def test_a_model_failure_is_never_safe(monkeypatch):
    per, _ = run_stub(monkeypatch, [fake_example("clean-1", "dangerous", "critical")], "SAFE", ok=False)
    assert per["clean-1"]["verdicts"] == ["ERROR", "ERROR"] and per["clean-1"]["candidate_safe_runs"] == 0


def test_m1_and_m2_are_judged_on_any_run(monkeypatch):
    dangerous = [fake_example(f"clean-d{i}", "dangerous", "high") for i in range(20)]
    safe = [fake_example(f"clean-s{i}", "safe") for i in range(20)]
    per, _ = run_stub(monkeypatch, dangerous + safe, "REQUIRES_REVIEW")
    good = me.gates({**per}, CRITERION)["python"]
    assert good["false_safe"] == 0 and good["safe_allowed"] is True                    # 0 of 20, nothing was SAFE
    per["clean-d0"]["candidate_safe_runs"] = 1                                          # one run on one example
    bad = me.gates(per, CRITERION)["python"]
    assert bad["false_safe"] == 1 and bad["safe_allowed"] is False                      # 1 of 20: upper bound 23.6%
    per["clean-d0"].update(candidate_safe_runs=0, criticality="critical")
    per["clean-d1"].update(candidate_safe_runs=1, criticality="critical")
    assert me.gates(per, CRITERION)["python"]["critical_false_safe"] == 1
    assert "M1" in me.gates(per, CRITERION)["python"]["why"]


def test_provider_tokens_are_reported_apart_from_the_estimate(monkeypatch):
    per, _ = run_stub(monkeypatch, [fake_example("clean-1", "safe")], "SAFE", runs=3,
                      tokens={"input": 100, "output": 40, "calls": 1, "calls_measured": 1})
    tok = me.tokens(per)
    assert (tok["calls"], tok["calls_with_provider_usage"], tok["tokens_in_reported"], tok["tokens_out_reported"]) == (3, 3, 300, 120)
    silent, _ = run_stub(monkeypatch, [fake_example("clean-1", "safe")], "SAFE", runs=2, tokens=None)
    assert me.tokens(silent)["tokens_in_reported"] is None


def test_a_real_run_needs_a_key_and_an_explicit_confirmation(monkeypatch, capsys):
    monkeypatch.delenv("VISHAP_HUB_LLM_KEY", raising=False)
    assert me.main(["--runs", "1"]) == 2
    monkeypatch.setenv("VISHAP_HUB_LLM_KEY", "k")
    assert me.main(["--runs", "1"]) == 2                  # a key alone does not spend money
    assert "spends the key's money" in capsys.readouterr().err


def test_a_dry_run_changes_nothing_that_the_hub_reads(manifest, monkeypatch):
    if not bs.have_all_files(manifest):
        pytest.skip("the example files are not cached")
    before = bs.file_sha(bs.QUALITY_OUT)
    assert me.main(["--dry-run", "--runs", "1", "--per-side", "2", "--write"]) == 0
    assert bs.file_sha(bs.QUALITY_OUT) == before


def test_the_model_can_lend_its_agreement_only_where_the_model_mode_passed():
    covered = {"findings": [], "coverage": {"language": "python", "complete": True, "gaps": []}}
    base = {"safe_allowed": False, "dangerous": 40, "safe": 40, "why": "G1 failed"}
    with_model = {"languages": {"python": {**base, "model_mode": {"safe_allowed": True, "dangerous": 25, "safe": 25,
                                                                     "false_safe_upper_95": 0.13}}}}
    assert safe_gate.decide(covered, with_model, model_verdict="SAFE")["verdict"] == "SAFE"
    assert safe_gate.decide(covered, with_model, model_verdict="REQUIRES_REVIEW")["verdict"] == "REQUIRES_REVIEW"
    assert safe_gate.decide(covered, with_model)["verdict"] == "REQUIRES_REVIEW"
    failed = {"languages": {"python": {**base, "model_mode": {"safe_allowed": False}}}}
    assert safe_gate.decide(covered, failed, model_verdict="SAFE")["verdict"] == "REQUIRES_REVIEW"
    findings = {"findings": [{"severity": "low"}], "coverage": covered["coverage"]}
    assert safe_gate.decide(findings, with_model, model_verdict="SAFE")["verdict"] == "REQUIRES_REVIEW"
    gap = {"findings": [], "coverage": {"language": "python", "complete": False, "gaps": ["x"]}}
    assert safe_gate.decide(gap, with_model, model_verdict="SAFE")["verdict"] == "REQUIRES_REVIEW"
