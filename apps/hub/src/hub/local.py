"""In-process services: the hub calls the libraries, not URLs.

One URL means one process. Calling `https://…/analyze` over the network from inside
the same product buys nothing and costs a cold start, a timeout and a second place
where a key can be misconfigured.

This module wraps each component so the pipeline can run them locally:

* the validator is a plain function over a temp directory;
* the analyser's static rules are a plain function over text — no model, no network;
* the generator is deliberately absent: it needs a model and a workspace, and running
  it in-process is a separate decision, not an accident of plumbing.

Each wrapper returns the same shape the remote adapters did, so ``pipeline`` does not
care which one it is talking to.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import threading

MAX_FILES = 200

# Worker containers: how many run at once, and how long a caller waits for a free slot. A busy hub says so
# ("all validation workers are busy") instead of queueing without bound or running code unprotected.
_SLOTS = threading.BoundedSemaphore(max(1, int(os.getenv("VISHAP_HUB_WORKER_SLOTS", "2"))))
SLOT_WAIT_SECONDS = 30


def _spec_dict(spec: dict) -> dict:
    return {"language": spec.get("language", "python"), "files": list(spec.get("files", [])),
            "exports": list(spec.get("exports", [])), "tests": list(spec.get("tests", [])),
            "entry": spec.get("entry", "")}


def _validate_in_worker(root: str, spec: dict, image: str) -> dict:
    """One throw-away container per run (VISHAP_HUB_WORKER_IMAGE). Never falls back to the host."""
    try:
        from validator.container import run_in_container
    except ImportError:
        return {"ok": False, "error": "validator is not installed in this image"}
    if not _SLOTS.acquire(timeout=SLOT_WAIT_SECONDS):
        return {"ok": False, "error": "all validation workers are busy"}
    try:
        result = run_in_container(root, _spec_dict(spec), image=image,
                                  timeout=int(os.getenv("VISHAP_HUB_WORKER_TIMEOUT", "120")),
                                  docker=os.getenv("VISHAP_HUB_DOCKER", "docker"))
    finally:
        _SLOTS.release()
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error") or "the worker produced no report"}
    return {"ok": True, "report": result["report"],
            "isolation": {"kind": "container", "image": image, "container": result.get("name", ""),
                          "cleanup_confirmed": bool(result.get("cleanup_confirmed"))}}

def _materialize(files: dict) -> tuple[str, int]:
    """Write {path: text} into a fresh temp directory; paths that climb out are dropped. (root, written)."""
    root = tempfile.mkdtemp(prefix="hub-exploit-")
    written = 0
    for rel, text in (files or {}).items():
        if not isinstance(rel, str) or not isinstance(text, str):
            continue
        safe = os.path.normpath(rel).lstrip("\\/")
        if safe.startswith("..") or os.path.isabs(safe):
            continue
        target = os.path.join(root, safe)
        os.makedirs(os.path.dirname(target) or root, exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(text)
        written += 1
    return root, written


def run_exploits(files: dict, targets: list, *, require_netns: bool = True) -> dict:
    """The trusted exploit probes (validator.exploits) against `files`. Same isolation demand as the checks:
    a worker container when VISHAP_HUB_WORKER_IMAGE is set, otherwise only a network namespace. Never on the
    bare host. Returns {"ok", "exploits": [{"class", "entry", "result", "evidence"}]} or {"ok": False, "error"}.
    """
    if not isinstance(files, dict) or not files:
        return {"ok": False, "error": "no files to attack"}
    if len(files) > MAX_FILES:
        return {"ok": False, "error": f"too many files (>{MAX_FILES})"}
    root, written = _materialize(files)
    try:
        if not written:
            return {"ok": False, "error": "no usable files after sanitisation"}
        image = os.getenv("VISHAP_HUB_WORKER_IMAGE", "")
        if image and require_netns:
            return _exploits_in_worker(root, targets, image)
        try:
            from validator import exploits
            from validator.safe import refusal
        except ImportError:
            return {"ok": False, "error": "validator is not installed in this image"}
        why = refusal(require_netns=require_netns)
        if why:
            return {"ok": False, "error": why}
        return {"ok": True, "exploits": exploits.run_targets(root, targets)}
    except Exception as exc:  # noqa: BLE001 - reported, never silent
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _exploits_in_worker(root: str, targets: list, image: str) -> dict:
    try:
        from validator.container import run_in_container
    except ImportError:
        return {"ok": False, "error": "validator is not installed in this image"}
    if not _SLOTS.acquire(timeout=SLOT_WAIT_SECONDS):
        return {"ok": False, "error": "all validation workers are busy"}
    try:
        result = run_in_container(root, {"exploit_targets": list(targets)}, image=image, mode="exploits",
                                  timeout=int(os.getenv("VISHAP_HUB_WORKER_TIMEOUT", "120")),
                                  docker=os.getenv("VISHAP_HUB_DOCKER", "docker"))
    finally:
        _SLOTS.release()
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error") or "the worker produced no result"}
    answer = result["report"] or {}
    if answer.get("refused"):
        return {"ok": False, "error": answer["refused"]}
    return {"ok": True, "exploits": answer.get("exploits") or [],
            "isolation": {"kind": "container", "image": image, "cleanup_confirmed": bool(result.get("cleanup_confirmed"))}}

def validate_code(files: dict, spec: dict, *, require_netns: bool = True) -> dict:
    """Run the six-stage validator over a deliverable given as {path: text}."""
    try:
        from validator.engine import validate as run_validate
        from validator.models import Spec
    except ImportError:
        return {"ok": False, "error": "validator is not installed in this image"}

    if not isinstance(files, dict) or not files:
        return {"ok": False, "error": "no files to validate"}
    if len(files) > MAX_FILES:
        return {"ok": False, "error": f"too many files (>{MAX_FILES})"}

    root = tempfile.mkdtemp(prefix="hub-check-")
    try:
        written = 0
        for rel, text in files.items():
            if not isinstance(rel, str) or not isinstance(text, str):
                continue
            safe = os.path.normpath(rel).lstrip("\\/")
            if safe.startswith("..") or os.path.isabs(safe):
                continue  # a path that climbs out is not a deliverable
            target = os.path.join(root, safe)
            os.makedirs(os.path.dirname(target) or root, exist_ok=True)
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(text)
            written += 1

        # Nothing written means nothing was checked; reporting PASS here would be
        # the same fail-open the pipeline refuses one level up.
        if not written:
            return {"ok": False, "error": "no usable files after sanitisation"}

        image = os.getenv("VISHAP_HUB_WORKER_IMAGE", "")
        if image and require_netns:
            return _validate_in_worker(root, spec, image)

        report = run_validate(root, Spec(
            language=spec.get("language", "python"),
            files=list(spec.get("files", [])),
            exports=list(spec.get("exports", [])),
            tests=list(spec.get("tests", [])),
            entry=spec.get("entry", ""),
        ), require_netns=require_netns)
        return {"ok": True, "report": report.as_dict()}
    except Exception as exc:  # noqa: BLE001 - reported, never silent
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def analyse_static(material: str, model_verdict: str = "") -> dict:
    """Static rules only: no model, no network, a verdict in milliseconds.

    This is honest about what it is: `rules_only` in the report, so nobody mistakes a
    pattern match for a six-stage analysis.
    """
    try:
        from src.tools.safe_gate import decide
        from src.tools.static_scan import scan_material
    except ImportError:
        return {"ok": False, "error": "analyser is not installed in this image"}

    if not isinstance(material, str) or not material.strip():
        return {"ok": False, "error": "nothing to analyse"}

    try:
        scan = scan_material(material)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # scan_material returns a report, not a list: findings live under "findings".
    # Iterating the report itself yields its keys, which looked like a dozen findings
    # on a file with none — clean material was reported as REQUIRES_REVIEW.
    if isinstance(scan, dict):
        raw = scan.get("findings") or []
    elif isinstance(scan, (list, tuple)):
        raw = list(scan)
    else:
        raw = []

    items = []
    for finding in raw:
        if isinstance(finding, dict):
            # The scan names these `id`, `title`, `cwe`, `fix`; reading `message` and `detail` left every message empty.
            items.append({
                "rule": finding.get("rule") or finding.get("id") or finding.get("cwe") or "",
                "severity": finding.get("severity") or finding.get("priority") or "",
                "message": finding.get("message") or finding.get("title") or finding.get("detail") or "",
                "line": finding.get("line") or finding.get("lineno") or 0,
                "cwe": str(finding.get("cwe") or ""),
                "fix": str(finding.get("fix") or ""),
            })
        else:
            items.append({"rule": str(finding), "severity": "", "message": "", "line": 0, "cwe": "", "fix": ""})

    # SAFE is not "no findings". safe_gate.decide says SAFE only for a language whose rules have passed the registered
    # gates on an independent blind set, for a text the scan could read in full, with nothing found; every other
    # outcome is REQUIRES_REVIEW with the reason (tests/bench/blind_public/CRITERION.md).
    decision = decide(scan if isinstance(scan, dict) else {"findings": raw}, model_verdict=model_verdict)
    verdict = decision["verdict"]
    return {
        "ok": True,
        "verdict": verdict,
        "risk_verdict": verdict,
        "reason": decision["reason"],
        "meaning": decision["meaning"],
        "coverage": scan.get("coverage") if isinstance(scan, dict) else None,
        "cwe_ids": sorted({i["cwe"] or i["rule"] for i in items if i["cwe"] or i["rule"]}),
        "findings": items,
        "mode": "rules_only",
        "markdown": "",
        "raw": {"findings": items, "mode": "rules_only", "critical": decision["critical"]},
    }
