"""What a job store must do. The analog of Vishap's `api/job_store.py` (there: Redis or Postgres).

A job is one generate run started with `POST /api/generate/async`. The browser polls it. This module is only
the interface and the record; `job_store_memory.py` is the implementation (jobs live in the server's memory and
vanish when the server stops, which is fine for a tool that runs on one computer).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"
MAX_LOG_LINES = 500


@dataclass
class Job:
    id: str
    status: str = QUEUED
    stage: str = ""                       # the stage the last log line belongs to
    log: list[str] = field(default_factory=list)
    result: dict | None = None            # the same JSON as the synchronous answer
    http_status: int = 0
    error: str = ""
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)

    def to_dict(self, since: int = 0) -> dict:
        """`since` is how many log lines the caller already has; only the new ones are returned."""
        out = {"id": self.id, "status": self.status, "stage": self.stage, "log_from": since,
               "log": self.log[since:], "log_total": len(self.log), "error": self.error}
        if self.status in (DONE, FAILED):
            out["http_status"] = self.http_status
            out["result"] = self.result
        return out


class JobStore(Protocol):
    def create(self) -> Job: ...
    def get(self, job_id: str) -> Job | None: ...
    def start(self, job_id: str) -> None: ...
    def append_log(self, job_id: str, line: str, stage: str = "") -> None: ...
    def finish(self, job_id: str, result: dict | None, http_status: int, error: str = "") -> None: ...
