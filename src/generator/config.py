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
STRICT_MISSING_PCT = 50.0      # --strict: refuse when more than this share of the key data is missing
INJECTION_STOP = 3             # instruction-like phrases in a spec that stop the run
LOSS_MAX_PCT = 30.0            # share of planned code/test files the model may leave out before INCOMPLETE
REPRO_SEED = 42                # --repro: temperature 0 and this seed, if the endpoint takes them
CANDIDATES_MAX = 5             # --candidates N: at most this many
CANDIDATE_WORKERS = 3          # candidates generated at the same time
PROBE_MAX = 12                 # unusual values the COVE check sends


def api_token() -> str | None:
    """GENERATOR_API_TOKEN: required to bind to anything but loopback."""
    return os.environ.get("GENERATOR_API_TOKEN") or None


def allow_client_llm(host: str) -> bool:
    """May the browser send its own model settings? Yes on loopback, else only on request."""
    return host in LOOPBACK or os.environ.get("GENERATOR_ALLOW_CLIENT_LLM") == "1"


def check_only() -> bool:
    """GENERATOR_CHECK_ONLY=1: a public demo. The server only checks specs (Intake and Design): no model is
    called, no generated code is run, no key is needed, so it may listen on a public address without a token."""
    return os.environ.get("GENERATOR_CHECK_ONLY") == "1"


def public_hosts() -> set[str]:
    """Host names a public server answers to: GENERATOR_PUBLIC_HOSTS (comma separated) and, on Render,
    RENDER_EXTERNAL_HOSTNAME. The Host and Origin check still rejects every other name."""
    names = {n.strip().lower() for n in os.environ.get("GENERATOR_PUBLIC_HOSTS", "").split(",") if n.strip()}
    render = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip().lower()
    return names | ({render} if render else set())


def analyzer_command() -> str:
    """VISHAP_ANALYZER_CMD: how to start the Vishap analyzer (default: vishap)."""
    return os.environ.get("VISHAP_ANALYZER_CMD") or "vishap"


def validate_config(env: dict | None = None) -> tuple[list[str], list[str]]:
    """(errors, warnings) for the current environment. An error means a run cannot work as set up.

    The analog of Vishap's `validate_config`. It reads, never changes, and never prints a key.
    """
    import shutil
    env = os.environ if env is None else env
    errors: list[str] = []
    warnings: list[str] = []
    try:
        from generator.llm import config_from_env
        config_from_env(dict(env))
    except Exception as e:           # LLMConfigError and the provider allow-list errors
        warnings.append(f"model not configured: {e}")
    for name in ("GENERATOR_PRICE_IN", "GENERATOR_PRICE_OUT"):
        raw = env.get(name)
        if raw:
            try:
                if float(raw) < 0:
                    raise ValueError
            except ValueError:
                errors.append(f"{name} must be a non-negative number (USD per 1M tokens)")
    if env.get("LOG_FORMAT", "pretty") not in ("pretty", "json"):
        errors.append("LOG_FORMAT must be pretty or json")
    if env.get("LOG_LEVEL", "WARNING").upper() not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        errors.append("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR or CRITICAL")
    cmd = env.get("VISHAP_ANALYZER_CMD") or "vishap"
    if not shutil.which(cmd.split()[0]):
        warnings.append(f"analyzer command `{cmd}` not found: Verify runs without the Vishap Analyzer")
    return errors, warnings
