# -*- coding: utf-8 -*-
"""Scan a whole directory (or just what a diff added) with the built-in rule engine.

One pasted file is a toy; a review happens on a repository or a pull request. This module walks a
tree (no LLM, no network unless ``--deps`` is asked for), runs ``static_scan.scan_material`` on every
code/config file, gives each finding a stable fingerprint (file + rule + code, never the line number),
and can:

    * compare with a saved baseline            -> "2 new, 1 fixed, 40 unchanged"
    * keep only findings on lines a diff added -> what THIS pull request introduced
    * audit pinned dependencies against OSV    -> real advisories, not a guess (needs network)
    * write SARIF with one location per file   -> GitHub code scanning
    * optionally run the proof probes on handler files (--prove, executes code, isolated)

It does not follow symlinks, skips big files and vendored directories, and never executes anything
unless proof is explicitly requested.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from src.tools.findings_diff import assign_fingerprints, diff_findings, load_baseline, render_diff_md, save_baseline
from src.tools.static_scan import SEV_ORDER, scan_material, to_rules_view

CODE_EXT = {".py", ".pyw", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".java", ".c", ".h", ".cc", ".cpp", ".hpp",
            ".go", ".php", ".tf", ".tfvars", ".yml", ".yaml", ".sh"}
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "env", "__pycache__", "dist", "build", ".next", "target",
             "vendor", "site-packages", ".tox", ".mypy_cache", ".pytest_cache", "_to_delete", ".idea", ".vscode"}
SKIP_PREFIX = ("_backup", "_docs_backup", "_logs_")


def _is_code_file(name: str) -> bool:
    low = name.lower()
    return Path(low).suffix in CODE_EXT or low == "dockerfile" or low.startswith("dockerfile.")


def scan_repo(root: str, *, only: set | None = None, max_files: int = 2000, max_file_bytes: int = 400_000,
              exclude: tuple = ()) -> dict:
    """Scan every code/config file under ``root`` (or only the relative paths in ``only``)."""
    base = Path(root).resolve()
    findings: list[dict] = []
    routes: list[dict] = []
    skipped: list[dict] = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith(SKIP_PREFIX)
                             and not os.path.islink(os.path.join(dirpath, d)))
        for name in sorted(filenames):
            full = Path(dirpath) / name
            rel = full.relative_to(base).as_posix()
            if only is not None and rel not in only:
                continue
            if not _is_code_file(name) or any(re.search(p, rel) for p in exclude):
                continue
            if full.is_symlink():
                skipped.append({"file": rel, "reason": "symlink"})
                continue
            try:
                size = full.stat().st_size
            except OSError:
                continue
            if size > max_file_bytes:
                skipped.append({"file": rel, "reason": f"larger than {max_file_bytes} bytes"})
                continue
            if scanned >= max_files:
                skipped.append({"file": rel, "reason": f"max_files={max_files} reached"})
                continue
            text = full.read_text(encoding="utf-8", errors="replace")
            res = scan_material(text, rel)
            scanned += 1
            for f in res["findings"]:
                f = dict(f)
                f["file"] = rel
                findings.append(f)
            for r in res.get("routes", []):
                routes.append({**r, "file": rel})
    findings.sort(key=lambda f: (SEV_ORDER.get(f["severity"], 9), f["file"], f["line"]))
    by_sev = {s: sum(1 for f in findings if f["severity"] == s) for s in SEV_ORDER}
    return {"root": str(base), "files_scanned": scanned, "files_skipped": skipped, "findings": findings,
            "routes": routes, "by_severity": by_sev, "total_findings": len(findings),
            "logic_findings": sum(1 for f in findings if f.get("kind") == "logic")}


# ----------------------------------------------------------------------------- diff
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def parse_diff(diff_text: str) -> dict:
    """{relative_path: set(added line numbers)} from a unified diff."""
    added: dict[str, set] = {}
    path = None
    new_line = 0
    for line in (diff_text or "").splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip().split("\t")[0]
            path = None if target == "/dev/null" else (target[2:] if target.startswith("b/") else target)
            if path is not None:
                added.setdefault(path, set())
            continue
        m = _HUNK.match(line)
        if m:
            new_line = int(m.group(1))
            continue
        if path is None or line.startswith(("--- ", "diff ", "index ", "\\")):
            continue
        if line.startswith("+"):
            added[path].add(new_line)
            new_line += 1
        elif line.startswith("-"):
            continue
        else:
            new_line += 1
    return added


def scan_diff(root: str, diff_text: str, **kw) -> dict:
    """Scan the files a diff touches and keep only findings on lines the diff added."""
    added = parse_diff(diff_text)
    res = scan_repo(root, only={p for p, ls in added.items() if ls}, **kw)
    res["findings"] = [f for f in res["findings"] if f["line"] in added.get(f["file"], set())]
    res["by_severity"] = {s: sum(1 for f in res["findings"] if f["severity"] == s) for s in SEV_ORDER}
    res["total_findings"] = len(res["findings"])
    res["logic_findings"] = sum(1 for f in res["findings"] if f.get("kind") == "logic")
    res["diff_files"] = sorted(added)
    return res


# ----------------------------------------------------------------------------- dependencies (OSV)
OSV_BATCH = "https://api.osv.dev/v1/querybatch"
OSV_VULN = "https://api.osv.dev/v1/vulns/"
_REQ = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*(==|>=|<=|~=|!=|>|<|===)?\s*([A-Za-z0-9._+!*-]*)")
_OSV_SEV = {"CRITICAL": "critical", "HIGH": "high", "MODERATE": "medium", "MEDIUM": "medium", "LOW": "low"}


def parse_requirements(text: str) -> tuple[list, list]:
    """([(name, version, line)] for pinned ==, [(name, line, spec)] for the rest)."""
    pinned, loose = [], []
    for i, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.split("#", 1)[0].split(";", 1)[0].strip()
        if not line or line.startswith(("-", "git+", "http")):
            continue
        m = _REQ.match(line)
        if not m:
            continue
        name, op, ver = m.group(1), m.group(2), m.group(3)
        if op in ("==", "===") and ver and "*" not in ver:
            pinned.append((name, ver, i))
        else:
            loose.append((name, i, line))
    return pinned, loose


def parse_package_lock(text: str) -> list:
    try:
        data = json.loads(text)
    except ValueError:
        return []
    out = []
    pk = data.get("packages")
    if isinstance(pk, dict):
        for path, meta in pk.items():
            if path and isinstance(meta, dict) and meta.get("version") and "node_modules/" in path:
                out.append((path.rsplit("node_modules/", 1)[-1], meta["version"], 1))
    elif isinstance(data.get("dependencies"), dict):
        for name, meta in data["dependencies"].items():
            if isinstance(meta, dict) and meta.get("version"):
                out.append((name, meta["version"], 1))
    return out


def _http_json(url: str, payload: dict | None = None, timeout: int = 12) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json",
                                                         "User-Agent": "vishap-sca"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed https endpoint)
        return json.loads(r.read().decode("utf-8"))


def _fixed_versions(vuln: dict) -> list:
    fixed = []
    for aff in vuln.get("affected", []) or []:
        for rng in aff.get("ranges", []) or []:
            for ev in rng.get("events", []) or []:
                if ev.get("fixed"):
                    fixed.append(ev["fixed"])
    return sorted(set(fixed))


def check_osv(packages: list, ecosystem: str, *, post=None, get=None, max_details: int = 60) -> dict:
    """Query OSV for [(name, version, line)]. Fail-open: an outage returns available=False, never raises."""
    post = post or (lambda url, payload: _http_json(url, payload))
    get = get or (lambda url: _http_json(url))
    if not packages:
        return {"available": True, "vulnerabilities": []}
    try:
        queries = [{"package": {"name": n, "ecosystem": ecosystem}, "version": v} for n, v, _ in packages]
        resp = post(OSV_BATCH, {"queries": queries})
        vulns = []
        details = 0
        for (name, version, line), res in zip(packages, resp.get("results", [])):
            for v in (res or {}).get("vulns", []) or []:
                info = {}
                if details < max_details:
                    try:
                        info = get(OSV_VULN + v["id"])
                        details += 1
                    except Exception:
                        info = {}
                sev = _OSV_SEV.get(str((info.get("database_specific") or {}).get("severity", "")).upper(), "high")
                vulns.append({"name": name, "version": version, "line": line, "id": v["id"], "severity": sev,
                              "ecosystem": ecosystem, "fix_versions": _fixed_versions(info),
                              "description": (info.get("summary") or info.get("details") or "")[:200]})
        return {"available": True, "vulnerabilities": vulns}
    except (urllib.error.URLError, OSError, ValueError, KeyError, TimeoutError) as e:
        return {"available": False, "error": f"{type(e).__name__}: {e}", "vulnerabilities": []}


def scan_dependencies(root: str, *, post=None, get=None) -> dict:
    """Find requirements*.txt / package-lock.json (3 levels deep) and audit pinned versions with OSV."""
    base = Path(root).resolve()
    findings: list[dict] = []
    files, errors = [], []
    packages = 0
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        depth = len(Path(dirpath).relative_to(base).parts)
        dirnames[:] = [] if depth >= 3 else sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            low = name.lower()
            full = Path(dirpath) / name
            rel = full.relative_to(base).as_posix()
            if low.startswith("requirements") and low.endswith(".txt"):
                eco, (pinned, loose) = "PyPI", parse_requirements(full.read_text(encoding="utf-8", errors="replace"))
            elif low == "package-lock.json":
                eco, pinned, loose = "npm", parse_package_lock(full.read_text(encoding="utf-8", errors="replace")), []
            else:
                continue
            files.append(rel)
            packages += len(pinned)
            for n, ln, spec in loose:
                findings.append({"id": "dep-unpinned", "title": f"{n} is not pinned to one version",
                                 "severity": "low", "cwe": "", "kind": "logic", "line": ln, "file": rel,
                                 "snippet": spec[:160],
                                 "fix": "Pin with == (or a lock file) so an audit knows which version actually runs."})
            res = check_osv(pinned, eco, post=post, get=get)
            if not res["available"]:
                errors.append(f"{rel}: {res.get('error')}")
            for v in res["vulnerabilities"]:
                fix = (f"Upgrade to {', '.join(v['fix_versions'][:3])}." if v["fix_versions"] else "No fixed version listed; check the advisory.")
                findings.append({"id": "dep-vuln", "title": f"{v['name']}=={v['version']}: {v['id']}",
                                 "severity": v["severity"], "cwe": "CWE-1395", "kind": "security", "line": v["line"],
                                 "file": rel, "snippet": f"{v['name']}=={v['version']}", "fix": fix + " " + v["description"]})
    return {"available": not errors, "errors": errors, "files": files, "packages": packages, "findings": findings}


# ----------------------------------------------------------------------------- output
def render_scan_md(result: dict, diff: dict | None = None, limit: int = 40) -> str:
    sev = result.get("by_severity", {})
    out = ["# Vishap scan", "",
           f"**Files scanned:** {result['files_scanned']} · **Findings:** {result['total_findings']} "
           f"({', '.join(f'{sev.get(s, 0)} {s}' for s in SEV_ORDER)}) · **Logic:** {result.get('logic_findings', 0)}", ""]
    if result.get("files_skipped"):
        out += [f"_Skipped {len(result['files_skipped'])} file(s): " +
                ", ".join(f"{s['file']} ({s['reason']})" for s in result['files_skipped'][:5]) + "_", ""]
    if diff:
        out += [render_diff_md(diff)]
    deps = result.get("deps")
    if deps is not None:
        out.append(f"**Dependencies:** {deps['packages']} pinned package(s) in {len(deps['files'])} file(s)"
                   + (f" · OSV unavailable: {'; '.join(deps['errors'])}" if deps.get("errors") else ""))
        out.append("")
    shown = (diff["new"] if diff else result["findings"])[:limit]
    if shown:
        out += ["| Severity | File:line | Finding | Proof |", "|---|---|---|---|"]
        for f in shown:
            proof = f.get("status") if f.get("status") in ("CONFIRMED", "NOT_REPRODUCED", "INCONCLUSIVE") else ""
            out.append(f"| {f['severity']} | `{f['file']}:{f['line']}` | {f['title']} | {proof} |")
        rest = len(diff["new"] if diff else result["findings"]) - len(shown)
        if rest > 0:
            out.append(f"\n…and {rest} more (see --json).")
    else:
        out.append("No findings." if not diff else "No new findings.")
    out.append("")
    return "\n".join(out)


def scan_cli(path: str, *, baseline: str | None = None, save_baseline_path: str | None = None,
             diff_file: str | None = None, deps: bool = False, sarif: str | None = None,
             json_out: str | None = None, output: str | None = None, fail_on: str | None = None,
             prove_handlers: bool = False, exclude: tuple = (), max_files: int = 2000) -> int:
    """``vishap scan``. Exit 0 = ok, 1 = gate failed (finding at/above --fail-on, new ones only with a baseline), 2 = error."""
    root = Path(path)
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 2
    if diff_file:
        text = sys.stdin.read() if diff_file == "-" else Path(diff_file).read_text(encoding="utf-8", errors="replace")
        result = scan_diff(str(root), text, exclude=exclude, max_files=max_files)
    else:
        result = scan_repo(str(root), exclude=exclude, max_files=max_files)
    if deps:
        d = scan_dependencies(str(root))
        result["deps"] = d
        result["findings"] = sorted(result["findings"] + d["findings"],
                                    key=lambda f: (SEV_ORDER.get(f["severity"], 9), f["file"], f["line"]))
        result["total_findings"] = len(result["findings"])
        result["by_severity"] = {s: sum(1 for f in result["findings"] if f["severity"] == s) for s in SEV_ORDER}
    # one identity scheme for everything: file + rule + code (never the line)
    seen: dict[str, list] = {}
    for f in result["findings"]:
        seen.setdefault(f["file"], []).append(f)
    for fname, fs in seen.items():
        assign_fingerprints(fs, fname)
    if prove_handlers:
        from src.tools.proof import proof_allowed, prove
        os.environ["VISHAP_PROVE"] = "1"
        ok, why = proof_allowed()
        if not ok:
            print(f"proof:         NOT RUN ({why})", file=sys.stderr)
        else:
            for fname, fs in seen.items():
                if fname.endswith(".py") and any(f["id"] in ("sqli-fstring", "sqli-concat", "route-no-auth", "path-traversal-sendfile",
                                                              "path-traversal", "route-amount-no-bounds", "cmd-injection-py") for f in fs):
                    code = (root / fname).read_text(encoding="utf-8", errors="replace")
                    prove(code, fs)
    diff = None
    if baseline:
        diff = diff_findings(load_baseline(baseline), result["findings"])
    if save_baseline_path:
        n = save_baseline(result["findings"], save_baseline_path)
        print(f"baseline_saved: {n} fingerprints -> {save_baseline_path}")
    md = render_scan_md(result, diff)
    if output:
        Path(output).write_text(md, encoding="utf-8")
        print(f"Written: {output}")
    else:
        print(md)
    if json_out:
        Path(json_out).write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    if sarif:
        from src.tools.sarif import to_sarif, write_sarif
        sast_like = {"vishap_rules": {"available": True, "findings": to_rules_view(result["findings"])}}
        write_sarif(to_sarif({}, sast_result=sast_like, source_file="."), sarif)
        print(f"sarif:         {sarif} ({len(result['findings'])} results)")
    if fail_on:
        floor = SEV_ORDER.get(fail_on.lower(), 9)
        pool = diff["new"] if diff else result["findings"]
        bad = [f for f in pool if SEV_ORDER.get(f["severity"], 9) <= floor]
        if bad:
            print(f"gate:          FAILED ({len(bad)} {'new ' if diff else ''}finding(s) at or above {fail_on})", file=sys.stderr)
            return 1
        print(f"gate:          PASSED (nothing {'new ' if diff else ''}at or above {fail_on})")
    return 0
