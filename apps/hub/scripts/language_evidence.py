"""Build apps/hub/src/hub/data/language_evidence.json from the analyzer's labelled benchmark.

    python apps/hub/scripts/language_evidence.py --write     # regenerate after the benchmark changed
    python apps/hub/scripts/language_evidence.py --check     # exit 1 if the committed file is stale (CI)

The hub tells a client how well the rules are measured for the language it just analysed. It can only say
that from data, and the data is the labelled benchmark (`tests/bench/labelled`): examples with a label, an
expected finding and a reason, dangerous and safe alike. This script copies the counts, per language, in the
two modes the benchmark measures (`named`: a file name was given; `pasted`: only the text, which is what the
hub sends). It records the hashes of what it read, so a stale copy is detectable, and nothing else.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BENCH = os.path.join(ROOT, "apps", "analyzer", "tests", "bench", "labelled")
OUT = os.path.join(ROOT, "apps", "hub", "src", "hub", "data", "language_evidence.json")


def _read(path: str) -> tuple[dict, str]:
    raw = open(path, "rb").read()                       # noqa: SIM115 - one short read, closed by the GC at exit
    return json.loads(raw.decode("utf-8-sig")), hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def build() -> dict:
    results, results_sha = _read(os.path.join(BENCH, "RESULTS.json"))
    manifest, manifest_sha = _read(os.path.join(BENCH, "manifest.json"))
    langs: dict = {}
    for mode in ("named", "pasted"):
        counts = results["summary_counts"][mode]
        for row in counts["dangerous"]:
            d = langs.setdefault(row["language"], {}).setdefault(mode, {})
            for key, src in (("dangerous_examples", "examples"), ("expected_findings", "expected_findings"),
                             ("hit_findings", "hit_findings"), ("wrong_line_only", "wrong_line_only"),
                             ("dangerous_got_safe", "safe_verdicts")):
                d[key] = d.get(key, 0) + row[src]
            d["critical_got_safe"] = d.get("critical_got_safe", 0) + (row["safe_verdicts"] if row["criticality"] == "critical" else 0)
        for row in counts["safe"]:
            d = langs.setdefault(row["language"], {}).setdefault(mode, {})
            d["safe_examples"] = d.get("safe_examples", 0) + row["examples"]
            d["safe_flagged"] = d.get("safe_flagged", 0) + row["with_findings"]
            d["fp_findings"] = d.get("fp_findings", 0) + row["fp_findings"]
    for lang, modes in langs.items():
        for m in modes.values():
            for key in ("dangerous_examples", "expected_findings", "hit_findings", "wrong_line_only",
                        "dangerous_got_safe", "critical_got_safe", "safe_examples", "safe_flagged", "fp_findings"):
                m.setdefault(key, 0)
        modes["not_independent_examples"] = sum(1 for e in manifest["examples"]
                                                if e["language"] == lang and e.get("rules_written_after"))
    return {
        "schema": 1,
        "what_it_is": "Counts copied from the analyzer's labelled benchmark (rules alone: no model, no network). "
                      "They say what the rules do on those examples, not on your code.",
        "source": {"results": "apps/analyzer/tests/bench/labelled/RESULTS.json", "results_sha256": results_sha,
                   "manifest": "apps/analyzer/tests/bench/labelled/manifest.json", "manifest_sha256": manifest_sha,
                   "examples": len(manifest["examples"])},
        "languages": dict(sorted(langs.items())),
    }


def main(argv: list[str]) -> int:
    new = json.dumps(build(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    if "--write" in argv:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new)
        print("wrote", OUT)
        return 0
    try:
        with open(OUT, encoding="utf-8", newline="") as fh:
            old = fh.read().replace("\r\n", "\n")
    except OSError:
        old = ""
    if old != new:
        print("language_evidence.json is stale: run `python apps/hub/scripts/language_evidence.py --write`")
        return 1
    print("language_evidence.json is up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))