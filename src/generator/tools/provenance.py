"""Where a run came from: which spec, which generator, which model, which prompts.

The analog of Vishap's `tools/provenance.py`. It goes into the trace so that a run can be explained later:
the same spec hash, the same prompt hashes and the same model name mean the same inputs. It holds no key and
no full URL: only the host of the endpoint.
"""

from __future__ import annotations

import hashlib
import platform
import urllib.parse
from pathlib import Path

from generator.pipeline.prompts import load_prompt
from generator.pipeline.stages import prompt_names
from generator.version import __version__


def prompt_hashes() -> dict[str, str]:
    return {name: hashlib.sha256(load_prompt(name).encode("utf-8")).hexdigest()[:12]
            for name in prompt_names()}


def get_provenance(spec, spec_path, config, redaction: dict[str, int] | None = None) -> dict:
    model = None
    if config is not None:
        model = {"name": config.model, "host": urllib.parse.urlsplit(config.url).hostname or ""}
    return {
        "generator": __version__,
        "python": platform.python_version(),
        "spec": {"name": Path(spec_path).name, "sha256": spec.sha256, "updated": spec.updated.isoformat()},
        "model": model,
        "prompts": prompt_hashes(),
        "redaction": dict(redaction or {}),
    }


def provenance_summary(p: dict) -> str:
    model = p.get("model")
    who = f"{model['name']} at {model['host']}" if model else "model not resolved"
    red = p.get("redaction") or {}
    redacted = f", redacted before the model: {sum(red.values())}" if red else ""
    return f"generator {p['generator']}, spec {p['spec']['sha256'][:12]}, {who}{redacted}"
