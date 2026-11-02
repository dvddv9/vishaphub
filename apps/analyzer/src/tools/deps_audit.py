# -*- coding: utf-8 -*-
"""Dependency manifests: what the packages a project asks for say about its risk.

Reads requirements*.txt, pyproject.toml, package.json and package-lock.json from text (no files on disk).

Offline, always on (no network, nothing leaves the process):
  * packages pulled from a URL, VCS or local path (not what the registry vets);
  * a plain-http package index, an extra index (dependency confusion), a trusted-host override;
  * names one letter away from a very popular package (typosquatting);
  * dependencies with no exact version (one summary finding per manifest).

Online, opt-in (``VISHAP_DEPS_ONLINE=1`` or ``online=True``): only package *names and versions* are
sent - never code - to PyPI / the npm registry (does the package exist?) and to OSV (known advisories).
A package missing from the registry is the signature of a name a model invented; it can also be a
private package, so the finding says so. OSV's batch answer carries advisory ids but no score, so a
hit is reported as "high" and the ids are listed for a person to read.

Network failures are reported as ``degraded`` notes: a check that did not run is never silence.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

try:  # Python 3.11+
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]

MAX_DEPS = 400            # parse at most this many entries
MAX_ONLINE = 40           # look at most this many up on the network
FETCH_TIMEOUT = 8

POPULAR = {
    "PyPI": {
        "requests", "numpy", "pandas", "flask", "django", "scipy", "pytest", "urllib3", "boto3", "setuptools",
        "cryptography", "pillow", "sqlalchemy", "fastapi", "pydantic", "httpx", "aiohttp", "jinja2", "click",
        "pyyaml", "matplotlib", "tensorflow", "torch", "scikit-learn", "beautifulsoup4", "lxml", "openpyxl",
        "redis", "psycopg2", "uvicorn", "gunicorn", "celery", "selenium", "certifi", "packaging", "colorama",
        "tqdm", "rich", "typer", "python-dotenv", "anthropic", "openai", "langchain", "transformers", "pyjwt",
        "paramiko", "werkzeug", "markupsafe", "protobuf", "grpcio", "pytest-cov", "websockets", "starlette",
    },
    "npm": {
        "react", "lodash", "express", "axios", "moment", "webpack", "typescript", "vue", "next", "jquery",
        "chalk", "commander", "dotenv", "eslint", "prettier", "jest", "mocha", "react-dom", "underscore",
        "request", "async", "debug", "uuid", "bluebird", "rxjs", "tslib", "vite", "zod", "cors", "body-parser",
        "mongoose", "socket.io", "nodemon", "passport", "jsonwebtoken", "bcrypt", "cheerio", "puppeteer",
        "yargs", "glob", "minimist", "semver", "classnames", "redux", "tailwindcss", "postcss", "angular",
    },
}


@dataclass(frozen=True)
class Dep:
    name: str
    ecosystem: str          # "PyPI" | "npm"
    spec: str               # what the manifest wrote after the name
    version: str            # exact pinned version or ""
    line: int


# ---- detection and parsing -----------------------------------------------------------------------------------

_REQ_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)$")
_PINNED = re.compile(r"^===?\s*([0-9][A-Za-z0-9.!+_-]*)$")
# A version specifier, not any line that starts with "=": "x = 1" is Python, "x==1" is a requirement.
_ONE_SPEC = r"(?:===|==|~=|!=|<=|>=|<|>)\s*[A-Za-z0-9*][A-Za-z0-9.*!+_-]*"
_SPEC = re.compile(r"^" + _ONE_SPEC + r"(?:\s*,\s*" + _ONE_SPEC + r")*$")
_DIRECT_REF = re.compile(r"^(git\+|hg\+|svn\+|https?://|file:|\.{1,2}/|/)")
_SEMVER_EXACT = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")


def _norm(name: str, ecosystem: str) -> str:
    low = name.lower()
    return re.sub(r"[-_.]+", "-", low) if ecosystem == "PyPI" else low


def _req_line(raw: str) -> tuple[str, str] | None:
    """('name', 'rest') for a plain PEP 508 requirement line, else None."""
    line = raw.split(" #", 1)[0].split(";", 1)[0].strip()
    m = _REQ_NAME.match(line)
    if not m:
        return None
    rest = (m.group(3) or "").strip()
    if rest and not (_SPEC.match(rest) or rest.startswith("@")):
        return None
    return m.group(1), rest


def detect(filename: str, text: str) -> str | None:
    base = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    if base == "package.json":
        return "package.json"
    if base == "package-lock.json":
        return "package-lock"
    if base == "pyproject.toml":
        return "pyproject"
    if base.endswith(".txt") and ("requirements" in base or "constraints" in base):
        return "requirements"
    if base and base not in ("", "material"):
        # A named file that is not a manifest is never sniffed: code is code.
        return None
    body = (text or "").strip()
    if body.startswith("{"):
        try:
            data = json.loads(body)
        except ValueError:
            return None
        if isinstance(data, dict) and any(k in data for k in ("dependencies", "devDependencies")):
            return "package.json"
        return None
    lines = [ln.strip() for ln in body.splitlines()
             if ln.strip() and not ln.strip().startswith(("#", "-")) and not _DIRECT_REF.match(ln.strip())]
    if len(lines) < 2:
        return None
    parsed = [_req_line(ln) for ln in lines]
    if any(p is None for p in parsed):
        return None
    if sum(1 for p in parsed if p and p[1]) * 2 < len(parsed):
        return None
    # Without a file name the text must look like versions ("1.26"), or "a >= 3" lines of code would pass for one.
    if not any(p and "." in p[1] for p in parsed):
        return None
    return "requirements"


def _parse_requirements(text: str) -> tuple[list[Dep], list[dict]]:
    deps: list[Dep] = []
    config: list[dict] = []
    for n, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if len(deps) >= MAX_DEPS:
            break
        low = line.lower()
        if low.startswith(("--index-url", "-i ", "--extra-index-url", "--trusted-host", "--find-links", "-f ")):
            config.append({"line": n, "text": line})
            continue
        if line.startswith("-"):
            if line.startswith(("-e ", "--editable")):
                config.append({"line": n, "text": line, "direct": True})
            continue
        if _DIRECT_REF.match(line):
            config.append({"line": n, "text": line, "direct": True})
            continue
        got = _req_line(line)
        if not got:
            continue
        name, rest = got
        if rest.startswith("@"):
            config.append({"line": n, "text": line, "direct": True})
            continue
        m = _PINNED.match(rest.replace(" ", ""))
        deps.append(Dep(name, "PyPI", rest, m.group(1) if m and "*" not in rest else "", n))
    return deps, config


def _parse_pyproject(text: str) -> tuple[list[Dep], list[dict]]:
    deps: list[Dep] = []
    config: list[dict] = []
    if tomllib is None:
        return deps, config
    try:
        data = tomllib.loads(text)
    except Exception:  # noqa: BLE001 - a broken file is "no dependencies read", reported by the caller
        return deps, config
    where = {}
    for n, raw in enumerate(text.splitlines(), start=1):
        for m in re.finditer(r"""["']([A-Za-z0-9][A-Za-z0-9._-]*)""", raw):
            where.setdefault(m.group(1).lower(), n)
    strings: list[str] = list((data.get("project") or {}).get("dependencies") or [])
    for group in ((data.get("project") or {}).get("optional-dependencies") or {}).values():
        strings += list(group or [])
    for item in strings[:MAX_DEPS]:
        got = _req_line(str(item))
        if not got:
            continue
        name, rest = got
        m = _PINNED.match(rest.replace(" ", ""))
        deps.append(Dep(name, "PyPI", rest, m.group(1) if m and "*" not in rest else "", where.get(name.lower(), 0)))
    poetry = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
    for name, spec in list(poetry.items())[:MAX_DEPS]:
        if name.lower() == "python":
            continue
        s = spec if isinstance(spec, str) else str((spec or {}).get("version", ""))
        exact = s if re.match(r"^[0-9][A-Za-z0-9.+_-]*$", s) else ""
        deps.append(Dep(name, "PyPI", s, exact, where.get(name.lower(), 0)))
    return deps, config


def _parse_package_json(text: str) -> tuple[list[Dep], list[dict]]:
    deps: list[Dep] = []
    config: list[dict] = []
    try:
        data = json.loads(text)
    except ValueError:
        return deps, config
    if not isinstance(data, dict):
        return deps, config
    lines = text.splitlines()

    def at(name: str) -> int:
        needle = json.dumps(name)
        return next((i for i, ln in enumerate(lines, start=1) if needle in ln), 0)

    for group in ("dependencies", "devDependencies", "optionalDependencies"):
        table = data.get(group)
        if not isinstance(table, dict):
            continue
        for name, spec in list(table.items())[:MAX_DEPS]:
            s = str(spec).strip()
            n = at(name)
            if re.match(r"^(git\+|git:|github:|https?:|file:|link:|\.{1,2}/|/|[\w.-]+/[\w.-]+(#.*)?$)", s) and not s.startswith("@"):
                config.append({"line": n, "text": f"{name}: {s}", "direct": True})
                continue
            deps.append(Dep(name, "npm", s, s if _SEMVER_EXACT.match(s) else "", n))
    return deps, config


def _parse_package_lock(text: str) -> tuple[list[Dep], list[dict]]:
    """Read exact npm versions from v1/v2/v3 lockfiles; line numbers use the lockfile root."""
    try:
        data = json.loads(text)
    except ValueError:
        return [], []
    if not isinstance(data, dict):
        return [], []
    deps: list[Dep] = []
    packages = data.get("packages")
    if isinstance(packages, dict):
        for path, meta in packages.items():
            if not isinstance(meta, dict) or not meta.get("version") or "node_modules/" not in path:
                continue
            name = path.rsplit("node_modules/", 1)[-1]
            version = str(meta["version"])
            deps.append(Dep(name, "npm", version, version, 1))
    else:
        def visit(tree: dict, depth: int = 0) -> None:
            if depth > 64:
                return
            for name, meta in tree.items():
                if not isinstance(meta, dict):
                    continue
                version = str(meta.get("version") or "")
                if version:
                    deps.append(Dep(name, "npm", version, version, 1))
                children = meta.get("dependencies")
                if isinstance(children, dict):
                    visit(children, depth + 1)
        visit(data.get("dependencies") or {})
    return deps[:MAX_DEPS], []


# ---- findings -----------------------------------------------------------------------------------------------

def _finding(rid: str, title: str, severity: str, cwe: str, line: int, snippet: str, fix: str) -> dict:
    return {"id": rid, "title": title, "severity": severity, "cwe": cwe, "kind": "security",
            "line": int(line or 1), "snippet": snippet[:160], "fix": fix, "source": "deps"}


def _within_one(a: str, b: str) -> bool:
    if a == b:
        return False
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diffs = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diffs) == 1:
            return True
        return len(diffs) == 2 and diffs[1] == diffs[0] + 1 and a[diffs[0]] == b[diffs[1]] and a[diffs[1]] == b[diffs[0]]
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def _typosquat(dep: Dep) -> str | None:
    name = _norm(dep.name, dep.ecosystem)
    popular = POPULAR[dep.ecosystem]
    if name in popular or len(name) < 5:
        return None
    return next((p for p in sorted(popular) if len(p) >= 5 and _within_one(name, p)), None)


def offline_findings(deps: list[Dep], config: list[dict]) -> list[dict]:
    out: list[dict] = []
    for c in config:
        low = c["text"].lower()
        if c.get("direct"):
            out.append(_finding(
                "deps-direct-url", "Dependency taken from a URL, VCS or local path", "medium", "CWE-829", c["line"],
                c["text"], "Install from the registry with an exact version (and a hash), or vendor and review the code."))
        elif low.startswith(("--index-url", "-i ")) and "http://" in low:
            out.append(_finding(
                "deps-index-http", "Package index over plain http", "high", "CWE-319", c["line"], c["text"],
                "Use https for every index; plain http lets anyone on the path swap the packages."))
        elif low.startswith("--extra-index-url"):
            out.append(_finding(
                "deps-extra-index", "Extra package index (dependency confusion risk)", "medium", "CWE-427", c["line"],
                c["text"], "Pin the private index as the only index, or reserve your private names on the public one."))
        elif low.startswith("--trusted-host"):
            out.append(_finding(
                "deps-trusted-host", "Package host trusted without certificate verification", "medium", "CWE-295",
                c["line"], c["text"], "Remove --trusted-host and fix the certificate instead."))
    for d in deps:
        near = _typosquat(d)
        if near:
            out.append(_finding(
                "deps-typosquat", f"Package name is one letter from the popular '{near}'", "medium", "CWE-1357",
                d.line, f"{d.name}{d.spec}", f"Confirm '{d.name}' is the package you meant and not a lookalike of '{near}'."))
    loose = [d for d in deps if not d.version]
    if loose:
        names = ", ".join(d.name for d in loose[:8]) + (" ..." if len(loose) > 8 else "")
        out.append(_finding(
            "deps-unpinned", f"{len(loose)} of {len(deps)} dependencies have no exact version", "low", "CWE-1104",
            loose[0].line, names, "Pin exact versions (or commit a lockfile) so a new release cannot change what runs."))
    return out


# ---- online (opt-in) ----------------------------------------------------------------------------------------

def online_enabled() -> bool:
    return os.environ.get("VISHAP_DEPS_ONLINE", "").strip().lower() in ("1", "true", "yes", "on")


def _http_fetch(url: str, payload: dict | None = None) -> tuple[int, object]:
    """(status, parsed json or None); status 0 means the request itself failed."""
    if not url.startswith("https://"):
        return 0, None
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": "vishap-deps-audit", "Accept": "application/json",
        **({"Content-Type": "application/json"} if data else {})})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:  # noqa: S310 - https only, checked above
            return resp.status, json.loads(resp.read(2_000_000).decode("utf-8", "replace") or "null")
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:  # noqa: BLE001 - reported as degraded by the caller
        return 0, None


def _registry_url(dep: Dep) -> str:
    if dep.ecosystem == "PyPI":
        return f"https://pypi.org/pypi/{urllib.parse.quote(dep.name)}/json"
    return "https://registry.npmjs.org/" + urllib.parse.quote(dep.name, safe="@").replace("/", "%2F")


def online_findings(deps: list[Dep], fetch=None) -> tuple[list[dict], list[str]]:
    fetch = fetch or _http_fetch
    out: list[dict] = []
    degraded: list[str] = []
    look = deps[:MAX_ONLINE]
    if len(deps) > MAX_ONLINE:
        degraded.append(f"online checks covered the first {MAX_ONLINE} of {len(deps)} dependencies")
    failed = 0
    for d in look:
        status, _ = fetch(_registry_url(d), None)
        if status == 404:
            out.append(_finding(
                "deps-missing", f"'{d.name}' is not in the {d.ecosystem} registry", "high", "CWE-1357", d.line,
                f"{d.name}{d.spec}",
                "A package no registry knows is often a name a model invented, which an attacker can then register. "
                "Confirm it is a private package or remove it."))
        elif status != 200:
            failed += 1
    pinned = [d for d in look if d.version]
    if pinned:
        queries = [{"package": {"name": d.name, "ecosystem": d.ecosystem}, "version": d.version} for d in pinned]
        status, body = fetch("https://api.osv.dev/v1/querybatch", {"queries": queries})
        results = (body or {}).get("results") if isinstance(body, dict) else None
        if status == 200 and isinstance(results, list) and len(results) == len(pinned):
            for d, res in zip(pinned, results):
                vulns = (res or {}).get("vulns") or []
                if vulns:
                    ids = ", ".join(str(v.get("id")) for v in vulns[:5] if isinstance(v, dict))
                    out.append(_finding(
                        "deps-vulnerable", f"{d.name} {d.version} has {len(vulns)} known advisor"
                        f"{'y' if len(vulns) == 1 else 'ies'} (OSV)", "high", "CWE-1395", d.line,
                        f"{d.name}=={d.version}: {ids}",
                        "Upgrade to a fixed version; read the advisories, severity is not in the batch answer."))
        else:
            degraded.append("the vulnerability lookup (OSV) did not answer; known advisories were not checked")
    if failed:
        degraded.append(f"{failed} registry lookups failed; those packages were not checked for existence")
    return out, degraded


# ---- entry point --------------------------------------------------------------------------------------------

def audit(filename: str, text: str, *, online: bool | None = None, fetch=None) -> dict | None:
    """None when the text is not a dependency manifest; otherwise {"findings", "degraded", "deps", "kind"}."""
    kind = detect(filename, text)
    if not kind:
        return None
    parse = {"requirements": _parse_requirements, "pyproject": _parse_pyproject,
             "package.json": _parse_package_json, "package-lock": _parse_package_lock}[kind]
    deps, config = parse(text)
    findings = offline_findings(deps, config)
    degraded: list[str] = []
    if not deps and not config:
        degraded.append("no dependencies could be read from this file")
    if online if online is not None else online_enabled():
        more, notes = online_findings(deps, fetch)
        findings += more
        degraded += notes
    else:
        degraded.append("online checks are off (VISHAP_DEPS_ONLINE): package existence and known advisories were not checked")
    return {"kind": kind, "deps": len(deps), "findings": findings, "degraded": degraded}
