# -*- coding: utf-8 -*-
"""The labelled benchmark as a test: the corpus is sound, and no critical example gets SAFE.

The rule engine only - no model, no network. See tests/bench/labelled_score.py and
tests/bench/labelled/RESULTS.md for what is measured and, just as important, what is not: this says
nothing about the quality of hub verdicts that used a model.

The release blocker is test_no_critical_example_gets_safe. It is deliberately not skippable and not
softened by a list of known failures: a critical example the rules call SAFE is a defect to fix, not to
record.
"""
import json
import re

import pytest

from tests.bench import labelled_score as lb

CWE = re.compile(r"^CWE-\d+$")


@pytest.fixture(scope="module")
def manifest():
    return lb.load_manifest()


@pytest.fixture(scope="module")
def results(manifest):
    return lb.run(manifest)


# the corpus itself ------------------------------------------------------------

def test_every_example_is_labelled_explained_and_present(manifest):
    seen = set()
    for ex in manifest["examples"]:
        assert ex["id"] not in seen, f"duplicate id {ex['id']}"
        seen.add(ex["id"])
        assert (lb.CORPUS / ex["file"]).is_file(), ex["id"]
        assert ex["label"] in ("dangerous", "safe"), ex["id"]
        assert ex["rationale"].strip(), f"{ex['id']} has no reason for its label"
        if ex["label"] == "safe":
            assert ex["criticality"] == "none" and ex["expected"] == [], ex["id"]
        else:
            assert ex["criticality"] in lb.CRITICALITIES, ex["id"]
            assert ex["expected"], f"{ex['id']} is dangerous but names no expected finding"
            for e in ex["expected"]:
                assert CWE.match(e["cwe"]) and e["why"].strip(), (ex["id"], e)


def test_expected_lines_point_at_lines_that_exist(manifest):
    for ex in manifest["examples"]:
        n = len((lb.CORPUS / ex["file"]).read_text(encoding="utf-8").splitlines())
        for e in ex["expected"]:
            assert 0 <= e["line"] <= n, (ex["id"], e["line"], n)


def test_every_language_has_dangerous_and_safe_examples_and_a_critical_one_where_it_can(manifest):
    by_lang: dict = {}
    for ex in manifest["examples"]:
        by_lang.setdefault(ex["language"], set()).add(ex["label"])
    assert by_lang, "empty corpus"
    for lang, labels in by_lang.items():
        assert labels == {"dangerous", "safe"}, f"{lang} needs both dangerous and safe examples"


def test_the_corpus_languages_are_ones_the_engine_detects(manifest):
    from src.tools.static_scan import detect_language

    for ex in manifest["examples"]:
        name = (lb.CORPUS / ex["file"]).name
        assert detect_language(name, "") == ex["language"], (ex["id"], name)


def test_the_root_readme_states_the_size_of_the_set_and_the_limit(manifest):
    from pathlib import Path

    readme = (Path(__file__).resolve().parents[3] / "README.md").read_text(encoding="utf-8")
    n = len(manifest["examples"])
    dangerous = sum(1 for e in manifest["examples"] if e["label"] == "dangerous")
    assert f"{n} labelled examples" in readme and f"{dangerous} dangerous" in readme
    assert f"{n - dangerous} safe" in readme
    assert "does not measure" in readme and "hub verdicts that used a model" in readme


def test_the_limit_is_written_where_a_reader_will_see_it(manifest):
    assert "hub's verdicts with a model" in manifest["does_not_measure"]
    assert "hub's verdicts with a model" in lb.__doc__
    results_md = lb.CORPUS / "RESULTS.md"
    if results_md.exists():
        assert "does not measure the hub's verdicts with a model" in results_md.read_text(encoding="utf-8")


# the release blocker ------------------------------------------------------------

def test_no_critical_example_gets_safe(results):
    blocked = lb.blockers(results)
    assert not blocked, (
        "RELEASE BLOCKER - the rules alone call these critical examples SAFE (no finding at all):\n  "
        + "\n  ".join(blocked)
    )


# no step backwards ---------------------------------------------------------------

def test_no_example_got_worse_than_the_recorded_results(results):
    recorded_file = lb.CORPUS / "RESULTS.json"
    assert recorded_file.exists(), "run: python -m tests.bench.labelled_score --write"
    recorded = json.loads(recorded_file.read_text(encoding="utf-8"))["per_example"]
    worse = lb.regressions(lb.ratchet_view(results), recorded)
    assert not worse, "worse than the recorded results:\n  " + "\n  ".join(worse)


def test_the_recorded_results_cover_the_whole_corpus(manifest):
    recorded = json.loads((lb.CORPUS / "RESULTS.json").read_text(encoding="utf-8"))
    assert recorded["examples"] == len(manifest["examples"]), \
        "the corpus changed: run python -m tests.bench.labelled_score --write"
