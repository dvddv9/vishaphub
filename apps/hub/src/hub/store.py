"""The last runs, so a client can come back to one.

A run that lives only in an HTTP response is a demo. The store keeps the finished
runs in memory — bounded, oldest first, thread-safe — and can mirror them to a file so
a restart does not erase the day. It is deliberately not a database: one process, one
deployment, no migration to maintain for a feature whose first job is «open the run I
was looking at».
"""
from __future__ import annotations

import collections
import json
import os
import threading

DEFAULT_KEEP = 200


class RunStore:
    def __init__(self, keep: int = DEFAULT_KEEP, path: str = ""):
        self.keep = max(1, keep)
        self.path = path
        self._runs: collections.OrderedDict[str, dict] = collections.OrderedDict()
        self._lock = threading.Lock()
        if path and os.path.exists(path):
            self._load(path)

    # ---- file mirror ----------------------------------------------------

    def _load(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as fh:
                saved = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return
        for record in saved if isinstance(saved, list) else []:
            if isinstance(record, dict) and record.get("id"):
                self._runs[str(record["id"])] = record
        while len(self._runs) > self.keep:
            self._runs.popitem(last=False)

    def _flush(self) -> None:
        if not self.path:
            return
        tmp = f"{self.path}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(list(self._runs.values()), fh, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            pass          # a run that cannot be written is still a run that happened

    # ---- api ------------------------------------------------------------

    def save(self, record: dict) -> str:
        run_id = str(record["id"])
        with self._lock:
            self._runs[run_id] = record
            self._runs.move_to_end(run_id)
            while len(self._runs) > self.keep:
                self._runs.popitem(last=False)
            self._flush()
        return run_id

    def get(self, run_id: str) -> dict | None:
        with self._lock:
            return self._runs.get(str(run_id))

    def list(self, limit: int = 20) -> list[dict]:
        """Newest first: id, verdict, time and the plan — not the whole material."""
        with self._lock:
            records = list(self._runs.values())[-limit:]
        return [
            {
                "id": r.get("id"),
                "at": r.get("at"),
                "verdict": r.get("verdict"),
                "ok": r.get("ok"),
                "plan": r.get("plan"),
                "summary": r.get("summary", "")[:200],
            }
            for r in reversed(records)
        ]

    def __len__(self) -> int:
        with self._lock:
            return len(self._runs)
