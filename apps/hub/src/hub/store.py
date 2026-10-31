"""The last runs, so a client can come back to one - and only its own.

A run that lives only in an HTTP response is a demo. The store keeps the finished
runs in memory - bounded, oldest first, thread-safe - and can mirror them to a file so
a restart does not erase the day. It is deliberately not a database: one process, one
deployment, no migration to maintain for a feature whose first job is <open the run I
was looking at>.

Every run carries the owners who made it, as hashes of their tokens (the token itself
is never stored), and a `demo` flag the server sets for the page's own example. A run is
visible to its owners and, if it is a demo, to anyone. Nothing else is: `get_for` and
`list_for` are the doors, `get` and `list` are for code that already holds the whole
store. Two visitors who run the same material get the same run id, so owners are merged
on save rather than overwritten.
"""
from __future__ import annotations

import collections
import hashlib
import hmac
import json
import os
import threading

from . import accepted

DEFAULT_KEEP = 200


def owner_key(token: str) -> str:
    """What the store remembers of an owner token: its hash, never the token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _owns(record: dict, owner: str | None) -> bool:
    if not owner:
        return False
    return any(hmac.compare_digest(owner, str(o)) for o in record.get("owners") or [])


def _summary(record: dict) -> dict:
    return {
        "id": record.get("id"),
        "at": record.get("at"),
        "verdict": record.get("verdict"),
        "ok": record.get("ok"),
        "plan": record.get("plan"),
        "summary": record.get("summary", "")[:200],
    }


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
            old = self._runs.get(run_id)
            if old is not None:
                # same material, same plan, same id: both visitors keep their run. The demo
                # flag is NOT merged - it belongs to this record's own content alone.
                record["owners"] = sorted(set(old.get("owners") or []) | set(record.get("owners") or []))
                kept = (old.get("result") or {}).get("accepted")
                if kept and isinstance(record.get("result"), dict) and not record["result"].get("accepted"):
                    record["result"] = {**record["result"], "accepted": kept}     # the same run again keeps its notes
            self._runs[run_id] = record
            self._runs.move_to_end(run_id)
            while len(self._runs) > self.keep:
                self._runs.popitem(last=False)
            self._flush()
        return run_id

    def get_for(self, run_id: str, owner: str | None) -> dict | None:
        """The run, if `owner` made it or it is a demo; otherwise None - the same None as a missing run."""
        with self._lock:
            record = self._runs.get(str(run_id))
        if record is None or not (record.get("demo") or _owns(record, owner)):
            return None
        return accepted.shown({k: v for k, v in record.items() if k != "owners"})

    def annotate(self, run_id: str, owner: str | None, change) -> tuple[str, str]:
        """Change the result of a run this owner made: ("ok", ""), ("missing", "") or ("invalid", why).

        `change` takes the stored result and returns the new one, or raises ValueError. A run that is not
        theirs is "missing", the same answer as a run that is not there.
        """
        with self._lock:
            record = self._runs.get(str(run_id))
            if record is None or not _owns(record, owner):
                return "missing", ""
            try:
                record["result"] = change(record.get("result") or {})
            except ValueError as exc:
                return "invalid", str(exc)
            self._flush()
        return "ok", ""

    def list_for(self, owner: str | None, limit: int = 20) -> list[dict]:
        """Newest first, only the runs `owner` made: id, verdict, time and the plan - not the material."""
        with self._lock:
            mine = [r for r in self._runs.values() if _owns(r, owner)]
        return [_summary(r) for r in reversed(mine[-limit:])]

    def get(self, run_id: str) -> dict | None:
        """Unfiltered. For code that holds the whole store; a door uses `get_for`."""
        with self._lock:
            return self._runs.get(str(run_id))

    def list(self, limit: int = 20) -> list[dict]:
        """Unfiltered, newest first. For code that holds the whole store; a door uses `list_for`."""
        with self._lock:
            records = list(self._runs.values())[-limit:]
        return [_summary(r) for r in reversed(records)]

    def retention(self) -> str:
        """How long a run lives here, in the words the report page and the README both use."""
        if self.path:
            return (f"Kept on the server in a file: the last {self.keep} runs, until newer ones "
                    "push it out or the file is deleted.")
        return f"Kept in memory until the service restarts: the last {self.keep} runs, older ones are dropped."

    def __len__(self) -> int:
        with self._lock:
            return len(self._runs)
