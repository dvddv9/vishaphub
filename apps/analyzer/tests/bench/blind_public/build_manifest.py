# -*- coding: utf-8 -*-
"""Build the blind set's manifest from the sources' own labels. Run once; the output is committed and frozen.

    python -m tests.bench.blind_public.build_manifest

It follows SAMPLING.md to the letter: it downloads the pinned files, takes their labels from the sources'
own ground truth, hashes the files, and writes manifest.json and frozen_ids.sha256. It never runs the rules
on anything - the rules are not imported here - so nothing it does can depend on how they score.
"""
from __future__ import annotations

import ast
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
RAW = "https://raw.githubusercontent.com/{repo}/{sha}/{path}"

BENCHMARK_CRITICALITY = {"sqli": "critical", "cmdi": "critical", "pathtraver": "high", "xss": "high", "ldapi": "high",
                         "xpathi": "high", "trustbound": "high", "hash": "medium", "crypto": "medium",
                         "weakrand": "medium", "securecookie": "medium"}
DVWA_CRITICALITY = {"sqli": "critical", "sqli_blind": "critical", "exec": "critical", "fi": "critical",
                    "upload": "critical", "xss_r": "high", "xss_s": "high", "xss_d": "high", "csrf": "high",
                    "authbypass": "high", "open_redirect": "high"}
PER_SIDE = 12


def pins() -> dict:
    return json.loads((CACHE / "pins.json").read_text(encoding="utf-8"))


def fetch(source: str, path: str, required: bool = True) -> bytes | None:
    pin = pins()[source]
    cached = CACHE / source / path
    if cached.exists():
        return cached.read_bytes()
    url = RAW.format(repo=pin["repo"], sha=pin["sha"], path=path)
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "vishaphub-bench"})
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(data)
            return data
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and not required:
                return None
            if exc.code != 404 and attempt < 3:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))
    return None


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def entry(source, ident, path, language, label, criticality, expected, data) -> dict:
    pin = pins()[source]
    return {"id": f"{source}:{ident}", "source": source, "language": language, "label": label,
            "criticality": criticality, "expected": expected, "path": path,
            "url": RAW.format(repo=pin["repo"], sha=pin["sha"], path=path),
            "sha256": sha(data), "bytes": len(data), "post_run": False}


def benchmark() -> list[dict]:
    csv = fetch("benchmark", "expectedresults-1.2.csv").decode("utf-8")
    rows = {}
    for line in csv.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 4 and parts[0].startswith("BenchmarkTest"):
            rows[parts[0]] = (parts[1], parts[2].lower() == "true", parts[3])
    out = []
    for category in sorted({c for c, _, _ in rows.values()}):
        for real in (True, False):
            names = sorted((n for n, (c, r, _) in rows.items() if c == category and r == real),
                           key=lambda n: hashlib.sha256(n.encode()).hexdigest())[:PER_SIDE]
            for name in names:
                path = f"src/main/java/org/owasp/benchmark/testcode/{name}.java"
                data = fetch("benchmark", path)
                if real:
                    out.append(entry("benchmark", name, path, "java", "dangerous", BENCHMARK_CRITICALITY[category],
                                     [{"category": category, "cwe": f"CWE-{rows[name][2]}",
                                       "why": "expectedresults-1.2.csv: real vulnerability = true"}], data))
                else:
                    out.append(entry("benchmark", name, path, "java", "safe", "none", [], data))
    return out


def dvwa() -> list[dict]:
    api = (f"https://api.github.com/repos/{pins()['dvwa']['repo']}/contents/vulnerabilities"
           f"?ref={pins()['dvwa']['sha']}")
    listing = json.loads(urllib.request.urlopen(
        urllib.request.Request(api, headers={"User-Agent": "vishaphub-bench"}), timeout=60).read())
    out = []
    for item in sorted(listing, key=lambda i: i["name"]):
        if item["type"] != "dir" or item["name"].startswith("view_"):
            continue
        name = item["name"]
        for level, label in (("low", "dangerous"), ("medium", "dangerous"), ("impossible", "safe")):
            path = f"vulnerabilities/{name}/source/{level}.php"
            data = fetch("dvwa", path, required=False)
            if data is None:
                continue
            if label == "dangerous":
                out.append(entry("dvwa", f"{name}/{level}", path, "php", label, DVWA_CRITICALITY.get(name, "medium"),
                                 [{"category": name, "why": f"DVWA design: {level}.php is a vulnerable level"}], data))
            else:
                out.append(entry("dvwa", f"{name}/{level}", path, "php", label, "none", [], data))
    return out


def bandit() -> tuple[list[dict], list[dict]]:
    tree = ast.parse(fetch("bandit", "tests/functional/test_functional.py").decode("utf-8"))
    out, left_out, seen = [], [], set()
    for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")):
        expect = None
        for stmt in fn.body:
            for node in ast.walk(stmt):
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "expect" for t in node.targets):
                    try:
                        expect = ast.literal_eval(node.value)
                    except ValueError:
                        expect = None
                is_call = (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                           and node.func.attr == "check_example" and node.args)
                if not is_call:
                    continue
                first = node.args[0]
                if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                    left_out.append({"test": fn.name, "reason": "example file name is not a literal"})
                    continue
                if not isinstance(expect, dict) or "SEVERITY" not in expect:
                    left_out.append({"file": first.value, "reason": "expectation is not a literal dict"})
                    continue
                name = first.value
                if name in seen:
                    left_out.append({"file": name, "reason": "checked more than once: first expectation kept"})
                    continue
                seen.add(name)
                data = fetch("bandit", f"examples/{name}", required=False)
                if data is None:
                    left_out.append({"file": name, "reason": "no such file in examples/ at the pinned commit"})
                    continue
                sev = expect["SEVERITY"]
                total = sum(sev.get(k, 0) for k in ("UNDEFINED", "LOW", "MEDIUM", "HIGH"))
                if total == 0:
                    out.append(entry("bandit", name, f"examples/{name}", "python", "safe", "none", [], data))
                else:
                    crit = "critical" if sev.get("HIGH") else "high" if sev.get("MEDIUM") else "medium"
                    why = f"test_functional.py expects {total} issue(s): {sev}"
                    out.append(entry("bandit", name, f"examples/{name}", "python", "dangerous", crit,
                                     [{"category": "bandit-expected", "why": why}], data))
    return out, left_out


def main() -> None:
    examples = benchmark() + dvwa()
    bandit_examples, left_out = bandit()
    examples += bandit_examples
    ids = [e["id"] for e in examples]
    assert len(ids) == len(set(ids)), "duplicate ids"
    manifest = {"version": 1, "sources": pins(), "left_out": left_out, "examples": examples}
    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n",
                                        encoding="utf-8", newline="\n")
    (HERE / "frozen_ids.sha256").write_text(hashlib.sha256(("\n".join(sorted(ids)) + "\n").encode()).hexdigest() + "\n",
                                           encoding="utf-8", newline="\n")
    counts = {}
    for e in examples:
        counts[(e["language"], e["label"])] = counts.get((e["language"], e["label"]), 0) + 1
    print("examples:", len(examples), "| left out:", len(left_out))
    for key, value in sorted(counts.items()):
        print(" ", key, value)


if __name__ == "__main__":
    main()