"""Compare local rules, Semgrep, and CodeQL SARIF against the same labelled corpus.

Example:
  python -m tests.bench.compare_sarif --sarif semgrep=semgrep.sarif \
    --covered semgrep=python,javascript,typescript,java,go,php,c,cpp

Run each external engine against ``tests/bench/labelled``. For CodeQL, pass one SARIF
per database/language (for example ``codeql-java=java.sarif``) and state that language
in ``--covered``. Results outside the corpus are ignored; unreported expected findings
inside a declared language are false negatives. No engine is installed or invoked here.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlparse

HERE = Path(__file__).parent
CORPUS = HERE / "labelled"
_CWE = re.compile(r"(?i)\bcwe[-_/ ]?0*(\d{1,5})\b")


def _normal_path(value: str) -> str:
    value = unquote(value or "").replace("\\", "/")
    parsed = urlparse(value)
    if parsed.scheme == "file":
        value = parsed.path.lstrip("/") if not re.match(r"^/[A-Za-z]:", parsed.path) else parsed.path[1:]
    value = value.lower().lstrip("./")
    marker = "/labelled/"
    if marker in value:
        value = value.rsplit(marker, 1)[1]
    return value


def _corpus_file(uri: str, expected_files: set[str]) -> str | None:
    path = _normal_path(uri)
    matches = [name for name in expected_files if path == name.lower() or path.endswith("/" + name.lower())]
    return max(matches, key=len) if matches else None


def _sarif_rules(run: dict) -> dict[int, dict]:
    return {i: rule for i, rule in enumerate((run.get("tool", {}).get("driver", {}).get("rules") or []))}


def _cwes(result: dict, rules: dict[int, dict]) -> set[str]:
    rule = result.get("rule") if isinstance(result.get("rule"), dict) else {}
    if not rule and isinstance(result.get("ruleIndex"), int):
        rule = rules.get(result["ruleIndex"], {})
    values: list[str] = [str(result.get("ruleId") or "")]
    for obj in (result, rule):
        values.extend(str(v) for v in (obj.get("properties", {}).get("tags") or []))
        values.extend(str(v) for v in (obj.get("relationships") or []))
    found: set[str] = set()
    for value in values:
        for match in _CWE.finditer(value):
            found.add(f"CWE-{int(match.group(1))}")
    # Common query/rule identifiers use stable vulnerability names but omit CWE tags.
    if not found:
        names = " ".join(values).lower()
        aliases = (("sqli", "CWE-89"), ("sql-injection", "CWE-89"), ("xss", "CWE-79"),
                   ("cmdi", "CWE-78"), ("command-injection", "CWE-78"), ("path-traversal", "CWE-22"),
                   ("pathtraversal", "CWE-22"), ("hardcoded-credential", "CWE-798"),
                   ("hard-coded-credential", "CWE-798"), ("deserial", "CWE-502"),
                   ("ssrf", "CWE-918"), ("xxe", "CWE-611"), ("weak-hash", "CWE-327"))
        found.update(cwe for token, cwe in aliases if token in names)
    return found


def load_manifest() -> dict:
    return json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))


def local_detections(manifest: dict, mode: str = "named") -> list[dict]:
    from src.tools.static_scan import scan_material

    out = []
    for example in manifest["examples"]:
        path = CORPUS / example["file"]
        scan = scan_material(path.read_text(encoding="utf-8"), path.name if mode == "named" else "")
        out.extend({"file": example["file"], "line": int(f.get("line") or 0), "cwes": {str(f.get("cwe") or "")},
                    "severity": f.get("severity", ""), "rule": f.get("id", "")}
                   for f in scan.get("findings") or [])
    return out


def sarif_detections(path: Path, expected_files: set[str]) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for run in data.get("runs") or []:
        rules = _sarif_rules(run)
        for result in run.get("results") or []:
            locations = result.get("locations") or []
            if not locations:
                continue
            physical = (locations[0].get("physicalLocation") or {})
            artifact = physical.get("artifactLocation") or {}
            file = _corpus_file(str(artifact.get("uri") or ""), expected_files)
            if not file:
                continue
            region = physical.get("region") or {}
            out.append({"file": file, "line": int(region.get("startLine") or 0),
                        "cwes": _cwes(result, rules), "severity": result.get("level", ""),
                        "rule": result.get("ruleId", "")})
    return out


def score(manifest: dict, detections: list[dict], covered: set[str] | None = None) -> dict:
    expected_files = {ex["file"] for ex in manifest["examples"]}
    language_by_file = {ex["file"]: ex["language"] for ex in manifest["examples"]}
    examples = {ex["file"]: ex for ex in manifest["examples"]
                if covered is None or ex["language"] in covered}
    by_file: dict[str, list[dict]] = defaultdict(list)
    for item in detections:
        if item.get("file") in examples:
            by_file[item["file"]].append(item)

    tp = fp = expected_count = safe_files = safe_false_positive_files = 0
    language_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "expected": 0, "safe": 0, "safe_fp": 0})
    for file, example in examples.items():
        lang = language_by_file[file]
        rows = by_file[file]
        expected = example.get("expected") or []
        expected_count += len(expected)
        language_stats[lang]["expected"] += len(expected)
        if example.get("label") == "safe":
            safe_files += 1
            language_stats[lang]["safe"] += 1
        unmatched = list(rows)
        hit_count = 0
        for exp in expected:
            cwe = str(exp.get("cwe") or "")
            line = int(exp.get("line") or 0)
            hit = next((idx for idx, det in enumerate(unmatched)
                        if cwe and cwe in (det.get("cwes") or set())
                        and (line == 0 or not det.get("line") or line == int(det["line"]))), None)
            if hit is not None:
                unmatched.pop(hit)
                hit_count += 1
        file_fp = len(unmatched)
        tp += hit_count
        fp += file_fp
        language_stats[lang]["tp"] += hit_count
        language_stats[lang]["fp"] += file_fp
        if example.get("label") == "safe" and rows:
            safe_false_positive_files += 1
            language_stats[lang]["safe_fp"] += 1

    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / expected_count if expected_count else 1.0
    return {"examples": len(examples), "covered_languages": sorted(covered) if covered is not None else sorted(set(language_by_file.values())),
            "expected_findings": expected_count, "true_positives": tp, "false_positives": fp,
            "false_negatives": expected_count - tp, "precision": round(precision, 4), "recall": round(recall, 4),
            "safe_examples": safe_files, "safe_examples_with_findings": safe_false_positive_files,
            "safe_false_positive_rate": round(safe_false_positive_files / safe_files, 4) if safe_files else None,
            "per_language": {lang: {**stats,
                                    "precision": round(stats["tp"] / (stats["tp"] + stats["fp"]), 4)
                                    if stats["tp"] + stats["fp"] else 1.0,
                                    "recall": round(stats["tp"] / stats["expected"], 4)
                                    if stats["expected"] else None}
                             for lang, stats in sorted(language_stats.items())}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sarif", action="append", default=[], metavar="ENGINE=FILE",
                        help="SARIF export from Semgrep or CodeQL; repeat for each engine/language")
    parser.add_argument("--covered", action="append", default=[], metavar="ENGINE=LANG1,LANG2",
                        help="Languages that engine actually analyzed; required for every --sarif")
    parser.add_argument("--mode", choices=("named", "pasted"), default="named")
    parser.add_argument("--json", dest="output", help="Write machine-readable results to this file")
    args = parser.parse_args()
    manifest = load_manifest()
    expected_files = {ex["file"] for ex in manifest["examples"]}
    results = {"corpus": "labelled-106", "mode": args.mode,
               "vishap": score(manifest, local_detections(manifest, args.mode))}
    coverage = {}
    for item in args.covered:
        engine, sep, values = item.partition("=")
        if not sep or not engine or not values:
            parser.error(f"invalid --covered value: {item!r}")
        coverage[engine] = {x.strip().lower() for x in values.split(",") if x.strip()}
    for item in args.sarif:
        engine, sep, filename = item.partition("=")
        if not sep or not engine or not filename or engine not in coverage:
            parser.error(f"each --sarif needs an engine=path and a matching --covered engine=languages: {item!r}")
        results[engine] = score(manifest, sarif_detections(Path(filename), expected_files), coverage[engine])
    rendered = json.dumps(results, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
