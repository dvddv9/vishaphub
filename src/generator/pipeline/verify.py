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
from generator.tools.analyzer import AnalyzerResult
from generator.pipeline.build import TEST_NAME_RE
from generator.pipeline.sandbox import DEFAULT_TIMEOUT, run_sandbox
from generator.pipeline.design import DesignResult
from generator.pipeline.intake import Requirement
from generator.tools.spec import REQUIREMENT_LISTS, Spec

RULE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s+(letters and digits|letters|digits)\s*$", re.I)
ABSENT = object()


# ---------------------------------------------------------------- results

@dataclass(frozen=True)
class Evidence:
    source: str     # model-test | attack | rule
    name: str
    status: str     # pass | fail | error | skipped
    detail: str = ""

    def to_dict(self) -> dict:
        return {"source": self.source, "name": self.name,
                "status": self.status, "detail": self.detail}


@dataclass(frozen=True)
class RequirementVerdict:
    id: str
    priority: str
    status: str     # passed | failed | needs_verification | not_verified
    evidence: tuple[Evidence, ...]
    note: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "priority": self.priority, "status": self.status,
                "note": self.note, "evidence": [e.to_dict() for e in self.evidence]}


@dataclass(frozen=True)
class VerifyResult:
    requirements: tuple[RequirementVerdict, ...]
    code_verdict: str           # passed | failed | needs_verification
    spec_stale: bool
    spec_age_days: int
    coverage_status: str        # ok | below | skipped
    coverage_percent: float | None
    coverage_note: str
    problems: tuple[str, ...]
    notes: tuple[str, ...] = ()
    analyzer: AnalyzerResult | None = None

    @property
    def passed(self) -> int:
        return sum(1 for r in self.requirements if r.status == "passed")

    def to_dict(self) -> dict:
        return {
            "code_verdict": self.code_verdict,
            "spec": {"stale": self.spec_stale, "age_days": self.spec_age_days},
            "coverage": {"status": self.coverage_status, "percent": self.coverage_percent,
                         "minimum": COVERAGE_MIN, "note": self.coverage_note},
            "problems": list(self.problems),
            "notes": list(self.notes),
            "analyzer": self.analyzer.to_dict() if self.analyzer else None,
            "requirements": [r.to_dict() for r in self.requirements],
        }


# ---------------------------------------------------------------- rules

@dataclass(frozen=True)
class Rule:
    lo: int
    hi: int
    kind: str

    def valid(self, n: int, pattern: str | None = None) -> str:
        pat = pattern or {"letters and digits": "a1", "letters": "ab", "digits": "12"}[self.kind]
        return (pat * (n // len(pat) + 1))[:n]


def parse_rule(text) -> Rule | None:
    m = RULE_RE.match(text or "") if isinstance(text, str) else None
    if not m:
        return None
    lo, hi = int(m.group(1)), int(m.group(2))
    if hi < lo or hi < 1:
        return None
    return Rule(lo, hi, m.group(3).lower())


def input_cases(item: dict) -> list[tuple[str, str, object]] | None:
    """(label, expect, value) for one input; None when the rule is not machine-readable."""
    rule = parse_rule(item.get("rule"))
    if rule is None:
        return None
    n = max(rule.lo, 1)
    base = rule.valid(n)
    cases: list[tuple[str, str, object]] = []
    if rule.lo >= 1:
        cases += [("absent", "reject", ABSENT), ("empty", "reject", "")]
    cases.append((f"length {rule.hi + 1}", "reject", rule.valid(rule.hi + 1)))
    if n + 1 <= rule.hi:
        if item["in"] == "query":
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


# ---------------------------------------------------------------- static checks

SQL_CALLS = {"execute", "executemany", "executescript", "raw", "text"}
LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}


def _assignments(tree: ast.AST) -> dict[str, list[ast.AST]]:
    out: dict[str, list[ast.AST]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out.setdefault(t.id, []).append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            out.setdefault(node.target.id, []).append(node.value)
    return out


def sql_findings(tree: ast.AST) -> list[str]:
    assigns = _assignments(tree)

    def built(expr, depth=0):
        if isinstance(expr, ast.JoinedStr):
            return "an f-string"
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, (ast.Mod, ast.Add)):
            return "% or +"
        if (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute)
                and expr.func.attr in ("format", "join")):
            return f".{expr.func.attr}()"
        if isinstance(expr, ast.Name) and depth < 3:
            for value in assigns.get(expr.id, []):
                why = built(value, depth + 1)
                if why:
                    return f"{why} (through {expr.id})"
        return None

    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and node.args:
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if name in SQL_CALLS:
                why = built(node.args[0])
                if why:
                    found.append(f"line {node.lineno}: {name}() gets SQL built with {why}")
    return found


# Names that carry request data: Flask `request`, WSGI `environ`.
REQUEST_NAMES = {"request", "environ"}


def log_findings(tree: ast.AST) -> list[str]:
    assigns = _assignments(tree)

    def mentions(expr, tainted):
        return any(isinstance(n, ast.Name) and (n.id in REQUEST_NAMES or n.id in tainted)
                   for n in ast.walk(expr))

    tainted: set[str] = set()
    for _ in range(4):
        for name, values in assigns.items():
            if any(mentions(v, tainted) for v in values):
                tainted.add(name)

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        is_print = isinstance(f, ast.Name) and f.id == "print"
        is_log = (isinstance(f, ast.Attribute) and f.attr in LOG_METHODS
                  and "log" in ast.unparse(f.value).lower())
        if not (is_print or is_log):
            continue
        args = list(node.args) + [k.value for k in node.keywords]
        if any(mentions(a, tainted) for a in args):
            found.append(f"line {node.lineno}: {ast.unparse(f)}() gets request data")
    return found


# ---------------------------------------------------------------- verify

def _items_by_requirement(spec: Spec, reqs) -> dict[str, tuple[str, dict]]:
    pairs = [(f, item) for f in REQUIREMENT_LISTS for item, _ in spec.items.get(f, [])]
    return {r.id: pair for r, pair in zip(reqs, pairs)}


def _module_name(path: str) -> str:
    return ".".join(PurePosixPath(path).with_suffix("").parts)


def _build_requests(spec: Spec, item_of: dict) -> tuple[list[dict], list[tuple[str, str]], set[int]]:
    inputs = [item for item, _ in spec.items.get("inputs", [])]
    statuses = {o["status"] for o, _ in spec.items.get("outputs", [])}
    reject = (statuses & {400, 422}) or {400, 422}
    defaults = {}
    for i in inputs:
        r = parse_rule(i.get("rule"))
        defaults[i["name"]] = r.valid(max(r.lo, 1)) if r else "a"

    def make(rid, label, expect, target, value, marker=None):
        query, headers = {}, {}
        for i in inputs:
            if i["in"] not in ("query", "header"):
                continue
            v = defaults[i["name"]]
            if i is target:
                if value is ABSENT:
                    continue
                v = value
            (query if i["in"] == "query" else headers)[i["name"]] = v
        req = {"id": f"{rid}:{label}", "req": rid, "label": label, "expect": expect,
               "query": query, "headers": headers}
        if marker:
            req["marker"] = marker
        return req

    requests, skipped = [], []
    for rid, (field, item) in item_of.items():
        if field == "inputs":
            if item["in"] not in ("query", "header"):
                skipped.append((rid, f"input in {item['in']} is not attacked yet"))
                continue
            cases = input_cases(item)
            if cases is None:
                skipped.append((rid, "rule is not machine-readable"))
                continue
            for label, expect, value in cases:
                requests.append(make(rid, label, expect, item, value))
        elif field == "must_never" and item["id"] == "log-raw-input":
            for i in inputs:
                if i["in"] not in ("query", "header"):
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


def _decide(evidence: list[Evidence]) -> tuple[str, str]:
    own = [e for e in evidence if e.source in ("attack", "rule") and e.status in ("pass", "fail")]
    model = [e for e in evidence if e.source == "model-test" and e.status != "skipped"]
    if any(e.status == "fail" for e in own):
        return "failed", ""
    model_bad = [e for e in model if e.status != "pass"]
    if model_bad and own:
        return "needs_verification", "a model test fails while Verify's own checks pass; the test may be wrong"
    if model_bad:
        return "failed", ""
    if model or own:
        return "passed", ""
    return "not_verified", "no test or check covers it"


def verify(spec: Spec, requirements: tuple[Requirement, ...], design: DesignResult,
           files: dict[str, str], *, today: dt.date | None = None,
           timeout: float = DEFAULT_TIMEOUT, python: str | None = None,
           analyzer: Callable[[dict[str, str]], AnalyzerResult] | None = None,
           coverage: str = "auto") -> VerifyResult:
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
        check = {"sql-from-input": sql_findings, "log-raw-input": log_findings}.get(item["id"])
        if check:
            found = [f"{p} {x}" for p, t in trees.items() for x in check(t)]
            evidence[rid].append(Evidence("rule", item["id"], "fail" if found else "pass", "; ".join(found)))

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
                coverage_status = "ok" if coverage_percent >= COVERAGE_MIN else "below"

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
        status, note = _decide(evidence[r.id])
        verdicts.append(RequirementVerdict(r.id, r.priority, status, tuple(evidence[r.id]), note))

    hard = [v for v in verdicts if v.priority in ("critical", "high")]
    if any(v.status == "failed" for v in hard) or (analyzer_result and analyzer_result.status == "failed"):
        code_verdict = "failed"
    elif any(v.status != "passed" for v in hard) or coverage_status == "below" or problems:
        code_verdict = "needs_verification"
    else:
        code_verdict = "passed"

    age = (today - spec.updated).days
    return VerifyResult(
        requirements=tuple(verdicts), code_verdict=code_verdict,
        spec_stale=age > STALE_DAYS, spec_age_days=age,
        coverage_status=coverage_status, coverage_percent=coverage_percent,
        coverage_note=coverage_note, problems=tuple(problems),
        notes=tuple(notes), analyzer=analyzer_result)
