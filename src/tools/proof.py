# -*- coding: utf-8 -*-
"""Proof, not opinion: run the submitted handlers with probe values and record what happens.

A finding from a rule or an LLM is a claim. This module turns some claims into evidence:

    sqli           the probe text ends up INSIDE the executed SQL statement
    cmdi           the probe text ends up in a shell command string
    traversal      '../' or an absolute path reaches send_file()/open() unchanged
    amount         a negative amount reaches an UPDATE/INSERT/DELETE
    auth           the handler acts (db/file/process) with no credentials at all

and each finding gets ``proof = {"status": CONFIRMED | NOT_REPRODUCED | INCONCLUSIVE, ...}``.
``verify_patch`` runs the same probes on the original and on a patched version, so "the fix
works" means "the exploit that worked before no longer works", not "the code looks fine".

SAFETY. This EXECUTES the submitted module (its top-level code too). Therefore:
  * it is OFF unless ``VISHAP_PROVE=1``;
  * it runs only inside bubblewrap (no network, read-only file system, private /tmp) unless
    ``VISHAP_PROVE_UNISOLATED=1`` is also set: use that only for code you would run anyway;
  * the child gets a clean environment (no keys), CPU/memory limits and a hard timeout;
  * inside the child every file/process/network function is replaced by a recorder
    (src/tools/proof_harness.py).
Scope today: Flask-style handlers, sqlite3. FastAPI/Express and other database libraries are
reported as INCONCLUSIVE, never as safe. A race (check-then-act) cannot be proven without a real
database and stays a suspicion.
"""
from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).with_name("proof_harness.py")

#: finding id -> checks that can prove it (any CONFIRMED check proves it)
CHECKS_FOR = {
    "sqli-concat": ("sqli",), "sqli-fstring": ("sqli",),
    "cmd-injection-py": ("cmdi",), "shell-true": ("cmdi",),
    "path-traversal": ("traversal", "traversal_abs"), "path-traversal-sendfile": ("traversal", "traversal_abs"),
    "route-amount-no-bounds": ("amount",), "route-no-auth": ("auth",),
}


def proof_enabled() -> bool:
    return os.environ.get("VISHAP_PROVE", "").strip().lower() in ("1", "true", "yes")


@functools.lru_cache(maxsize=1)
def isolation_level() -> str:
    """'bwrap' (contained), 'unshare' (network only) or 'process' (no containment)."""
    if os.name != "posix":
        return "process"
    if shutil.which("bwrap"):
        try:
            r = subprocess.run(["bwrap", "--unshare-all", "--die-with-parent", "--ro-bind", "/", "/",
                                "--dev", "/dev", "--proc", "/proc", "true"],
                               capture_output=True, timeout=10)
            if r.returncode == 0:
                return "bwrap"
        except Exception:
            pass
    if shutil.which("unshare"):
        try:
            if subprocess.run(["unshare", "--net", "--map-root-user", "true"], capture_output=True, timeout=10).returncode == 0:
                return "unshare"
        except Exception:
            pass
    return "process"


def proof_allowed() -> tuple[bool, str]:
    """(allowed, reason). Containment is required unless the operator opts out explicitly."""
    if not proof_enabled():
        return False, "proof is off (set VISHAP_PROVE=1)"
    level = isolation_level()
    if level == "bwrap":
        return True, "bwrap"
    if os.environ.get("VISHAP_PROVE_UNISOLATED", "").strip().lower() in ("1", "true", "yes"):
        return True, level + " (unisolated, operator opted in)"
    return False, f"no containment available ({level}); set VISHAP_PROVE_UNISOLATED=1 only for code you trust"


def _limits():  # pragma: no cover - runs in the child between fork and exec
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
    resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))


def _run_harness(code: str, timeout: int = 20, force: bool = False) -> dict:
    """Run the harness on ``code``; return its JSON document or {"error": ...}."""
    if not force:
        ok, why = proof_allowed()
        if not ok:
            return {"error": why, "results": [], "handlers": 0, "notes": []}
    level = isolation_level()
    tmp = tempfile.mkdtemp(prefix="vishap_proof_")
    try:
        target = Path(tmp) / "target.py"
        target.write_text(code, encoding="utf-8")
        try:
            from src.pipeline.sandbox import _sandbox_env
            env = _sandbox_env(tmp)
        except Exception:
            env = {"PATH": os.environ.get("PATH", ""), "VISHAP_SANDBOX": "1"}
        # A virtualenv lives under /home, which the sandbox hides. The harness is stdlib-only, so run it with
        # the real interpreter (venv python is a symlink) and, if that interpreter itself lives under /home or
        # /root (pyenv, uv), put just its prefix back read-only.
        exe = os.path.realpath(sys.executable)
        cmd = [exe, "-I", str(HARNESS), str(target)]
        kw: dict = {}
        if level == "bwrap":
            visible = []
            for d in {os.path.realpath(sys.base_prefix), os.path.dirname(exe)}:
                if d.startswith(("/home/", "/root/")):
                    visible += ["--ro-bind", d, d]
            cmd = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--ro-bind", "/", "/",
                   "--tmpfs", "/root", "--tmpfs", "/home"] + visible + [
                   "--bind", tmp, tmp, "--dev", "/dev", "--proc", "/proc", "--chdir", tmp] + cmd
        elif level == "unshare":
            cmd = ["unshare", "--net", "--map-root-user"] + cmd
        if os.name == "posix":
            kw["preexec_fn"] = _limits
        elif os.name == "nt":
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            p = subprocess.run(cmd, cwd=tmp, env=env, capture_output=True, text=True, timeout=timeout, **kw)
        except subprocess.TimeoutExpired:
            return {"error": f"proof run timed out after {timeout}s", "results": [], "handlers": 0, "notes": []}
        lines = [ln for ln in (p.stdout or "").splitlines() if ln.startswith("{")]
        if not lines:
            return {"error": "harness produced no result: " + (p.stderr or "")[-200:], "results": [], "handlers": 0, "notes": []}
        doc = json.loads(lines[-1])
        doc["isolation"] = level
        return doc
    except Exception as e:  # never break the analysis because the proof failed
        return {"error": f"{type(e).__name__}: {e}", "results": [], "handlers": 0, "notes": []}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def prove(code: str, findings: list | None = None, *, force: bool = False, timeout: int = 20) -> dict:
    """Run the probes. With ``findings``, annotate each one in place (finding['proof'], finding['status'])."""
    doc = _run_harness(code, timeout=timeout, force=force)
    if findings is not None and not doc.get("error"):
        annotate(findings, doc)
    doc["enabled"] = not (doc.get("error") or "").startswith(("proof is off", "no containment"))
    return doc


def annotate(findings: list, doc: dict) -> None:
    """Attach proof to the findings the checks can speak about. Others stay UNCONFIRMED."""
    results = doc.get("results") or []
    for f in findings:
        checks = CHECKS_FOR.get(f.get("id", ""))
        if not checks:
            f.setdefault("status", "UNCONFIRMED")
            continue
        line = int(f.get("line") or 0)
        mine = [r for r in results if r["check"] in checks and r["start"] <= line <= r["end"]]
        if not mine:
            f["status"] = "UNCONFIRMED"
            f["proof"] = {"status": "INCONCLUSIVE", "evidence": "line is not inside a handler the harness could run"}
            continue
        best = next((r for r in mine if r["status"] == "CONFIRMED"), None) \
            or next((r for r in mine if r["status"] == "NOT_REPRODUCED"), None) or mine[0]
        f["proof"] = {"status": best["status"], "check": best["check"], "evidence": best["evidence"],
                      "route": best["route"], "isolation": doc.get("isolation", "")}
        f["status"] = "CONFIRMED" if best["status"] == "CONFIRMED" else (
            "NOT_REPRODUCED" if best["status"] == "NOT_REPRODUCED" else "UNCONFIRMED")


def _confirmed(doc: dict) -> set:
    return {(r["function"], r["check"]) for r in doc.get("results", []) if r["status"] == "CONFIRMED"}


def verify_patch(original: str, patched: str, *, force: bool = False, timeout: int = 20) -> dict:
    """Did the patch close the exploits that worked before, and open none?"""
    try:
        import ast
        ast.parse(patched)
    except SyntaxError as e:
        return {"verdict": "REJECTED", "reason": f"patched code does not parse: {e.msg} (line {e.lineno})",
                "closed": [], "still_open": [], "regressions": []}
    before = _run_harness(original, timeout=timeout, force=force)
    if before.get("error"):
        return {"verdict": "CANNOT_VERIFY", "reason": before["error"], "closed": [], "still_open": [], "regressions": []}
    after = _run_harness(patched, timeout=timeout, force=force)
    if after.get("error"):
        return {"verdict": "CANNOT_VERIFY", "reason": "patched code: " + after["error"], "closed": [], "still_open": [], "regressions": []}
    b, a = _confirmed(before), _confirmed(after)
    names_before = {r["function"] for r in before["results"]}
    names_after = {r["function"] for r in after["results"]}
    removed = sorted(names_before - names_after)
    closed = sorted(b - a)
    still = sorted(b & a)
    regress = sorted(a - b)
    fmt = lambda xs: [f"{fn}:{chk}" for fn, chk in xs]  # noqa: E731
    if not b:
        verdict, reason = "CANNOT_VERIFY", "no exploit was reproducible before the patch, nothing to compare"
    elif regress:
        verdict, reason = "REGRESSION", "the patch opens a new exploitable path"
    elif still and not closed:
        verdict, reason = "NO_EFFECT", "every exploit that worked before still works"
    elif still:
        verdict, reason = "PARTIAL", "some exploits are closed, some still work"
    elif removed:
        verdict, reason = "SUSPICIOUS", "exploits are gone, but handlers were removed: " + ", ".join(removed)
    else:
        verdict, reason = "CLOSES_EXPLOITS", "every exploit that worked before no longer works"
    return {"verdict": verdict, "reason": reason, "closed": fmt(closed), "still_open": fmt(still),
            "regressions": fmt(regress), "removed_handlers": removed,
            "isolation": before.get("isolation", "")}


def render_verified_md(findings: list, doc: dict | None = None) -> str:
    """Short block that goes FIRST in a report: what was proven, what was not."""
    proven = [f for f in findings if f.get("status") == "CONFIRMED"]
    refuted = [f for f in findings if f.get("status") == "NOT_REPRODUCED"]
    if not proven and not refuted:
        return ""
    out = ["## Verified findings", ""]
    if doc and doc.get("isolation"):
        out += [f"_Probes were run against the submitted handlers (isolation: {doc['isolation']}). "
                "CONFIRMED means the exploit worked in that run; everything else is a suspicion._", ""]
    for f in proven:
        out.append(f"- **CONFIRMED** {f['title']} (line {f['line']}): {f['proof']['evidence'][:200]}")
    for f in refuted:
        out.append(f"- not reproduced: {f['title']} (line {f['line']}): {f['proof']['evidence'][:140]}")
    out.append("")
    return "\n".join(out)


def prove_cli(input_path: str, patched: str | None = None, unisolated: bool = False) -> int:
    """``vishap prove``: print what the probes found. Exit 0 = nothing confirmed / patch closes the exploits,
    1 = something confirmed / patch does not close them, 2 = could not run."""
    from src.tools.static_scan import scan_material

    os.environ["VISHAP_PROVE"] = "1"
    if unisolated:
        os.environ["VISHAP_PROVE_UNISOLATED"] = "1"
    path = Path(input_path)
    if not path.exists():
        print(f"Error: {path} not found", file=sys.stderr)
        return 2
    allowed, why = proof_allowed()
    if not allowed:
        print(f"proof:         NOT RUN ({why})", file=sys.stderr)
        return 2
    code = path.read_text(encoding="utf-8", errors="replace")
    scan = scan_material(code, path.name)
    doc = prove(code, scan["findings"])
    if doc.get("error"):
        print(f"proof:         ERROR ({doc['error']})", file=sys.stderr)
        return 2
    print(f"isolation:     {doc.get('isolation')}  handlers: {doc.get('handlers')}")
    confirmed = [f for f in scan["findings"] if f.get("status") == "CONFIRMED"]
    for f in scan["findings"]:
        pr = f.get("proof")
        if pr:
            print(f"  {pr['status']:15} {f['id']:26} line {f['line']:<4} {pr['evidence'][:110]}")
    print(f"confirmed:     {len(confirmed)} of {len(scan['findings'])} findings")
    if patched:
        fixed = Path(patched).read_text(encoding="utf-8", errors="replace")
        v = verify_patch(code, fixed)
        print(f"patch:         {v['verdict']} - {v['reason']}")
        for key in ("closed", "still_open", "regressions"):
            if v.get(key):
                print(f"  {key}: {', '.join(v[key])}")
        return 0 if v["verdict"] == "CLOSES_EXPLOITS" else 1
    return 1 if confirmed else 0
