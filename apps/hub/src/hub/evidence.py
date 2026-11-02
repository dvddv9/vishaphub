"""What a run rests on, as data that goes into its fingerprint.

The fingerprint already fixed the input, the plan, the rule versions, the verdict and the steps. A
claim about a *fix* needs more: which snapshot the patch was made against, what the patch was, what
the checks ran on, under which sandbox profile, what each check said, how many attempts there were and
why they stopped, and whether the temporary environment was really cleaned up.

Everything here is deterministic: no time, no container name, no random id. Another run of the same
thing gives the same bytes, and another reader can recompute every hash from the files.
"""
from __future__ import annotations

import hashlib
import json


def canonical(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha(payload: object) -> str:
    return hashlib.sha256(canonical(payload)).hexdigest()


def file_hashes(files: dict | None) -> dict:
    return {name: hashlib.sha256(text.encode("utf-8")).hexdigest()
            for name, text in sorted((files or {}).items()) if isinstance(text, str)}


def _sandbox_profile(validator: dict) -> dict:
    iso = (validator or {}).get("isolation") or {}
    if iso.get("kind") == "container":
        try:
            from validator.container import profile
        except ImportError:
            return {"name": "container", "note": "profile unavailable"}
        prof = profile()
        return {**prof, "sha256": sha(prof), "image": iso.get("image", "")}
    notes = [c.get("note") for c in (validator or {}).get("checks", []) if c.get("note")]
    return {"name": "in-process", "note": notes[0] if notes else "no isolation note"}


def _check_rows(validator: dict, analyser: dict, creator_validator: dict | None = None) -> list[dict]:
    rows = []
    for stage, check in (("validator", validator), ("creator_validator", creator_validator)):
        for c in (check or {}).get("checks", []):
            rows.append({"stage": stage, "name": c.get("name"), "ok": bool(c.get("ok")),
                         "skipped": bool(c.get("skipped")), "findings": len(c.get("findings") or []),
                         "note": c.get("note") or ""})
    if analyser:
        rows.append({"stage": "analyser", "name": analyser.get("mode") or "rules", "ok": True,
                     "skipped": False, "findings": len(analyser.get("findings") or []),
                     "note": analyser.get("verdict") or ""})
    return rows


def _fix_check(pc: dict | None) -> dict | None:
    """What the patch check decided and on what: hashes and counts, no text of the code."""
    if not pc:
        return None
    v = pc.get("validator") or {}
    return {"status": pc.get("status"), "reason": pc.get("reason"), "applied": bool(pc.get("applied")),
            "diff_sha256": pc.get("diff_sha256", ""), "snapshot_sha256": pc.get("snapshot_sha256", ""),
            "patched_sha256": pc.get("patched_sha256", ""), "files_changed": pc.get("files_changed", []),
            "removed": pc.get("removed") or {"files": [], "symbols": []},
            "rules": pc.get("rules") or {}, "validator": {"verdict": v.get("verdict", ""), "tests_ran": bool(v.get("tests_ran"))}}


def build(*, supplied_files: dict, checked_files: dict, patch: dict, corrected_version: dict | None = None,
          checks: dict, answer: dict, model_verdict: str,
          rules: dict, attempts: int, stop_reason: str, not_checked: list, patch_check: dict | None = None, fix_attempts: list | None = None, external: list | None = None, question: str = "") -> dict:
    validator = checks.get("validator") or {}
    creator_validator = checks.get("creator_validator") or {}
    analyser = checks.get("analyser") or {}
    iso = creator_validator.get("isolation") or validator.get("isolation") or {}
    patch_files = file_hashes(patch)
    out = {
        "snapshot": {"files": file_hashes(supplied_files), "sha256": sha(file_hashes(supplied_files))},
        "patch": {"proposed": bool(patch), "diff_sha256": sha(patch_files) if patch else "", "files": patch_files},
        # What each reader really read. A model patch is only analysed by the rules unless the client sent no
        # files of its own: then the validator runs on the patch. Never left implicit.
        "validator_ran_on": {"what": ("model patch" if patch and not supplied_files else
                                       "supplied files" if supplied_files else "nothing"),
                             "files": file_hashes(checked_files) if validator else {}},
        "creator_validator_ran_on": {
            "what": "Creator corrected version" if creator_validator else "not run",
            "files": file_hashes(corrected_version) if creator_validator else {},
            "verdict": creator_validator.get("verdict"),
            "status": creator_validator.get("status"),
        },
        "analyser_read": {"material": bool(analyser), "patch_files": sorted(patch_files) if analyser else []},
        "versions": {"rules": rules, "sandbox_profile": _sandbox_profile(validator)},
        "checks_run": _check_rows(validator, analyser, creator_validator),
        "exploit_tests": list((patch_check or {}).get("exploit") or []),
        "fix_check": _fix_check(patch_check),
        "fix_attempts": list(fix_attempts or []),
        "attempts": attempts,
        "stop_reason": stop_reason,
        "cleanup": {"confirmed": iso.get("cleanup_confirmed") if iso else None},
        "model": {"consulted": bool(checks.get("generator")), "name": answer.get("model", ""),
                  "verdict": model_verdict or "", "findings": len(answer.get("findings") or [])},
        # how well the rules are measured for each language they read: counts from a labelled benchmark
        "languages": list(analyser.get("languages") or []),
        "rules_found": {"analyser": len(analyser.get("findings") or []),
                        "validator": sum(len(c.get("findings") or []) for c in validator.get("checks", [])),
                        "creator_validator": sum(len(c.get("findings") or [])
                                                  for c in creator_validator.get("checks", []))},
        "not_checked": list(not_checked or []),
    }
    if corrected_version:
        corrected_files = file_hashes(corrected_version)
        out["corrected_version"] = {
            "files": corrected_files, "sha256": sha(corrected_files),
            "verified": creator_validator.get("status") == "COMPLETED",
            "validator_status": creator_validator.get("status"),
            "validator_verdict": creator_validator.get("verdict"),
        }
    if out["model"]["consulted"]:
        # what the model said decided the verdict, so the record holds the content and not only the count:
        # two runs whose answers differ must not share a fingerprint. Only when present, so a run without
        # findings or a question keeps the fingerprint it always had.
        if answer.get("findings"):
            out["model"]["findings_sha256"] = sha(answer.get("findings"))
        if (question or "").strip():
            out["model"]["question_sha256"] = hashlib.sha256(question.strip().encode("utf-8")).hexdigest()
    if external:     # only when present: a run without a SARIF keeps the fingerprint it always had
        out["external"] = {"count": len(external), "sha256": sha(external)}
    return out
