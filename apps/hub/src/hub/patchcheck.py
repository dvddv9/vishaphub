"""Patch check without a model: a bounded diff to a known snapshot, applied to a copy, re-checked.

A proposed fix is a claim. This module turns it into a status:

    FIX_VERIFIED   the mandatory checks passed (not merely: the finding went away)
    FIX_PARTIAL    nothing broke, but something mandatory is missing or something else went away with it
    FIX_REJECTED   the patch is outside its bounds, touches trusted checks, does not apply, breaks the
                   deliverable's own checks, adds findings, or leaves a reproduced exploit working
    FIX_UNVERIFIED the checks could not be run (no confirmed isolation, no worker, an error)

It never changes the risk verdict, and it never asks a model anything. The same snapshot and the same
diff give the same result.

What cannot buy a FIX_VERIFIED: deleting the file or function that held the finding, deleting or
editing a test, touching the test configuration, a patch whose tests never ran.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
import re

from . import exploits as exploits_mod
from . import statuses

MAX_FILES = 20
MAX_DIFF_BYTES = 200_000
MAX_CHANGED_LINES = 2000

#: Files that decide what the checks are or how they run. A patch that touches one is not a fix.
TRUSTED_NAMES = frozenset({"conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml",
                           "noxfile.py", "sitecustomize.py", "usercustomize.py", ".coveragerc"})
TRUSTED_DIRS = (".github/", ".git/", ".circleci/")

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class PatchError(ValueError):
    """The diff is malformed, out of bounds, or does not apply to the snapshot."""


def sha(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


# --- the diff ---------------------------------------------------------------------------------

def diff_from_files(snapshot: dict, files: dict) -> str:
    """The unified diff that turns the snapshot into `files` ({path: new text}; None deletes a file).

    The model's patch is a dict of whole files. It goes through the same bounded diff as a hand-written
    one, so there is one path and one set of limits.
    """
    out: list[str] = []
    for path in sorted(files):
        old, new = snapshot.get(path), files[path]
        if old == new:
            continue
        a = "/dev/null" if old is None else f"a/{path}"
        b = "/dev/null" if new is None else f"b/{path}"
        out.extend(difflib.unified_diff((old or "").splitlines(True), (new or "").splitlines(True),
                                        fromfile=a, tofile=b))
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n\\ No newline at end of file\n"
    return "".join(out)


def _clean_path(raw: str) -> str | None:
    raw = raw.split("\t")[0].strip()
    if raw == "/dev/null":
        return None
    if raw[:2] in ("a/", "b/"):
        raw = raw[2:]
    return raw


def parse(diff: str) -> list[dict]:
    """[{old, new, hunks: [(old_start, [(op, text)])]}] from a unified diff. Anything odd is refused."""
    if len(diff.encode("utf-8")) > MAX_DIFF_BYTES:
        raise PatchError(f"the diff is larger than {MAX_DIFF_BYTES} bytes")
    files: list[dict] = []
    cur: dict | None = None
    hunk: list | None = None
    lines = diff.splitlines(True)
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- "):
            if i + 1 >= len(lines) or not lines[i + 1].startswith("+++ "):
                raise PatchError("a '---' line without its '+++' line")
            cur = {"old": _clean_path(line[4:].rstrip("\r\n")), "new": _clean_path(lines[i + 1][4:].rstrip("\r\n")),
                   "hunks": []}
            files.append(cur)
            hunk = None
            i += 2
            continue
        m = _HUNK.match(line)
        if m:
            if cur is None:
                raise PatchError("a hunk before any file header")
            hunk = [int(m.group(1)), []]
            cur["hunks"].append(hunk)
        elif hunk is not None and line[:1] in (" ", "-", "+"):
            hunk[1].append((line[0], line[1:]))
        elif hunk is not None and line.startswith("\\"):
            if hunk[1]:
                op, text = hunk[1][-1]
                hunk[1][-1] = (op, text.rstrip("\r\n"))
        elif line.strip() and not line.startswith(("diff ", "index ", "new file", "deleted file", "similarity")):
            raise PatchError(f"unexpected line in the diff: {line[:60]!r}")
        i += 1
    if not files:
        raise PatchError("the diff contains no files")
    return files


def _apply_one(old_text: str | None, hunks: list) -> str:
    src = (old_text or "").splitlines(True)
    out: list[str] = []
    pos = 0
    for start, body in hunks:
        at = max(start - 1, 0) if (old_text or body and any(op != "+" for op, _ in body)) else 0
        if at < pos:
            raise PatchError("hunks overlap or are out of order")
        out.extend(src[pos:at])
        pos = at
        for op, text in body:
            if op == "+":
                out.append(text)
                continue
            if pos >= len(src) or src[pos].rstrip("\r\n") != text.rstrip("\r\n"):
                raise PatchError(f"a hunk does not match the snapshot near line {pos + 1}")
            if op == " ":
                out.append(src[pos])
            pos += 1
    out.extend(src[pos:])
    return "".join(out)


def _changed_lines(files: list[dict]) -> int:
    return sum(1 for f in files for _, body in f["hunks"] for op, _ in body if op in "+-")


def _bad_path(path: str) -> str:
    if not path or "\x00" in path or path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", path):
        return "is not a relative path"
    parts = path.replace("\\", "/").split("/")
    if ".." in parts:
        return "climbs out of the deliverable"
    return ""


def _is_trusted(path: str, trusted: set[str]) -> bool:
    norm = path.replace("\\", "/")
    name = norm.rsplit("/", 1)[-1]
    return (norm in trusted or name in TRUSTED_NAMES or norm.startswith(TRUSTED_DIRS)
            or any(norm.endswith("/" + t) for t in trusted)
            or name.startswith("test_") or name.endswith("_test.py"))


def apply(snapshot: dict, diff: str, *, trusted: set[str] | None = None) -> tuple[dict, list[str]]:
    """The patched copy ({path: text}, deleted files removed) and the list of changed paths.

    Raises PatchError for anything outside bounds, including a path that is trusted. The snapshot dict
    is not modified.
    """
    trusted = {t.replace("\\", "/") for t in (trusted or set())}
    parsed = parse(diff)
    if len(parsed) > MAX_FILES:
        raise PatchError(f"the patch touches more than {MAX_FILES} files")
    if _changed_lines(parsed) > MAX_CHANGED_LINES:
        raise PatchError(f"the patch changes more than {MAX_CHANGED_LINES} lines")
    result = dict(snapshot)
    changed: list[str] = []
    for f in parsed:
        old_p, new_p = f["old"], f["new"]
        for p in (old_p, new_p):
            if p is not None and _bad_path(p):
                raise PatchError(f"path {p!r} {_bad_path(p)}")
            if p is not None and _is_trusted(p, trusted):
                raise PatchError(f"path {p!r} belongs to the trusted checks and cannot be patched")
        if old_p is not None and old_p not in snapshot:
            raise PatchError(f"the diff changes {old_p!r}, which is not in the snapshot")
        if old_p is None and new_p in snapshot:
            raise PatchError(f"the diff creates {new_p!r}, which already exists")
        text = _apply_one(snapshot.get(old_p) if old_p else None, f["hunks"])
        if new_p is None:
            result.pop(old_p, None)
            changed.append(old_p)
        else:
            if old_p and old_p != new_p:
                raise PatchError("renames are not accepted")
            result[new_p] = text
            changed.append(new_p)
    return result, sorted(set(changed))


# --- what the patch did -----------------------------------------------------------------------

def _symbols(text: str) -> set[str] | None:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    return {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def _removed(before: dict, after: dict) -> tuple[list[str], list[str]]:
    files = sorted(p for p in before if p not in after)
    symbols = []
    for path in sorted(before):
        if path in after and path.endswith(".py"):
            old, new = _symbols(before[path]), _symbols(after[path])
            if old is not None and new is not None:
                symbols += [f"{path}:{name}" for name in sorted(old - new)]
    return files, symbols


def _findings(files: dict, analyse) -> tuple[dict, dict, dict]:
    """(counts, worst severity, CWE) per "path::rule", over every file the rules can read."""
    counts: dict = {}
    worst: dict = {}
    cwes: dict = {}
    for path in sorted(files):
        if not files[path].strip():
            continue
        result = analyse(files[path])
        if not result.get("ok"):
            raise PatchError("the rules could not read " + path)
        for f in result.get("findings") or []:
            key = f"{path}::{f.get('rule')}"
            counts[key] = counts.get(key, 0) + 1
            worst[key] = f.get("severity") or "low"
            cwes[key] = f.get("cwe") or ""
    return counts, worst, cwes


def _result(status: str, reason: str, **extra) -> dict:
    return {"status": status, "reason": reason, **extra}


def check(snapshot: dict, *, diff: str | None = None, files: dict | None = None, spec: dict | None = None,
          validate=None, analyse=None, exploit=None) -> dict:
    """Apply a patch to a copy of `snapshot` and decide its fix status. Never raises.

    `diff` is a unified diff; `files` ({path: text}) is the model's whole-file form, turned into the same
    diff. `validate` and `analyse` default to the hub's in-process services (the validator runs only where
    the isolation is confirmed). `exploit(before, after)` is the hook for trusted exploit tests: it returns
    [{"class", "before": "reproduced"|"not_reproduced"|"error", "after": same}].
    """
    from . import local

    validate = validate or local.validate_code
    analyse = analyse or local.analyse_static
    spec = dict(spec or {})
    snapshot = {k: v for k, v in (snapshot or {}).items() if isinstance(v, str)}
    try:
        text = diff if diff is not None else diff_from_files(snapshot, files or {})
        if not text.strip():
            return _result(statuses.FIX_REJECTED, "the patch changes nothing", applied=False)
        trusted = {str(t) for t in spec.get("tests", [])}
        patched, changed = apply(snapshot, text, trusted=trusted)
    except PatchError as exc:
        return _result(statuses.FIX_REJECTED, str(exc), applied=False)
    out = {"applied": True, "diff_sha256": sha(text), "files_changed": changed,
           "snapshot_sha256": sha(snapshot), "patched_sha256": sha(patched)}

    for path in changed:
        if path in patched and path.endswith(".py") and _symbols(patched[path]) is None:
            return _result(statuses.FIX_REJECTED, f"{path} does not parse after the patch", **out)

    removed_files, removed_symbols = _removed(snapshot, patched)
    out["removed"] = {"files": removed_files, "symbols": removed_symbols}

    try:
        (before, _, before_cwe), (after, after_sev, after_cwe) = _findings(snapshot, analyse), _findings(patched, analyse)
    except PatchError as exc:
        return _result(statuses.FIX_UNVERIFIED, str(exc), **out)
    fixed = sorted(k for k in before if after.get(k, 0) < before[k])
    new = sorted(k for k in after if after[k] > before.get(k, 0))
    out["rules"] = {"before": sum(before.values()), "after": sum(after.values()), "fixed": fixed, "new": new}

    run = validate(patched, spec)
    report = run.get("report") or {}
    checks = report.get("checks") or []
    out["validator"] = {"verdict": report.get("verdict", ""), "isolation": run.get("isolation"),
                        "ran": bool(run.get("ok"))}
    if not run.get("ok"):
        return _result(statuses.FIX_UNVERIFIED, "the validator could not run: " + str(run.get("error") or "no result"), **out)
    if any(c.get("name") == "isolation" and not c.get("ok") for c in checks):
        return _result(statuses.FIX_UNVERIFIED, "the isolation was not confirmed, so nothing was run: "
                       + str(report.get("reason") or ""), **out)
    behavior = next((c for c in checks if c.get("name") == "behavior"), None)
    tests_ran = bool(behavior and not behavior.get("skipped") and behavior.get("ok"))
    out["validator"]["tests_ran"] = tests_ran
    if report.get("verdict") not in ("PASS", "NEEDS_REVIEW"):
        return _result(statuses.FIX_REJECTED, "the deliverable's own checks fail after the patch ("
                       + str(report.get("verdict")) + ")", **out)
    if new:
        return _result(statuses.FIX_REJECTED, "the patch introduces findings: " + ", ".join(new), **out)
    # The validator's verdict alone is not enough: a failing test leaves it at NEEDS_REVIEW. A check that
    # fails after the patch and passed before is the patch's doing; one that already failed is not, but it
    # means that check proves nothing about the fix.
    failed = sorted(c["name"] for c in checks if not c.get("skipped") and not c.get("ok"))
    already: list[str] = []
    if failed:
        base_run = validate(snapshot, spec)
        if not base_run.get("ok"):
            return _result(statuses.FIX_UNVERIFIED, "the original could not be checked for comparison: "
                           + str(base_run.get("error") or "no result"), **out)
        base_failed = {c["name"] for c in (base_run.get("report") or {}).get("checks", [])
                       if not c.get("skipped") and not c.get("ok")}
        broke = [n for n in failed if n not in base_failed]
        if broke:
            return _result(statuses.FIX_REJECTED, "checks that passed before fail after the patch: "
                           + ", ".join(broke), **out)
        already = failed
    out["validator"]["failed_before_and_after"] = already

    # Trusted exploit tests, from the caller's spec and never from the patch. A hook can also be given.
    targets = spec.get("exploit_targets") or []
    if exploit is None and targets:
        exploit = exploits_mod.make_hook(targets)
    rows: list[dict] = []
    if exploit is not None:
        try:
            rows = exploit(snapshot, patched)
        except exploits_mod.ExploitRunError as exc:
            return _result(statuses.FIX_UNVERIFIED, str(exc), **out)
        out["exploit"] = rows
        still = [e["class"] for e in rows if e.get("after") == "reproduced"]
        if still:
            return _result(statuses.FIX_REJECTED, "the exploit still works after the patch: " + ", ".join(still), **out)

    # A fix for an attack class is only as good as the test that first shows the attack working and then
    # not working. The rules cannot tell: `subprocess.run([...])` and `open(realpath(...))` are flagged just
    # like the vulnerable code, and a vulnerable query built with `+=` or `join` is not flagged at all.
    by_class = {r.get("class"): r for r in rows}
    proven = {k: r for k, r in by_class.items() if r.get("before") == "reproduced" and r.get("after") == "not_reproduced"}
    fixed_classes = {c for c in (exploits_mod.class_of(k.split("::", 1)[1], before_cwe.get(k)) for k in fixed) if c}
    untested = []
    exploit_gaps = []
    for kind in sorted(fixed_classes | set(by_class)):
        name = exploits_mod.CLASS_NAMES.get(kind, kind)
        row = by_class.get(kind)
        if row is None:
            untested.append(kind)
            exploit_gaps.append(f"no exploit test for {name}: not verified by a test")
        elif row.get("before") != "reproduced":
            untested.append(kind)
            exploit_gaps.append(f"the exploit test for {name} did not reproduce the problem on the original"
                                f" ({row.get('before')})")
        elif row.get("after") != "not_reproduced":
            untested.append(kind)
            exploit_gaps.append(f"the exploit test for {name} could not confirm the fix ({row.get('after')})")
    out["exploit_untested"] = untested
    # A finding the rules keep raising on fixed code is discharged only by an exploit test that proves its
    # class fixed. The generic `taint-flow` rule has no class: it is discharged only in the file of a target
    # whose exploit test passed.
    proven_files = {r["entry"].split(":")[0].replace(".", "/") + ".py" for r in proven.values() if r.get("entry")}

    def discharged(key: str) -> bool:
        path, rule = key.split("::", 1)
        return (exploits_mod.class_of(rule, after_cwe.get(key)) in proven
                or (rule == "taint-flow" and path in proven_files))

    blocking = sorted(k for k in after if after_sev.get(k) in ("critical", "high") and not discharged(k))
    out["rules"]["remaining_critical_or_high"] = blocking

    gaps = []
    if removed_files or removed_symbols:
        gaps.append("code went away with the patch: " + ", ".join(removed_files + removed_symbols))
    if already:
        gaps.append("checks already failing before the patch prove nothing about it: " + ", ".join(already))
    if not tests_ran:
        gaps.append("no test of the deliverable ran")
    if not fixed and not proven:
        gaps.append("the rules had no finding that the patch removed")
    gaps.extend(exploit_gaps)
    if blocking:
        gaps.append("a critical or high finding remains: " + ", ".join(blocking))
    if gaps:
        return _result(statuses.FIX_PARTIAL, "; ".join(gaps), **out)
    return _result(statuses.FIX_VERIFIED, "applied to a copy; the rules found fewer findings, none new; "
                   "the deliverable's own tests ran in a confirmed isolation and passed", **out)