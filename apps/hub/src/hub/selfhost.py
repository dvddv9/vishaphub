"""Setting the hub up on one machine: `vishap-hub init`, `doctor`, `serve`.

The settings live in one plain file, ``config.env`` in the hub's home (``VISHAP_HUB_HOME``, default
``~/.vishaphub``), in the same ``NAME=value`` form the Docker bundle uses. A variable that is already in the
environment wins over the file, so a one-off override needs no edit. The file holds the model key, so it is
written readable by its owner only (where the platform can).
"""
from __future__ import annotations

import getpass
import os
import secrets
import shutil
import sys
from pathlib import Path

from . import egress, isolation, llm

KEYS = ("VISHAP_HUB_LLM_PROVIDER", "VISHAP_HUB_LLM_URL", "VISHAP_HUB_LLM_MODEL", "VISHAP_HUB_LLM_KEY",
        "VISHAP_HUB_OFFLINE", "VISHAP_HUB_ALLOWED_HOSTS", "VISHAP_HUB_VOICE", "VISHAP_HUB_ISOLATION",
        "VISHAP_HUB_WORKER_IMAGE", "VISHAP_HUB_HOST", "PORT", "VISHAP_HUB_RUNS_FILE")


def home() -> Path:
    return Path(os.getenv("VISHAP_HUB_HOME") or Path.home() / ".vishaphub")


def config_path() -> Path:
    return home() / "config.env"


def parse(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        out[name.strip()] = value.strip().strip('"').strip("'")
    return out


def load(environ=None) -> dict[str, str]:
    """Put the file's settings into the environment (what is already set stays) and return what was read."""
    if environ is None:
        environ = os.environ
    path = config_path()
    if not path.is_file():
        return {}
    values = parse(path.read_text(encoding="utf-8"))
    for name, value in values.items():
        if name in KEYS and name not in environ:
            environ[name] = value
    return values


def write(values: dict[str, str]) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# VishapHub settings. Holds the model key: keep this file private."]
    lines += [f"{k}={values[k]}" for k in KEYS if values.get(k, "") != ""]
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    os.replace(tmp, path)
    return path


def _ask(question: str, default: str, answers: list[str] | None, secret: bool = False) -> str:
    if answers is not None:
        return answers.pop(0) if answers else default
    prompt = f"{question} [{default}] " if default else f"{question} "
    try:
        reply = (getpass.getpass(prompt) if secret else input(prompt)).strip()
    except EOFError:
        reply = ""
    return reply or default


def wizard(args, answers: list[str] | None = None) -> dict[str, str]:
    """Ask what is not given as a flag. `answers` is for tests: it replaces the keyboard."""
    v: dict[str, str] = {}
    provider = args.provider or _ask("Model: anthropic (Claude), deepseek, openai (ChatGPT, OpenRouter, LM Studio, vLLM), ollama (local) "
                                     "or none (rules only)", "anthropic", answers)
    if provider not in llm.PROVIDERS:
        raise SystemExit(f"unknown provider: {provider} (use one of {', '.join(llm.PROVIDERS)})")
    v["VISHAP_HUB_LLM_PROVIDER"] = provider
    if provider == "openai":
        v["VISHAP_HUB_LLM_URL"] = args.url or _ask("Server address", "http://localhost:11434/v1", answers)
        v["VISHAP_HUB_LLM_MODEL"] = args.model or _ask("Model name, as the server calls it", "llama3.1", answers)
    elif provider == "ollama":
        v["VISHAP_HUB_LLM_MODEL"] = args.model or _ask("Model name, as `ollama list` shows it", "llama3.1", answers)
    elif provider in ("anthropic", "deepseek") and args.model:
        v["VISHAP_HUB_LLM_MODEL"] = args.model
    if provider != "none":
        key = args.key if args.key is not None else _ask("Key (empty for a server on this machine)", "", answers, secret=True)
        v["VISHAP_HUB_LLM_KEY"] = key
    offline = args.offline if args.offline is not None else \
        _ask("Keep everything on this machine and its private network? (y/n; also turns the voice off)", "n", answers).lower() in ("y", "yes")
    if offline:
        v["VISHAP_HUB_OFFLINE"] = "1"
        v["VISHAP_HUB_VOICE"] = "0"
    mode = args.isolation or _ask("Run submitted code: host (this machine, for code you trust), auto, or docker "
                                  "(a one-off container per run)", "host", answers)
    if mode not in isolation.MODES:
        raise SystemExit(f"unknown isolation: {mode} (use one of {', '.join(isolation.MODES)})")
    v["VISHAP_HUB_ISOLATION"] = mode
    if mode == "docker":
        v["VISHAP_HUB_WORKER_IMAGE"] = args.worker_image or _ask("Worker image", "vishaphub/validator:local", answers)
    v["VISHAP_HUB_HOST"] = "127.0.0.1"
    v["PORT"] = str(args.port or 8080)
    v["VISHAP_HUB_RUNS_FILE"] = str(home() / "runs.json")
    return v


def init(args, answers: list[str] | None = None) -> int:
    path = config_path()
    if path.exists() and not args.force:
        print(f"{path} exists. Use --force to replace it, or edit it by hand.", file=sys.stderr)
        return 1
    values = wizard(args, answers)
    print(f"Wrote {write(values)}")
    print("Check it with:  vishap-hub doctor\nStart it with:  vishap-hub serve")
    return 0


def doctor() -> int:
    """Say what this installation will do. Exit 1 when something it was set up for cannot work."""
    load()
    bad = 0

    def line(ok: bool | None, text: str) -> None:
        nonlocal bad
        if ok is False:
            bad += 1
        print(("ok   " if ok else "FAIL " if ok is False else "note ") + text)

    path = config_path()
    line(None, f"settings file: {path}" + ("" if path.is_file() else " (not there: run `vishap-hub init`)"))
    try:
        s = llm.settings()
        where = s.base_url or "(none)"
        line(True, f"model: {s.provider}" + (f" {s.model} at {where}" if s.provider != "none" else " (no model: rules and validator only)"))
        if s.provider != "none":
            has = llm.available("")
            if has:
                line(True, "key present")
            elif s.key_required:
                line(False, "no key - this provider needs one (VISHAP_HUB_LLM_KEY)")
            else:
                line(None, "no key (not needed for a server on this machine)")
    except llm.ConfigError as exc:
        line(False, f"model settings: {exc}")
    try:
        mode = isolation.policy()
        line(True, f"submitted code runs: {mode}")
        image = os.getenv("VISHAP_HUB_WORKER_IMAGE", "")
        if mode == "docker":
            line(bool(image), f"worker image: {image or 'VISHAP_HUB_WORKER_IMAGE is not set'}")
            line(shutil.which(os.getenv("VISHAP_HUB_DOCKER", "docker")) is not None, "docker command found")
        if mode == "host":
            line(None, "host mode is not a sandbox: only for code you wrote or trust")
    except isolation.PolicyError as exc:
        line(False, str(exc))
    try:
        import validator  # noqa: F401
        line(True, "validator installed")
    except ImportError:
        line(False, "validator is not installed (code cannot be checked)")
    line(True if egress.offline() else None, "offline: connections outside this machine and the private network are refused"
         if egress.offline() else "offline mode is off")
    return 1 if bad else 0


def serve() -> int:
    load()
    try:
        isolation.policy()
        llm.settings()
    except (isolation.PolicyError, llm.ConfigError) as exc:
        print(f"cannot start: {exc}", file=sys.stderr)
        return 2
    os.environ.setdefault("VISHAP_HUB_HOST", "127.0.0.1")
    # imported late: the server reads its settings from the environment at import time
    from . import server
    server.main()
    return 0


def new_secret() -> str:
    return secrets.token_hex(16)
