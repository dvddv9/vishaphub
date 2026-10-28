"""Adapters to the three services. Every call returns a dict, never raises.

A service that is down must not take the hub down with it: each adapter turns a
failure into ``{"ok": False, "error": ...}`` so the pipeline can decide whether the
run continues or stops with an honest verdict.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass

DEFAULT_TIMEOUT = 300


@dataclass
class ServiceConfig:
    analyser_url: str = os.getenv("VISHAP_ANALYSER_URL", "https://vishap-zwpx.onrender.com")
    generator_url: str = os.getenv("VISHAP_GENERATOR_URL", "")
    validator_cmd: str = os.getenv("VISHAP_VALIDATOR_CMD", "")
    api_key: str = os.getenv("VISHAP_API_KEY", "")
    llm_key: str = os.getenv("VISHAP_LLM_KEY", "")
    timeout: int = DEFAULT_TIMEOUT


def _post(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    if not url:
        return {"ok": False, "error": "service url is not configured"}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={**headers, "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return {"ok": True, "data": json.load(response)}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        return {"ok": False, "error": f"HTTP {exc.code}: {detail}"}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _headers(cfg: ServiceConfig) -> dict:
    headers = {}
    if cfg.api_key:
        headers["X-API-Key"] = cfg.api_key
    if cfg.llm_key:
        headers["X-LLM-Api-Key"] = cfg.llm_key
    return headers


def analyse(cfg: ServiceConfig, material: str, filename: str = "input.txt") -> dict:
    """Ask the analyser for a security verdict on the material."""
    result = _post(
        f"{cfg.analyser_url.rstrip('/')}/analyze",
        {"material": material, "filename": filename},
        _headers(cfg),
        cfg.timeout,
    )
    if not result["ok"]:
        return result
    data = result["data"]
    return {
        "ok": True,
        "verdict": data.get("verdict", ""),
        "risk_verdict": data.get("risk_verdict", ""),
        "cwe_ids": data.get("cwe_ids") or [],
        "markdown": data.get("final_markdown", ""),
        "raw": data,
    }


def generate(cfg: ServiceConfig, spec: str, out_dir: str) -> dict:
    """Ask the generator for a deliverable built from the spec."""
    # The generator speaks a stdlib HTTP API: POST /api/generate with the spec text.
    result = _post(
        f"{cfg.generator_url.rstrip('/')}/api/generate",
        {"spec": spec},
        _headers(cfg),
        cfg.timeout,
    )
    if not result["ok"]:
        return result
    data = result["data"]
    return {"ok": True, "out_dir": data.get("out_dir") or out_dir, "raw": data}


def validate(cfg: ServiceConfig, root: str, spec: dict) -> dict:
    """Run the validator over a deliverable.

    Prefers the CLI (``VISHAP_VALIDATOR_CMD``) because the validator is a local,
    deterministic tool; falls back to importing it when it is installed.
    """
    spec_fd, spec_path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(spec_fd, "w", encoding="utf-8") as fh:
            json.dump(spec, fh, ensure_ascii=False)
        cmd = (cfg.validator_cmd or f"{sys.executable} -m validator.cli").split()
        proc = subprocess.run(
            [*cmd, "check", root, "--spec", spec_path, "--json"],
            capture_output=True,
            text=True,
            timeout=cfg.timeout,
        )
        if proc.returncode not in (0, 1):
            return {"ok": False, "error": f"validator exited {proc.returncode}: {(proc.stderr or '')[:300]}"}
        return {"ok": True, "report": json.loads(proc.stdout)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"validator timed out after {cfg.timeout} s"}
    except (json.JSONDecodeError, OSError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        os.unlink(spec_path)
