"""Settings that are not secrets: paths, limits, defaults, and the few environment switches.

The model settings (CUSTOM_LLM_*) live in llm/providers.py. Environment switches are read
when asked, not at import, so a test or a long-running server sees the current value.
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = PACKAGE_DIR / "prompts"
WEB_DIR = PACKAGE_DIR / "web"
WEB_INDEX = WEB_DIR / "index.html"

# --- server
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})
MAX_BODY = 256 * 1024          # bytes of a request body
MAX_SPEC_CHARS = 100_000       # characters of one spec.yaml
MAX_REPAIRS = 5

# --- pipeline
DEFAULT_REPAIRS = 2
STALE_DAYS = 90                # a spec older than this blocks the gate
COVERAGE_MIN = 80.0            # percent


def api_token() -> str | None:
    """GENERATOR_API_TOKEN: required to bind to anything but loopback."""
    return os.environ.get("GENERATOR_API_TOKEN") or None


def allow_client_llm(host: str) -> bool:
    """May the browser send its own model settings? Yes on loopback, else only on request."""
    return host in LOOPBACK or os.environ.get("GENERATOR_ALLOW_CLIENT_LLM") == "1"


def analyzer_command() -> str:
    """VISHAP_ANALYZER_CMD: how to start the Vishap analyzer (default: vishap)."""
    return os.environ.get("VISHAP_ANALYZER_CMD") or "vishap"
