"""Do the model's tests notice when the code is wrong? Break the code on purpose and see.

The generated tests are the model's own work, and a test can pass on code that does nothing it claims (the first
real run's test "raw input is not logged" passed on code that logs nothing). A mutant is the code with one small
change: `fullmatch` becomes `match`, `==` becomes `!=`, a status code goes up by one, an `if` is negated. If the tests
still pass, they would not have caught that bug: the mutant survived. The judge is the run, no model is called.

Honest limits: some mutants change nothing a test could see (an equivalent mutant), so a score below 100 is not
always a weak test; and the score covers only the model's tests, not Verify's own attacks. The result lists the
survivors, with the line and the change, so a person (or a repair round) can look at each.
"""

from __future__ import annotations

import ast
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from generator.pipeline.sandbox import run_sandbox

MUTANT_TIMEOUT = 20.0        # seconds for the tests of one mutant; a timeout counts as caught
BUDGET_S = 90.0              # all mutants together; the rest is left out and the result says so
WORKERS = 4

SWAP_COMPARE = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE,
                ast.GtE: ast.Gt, ast.Is: ast.IsNot, ast.IsNot: ast.Is, ast.In: ast.NotIn, ast.NotIn: ast.In}
SYMBOL = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Is: "is",
          ast.IsNot: "is not", ast.In: "in", ast.NotIn: "not in"}
STATUS_RE = re.compile(r"^([1-5]\d\d)( .*)?$")
ATTR_SWAP = {"fullmatch": "match", "match": "search"}      # a regex that no longer covers the whole string


@dataclass(frozen=True)
class Mutant:
    index: int
    file: str
    line: int
    kind: str
    change: str                      # what was changed, in words and code
    path: tuple = ()                 # where in the tree (child indexes), to apply the change again
    new: object = None               # the replacement value for the operators that need one


@dataclass
class MutationResult:
    status: str = "skipped"          # ok | skipped
    note: str = ""
    planned: int = 0                 # mutants found in the code
    run: int = 0                     # mutants whose tests were run
    killed: int = 0
    survivors: list = field(default_factory=list)       # list[Mutant]
    stopped: str = ""                # why not all planned mutants ran

    @property
    def score(self) -> float | None:
        return round(100.0 * self.killed / self.run, 1) if self.run else None

    def to_dict(self) -> dict:
        d = {"status": self.status, "note": self.note, "planned": self.planned, "run": self.run,
             "killed": self.killed, "score": self.score,
             "survivors": [{"file": m.file, "line": m.line, "kind": m.kind, "change": m.change} for m in self.survivors]}
        if self.stopped:
            d["stopped"] = self.stopped
        return d


def _is_main_guard(node: ast.If) -> bool:
    t = node.test
    return isinstance(t, ast.Compare) and isinstance(t.left, ast.Name) and t.left.id == "__name__"


def _children(node: ast.AST):
    return list(ast.iter_child_nodes(node))


def _walk(node: ast.AST, path: tuple = ()):
    yield node, path
    for i, child in enumerate(_children(node)):
        yield from _walk(child, path + (i,))


def _node_at(tree: ast.AST, path: tuple) -> ast.AST:
    for i in path:
        tree = _children(tree)[i]
    return tree


def find_mutants(path: str, source: str) -> list[Mutant]:
    """Every single change the operators allow in one file, in source order. No file, no mutants on a syntax error."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out: list[Mutant] = []

    def add(kind, node, p, change, new=None):
        out.append(Mutant(0, path, getattr(node, "lineno", 0), kind, change, p, new))

    for node, p in _walk(tree):
        if isinstance(node, ast.Compare):
            for k, op in enumerate(node.ops):
                if type(op) in SWAP_COMPARE and not (isinstance(node.left, ast.Name) and node.left.id == "__name__"):
                    add("compare", node, p, f"`{SYMBOL[type(op)]}` becomes `{SYMBOL[SWAP_COMPARE[type(op)]]}`", ("op", k))
        elif isinstance(node, ast.BoolOp):
            now, then = ("and", "or") if isinstance(node.op, ast.And) else ("or", "and")
            add("boolean", node, p, f"`{now}` becomes `{then}`", then)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            add("not", node, p, "`not` is removed")
        elif isinstance(node, ast.If) and not _is_main_guard(node):
            add("if", node, p, "the condition of an `if` is negated")
        elif isinstance(node, ast.Constant):
            v = node.value
            if isinstance(v, bool) or v is None:
                continue
            if isinstance(v, int) and abs(v) <= 100_000:
                add("number", node, p, f"the number {v} becomes {v + 1}", v + 1)
            elif isinstance(v, str):
                m = STATUS_RE.match(v)
                if m:
                    new = str(int(m.group(1)) + 1) + (m.group(2) or "")
                    add("status", node, p, f"the status \"{v}\" becomes \"{new}\"", new)
        elif isinstance(node, ast.Attribute) and node.attr in ATTR_SWAP:
            add("regex", node, p, f"`.{node.attr}` becomes `.{ATTR_SWAP[node.attr]}`", ATTR_SWAP[node.attr])
    out.sort(key=lambda m: (m.line, m.kind, m.change))
    return [with_index(m, i) for i, m in enumerate(out)]


def with_index(m: Mutant, index: int) -> Mutant:
    return Mutant(index, m.file, m.line, m.kind, m.change, m.path, m.new)


def apply(source: str, m: Mutant) -> str | None:
    """The source with the one change made, or None when the change cannot be applied."""
    tree = ast.parse(source)
    node = _node_at(tree, m.path)
    if m.kind == "compare":
        _, k = m.new
        node.ops[k] = SWAP_COMPARE[type(node.ops[k])]()
    elif m.kind == "boolean":
        node.op = ast.Or() if m.new == "or" else ast.And()
    elif m.kind == "not":
        replacement = node.operand
        return _replace(tree, m.path, replacement)
    elif m.kind == "if":
        node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
    elif m.kind in ("number", "status"):
        node.value = m.new
    elif m.kind == "regex":
        node.attr = m.new
    else:
        return None
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def _replace(tree: ast.AST, path: tuple, new: ast.AST) -> str:
    parent = _node_at(tree, path[:-1])
    target = _children(parent)[path[-1]]
    for name, value in ast.iter_fields(parent):
        if value is target:
            setattr(parent, name, new)
            break
        if isinstance(value, list):
            for j, item in enumerate(value):
                if item is target:
                    value[j] = new
                    break
            else:
                continue
            break
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def sample(mutants: list[Mutant], limit: int) -> list[Mutant]:
    """At most `limit` mutants spread evenly over the list, the same ones every time."""
    if limit <= 0 or len(mutants) <= limit:
        return mutants if limit > 0 else []
    step = len(mutants) / limit
    return [mutants[int(i * step)] for i in range(limit)]


def _caught(run: dict) -> bool:
    if run.get("status") != "ok":
        return True                              # a crash or a timeout is a visible difference
    return any(st in ("fail", "error") for st in run["tests"].values())


def run_mutation(files: dict[str, str], code_files: list[str], test_files: list[str], limit: int, *,
                 python: str, timeout: float = MUTANT_TIMEOUT, budget_s: float = BUDGET_S,
                 workers: int = WORKERS, clock=time.monotonic) -> MutationResult:
    """Run the model's tests against up to `limit` mutants of the code files."""
    res = MutationResult()
    if limit <= 0:
        res.note = "mutation check is off"
        return res
    if not test_files or not code_files:
        res.note = "there are no tests or no code to mutate"
        return res
    py_code = [p for p in code_files if p.endswith(".py")]
    allm: list[Mutant] = []
    for p in py_code:
        allm += find_mutants(p, files[p])
    allm = [with_index(m, i) for i, m in enumerate(allm)]
    res.planned = len(allm)
    if not allm:
        res.note = "no mutation operator applies to this code"
        return res
    plan = {"tests_dir": str(PurePosixPath(test_files[0]).parent), "code_files": code_files, "coverage": "off"}
    base = run_sandbox(files, "tests", plan, timeout, python)
    if base.get("status") != "ok" or any(st in ("fail", "error") for st in base["tests"].values()):
        res.note = "the tests do not all pass on the original code, so a mutant proves nothing"
        return res
    chosen = sample(allm, limit)
    started = clock()

    def one(m: Mutant):
        if clock() - started > budget_s:
            return m, None
        mutated = apply(files[m.file], m)
        if mutated is None:
            return m, None
        changed = dict(files)
        changed[m.file] = mutated
        return m, _caught(run_sandbox(changed, "tests", plan, timeout, python))

    with ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="vg-mut") as pool:
        results = list(pool.map(one, chosen))
    for m, caught in results:
        if caught is None:
            continue
        res.run += 1
        if caught:
            res.killed += 1
        else:
            res.survivors.append(m)
    left = len(chosen) - res.run
    if left:
        res.stopped = f"{left} of {len(chosen)} mutants were left out (time budget {budget_s:g} s)"
    if res.run == 0:
        res.note = "no mutant could be run"
        return res
    res.status = "ok"
    return res


def survivors_text(res: MutationResult) -> str:
    """The survivors as lines for a repair round: where, what changed, and the ask."""
    lines = [f"mutation: {res.killed} of {res.run} changes to the code were caught by your tests; these were not:"]
    for m in res.survivors:
        lines.append(f"  {m.file}:{m.line} {m.change}")
    lines.append("write a test for each one that fails when the code is changed this way and passes on the real code. "
                 "Do not change the code files.")
    return "\n".join(lines)
