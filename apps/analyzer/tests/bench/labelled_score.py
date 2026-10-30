# -*- coding: utf-8 -*-
"""Labelled benchmark for the analyzer's built-in rules: no model, no network, no key.

    python -m tests.bench.labelled_score            # print the tables
    python -m tests.bench.labelled_score --write    # also write labelled/RESULTS.md and RESULTS.json

What it measures: ``src.tools.static_scan.scan_material`` - the rule engine - on examples in
``labelled/``, each labelled dangerous or safe, with the expected findings (CWE + line) and the
reason for the label written down in ``labelled/manifest.json``.

What it does NOT measure: the hub's verdicts with a model. There the model proposes and the rules
decide, and none of that runs here. A good number in this file says what the rules do alone; it
says nothing about the quality of a hub run that used a model.

Two modes, because the two ways in differ:
  named   the file name is given (an upload): language comes from the extension
  pasted  no file name (what the hub does with pasted code): language is sniffed from the text

Verdict. The hub calls a run SAFE when the rules found nothing at all, so that is what SAFE means
here too. The release blocker: no example labelled critical may get SAFE, in either mode.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
CORPUS = HERE / "labelled"
MODES = ("named", "pasted")
CRITICALITIES = ("critical", "high", "medium", "low")
SEVERITIES = ("critical", "high", "medium", "low")


def load_manifest() -> dict:
    return json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))


def _scan(code: str, filename: str) -> tuple[dict, float]:
    from src.tools.static_scan import scan_material

    best, result = None, {}
    for _ in range(3):                      # the fastest of three: timing noise is not the rules' fault
        start = time.perf_counter()
        result = scan_material(code, filename)
        elapsed = (time.perf_counter() - start) * 1000
        best = elapsed if best is None else min(best, elapsed)
    return result, best or 0.0


def _hit(finding: dict, expected: dict) -> bool:
    return finding.get("cwe") == expected["cwe"] and (expected["line"] == 0 or finding.get("line") == expected["line"])


def run(manifest: dict | None = None) -> dict:
    """results[mode][example id] -> what the engine did with that example."""
    manifest = manifest or load_manifest()
    results: dict = {mode: {} for mode in MODES}
    for ex in manifest["examples"]:
        path = CORPUS / ex["file"]
        code = path.read_text(encoding="utf-8")
        for mode in MODES:
            scan, ms = _scan(code, path.name if mode == "named" else "")
            findings = scan.get("findings") or []
            sev = {s: 0 for s in SEVERITIES}
            for f in findings:
                sev[f.get("severity", "low")] = sev.get(f.get("severity", "low"), 0) + 1
            hits = sum(1 for e in ex["expected"] if any(_hit(f, e) for f in findings))
            same_class = sum(1 for e in ex["expected"] if any(f.get("cwe") == e["cwe"] for f in findings))
            unexpected = sum(1 for f in findings if not any(_hit(f, e) for e in ex["expected"]))
            results[mode][ex["id"]] = {
                "language": ex["language"], "label": ex["label"], "criticality": ex["criticality"],
                "rules_written_after": bool(ex.get("rules_written_after")),
                "detected_language": scan.get("language", ""),
                "findings": len(findings), "by_severity": sev,
                "expected": len(ex["expected"]), "hits": hits, "same_class": same_class,
                "unexpected": unexpected, "safe_verdict": len(findings) == 0, "ms": round(ms, 3),
                "found": [{"id": f.get("id"), "cwe": f.get("cwe"), "severity": f.get("severity"), "line": f.get("line")}
                          for f in findings],
            }
    return results


def blockers(results: dict) -> list[str]:
    """Examples labelled critical that the engine called SAFE. Any entry blocks the release."""
    return [f"{mode}: {ex_id} ({r['language']})"
            for mode, per in results.items() for ex_id, r in per.items()
            if r["label"] == "dangerous" and r["criticality"] == "critical" and r["safe_verdict"]]


def summarise(results: dict) -> dict:
    out: dict = {}
    for mode, per in results.items():
        langs = sorted({r["language"] for r in per.values()})
        dangerous, safe, detect, timing = [], [], [], []
        for lang in langs:
            rows = [r for r in per.values() if r["language"] == lang]
            for crit in CRITICALITIES:
                sel = [r for r in rows if r["label"] == "dangerous" and r["criticality"] == crit]
                if sel:
                    dangerous.append({
                        "language": lang, "criticality": crit, "examples": len(sel),
                        "found": sum(1 for r in sel if r["hits"] > 0),
                        "expected_findings": sum(r["expected"] for r in sel),
                        "hit_findings": sum(r["hits"] for r in sel),
                        "wrong_line_only": sum(r["same_class"] - r["hits"] for r in sel),
                        "safe_verdicts": sum(1 for r in sel if r["safe_verdict"]),
                    })
            sel = [r for r in rows if r["label"] == "safe"]
            if sel:
                fp = {s: sum(r["by_severity"].get(s, 0) for r in sel) for s in SEVERITIES}
                safe.append({"language": lang, "examples": len(sel),
                             "with_findings": sum(1 for r in sel if r["findings"]),
                             "fp_findings": sum(r["findings"] for r in sel), "fp_by_severity": fp})
            detect.append({"language": lang, "examples": len(rows),
                           "language_detected": sum(1 for r in rows if r["detected_language"] == lang)})
            ms = [r["ms"] for r in rows]
            timing.append({"language": lang, "median_ms": round(statistics.median(ms), 2), "max_ms": round(max(ms), 2)})
        out[mode] = {"dangerous": dangerous, "safe": safe, "language_detection": detect, "timing": timing}
    return out


def ratchet_view(results: dict) -> dict:
    """What is recorded in RESULTS.json and compared later: outcomes, never timings."""
    return {mode: {ex_id: {"hits": r["hits"], "expected": r["expected"], "findings": r["findings"],
                           "safe_verdict": r["safe_verdict"]} for ex_id, r in per.items()}
            for mode, per in results.items()}


def regressions(current: dict, recorded: dict) -> list[str]:
    """Outcomes that got worse than the recorded ones. Improvements are not regressions."""
    bad = []
    for mode, per in recorded.items():
        for ex_id, old in per.items():
            new = current.get(mode, {}).get(ex_id)
            if new is None:
                bad.append(f"{mode}: {ex_id} is recorded but no longer in the corpus")
            elif new["hits"] < old["hits"]:
                bad.append(f"{mode}: {ex_id} lost expected findings ({old['hits']} -> {new['hits']})")
            elif old["expected"] == 0 and new["findings"] > old["findings"]:
                bad.append(f"{mode}: {ex_id} (safe) gained false positives ({old['findings']} -> {new['findings']})")
            elif old["expected"] and old["safe_verdict"] is False and new["safe_verdict"]:
                bad.append(f"{mode}: {ex_id} became SAFE")
    return bad


def before_after(results: dict, manifest: dict) -> list[str]:
    """Compare with labelled/RESULTS.before-rules.json: the first run, before the PHP and Go rules were written."""
    path = CORPUS / "RESULTS.before-rules.json"
    if not path.exists():
        return []
    before = json.loads(path.read_text(encoding="utf-8"))["per_example"]
    meta = {e["id"]: e for e in manifest["examples"]}

    def numbers(per: dict) -> dict:
        dangerous = [(i, r) for i, r in per.items() if i in meta and meta[i]["label"] == "dangerous"]
        safe = [(i, r) for i, r in per.items() if i in meta and meta[i]["label"] == "safe"]
        crit = [r for i, r in dangerous if meta[i]["criticality"] == "critical"]
        return {"hit": sum(r["hits"] for _, r in dangerous), "exp": sum(r["expected"] for _, r in dangerous),
                "crit_safe": sum(1 for r in crit if r["safe_verdict"]), "crit": len(crit),
                "fp_examples": sum(1 for _, r in safe if r["findings"]), "safe": len(safe),
                "fp_findings": sum(r["findings"] for _, r in safe)}

    lines = ["## Before and after the PHP and Go rules", "",
             "`RESULTS.before-rules.md` / `.json` are the first run, kept as they were. Three critical examples got SAFE "
             "then; rules for PHP shell calls, PHP `eval` and Go `sh -c` were written for them, and a fourth safe example "
             "was added to show the same-line escape the PHP rule can see. The examples marked `rules_written_after` "
             "therefore guard against regression and are not independent evidence of recall.", "",
             "| mode | measure | before | after |", "|---|---|---:|---:|"]
    for mode in MODES:
        a, b = numbers(before.get(mode, {})), numbers(ratchet_view(results)[mode])
        lines += [f"| {mode} | recall (expected findings hit) | {_pct(a['hit'], a['exp'])} ({a['hit']}/{a['exp']}) | "
                  f"{_pct(b['hit'], b['exp'])} ({b['hit']}/{b['exp']}) |",
                  f"| {mode} | critical examples that got SAFE | {a['crit_safe']} of {a['crit']} | {b['crit_safe']} of {b['crit']} |",
                  f"| {mode} | safe examples flagged (false positives) | {a['fp_examples']} of {a['safe']} | {b['fp_examples']} of {b['safe']} |"]
    lines += ["", "The one new false positive is `php-safe-json-escapeshellarg`: the host is escaped on a line before the "
              "call, and a rule that reads one line at a time cannot see that. It is left in the set on purpose.", ""]
    return lines


def _pct(a: int, b: int) -> str:
    return "-" if not b else f"{100 * a / b:.0f}%"


def render(results: dict, manifest: dict) -> str:
    summary = summarise(results)
    n_danger = sum(1 for e in manifest["examples"] if e["label"] == "dangerous")
    n_safe = len(manifest["examples"]) - n_danger
    lines = [
        "# Labelled benchmark: the analyzer's rules alone",
        "",
        f"{len(manifest['examples'])} examples ({n_danger} dangerous, {n_safe} safe), "
        f"{len({e['language'] for e in manifest['examples']})} languages. Produced by "
        "`python -m tests.bench.labelled_score --write`; the examples, their expected findings and the reason for "
        "each label are in `manifest.json`.",
        "",
        "## What this does and does not measure",
        "",
        manifest["scope"],
        "",
        "**It does not measure the hub's verdicts with a model.** In the hub the model proposes and the rules "
        "decide, and none of that runs here: no model, no network, no key. The numbers below say what the rules "
        "do alone. They say nothing about the quality of a hub run that used a model, in either direction.",
        "",
        "SAFE means what it means in the hub: the rules found nothing at all. A finding on the wrong line, or of "
        "the wrong class, is a miss but not SAFE.",
        "",
        "**Release blocker:** no example labelled critical may get SAFE, in either mode "
        "(`tests/test_bench_labelled.py`).",
        "",
    ]
    block = blockers(results)
    lines += ["### Blocker status", "",
              ("**BLOCKED** - " + str(len(block)) + " critical example(s) got SAFE:" if block
               else "Clear: no critical example got SAFE in either mode.")]
    lines += [f"- {b}" for b in block] + [""]

    lines += before_after(results, manifest)
    for mode in MODES:
        s = summary[mode]
        lines += [f"## Mode `{mode}`" + (" (file name given, as an upload)" if mode == "named"
                                          else " (no file name, language sniffed - what the hub does with pasted code)"), ""]
        lines += ["### Dangerous examples, by language and criticality", "",
                  "| language | criticality | examples | found | recall (findings) | right class, wrong line | SAFE |",
                  "|---|---|---:|---:|---:|---:|---:|"]
        for r in s["dangerous"]:
            lines.append(f"| {r['language']} | {r['criticality']} | {r['examples']} | {r['found']} | "
                         f"{_pct(r['hit_findings'], r['expected_findings'])} ({r['hit_findings']}/{r['expected_findings']}) | "
                         f"{r['wrong_line_only']} | {r['safe_verdicts']} |")
        tot_exp = sum(r["expected_findings"] for r in s["dangerous"])
        tot_hit = sum(r["hit_findings"] for r in s["dangerous"])
        held = [r for r in results[mode].values() if r["label"] == "dangerous" and not r["rules_written_after"]]
        held_exp, held_hit = sum(r["expected"] for r in held), sum(r["hits"] for r in held)
        lines += ["", f"Overall recall: {_pct(tot_hit, tot_exp)} ({tot_hit}/{tot_exp} expected findings). "
                      f"Without the examples the rules were written for after the first run "
                      f"(`rules_written_after` in the manifest): {_pct(held_hit, held_exp)} ({held_hit}/{held_exp}).", ""]
        lines += ["### Safe examples: false positives", "",
                  "| language | examples | with findings | findings | critical | high | medium | low |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for r in s["safe"]:
            fp = r["fp_by_severity"]
            lines.append(f"| {r['language']} | {r['examples']} | {r['with_findings']} | {r['fp_findings']} | "
                         f"{fp['critical']} | {fp['high']} | {fp['medium']} | {fp['low']} |")
        lines += ["", "### Language detection and time", "",
                  "| language | examples | language detected | median ms | max ms |", "|---|---:|---:|---:|---:|"]
        for d, tm in zip(s["language_detection"], s["timing"]):
            lines.append(f"| {d['language']} | {d['examples']} | {d['language_detected']}/{d['examples']} | "
                         f"{tm['median_ms']} | {tm['max_ms']} |")
        lines.append("")
        misses = [(i, r) for i, r in results[mode].items() if r["label"] == "dangerous" and r["hits"] < r["expected"]]
        lines += [f"### Misses in mode `{mode}` ({len(misses)} examples with an expected finding not hit)", ""]
        for i, r in sorted(misses, key=lambda x: (CRITICALITIES.index(x[1]["criticality"]), x[0])):
            how = "SAFE" if r["safe_verdict"] else f"{r['findings']} other finding(s)"
            lines.append(f"- `{i}` ({r['language']}, {r['criticality']}): {r['hits']}/{r['expected']} hit, {how}")
        fps = [(i, r) for i, r in results[mode].items() if r["label"] == "safe" and r["findings"]]
        lines += ["", f"### False positives in mode `{mode}` ({len(fps)} safe examples flagged)", ""]
        for i, r in fps:
            lines.append(f"- `{i}`: " + ", ".join(f"{f['id']} line {f['line']} ({f['severity']})" for f in r["found"]))
        lines.append("")
    lines += ["Timings are the fastest of three runs on whatever machine produced this file; they are not "
              "compared between runs. Everything else in this file is deterministic.", ""]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    manifest = load_manifest()
    results = run(manifest)
    text = render(results, manifest)
    print(text)
    if "--write" in argv:
        (CORPUS / "RESULTS.md").write_text(text, encoding="utf-8", newline="\n")
        recorded = {"examples": len(manifest["examples"]), "summary_counts": {
            mode: {"dangerous": s["dangerous"], "safe": s["safe"]} for mode, s in summarise(results).items()},
            "per_example": ratchet_view(results)}
        (CORPUS / "RESULTS.json").write_text(json.dumps(recorded, ensure_ascii=False, indent=1) + "\n",
                                             encoding="utf-8", newline="\n")
        print("written: labelled/RESULTS.md, labelled/RESULTS.json", file=sys.stderr)
    return 1 if blockers(results) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
