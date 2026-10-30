# -*- coding: utf-8 -*-
"""Where the analyzer's secrets are read from: a file outside the project tree, never one inside it.

Agents (Codex, Claude, any MCP client) open the repository as a project and can read every file in it. A `.env` in
the tree is therefore a readable file, not a secret, whatever `.gitignore` says. So:

  1. VISHAP_ENV_FILE, if set, names the file;
  2. otherwise ~/.vishap/analyzer.env, if it exists;
  3. nothing else. A `.env` next to the code is not loaded, and if one exists the analyzer refuses to start and says
     where to move it. `.env.example` (placeholders, no secrets) is the only dotenv file that belongs in the tree.

docker compose reads `.env` from the compose file's folder by itself; run it with the file outside the tree:
    docker compose --env-file ~/.vishap/analyzer.env up
"""
from __future__ import annotations

import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
#: the names a secret file takes when someone puts it next to the code; `.env.example` is not one of them
STRAY_NAMES = (".env", ".env.local", ".env.production")


def env_file_path() -> Path | None:
    explicit = os.getenv("VISHAP_ENV_FILE", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    default = Path.home() / ".vishap" / "analyzer.env"
    return default if default.exists() else None


def stray_files(root: Path | None = None) -> list[Path]:
    """Secret files that sit inside the project tree, where they are readable by whatever opens the project."""
    base = root or APP_ROOT
    return [p for p in (base / name for name in STRAY_NAMES) if p.exists()]


def load() -> Path | None:
    """Load the secret file into the environment. Returns the path that was loaded, or None."""
    stray = stray_files()
    if stray:
        raise RuntimeError(
            "A secret file is inside the project tree: " + ", ".join(str(p) for p in stray) + ". "
            "Anything that opens this project can read it. Move it outside, for example to "
            f"{Path.home() / '.vishap' / 'analyzer.env'}, or point VISHAP_ENV_FILE at it.")
    path = env_file_path()
    if path is None or not path.exists():
        return None
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=path)
    return path