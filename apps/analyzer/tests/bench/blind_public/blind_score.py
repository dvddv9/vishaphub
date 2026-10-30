# -*- coding: utf-8 -*-
"""Score the analyzer's rules on the blind set, and decide for which languages SAFE may be issued.

    python -m tests.bench.blind_public.blind_score            # print the report
    python -m tests.bench.blind_public.blind_score --write    # also write RESULTS.md, RESULTS.json and
                                                              # src/tools/quality.json (what the hub reads)
    python -m tests.bench.blind_public.blind_score --human labels.csv --dir path/to/files
                                                              # the same scoring on a person's own sample

The set, its sources and the gates were registered before the first run: CRITERION.md, SAMPLING.md, criterion.json,
frozen_ids.sha256. The example files are not in this repository (their licences differ); they are downloaded from the
pinned URLs into .cache/ and refused if their SHA-256 differs from the manifest.

What is measured: the rule engine, alone, no model. A result here says nothing about hub verdicts that used a model;
those are measured separately (model_eval.py) and are not part of this file.

Statistics are keyed by the language the engine DETECTED when the text is pasted without a file name, because that is
what the hub does and the hub decides per detected language.
"""
from __future__ import annotations

import csv
import hashlib
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

from src.tools import safe_gate
from src.tools.static_scan import scan_material

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
QUALITY_OUT = Path(__file__).resolve().parents[3] / "src" / "tools" / "quality.json"
MODES = ("named", "pasted")
CRITICALITIES = ("critical", "high", "medium")
#: what the engine says when it did not recognise the text, or when the text is a log: never a language that can pass
NOT_A_LANGUAGE = ("", "unknown", "log")


def load_manifest() -> dict:
    return json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))


def load_criterion() -> dict:
    return json.loads((HERE / "criterion.json").read_text(encoding="utf-8"))


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_ids_hash(manifest: dict) -> str:
    ids = sorted(e["id"] for e in manifest["examples"] if not e.get("post_run"))
    return hashlib.sha256(("\n".join(ids) + "\n").encode()).hexdigest()


def cached_path(entry: dict) -> Path:
    return CACHE / entry["source"] / entry["path"]


def have_all_files(manifest: dict) -> bool:
    return all(cached_path(e).exists() for e in manifest["examples"])


def get_code(entry: dict) -> str:
    """The example's text, from the cache or the pinned URL, refused if it is not the file the manifest names."""
    path = cached_path(entry)
    if not path.exists():
        request = urllib.request.Request(entry["url"], headers={"User-Agent": "vishaphub-bench"})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise RuntimeError(f"{entry['id']}: the file is not the one the manifest pins (sha256 differs)")
    return data.decode("utf-8", "replace")


def score_one(code: str, filename: str, entry: dict) -> dict:
    best, scan = None, {}
    for _ in range(3):
        start = time.perf_counter()
        scan = scan_material(code, filename)
        elapsed = (time.perf_counter() - start) * 1000
        best = elapsed if best is None else min(best, elapsed)
    findings = scan.get("findings") or []
    expected_cwes = {e.get("cwe") for e in entry["expected"] if e.get("cwe")}
    return {
        "detected": (scan.get("coverage") or {}).get("language", ""),
        "raw_safe": safe_gate.rules_found_nothing(scan),
        "findings": len(findings),
        "same_class": bool(expected_cwes and any(f.get("cwe") in expected_cwes for f in findings)),
        "gaps": (scan.get("coverage") or {}).get("gaps") or [],
        "ms": round(best or 0.0, 3),
    }


def run(manifest: dict | None = None) -> dict:
    """results[mode][example id] -> what the engine did. Every example, post_run ones included (flagged)."""
    manifest = manifest or load_manifest()
    results: dict = {mode: {} for mode in MODES}
    for entry in manifest["examples"]:
        code = get_code(entry)
        for mode in MODES:
            filename = Path(entry["path"]).name if mode == "named" else ""
            results[mode][entry["id"]] = {**score_one(code, filename, entry), "language": entry["language"],
                                          "source": entry["source"], "label": entry["label"],
                                          "criticality": entry["criticality"], "post_run": bool(entry.get("post_run")),
                                          "category": (entry["expected"][0].get("category") if entry["expected"] else None)}
    return results


def language_stats(per: dict, key: str = "detected") -> dict:
    """Counts per language for the gates. Post-run examples are not counted."""
    stats: dict = {}
    for r in per.values():
        if r["post_run"]:
            continue
        s = stats.setdefault(r[key], {"dangerous": 0, "safe": 0, "false_safe": 0, "critical_false_safe": 0,
                                      "safe_not_called_safe": 0, "false_safe_by": {c: 0 for c in CRITICALITIES},
                                      "dangerous_by": {c: 0 for c in CRITICALITIES}})
        if r["label"] == "dangerous":
            s["dangerous"] += 1
            s["dangerous_by"][r["criticality"]] += 1
            if r["raw_safe"]:
                s["false_safe"] += 1
                s["false_safe_by"][r["criticality"]] += 1
                if r["criticality"] == "critical":
                    s["critical_false_safe"] += 1
        else:
            s["safe"] += 1
            if not r["raw_safe"]:
                s["safe_not_called_safe"] += 1
    return stats


def quality_from(results: dict, criterion: dict, manifest: dict) -> dict:
    """What the hub reads. Keyed by the language the engine detects in pasted text."""
    languages = {}
    for lang, s in sorted(language_stats(results["pasted"]).items()):
        if lang in NOT_A_LANGUAGE:
            continue            # "unknown" has no false-SAFE only because its coverage is always incomplete: not a pass
        gate = safe_gate.evaluate_gates(s, criterion)
        languages[lang] = {"dangerous": s["dangerous"], "safe": s["safe"], "false_safe": s["false_safe"],
                           "critical_false_safe": s["critical_false_safe"],
                           "false_safe_upper_95": gate["false_safe_upper_95"],
                           "review_burden": round(s["safe_not_called_safe"] / s["safe"], 3) if s["safe"] else None,
                           "measured": gate["measured"], "safe_allowed": gate["safe_allowed"], "why": gate["why"]}
    return {"criterion_sha256": file_sha(HERE / "criterion.json"), "frozen_ids_sha256": frozen_ids_hash(manifest),
            "keyed_by": "the language the engine detects when text is pasted without a file name",
            "languages": languages}


def ratchet_view(results: dict) -> dict:
    return {mode: {i: {"raw_safe": r["raw_safe"], "findings": r["findings"]} for i, r in per.items()}
            for mode, per in results.items()}


def pct(n: int, d: int) -> str:
    return "-" if not d else f"{100 * n / d:.0f}%"


def render(results: dict, manifest: dict, criterion: dict) -> str:
    quality = quality_from(results, criterion, manifest)
    frozen = [e for e in manifest["examples"] if not e.get("post_run")]
    lines = [
        "# Blind set: the analyzer's rules on independently labelled examples",
        "",
        f"{len(frozen)} frozen examples from three sources (OWASP Benchmark for Java, DVWA, Bandit's examples), "
        "registered before the first run (`CRITERION.md`, `SAMPLING.md`, `frozen_ids.sha256`). The files are downloaded "
        "from pinned URLs and checked against the manifest's SHA-256; they are not in this repository.",
        "",
        "**What this measures:** the rule engine alone. It does not measure the hub's verdicts with a model; that is "
        "`model_eval.py`, paid and not part of CI. A result here says nothing about a hub run that used a model.",
        "",
        "**SAFE** is issued only for a language that passed the gates below, for a text the scan could read in full, "
        "with no finding. `raw SAFE` in the tables is the first two of those without the language gate: no finding and a "
        "complete scan. It is what the gates are about.",
        "",
        "## Gates and the decision per language",
        "",
        "Keyed by the language the engine detects when text is pasted without a file name, which is how the hub calls it.",
        "",
        "| language | dangerous | safe | false-SAFE | critical false-SAFE | 95% upper bound | review burden | measured | SAFE allowed | why |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for lang, q in quality["languages"].items():
        burden = "-" if q["review_burden"] is None else f"{100 * q['review_burden']:.0f}%"
        lines.append(f"| {lang} | {q['dangerous']} | {q['safe']} | {q['false_safe']} | {q['critical_false_safe']} | "
                     f"{100 * q['false_safe_upper_95']:.1f}% | {burden} | {'yes' if q['measured'] else 'no'} | "
                     f"**{'yes' if q['safe_allowed'] else 'no'}** | {q['why']} |")
    allowed = [lang for lang, q in quality["languages"].items() if q["safe_allowed"]]
    lines += ["", ("SAFE can be issued for: " + ", ".join(allowed) + "." if allowed else
                   "**SAFE cannot be issued for any language.** Every verdict the rules produce is REQUIRES_REVIEW until a "
                   "language passes."),
              "Languages with no source here (JavaScript, TypeScript, Go, C, C++, Terraform, YAML, Dockerfile) are unmeasured, "
              "so SAFE is never issued for them.", ""]
    lines += ["## By the example's true language, file name given (what an upload would see)", "",
              "Informational: the hub does not call the engine this way. Same gates, same counts.", "",
              "| language | dangerous | safe | false-SAFE | critical false-SAFE | 95% upper bound | G1 | G2 |", "|---|---:|---:|---:|---:|---:|---|---|"]
    for lang, s in sorted(language_stats(results["named"], key="language").items()):
        gate = safe_gate.evaluate_gates(s, criterion)
        lines.append(f"| {lang} | {s['dangerous']} | {s['safe']} | {s['false_safe']} | {s['critical_false_safe']} | "
                     f"{100 * gate['false_safe_upper_95']:.1f}% | {'pass' if gate['g1'] else 'FAIL'} | {'pass' if gate['g2'] else 'FAIL'} |")
    lines += [""]
    for mode in MODES:
        per = results[mode]
        lines += [f"## Mode `{mode}`" + (" (file name given)" if mode == "named" else " (pasted, language sniffed)"), "",
                  "| source | language | label | criticality | examples | raw SAFE | right class found |", "|---|---|---|---|---:|---:|---:|"]
        groups: dict = {}
        for r in per.values():
            if r["post_run"]:
                continue
            groups.setdefault((r["source"], r["language"], r["label"], r["criticality"]), []).append(r)
        for (source, lang, label, crit), rs in sorted(groups.items()):
            same = sum(1 for r in rs if r["same_class"])
            lines.append(f"| {source} | {lang} | {label} | {crit} | {len(rs)} | {sum(1 for r in rs if r['raw_safe'])} "
                         f"({pct(sum(1 for r in rs if r['raw_safe']), len(rs))}) | "
                         f"{same if label == 'dangerous' and source == 'benchmark' else '-'} |")
        ms = [r["ms"] for r in per.values()]
        lines += ["", f"Time per example: median {statistics.median(ms):.2f} ms, max {max(ms):.2f} ms.", ""]
        benchmark = [r for r in per.values() if r["source"] == "benchmark" and r["label"] == "dangerous" and not r["post_run"]]
        cats: dict = {}
        for r in benchmark:
            c = cats.setdefault(r["category"], [0, 0])
            c[0] += 1
            c[1] += 1 if r["raw_safe"] else 0
        lines += [f"OWASP Benchmark, dangerous examples called raw SAFE by category (mode `{mode}`): "
                  + ", ".join(f"{k} {v[1]}/{v[0]}" for k, v in sorted(cats.items())) + ".", ""]
    post = [i for i, r in results["pasted"].items() if r["post_run"]]
    lines += [f"## Examples added after the first run: {len(post)}", "",
              "Reported apart and never counted in a gate." if post else "None.", ""]
    empty = [e["id"] for e in manifest["examples"] if e["bytes"] == 0]
    lines += ["## Known flaws in the sample", "",
              (f"{len(empty)} example(s) are empty files in their source ({', '.join(empty)}). The sampling rule had no "
               "exception for an empty file and the rules say an example is never removed after the first run, so it is kept "
               "and counted as the source labelled it. It is a defect of the sample, not a finding about the rules.")
              if empty else "None known.", ""]
    lines += ["## Left out of the sample, and why", ""]
    lines += [f"- {x}" for x in manifest.get("left_out", [])] + [""]
    return "\n".join(lines)


def score_human(csv_path: Path, directory: Path, criterion: dict) -> str:
    """The same engine on a person's own labelled sample: a CSV with file,label[,criticality]."""
    per = {}
    with csv_path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            code = (directory / row["file"]).read_text(encoding="utf-8", errors="replace")
            entry = {"expected": []}
            r = score_one(code, "", entry)
            r.update({"language": r["detected"], "source": "human", "label": row["label"].strip().lower(),
                      "criticality": (row.get("criticality") or "medium").strip().lower() if row["label"].strip().lower() == "dangerous" else "none",
                      "post_run": False, "category": None})
            per[row["file"]] = r
    lines = ["# Human-labelled sample", ""]
    for lang, s in sorted(language_stats(per).items()):
        gate = safe_gate.evaluate_gates(s, criterion)
        lines.append(f"- {lang}: {s['dangerous']} dangerous, {s['safe']} safe, false-SAFE {s['false_safe']}, "
                     f"critical false-SAFE {s['critical_false_safe']}, upper bound {gate['false_safe_upper_95']:.1%}; {gate['why']}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    criterion = load_criterion()
    if "--human" in argv:
        i = argv.index("--human")
        directory = Path(argv[argv.index("--dir") + 1]) if "--dir" in argv else Path(".")
        print(score_human(Path(argv[i + 1]), directory, criterion))
        return 0
    manifest = load_manifest()
    results = run(manifest)
    text = render(results, manifest, criterion)
    print(text)
    if "--write" in argv:
        (HERE / "RESULTS.md").write_text(text, encoding="utf-8", newline="\n")
        recorded = {"criterion_sha256": file_sha(HERE / "criterion.json"), "frozen_ids_sha256": frozen_ids_hash(manifest),
                    "examples": len(manifest["examples"]), "per_example": ratchet_view(results)}
        (HERE / "RESULTS.json").write_text(json.dumps(recorded, ensure_ascii=False, indent=1) + "\n",
                                           encoding="utf-8", newline="\n")
        quality = quality_from(results, criterion, manifest)
        QUALITY_OUT.write_text(json.dumps(quality, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print("written: RESULTS.md, RESULTS.json, src/tools/quality.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))