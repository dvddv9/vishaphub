"""The history of runs written to an output folder: `<out>/.vishap/history.json`.

The analog of Vishap's `storage/history.py`: load, add an entry, find a finished entry by hash. It records what a
run did (spec hash, verdict, files, model usage), never file contents, never the key. The manifest of a run
(for rollback) stays in `<out>/.vishap/runs/<id>/`; this file is the readable list of all of them.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import threading
from pathlib import Path

HISTORY_NAME = "history.json"
META_DIR = ".vishap"
_LOCK = threading.Lock()


def history_path(root: str | os.PathLike) -> Path:
    return Path(root) / META_DIR / HISTORY_NAME


def load_history(root: str | os.PathLike) -> list[dict]:
    try:
        data = json.loads(history_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []


def _save(root: str | os.PathLike, entries: list[dict]) -> None:
    path = history_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".vg-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def add_entry(root: str | os.PathLike, entry: dict, now: dt.datetime | None = None) -> dict:
    """Append an entry stamped with the time; returns it. Safe for several threads (batch)."""
    entry = dict(entry)
    entry["timestamp"] = (now or dt.datetime.now().replace(microsecond=0)).isoformat()
    with _LOCK:
        entries = load_history(root)
        entries.append(entry)
        _save(root, entries)
    return entry


def mark_rolled_back(root: str | os.PathLike, run_id: str) -> bool:
    """Flag the entry of a rolled-back run; False when there is none."""
    with _LOCK:
        entries = load_history(root)
        hit = False
        for e in entries:
            if e.get("run_id") == run_id:
                e["rolled_back"] = True
                hit = True
        if hit:
            _save(root, entries)
        return hit


def find_done_by_hash(root: str | os.PathLike, spec_sha256: str) -> dict | None:
    """The latest run of this exact spec that passed and was not rolled back, or None."""
    if not spec_sha256:
        return None
    for e in reversed(load_history(root)):
        if (e.get("spec_sha256") == spec_sha256 and e.get("verdict") == "passed"
                and e.get("written") and not e.get("rolled_back")):
            return e
    return None


def clear_history(root: str | os.PathLike) -> int:
    """Delete the list (the run manifests stay, so rollback still works); returns how many entries."""
    with _LOCK:
        n = len(load_history(root))
        if n:
            _save(root, [])
        return n
