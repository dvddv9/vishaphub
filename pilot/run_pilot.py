"""The closed pilot: what the rules, the exploit probes and the patch check really do, counted.

    python pilot/run_pilot.py --image vishap-validator:worker --samples /path/to/samples --out pilot/results.json

No model is called and no data leaves this machine: the rules run in-process, everything that executes code
runs in worker containers (`docker run --network none --read-only ...`), and the code it executes is the
synthetic corpus in `pilot/cases.py`, our own. The samples that are not ours are only read by the rules,
never executed.

Phases
  A. the rules on the labelled samples (read, never run): findings, label hits within 2 lines, misses
  B. the rules on the synthetic corpus: detection of vulnerable forms, flags on their safe twins
  C. the exploit probes on the corpus, in containers: do they agree with the truth by construction?
  D. the patch check on scripted patches, in containers: does each get the status it should?
  E. determinism: the same scenarios again; the deterministic part must be byte-identical

Expectations for phase D are written down in this file BEFORE the run. A scenario whose status differs is a
"surprise". A documented limit that the pilot confirms is not.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("", "apps/hub/src", "packages/core/src", "apps/validator/src", "apps/analyzer"):
    path = os.path.join(ROOT, sub) if sub else ROOT
    if path not in sys.path:
        sys.path.insert(0, path)

from hub import exploits as hub_exploits
from hub import local, patchcheck

from pilot import cases as C

TOLERANCE = 2          # a finding within this many lines of a label counts as a hit, as in the comparison
V, P, R, U = "FIX_VERIFIED", "FIX_PARTIAL", "FIX_REJECTED", "FIX_UNVERIFIED"

GUTTED = {"sqli": "def find(cur, name):\n    return []\n",
          "path_traversal": "def read(base, name):\n    return \"\"\n",
          "command_injection": "def echo(text):\n    return None\n"}


def say(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


def sha(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def strip_ms(obj):
    if isinstance(obj, dict):
        return {k: strip_ms(v) for k, v in obj.items() if k != "ms"}
    if isinstance(obj, list):
        return [strip_ms(v) for v in obj]
    return obj


# --- A: the labelled samples --------------------------------------------------------------------------

def phase_samples(samples_dir: str, truth_path: str) -> list[dict]:
    with open(truth_path, encoding="utf-8-sig") as fh:
        truth = json.load(fh)
    out = []
    for name in sorted(os.listdir(samples_dir)):
        if not name.endswith(".py") or name.startswith("injection"):
            continue
        with open(os.path.join(samples_dir, name), encoding="utf-8-sig") as fh:
            text = fh.read()
        t0 = time.perf_counter()
        res = local.analyse_static(text)
        ms = round((time.perf_counter() - t0) * 1000, 1)
        findings = res.get("findings") or []
        base = name.split("_", 1)[1]                               # 01_shop_service.py -> shop_service.py
        bugs = [b for b in truth["bugs"] if b.get("file") == base]
        hit, miss = [], []
        for b in bugs:
            near = any(abs((f.get("line") or -99) - line) <= TOLERANCE for f in findings for line in b["lines"])
            (hit if near else miss).append(b["id"])
        label_lines = [line for b in bugs for line in b["lines"]]
        unmatched = [f for f in findings if not any(abs((f.get("line") or -99) - line) <= TOLERANCE
                                                    for line in label_lines)] if bugs else []
        rules: dict = {}
        for f in findings:
            rules[f["rule"]] = rules.get(f["rule"], 0) + 1
        out.append({"sample": name, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "ok": bool(res.get("ok")),
                    "verdict": res.get("verdict"), "findings": len(findings), "rules": dict(sorted(rules.items())),
                    "labelled": bool(bugs), "labels": len(bugs), "hits": len(hit), "missed": miss,
                    "unmatched_findings": len(unmatched) if bugs else None, "ms": ms})
    return out


# --- B: the rules on the corpus -----------------------------------------------------------------------

def _flags(case: dict, findings: list) -> list[str]:
    """Rules that point at the case's attack class (a generic taint-flow counts for path traversal)."""
    kind = case["class"]
    hits = []
    for f in findings:
        cls = hub_exploits.class_of(f.get("rule", ""), f.get("cwe"))
        if cls == kind or (kind == "path_traversal" and f.get("rule") == "taint-flow"):
            hits.append(f["rule"])
    return sorted(set(hits))


def phase_corpus_rules() -> list[dict]:
    rows = []
    for case in C.CASES:
        t0 = time.perf_counter()
        res = local.analyse_static(case["app"])
        ms = round((time.perf_counter() - t0) * 1000, 1)
        flagged = _flags(case, res.get("findings") or [])
        rows.append({"case": case["id"], "class": case["class"], "vulnerable": case["vulnerable"],
                     "flagged_by": flagged, "all_rules": sorted({f["rule"] for f in res.get("findings") or []}),
                     "outcome": ("TP" if flagged else "FN") if case["vulnerable"] else ("FP" if flagged else "TN"),
                     "ms": ms})
    return rows


# --- C: the probes in containers ------------------------------------------------------------------------

def phase_probes(failures: list) -> list[dict]:
    rows = []
    for case in C.CASES:
        t0 = time.perf_counter()
        res = local.run_exploits(C.files_of(case), [C.TARGETS[case["class"]]])
        ms = round((time.perf_counter() - t0) * 1000, 1)
        if not res.get("ok"):
            failures.append({"phase": "probes", "case": case["id"], "error": res.get("error")})
            rows.append({"case": case["id"], "truth_vulnerable": case["vulnerable"], "result": "sandbox-error",
                         "agrees": None, "error": res.get("error"), "ms": ms})
            continue
        got = res["exploits"][0]["result"]
        iso = res.get("isolation") or {}
        if iso.get("cleanup_confirmed") is not True:
            failures.append({"phase": "probes", "case": case["id"], "error": "cleanup not confirmed"})
        rows.append({"case": case["id"], "truth_vulnerable": case["vulnerable"], "result": got,
                     "agrees": (got == "reproduced") == case["vulnerable"] and got in ("reproduced", "not_reproduced"),
                     "cleanup_confirmed": iso.get("cleanup_confirmed"), "ms": ms})
    return rows


# --- D: scripted patches ----------------------------------------------------------------------------------

def scenarios() -> list[dict]:
    """(case, kind, patch, spec target?, expected status, note) - written down before anything runs."""
    out = []
    vulnerable = [c for c in C.CASES if c["vulnerable"]]
    first = {}
    for c in vulnerable:
        first.setdefault(c["class"], c["id"])
    for c in vulnerable:
        fix = C.by_id(C.FIX_WITH[c["class"]])["app"]
        out.append({"case": c["id"], "kind": "fix", "patch": {"app.py": fix}, "target": True, "expect": V,
                    "note": "the proper fix: the safe twin's code"})
        out.append({"case": c["id"], "kind": "cosmetic", "patch": {"app.py": c["app"] + "# reviewed\n"},
                    "target": True, "expect": R, "note": "a comment only: the attack still works"})
        if first[c["class"]] != c["id"]:
            continue
        out.append({"case": c["id"], "kind": "delete-function", "patch": {"app.py": "X = 1\n"}, "target": True,
                    "expect": R, "note": "the finding goes away with the code; the contract and tests fail"})
        out.append({"case": c["id"], "kind": "delete-test", "patch": {"test_app.py": None, "app.py": fix},
                    "target": True, "expect": R, "note": "a test is a trusted check"})
        out.append({"case": c["id"], "kind": "fix-without-exploit-test", "patch": {"app.py": fix}, "target": False,
                    "expect": P, "note": "fixed, but nothing proves the attack was ever there"})
        out.append({"case": c["id"], "kind": "gut-function", "patch": {"app.py": GUTTED[c["class"]]}, "target": True,
                    "expect": V if c["class"] == "command_injection" else R,
                    "note": ("KNOWN LIMIT: this case's own test asserts nothing, so a function that does nothing "
                             "passes it") if c["class"] == "command_injection" else "the case's test asserts the result"})
    pluseq = C.by_id("sqli-pluseq")["app"]
    out.append({"case": "sqli-concat", "kind": "rewrite-the-rules-cannot-see", "patch": {"app.py": pluseq},
                "target": True, "expect": R, "note": "same injection built with +=: the rules go quiet, the probe does not"})
    return out


def phase_scenarios(failures: list, only: set | None = None) -> list[dict]:
    rows = []
    plan = scenarios()
    for i, s in enumerate(plan, 1):
        if only is not None and (s["case"], s["kind"]) not in only:
            continue
        case = C.by_id(s["case"])
        snapshot = C.files_of(case)
        spec = C.spec_of(case, with_target=s["target"])
        t0 = time.perf_counter()
        try:
            res = patchcheck.check(snapshot, files=s["patch"], spec=spec)
        except Exception as exc:  # noqa: BLE001 - a crash is a result, not a reason to stop the pilot
            res = {"status": "CRASH", "reason": f"{type(exc).__name__}: {exc}"}
        ms = round((time.perf_counter() - t0) * 1000, 1)
        iso = ((res.get("validator") or {}).get("isolation")) or {}
        if res["status"] == U or res["status"] == "CRASH" or (iso and iso.get("cleanup_confirmed") is not True):
            failures.append({"phase": "scenarios", "case": s["case"], "kind": s["kind"], "status": res["status"],
                             "reason": res.get("reason")})
        rows.append({"case": s["case"], "kind": s["kind"], "expected": s["expect"], "note": s["note"],
                     "actual": res["status"], "match": res["status"] == s["expect"], "reason": res.get("reason"),
                     "rules": {k: (res.get("rules") or {}).get(k) for k in ("before", "after")},
                     "exploit": [(r.get("class"), r.get("before"), r.get("after")) for r in res.get("exploit") or []],
                     "isolation": iso.get("kind"), "cleanup_confirmed": iso.get("cleanup_confirmed"), "ms": ms})
        say(f"  [{i}/{len(plan)}] {s['case']} / {s['kind']}: {res['status']}" + ("" if res["status"] == s["expect"] else f"  (expected {s['expect']})"))
    return rows


# --- the run -------------------------------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default="vishap-validator:worker")
    ap.add_argument("--samples", default="", help="directory with the labelled samples (read by the rules only)")
    ap.add_argument("--truth", default=os.path.join(ROOT, "apps/analyzer/tests/bench/ground_truth_blind.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "results.json"))
    ap.add_argument("--rules-only", action="store_true", help="phases A and B only: no code is executed anywhere")
    args = ap.parse_args(argv)

    failures: list = []
    result: dict = {}
    if args.samples:
        say("A. the rules on the labelled samples ...")
        result["samples"] = phase_samples(args.samples, args.truth)
    say("B. the rules on the synthetic corpus ...")
    result["corpus_rules"] = phase_corpus_rules()

    if not args.rules_only:
        if not shutil.which("docker"):
            say("no docker: use --rules-only")
            return 2
        os.environ["VISHAP_HUB_WORKER_IMAGE"] = args.image
        say("C. the exploit probes in worker containers ...")
        result["probes"] = phase_probes(failures)
        say("D. the patch check on scripted patches (this takes minutes) ...")
        result["scenarios"] = phase_scenarios(failures)
        say("E. determinism: the same fix scenarios once more ...")
        pick = {(c["id"], "fix") for c in C.CASES if c["id"] in ("sqli-concat", "path-join", "cmd-system")}
        again = phase_scenarios(failures, only=pick)
        first = [r for r in result["scenarios"] if (r["case"], r["kind"]) in pick]
        result["determinism"] = {"scenarios": sorted(c for c, _ in pick),
                                 "identical": sha(strip_ms(first)) == sha(strip_ms(again))}
    result["sandbox_failures"] = failures

    deterministic = strip_ms(result)
    result["digest"] = sha(deterministic)
    result["meta"] = {"date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "python": platform.python_version(),
                      "image": None if args.rules_only else args.image, "model_called": False,
                      "executed_code": "none" if args.rules_only else "synthetic corpus only, in worker containers"}
    if not args.rules_only:
        try:
            result["meta"]["docker"] = subprocess.run(["docker", "--version"], capture_output=True, text=True,
                                                      check=False).stdout.strip()
        except OSError:
            pass
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(result, fh, indent=1, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    say(f"digest {result['digest'][:16]}  ->  {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())