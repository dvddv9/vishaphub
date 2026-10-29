"""A run's identity: what went in, what rules judged it, what came out.

A verdict a client cannot re-check is an opinion with a timestamp. The fingerprint is
the same run expressed as data: the material, the spec, the plan, the versions of the
rules that judged it, the verdict and the steps. Hash it and the run has an id the
client can quote; keep the record and the id can be opened again.

The hash is canonical (sorted keys, no whitespace, UTF-8) so the same run computed on
another machine gives the same digest — that is the whole point of calling it a proof
rather than a receipt.
"""
from __future__ import annotations

import hashlib
import json
import time
from importlib import import_module

HUB_RULES = "hub"


def _version(*modules: str) -> str:
    """The version of a rule set, or «unknown»: never a guess dressed as a number.

    The analyser ships its version as `src/version.py`, so the module name depends on
    how it was installed; every candidate is tried and an absent package stays honest.
    """
    for module in modules:
        for name in (module, f"{module}.version"):
            try:
                value = getattr(import_module(name), "__version__", "")
            except Exception:  # noqa: BLE001, S112 - an absent package is a fact, not a failure
                continue
            if value:
                return str(value)
    return "unknown"


def rules_version() -> dict:
    """Who judged: the hub, the validator's stages, the analyser's patterns."""
    return {
        "hub": _version("hub"),
        "validator": _version("validator"),
        "analyser": _version("src", "vishap", "version"),
    }


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def of(material: str, spec: object, files: dict, plan: dict, verdict: str,
       steps: list[dict], rules: dict | None = None) -> dict:
    """The run as a reproducible record, with a digest over everything that decided it."""
    rules = rules or rules_version()
    body = {
        "material_sha256": hashlib.sha256((material or "").encode("utf-8")).hexdigest(),
        "spec_sha256": hashlib.sha256(
            canonical(spec if isinstance(spec, dict) else {"text": str(spec or "")})).hexdigest(),
        "files": {name: hashlib.sha256(text.encode("utf-8")).hexdigest()
                  for name, text in sorted((files or {}).items())},
        "plan": plan,
        "rules": rules,
        "verdict": verdict,
        "steps": [{"stage": s.get("stage"), "verdict": s.get("verdict"), "ok": s.get("ok")}
                  for s in steps],
    }
    digest = hashlib.sha256(canonical(body)).hexdigest()
    return {
        "id": digest[:16],
        "digest": digest,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rules": rules,
        "body": body,
    }
