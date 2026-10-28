"""Verify: prove the generated code against the requirements.

Three outputs: a code verdict, a spec verdict (stale after 90 days) and
coverage (needs_verification under 80%).

Evidence per requirement comes from three sources:
  model-test  the test_rN tests the model wrote, run in a subprocess
  attack      requests Verify builds itself from the spec, run in a subprocess
  rule        static checks on the syntax tree for known must_never ids

Generated code runs in a subprocess in a temporary folder, with a
timeout, in UTF-8 mode, and with an environment stripped of everything
but basic system variables, so API keys are not visible to it. This is
not isolation: the code runs with the user's rights, can reach files and
the network, and hostile code could fake its own results. Verify checks
a cooperative model's work; it is not a security boundary.
"""

from __future__ import annotations

import ast
import datetime as dt
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath

from generator.config import COVERAGE_MIN, STALE_DAYS
from generator.pipeline.verdict import (Evidence, RequirementVerdict, VerifyResult,
                                        compute_code_verdict, compute_spec_verdict,
                                        decide_requirement)
from generator.tools.static_scan import RULES, scan_code
from generator.tools.analyzer import AnalyzerResult
from generator.pipeline.build import TEST_NAME_RE
from generator.pipeline.sandbox import DEFAULT_TIMEOUT, run_sandbox
from generator.pipeline.design import DesignResult
from generator.pipeline.intake import Requirement
from generator.tools.spec import REQUIREMENT_LISTS, Spec

ATTACKED = ("query", "header", "path", "body")      # the kinds of input Verify sends values to
RULE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s+(letters and digits|letters|digits)\s*$", re.I)
ABSENT = object()


# ---------------------------------------------------------------- rules

@dataclass(frozen=True)
class InputRule:
    lo: int
    hi: int
    kind: str

    def valid(self, n: int, pattern: str | None = None) -> str:
        pat = pattern or {"letters and digits": "a1", "letters": "ab", "digits": "12"}[self.kind]
        return (pat * (n // len(pat) + 1))[:n]


def parse_rule(text) -> InputRule | None:
    m = RULE_RE.match(text or "") if isinstance(text, str) else None
    if not m:
        return None
    lo, hi = int(m.group(1)), int(m.group(2))
    if hi < lo or hi < 1:
        return None
    return InputRule(lo, hi, m.group(3).lower())


def input_cases(item: dict) -> list[tuple[str, str, object]] | None:
    """(label, expect, value) for one input; None when the rule is not machine-readable."""
    rule = parse_rule(item.get("rule"))
    if rule is None:
        return None
    n = max(rule.lo, 1)
    base = rule.valid(n)
    cases: list[tuple[str, str, object]] = []
    if rule.lo >= 1:
        # a path value cannot be absent or empty: that is another route, not an invalid value
        cases += [] if item["in"] == "path" else [("absent", "reject", ABSENT), ("empty", "reject", "")]
    cases.append((f"length {rule.hi + 1}", "reject", rule.valid(rule.hi + 1)))
    if n + 1 <= rule.hi:
        if item["in"] in ("query", "path", "body"):
            cases.append(("trailing newline", "reject", base + "\n"))
        cases += [("trailing space", "reject", base + " "),
                  ("punctuation", "reject", base + "!"),
                  ("quote", "reject", base + "'")]
        if rule.kind == "letters":
            cases.append(("digit", "reject", base + "1"))
        if rule.kind == "digits":
            cases.append(("letter", "reject", base + "a"))
    cases += [(f"length {n}", "accept", base), (f"length {rule.hi}", "accept", rule.valid(rule.hi))]
    return cases


def _marker(item: dict) -> str:
    rule = parse_rule(item.get("rule"))
    if rule is None:
        return "vgmarker7q"
    pattern = {"letters and digits": "vg7q", "letters": "vgqz", "digits": "9071"}[rule.kind]
    n = min(rule.hi, max(rule.lo, 8))
    return rule.valid(n, pattern)


# ---------------------------------------------------------------- verify

def _items_by_requirement(spec: Spec, reqs) -> dict[str, tuple[str, dict]]:
    pairs = [(f, item) for f in REQUIREMENT_LISTS for item, _ in spec.items.get(f, [])]
    return {r.id: pair for r, pair in zip(reqs, pairs)}


def _module_name(path: str) -> str:
    return ".".join(PurePosixPath(path).with_suffix("").parts)


def default_values(inputs: list[dict]) -> dict[str, str]:
    """A valid value for every input: what the other inputs carry while one is attacked."""
    out = {}
    for i in inputs:
        r = parse_rule(i.get("rule"))
        out[i["name"]] = r.valid(max(r.lo, 1)) if r else "a"
    return out


def route_has(route: str | None, name: str) -> bool:
    """Does the route carry a placeholder for this path input: `<name>`, `<int:name>` or `{name}`?"""
    if not route:
        return False
    return bool(re.search(r"<(?:[A-Za-z_]+:)?" + re.escape(name) + r">|\{" + re.escape(name) + r"\}", route))


def make_request(inputs: list[dict], defaults: dict[str, str], rid: str, label: str, expect: str,
                 target: dict, value, marker: str | None = None) -> dict:
    """One request for the sandbox: `target` carries `value`, every other input a valid value.

    query and header go as they are; `path` values replace the placeholders of the route; `body` values
    become one JSON object. An input that is ABSENT is left out of its place.
    """
    query, headers, path_values, body = {}, {}, {}, {}
    for i in inputs:
        if i["in"] not in ATTACKED:
            continue
        v = defaults[i["name"]]
        if i is target:
            if value is ABSENT:
                continue
            v = value
        {"query": query, "header": headers, "path": path_values, "body": body}[i["in"]][i["name"]] = v
    req = {"id": f"{rid}:{label}", "req": rid, "label": label, "expect": expect,
           "query": query, "headers": headers}
    if path_values:
        req["path_values"] = path_values
    if any(i["in"] == "body" for i in inputs):
        req["json"] = body
    if marker:
        req["marker"] = marker
    return req


def _build_requests(spec: Spec, item_of: dict) -> tuple[list[dict], list[tuple[str, str]], set[int]]:
    inputs = [item for item, _ in spec.items.get("inputs", [])]
    statuses = {o["status"] for o, _ in spec.items.get("outputs", [])}
    reject = (statuses & {400, 422}) or {400, 422}
    defaults = default_values(inputs)
    route = spec.data.get("route")

    def make(rid, label, expect, target, value, marker=None):
        return make_request(inputs, defaults, rid, label, expect, target, value, marker)

    requests, skipped = [], []
    for rid, (field, item) in item_of.items():
        if field == "inputs":
            if item["in"] not in ATTACKED:
                skipped.append((rid, f"input in {item['in']} is not attacked"))
                continue
            if item["in"] == "path" and not route_has(route, item["name"]):
                skipped.append((rid, f"the route has no placeholder for the path input {item['name']}"))
                continue
            cases = input_cases(item)
            if cases is None:
                skipped.append((rid, "rule is not machine-readable"))
                continue
            for label, expect, value in cases:
                requests.append(make(rid, label, expect, item, value))
        elif field == "must_never" and item["id"] == "log-raw-input":
            for i in inputs:
                if i["in"] not in ATTACKED or (i["in"] == "path" and not route_has(route, i["name"])):
                    continue
                m = _marker(i)
                requests.append(make(rid, f"{i['name']} valid value not logged", "no-log", i, m, m))
                requests.append(make(rid, f"{i['name']} rejected value not logged", "no-log", i, m + "!", m))
    return requests, skipped, reject


def _judge(req: dict, res: dict, reject: set[int]) -> tuple[str, str]:
    if req["expect"] == "no-log":
        return ("fail", "the input value appeared in logs or output") if res["marker_seen"] else ("pass", "")
    if res["error"]:
        if req["expect"] == "accept":
            return "pass", f"raised {res['error']}, not a rejection"
        return "fail", f"raised {res['error']} instead of answering"
    code = res["status"]
    if req["expect"] == "reject":
        return ("pass", f"answered {code}") if code in reject else \
            ("fail", f"answered {code}, expected {' or '.join(map(str, sorted(reject)))}")
    return ("pass", f"answered {code}") if code not in reject else ("fail", f"rejected with {code}")


def verify(spec: Spec, requirements: tuple[Requirement, ...], design: DesignResult,
           files: dict[str, str], *, today: dt.date | None = None,
           timeout: float = DEFAULT_TIMEOUT, python: str | None = None,
           analyzer: Callable[[dict[str, str]], AnalyzerResult] | None = None,
           coverage: str = "auto", coverage_min: float = COVERAGE_MIN,
           stale_days: int = STALE_DAYS) -> VerifyResult:
    python = python or sys.executable
    today = today or dt.date.today()
    problems: list[str] = []
    notes: list[str] = []
    evidence: dict[str, list[Evidence]] = {r.id: [] for r in requirements}
    item_of = _items_by_requirement(spec, requirements)
    planned = {f.path: files[f.path] for f in design.files if f.path in files}
    code_files = [f.path for f in design.files if f.role == "code" and f.path in files]
    test_files = [f.path for f in design.files if f.role == "test" and f.path in files]
    python_target = str(spec.data.get("target", "")).startswith("python/")

    # rules
    trees = {}
    for p in code_files:
        if p.endswith(".py"):
            try:
                trees[p] = ast.parse(files[p])
            except SyntaxError as e:
                problems.append(f"{p} does not parse (line {e.lineno})")
    for rid, (field, item) in item_of.items():
        if field != "must_never" or not trees:
            continue
        if item["id"] in RULES:
            found = scan_code(item["id"], trees)
            rule = RULES[item["id"]]
            evidence[rid].append(Evidence("rule", item["id"], "fail" if found else "pass",
                                          "; ".join(found), cwe=rule.cwe))

    # model tests
    coverage_status, coverage_percent, coverage_note = "skipped", None, "no tests ran"
    if python_target and test_files and code_files:
        run = run_sandbox(planned, "tests",
                           {"tests_dir": str(PurePosixPath(test_files[0]).parent),
                            "code_files": code_files, "coverage": coverage}, timeout, python)
        if run["status"] != "ok":
            problems.append(f"model tests: {run['status']}")
        else:
            ran_any = False
            for name, st in sorted(run["tests"].items()):
                m = TEST_NAME_RE.match(name)
                rid = f"R{m.group(1)}" if m else None
                if rid in evidence:
                    ran_any = True
                    note = run["notes"].get(name, "").strip().splitlines()
                    evidence[rid].append(Evidence("model-test", name, st, note[-1] if note else ""))
                elif st == "error":
                    note = run["notes"].get(name, "").strip().splitlines()
                    problems.append(f"model tests could not load {name}: {note[-1] if note else ''}")
            if not ran_any:
                problems.append("no model test ran")
            coverage_percent = run.get("coverage")
            coverage_note = run.get("coverage_note") or ""
            if coverage_percent is None:
                coverage_status = "skipped"
            else:
                coverage_status = "ok" if coverage_percent >= coverage_min else "below"

    # attacks
    if python_target and code_files and spec.data.get("kind") == "http-endpoint":
        requests, skipped, reject = _build_requests(spec, item_of)
        for rid, why in skipped:
            evidence[rid].append(Evidence("attack", "-", "skipped", why))
        if requests:
            method = path = None
            if spec.data.get("route"):
                method, path = spec.data["route"].split(" ", 1)
            run = run_sandbox(planned, "attacks",
                               {"module": _module_name(code_files[0]), "method": method,
                                "path": path, "requests": requests}, timeout, python)
            if run["status"] != "ok":
                problems.append(f"attacks: {run['status']}")
            elif run.get("error"):
                problems.append(f"attacks: {run['error']}")
            else:
                by_id = {r["id"]: r for r in requests}
                for res in run["requests"]:
                    req = by_id[res["id"]]
                    status, detail = _judge(req, res, reject)
                    evidence[req["req"]].append(Evidence("attack", req["label"], status, detail))
                    if status == "pass" and req["expect"] == "accept" and (
                            res.get("error") or (res.get("status") or 0) >= 500):
                        notes.append(f"{req['req']} '{req['label']}': valid input gave a server error "
                                     f"({detail}); may only mean the sandbox has no database")

    analyzer_result = None
    if analyzer is not None and spec.data.get("check", "analyzer") == "analyzer":
        analyzer_result = analyzer({p: files[p] for p in code_files})
        if analyzer_result.status == "error":
            problems.append(f"analyzer: {analyzer_result.note}")
        elif analyzer_result.status == "skipped":
            notes.append(f"analyzer skipped: {analyzer_result.note}")

    verdicts = []
    for r in requirements:
        status, note = decide_requirement(evidence[r.id])
        verdicts.append(RequirementVerdict(r.id, r.priority, status, tuple(evidence[r.id]), note))

    analyzer_failed = bool(analyzer_result and analyzer_result.status == "failed")
    code_verdict = compute_code_verdict(verdicts, coverage_status, problems, analyzer_failed)

    stale, age = compute_spec_verdict((today - spec.updated).days, stale_days)
    return VerifyResult(
        requirements=tuple(verdicts), code_verdict=code_verdict,
        spec_stale=stale, spec_age_days=age,
        coverage_status=coverage_status, coverage_percent=coverage_percent,
        coverage_note=coverage_note, problems=tuple(problems),
        notes=tuple(notes), analyzer=analyzer_result,
        coverage_min=coverage_min, stale_days=stale_days)
