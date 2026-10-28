# -*- coding: utf-8 -*-
"""Recall scoreboard for the planted benchmark.

    python -m tests.bench.score engine            # the built-in rules, no LLM
    python -m tests.bench.score report FILE...    # any free-text report (a Vishap result, a plain model answer)

Prints which planted bugs were found and the recall. A keyword hit is a rough signal (a report that
says "debug" in passing counts), so read the misses, not just the number.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent


def load_truth() -> dict:
    return json.loads((HERE / "ground_truth.json").read_text(encoding="utf-8"))


def score_engine(findings: list, truth: dict | None = None) -> dict:
    truth = truth or load_truth()
    found, missed = [], []
    for b in truth["bugs"]:
        hit = any(f["id"] in b["rules"] and f["line"] in b["lines"] for f in findings)
        (found if hit else missed).append(b["id"])
    extra = [f for f in findings if not any(f["id"] in b["rules"] and f["line"] in b["lines"] for b in truth["bugs"])]
    return {"found": found, "missed": missed, "recall": len(found) / len(truth["bugs"]),
            "unexpected": [(f["id"], f["line"]) for f in extra]}


def score_report(text: str, truth: dict | None = None) -> dict:
    truth = truth or load_truth()
    low = text.lower()
    found = [b["id"] for b in truth["bugs"] if any(k in low for k in b["keywords"])]
    missed = [b["id"] for b in truth["bugs"] if b["id"] not in found]
    return {"found": found, "missed": missed, "recall": len(found) / len(truth["bugs"])}


def _print(name: str, res: dict, truth: dict) -> None:
    titles = {b["id"]: b["title"] for b in truth["bugs"]}
    print(f"{name}: {len(res['found'])}/{len(truth['bugs'])} planted bugs ({res['recall']:.0%})")
    for i in res["missed"]:
        print(f"  missed {i}: {titles[i]}")
    if res.get("unexpected"):
        print(f"  not in ground truth: {res['unexpected']}")


def main(argv: list) -> int:
    truth = load_truth()
    if len(argv) >= 1 and argv[0] == "engine":
        from src.tools.static_scan import scan_material
        code = (HERE / truth["file"]).read_text(encoding="utf-8")
        _print("engine", score_engine(scan_material(code, truth["file"])["findings"], truth), truth)
        return 0
    if len(argv) >= 2 and argv[0] == "report":
        for p in argv[1:]:
            _print(p, score_report(Path(p).read_text(encoding="utf-8", errors="replace"), truth), truth)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
