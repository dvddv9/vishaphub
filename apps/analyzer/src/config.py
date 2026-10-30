# -*- coding: utf-8 -*-
"""
РљРѕРЅС„РёРіСѓСЂР°С†РёСЏ Vishap.
"""
import os
import warnings
from pathlib import Path

from src import env_file

env_file.load()   # the secrets file lives outside the project tree: see src/env_file.py

# === РџСѓС‚Рё ===
ROOT_DIR = Path(__file__).parent.parent

# DATA_DIR вЂ” РІРЅРµ site-packages (env > ~/.vishap/data)
_env_data = os.getenv("VISHAP_DATA_DIR")
if _env_data:
    DATA_DIR = Path(_env_data)
else:
    DATA_DIR = Path.home() / ".vishap" / "data"

# PROMPTS_DIR вЂ” РІРЅСѓС‚СЂРё РїР°РєРµС‚Р° vishap/ (installed) РёР»Рё ROOT/vishap (dev)
try:
    import vishap as _vishap_pkg
    PROMPTS_DIR = Path(_vishap_pkg.__file__).parent
except ImportError:
    PROMPTS_DIR = ROOT_DIR / "vishap"

TOOLS_DIR = ROOT_DIR / "src" / "tools"

# === LLM: custom (OpenAI-compatible) ===
# DeepSeek / OpenAI / OpenAI-compatible API call any more (v7.0.0).

LLM_PROVIDER = os.getenv("VISHAP_LLM_PROVIDER", "auto").strip().lower()

CUSTOM_LLM_URL = os.getenv("CUSTOM_LLM_URL", "")
CUSTOM_LLM_KEY = os.getenv("CUSTOM_LLM_KEY", "")
CUSTOM_LLM_MODEL = os.getenv("CUSTOM_LLM_MODEL", "")
CUSTOM_LLM_TIMEOUT = float(os.getenv("CUSTOM_LLM_TIMEOUT", "120"))


# === FastAPI (UI -> API) ===
API_URL = os.getenv("API_URL", "http://localhost:5001")
CONVEYOR_API_KEY = os.getenv("CONVEYOR_API_KEY", "")
API_TIMEOUT_SHORT = 5
API_TIMEOUT_DEFAULT = 10
API_TIMEOUT_LONG = 300
API_TIMEOUT_BATCH = 900

# === Tavily Web Search ===
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
ENABLE_WEB_SEARCH = os.getenv("ENABLE_WEB_SEARCH", "false").lower() == "true"
SEARCH_MAX_RESULTS = int(os.getenv("SEARCH_MAX_RESULTS", "5"))
SEARCH_DEPTH = os.getenv("SEARCH_DEPTH", "basic")
DEEPSEEK_SEARCH_URL = os.getenv("DEEPSEEK_SEARCH_URL", "https://api.deepseek.com/v1/tools")

# === Р РµР¶РёРј LLM ===
MODE = "auto"

# === Р“РµРЅРµСЂР°С†РёСЏ ===
TEMPERATURE = 0.0
TEMPERATURE_CREATIVE = 0.3
MAX_TOKENS = 8000
MAX_TOKENS_STAGE4 = 16000

# === РЎРµСЂРІРµСЂ ===
PORT = int(os.getenv("PORT", "5001") or 5001)
APP_NAME = "Vishap"

# === Р›РѕРіРёСЂРѕРІР°РЅРёРµ (structlog, v6.1) ===
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv("LOG_FORMAT", "pretty")  # pretty | json

# === Р‘РµР·РѕРїР°СЃРЅРѕСЃС‚СЊ (Fernet, v6.1) ===
FERNET_KEY = os.getenv("FERNET_KEY", "")

# === GitHub App (v6.1) ===
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID", "")
GITHUB_PRIVATE_KEY = os.getenv("GITHUB_PRIVATE_KEY", "")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")

# === Clerk auth (v6.1) ===
CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY", "")
CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "")


# === Audit webhook (v6.3) ===
# When set, job lifecycle events are POSTed here for SIEM/compliance ingestion.
VISHAP_WEBHOOK_URL = os.getenv("VISHAP_WEBHOOK_URL", "")

# === Outbound email (v6.5) ===
# Without SMTP_HOST/USER/PASSWORD, send_email() is a no-op that logs and
# returns False, so the billing scripts stay runnable without a relay.
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or 587)
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "") or SMTP_USER

# === Р”Р°РЅРЅС‹Рµ ===
DATA_DIR.mkdir(parents=True, exist_ok=True)


# === Startup validation (v6.4) ===
#: Environment variables the API cannot run without.
REQUIRED_ENV_VARS = ("DATABASE_URL", "CLERK_SECRET_KEY")

_TRUE_VALUES = {"1", "true", "yes", "on"}


def is_dev_mode() -> bool:
    """True when VISHAP_DEV is set to a truthy value."""
    return os.getenv("VISHAP_DEV", "").strip().lower() in _TRUE_VALUES


def validate_config(strict: bool | None = None) -> list[str]:
    """Fail fast when required environment variables are missing.

    Returns the list of missing variable names (empty when everything is set).
    Raises :class:`RuntimeError` by default; in dev mode (``VISHAP_DEV=true``)
    it warns instead, so local work without Stripe/Clerk keys still starts.

    ``strict`` overrides the mode explicitly (used by tests).
    """
    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name, "").strip()]
    if not missing:
        return []

    detail = f"Missing env vars: {', '.join(missing)}. Check .env.example"
    if strict is None:
        strict = not is_dev_mode()

    if strict:
        raise RuntimeError(detail)

    # `warnings` rather than structlog: src.observability.logging imports this
    # module, so using the logger here would be circular.
    warnings.warn(detail, RuntimeWarning, stacklevel=2)
    return missing


# === Secrets: a placeholder is not a secret (v6.6) ===
#: Values that appear in documentation and examples. A live secret never looks
#: like one of these; if it does, everyone who read the example knows it too.
DEFAULT_PEPPERS = {
    "change-me-in-production",
    "change-me",
    "changeme",
    "change_me",
    "pepper",
    "secret",
    "test-pepper",
}


def validate_secrets(strict: bool | None = None) -> list[str]:
    """Fail fast when API_KEY_PEPPER is a placeholder.

    Tenant API keys are HMAC-SHA256 keyed with this pepper, so a placeholder makes
    every issued key forgeable by anyone who read `.env.example`. Checked hard only
    while ``VISHAP_TENANT_KEYS`` is on; otherwise it warns and lets dev start.
    """
    pepper = os.getenv("API_KEY_PEPPER", "").strip()
    tenants_on = os.getenv("VISHAP_TENANT_KEYS", "").strip().lower() in _TRUE_VALUES

    problems: list[str] = []
    if not pepper:
        if tenants_on:
            problems.append("API_KEY_PEPPER is not set while VISHAP_TENANT_KEYS is on")
    elif pepper.lower() in DEFAULT_PEPPERS:
        problems.append("API_KEY_PEPPER is a placeholder copied from .env.example")

    if not problems:
        return []

    detail = "; ".join(problems)
    if strict is None:
        strict = not is_dev_mode()
    if strict and tenants_on:
        raise RuntimeError(detail)

    warnings.warn(detail, RuntimeWarning, stacklevel=2)
    return problems
