# -*- coding: utf-8 -*-
"""Tests for baseline management (P0-1)."""
import json
from src.tools.baseline import (
    compute_fingerprint, save_baseline, load_baseline,
    filter_new, apply_baseline, BASELINE_VERSION,
)


def _rn(name="Nejavnoe", priority="kritichno", note="sizeof(data)", id_="RN-1"):
    return {"id": id_, "name": name, "priority": priority, "note": note}


def test_fp_stable():
    assert compute_fingerprint(_rn(), "x.c") == compute_fingerprint(_rn(), "x.c")
    assert len(compute_fingerprint(_rn(), "x.c")) == 16


def test_fp_ignores_id():
    assert compute_fingerprint(_rn(id_="RN-1"), "x.c") == compute_fingerprint(_rn(id_="RN-9"), "x.c")


def test_fp_ignores_ws_case():
    a = compute_fingerprint(_rn(name="Heap Overflow", priority="Critical"), "x.c")
    b = compute_fingerprint(_rn(name="  heap   overflow ", priority="critical"), "x.c")
    assert a == b


def test_fp_differs_name():
    assert compute_fingerprint(_rn(name="A"), "x.c") != compute_fingerprint(_rn(name="B"), "x.c")


def test_fp_differs_file():
    assert compute_fingerprint(_rn(), "a.c") != compute_fingerprint(_rn(), "b.c")


def test_fp_truncates_note():
    a = compute_fingerprint(_rn(note="x"*200), "x.c")
    b = compute_fingerprint(_rn(note="x"*100 + "TAIL"), "x.c")
    assert a == b


def test_save_load_roundtrip(tmp_path):
    nodes = [_rn(name="n"+str(i)) for i in range(5)]
    path = tmp_path / "b.json"
    assert save_baseline(nodes, str(path), "input.c") == 5
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == BASELINE_VERSION
    assert data["count"] == 5
    assert data["source_file"] == "input.c"
    assert len(load_baseline(str(path))) == 5


def test_load_missing(tmp_path):
    assert load_baseline(str(tmp_path / "no.json")) == set()


def test_load_corrupt(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("not json {{{", encoding="utf-8")
    assert load_baseline(str(p)) == set()


def test_load_invalid_schema(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text('["not", "dict"]', encoding="utf-8")
    assert load_baseline(str(p)) == set()


def test_filter_new():
    a = _rn(name="alpha")
    b = _rn(name="beta")
    baseline = {compute_fingerprint(a, "x.c")}
    new, known = filter_new([a, b], baseline, "x.c")
    assert len(new) == 1 and new[0]["name"] == "beta"
    assert len(known) == 1 and known[0]["name"] == "alpha"


def test_apply_save_then_filter(tmp_path):
    nodes = [_rn(name="n"+str(i)) for i in range(3)]
    path = tmp_path / "b.json"
    r1 = {"stage2": {"risk_nodes": nodes}}
    s1 = apply_baseline(r1, save_baseline_path=str(path), filename="x.c")
    assert s1["baseline_saved"] is True
    assert s1["baseline_saved_count"] == 3
    assert s1["baseline_used"] is False
    r2 = {"stage2": {"risk_nodes": [_rn(name="n"+str(i)) for i in range(3)]}}
    s2 = apply_baseline(r2, baseline_path=str(path), filename="x.c")
    assert s2["baseline_used"] is True
    assert s2["baseline_new"] == 0
    assert s2["baseline_known"] == 3
    assert r2["new_findings"] == []
    assert len(r2["known_findings"]) == 3


def test_apply_empty():
    r = {"stage2": {"risk_nodes": []}}
    s = apply_baseline(r, filename="x.c")
    assert s["baseline_total"] == 0


def test_apply_no_stage2():
    r = {}
    s = apply_baseline(r, filename="x.c")
    assert s["baseline_total"] == 0
    assert "baseline_stats" in r
