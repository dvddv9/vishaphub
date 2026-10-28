# src/storage/settings.py
import json
import os
from pathlib import Path

_SETTINGS_FILE = Path(os.getenv("SETTINGS_FILE", "data/settings.json"))


def _load() -> dict:
    if _SETTINGS_FILE.exists():
        try:
            return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save(data: dict) -> None:
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_settings() -> dict:
    return _load()


def update_settings(patch: dict) -> dict:
    data = _load()
    data.update(patch)
    _save(data)
    return data
