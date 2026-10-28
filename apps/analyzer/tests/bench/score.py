# -*- coding: utf-8 -*-
"""Recall scoreboard for the planted benchmarks.

    python -m tests.bench.score engine [planted|blind]         # the built-in rules, no LLM
    python -m tests.bench.score report FILE... [--set blind] [--file orders_service.py]
                                                               # any free-text report (a Vishap result, a plain model answer)

Two sets:
  planted  tests/bench/planted_app.py            18 bugs; the file says it is vulnerable (easy, primes a model)
  blind    tests/bench/blind/{shop,orders}_service.py   no hint in the code; the real comparison

A keyword hit is a rough signal, so the report prints the keyword that matched: read it, and read the
misses, not just the percentage. Score one report per file (--file) when you ran the files separately.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
SETS = {"planted": "ground_truth.json", "blind": "ground_truth_blind.json"}


def load_truth(name: str = "planted") -> dict:
    return json.loads((HERE / SETS[name]).read_text(encoding="utf-8"))


def _bug_file(bug: dict, truth: dict) -> str:
    return bug.get("file") or truth.get("file", "")


def score_engine(findings: list, truth: dict | None = None, *, file: str | None = None) -> dict:
    """``findings``: list of findings of one file (``file`` names it when the truth covers several)."""
    truth = truth or load_truth()
    bugs = [b for b in truth["bugs"] if file is None or _bug_file(b, truth) == file]
    found, missed = [], []
    for b in bugs:
        hit = any(f["id"] in b["rules"] and f["line"] in b["lines"] for f in findings)
        (found if hit else missed).append(b["id"])
    extra = [f for f in findings if not any(f["id"] in b["rules"] and f["line"] in b["lines"] for b in bugs)]
    return {"found": found, "missed": missed, "recall": len(found) / len(bugs) if bugs else 0.0,
            "total": len(bugs), "unexpected": [(f["id"], f["line"]) for f in extra]}


def score_report(text: str, truth: dict | None = None, *, file: str | None = None) -> dict:
    truth = truth or load_truth()
    bugs = [b for b in truth["bugs"] if file is None or _bug_file(b, truth) == file]
    low = text.lower()
    matched = {}
    for b in bugs:
        for k in b["keywords"]:
            if k in low:
                matched[b["id"]] = k
                break
    found = [b["id"] for b in bugs if b["id"] in matched]
    missed = [b["id"] for b in bugs if b["id"] not in matched]
    return {"found": found, "missed": missed, "matched": matched,
            "recall": len(found) / len(bugs) if bugs else 0.0, "total": len(bugs)}


def _print(name: str, res: dict, truth: dict) -> None:
    titles = {b["id"]: b["title"] for b in truth["bugs"]}
    print(f"{name}: {len(res['found'])}/{res['total']} planted bugs ({res['recall']:.0%})")
    for i in res["found"] if res.get("matched") else []:
        print(f"  found  {i} (matched '{res['matched'][i]}'): {titles[i]}")
    for i in res["missed"]:
        print(f"  missed {i}: {titles[i]}")
    if res.get("unexpected"):
        print(f"  engine findings not in the ground truth (check for false positives): {res['unexpected']}")


def _opt(argv: list, flag: str, default=None):
    if flag in argv:
        i = argv.index(flag)
        val = argv[i + 1] if i + 1 < len(argv) else default
        del argv[i:i + 2]
        return val
    return default


def main(argv: list) -> int:
    argv = list(argv)
    which = _opt(argv, "--set", "planted")
    only = _opt(argv, "--file", None)
    if argv and argv[0] == "engine":
        if len(argv) > 1 and argv[1] in SETS:
            which = argv[1]
        truth = load_truth(which)
        from src.tools.static_scan import scan_material
        files = truth.get("files") or [truth["file"]]
        for fname in files:
            path = HERE / truth.get("dir", "") / fname
            code = path.read_text(encoding="utf-8")
            res = score_engine(scan_material(code, fname)["findings"], truth, file=fname)
            _print(f"engine {which}/{fname}", res, truth)
        return 0
    if len(argv) >= 2 and argv[0] == "report":
        truth = load_truth(which)
        for p in argv[1:]:
            _print(p, score_report(Path(p).read_text(encoding="utf-8", errors="replace"), truth, file=only), truth)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
