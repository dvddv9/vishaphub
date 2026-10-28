"""Jobs in the server's memory: a dict under a lock, old jobs dropped."""

from __future__ import annotations

import secrets
import threading
import time

from generator.api.job_store import DONE, FAILED, MAX_LOG_LINES, RUNNING, Job

KEEP_SECONDS = 3600        # a finished job stays this long
MAX_JOBS = 50


class MemoryJobStore:
    def __init__(self, keep_seconds: float = KEEP_SECONDS, max_jobs: int = MAX_JOBS):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self.keep_seconds, self.max_jobs = keep_seconds, max_jobs

    def _purge(self, now: float) -> None:
        for jid in [j.id for j in self._jobs.values()
                    if j.status in (DONE, FAILED) and now - j.updated > self.keep_seconds]:
            del self._jobs[jid]
        while len(self._jobs) >= self.max_jobs:                    # the oldest finished job goes first
            finished = [j for j in self._jobs.values() if j.status in (DONE, FAILED)]
            if not finished:
                break
            del self._jobs[min(finished, key=lambda j: j.updated).id]

    def create(self) -> Job:
        with self._lock:
            self._purge(time.time())
            job = Job(id=secrets.token_urlsafe(16))              # unguessable: it is the only secret of a result
            self._jobs[job.id] = job
            return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def start(self, job_id: str) -> None:
        with self._lock:
            if job := self._jobs.get(job_id):
                job.status, job.updated = RUNNING, time.time()

    def append_log(self, job_id: str, line: str, stage: str = "") -> None:
        with self._lock:
            if job := self._jobs.get(job_id):
                if len(job.log) < MAX_LOG_LINES:
                    job.log.append(line)
                if stage:
                    job.stage = stage
                job.updated = time.time()

    def finish(self, job_id: str, result: dict | None, http_status: int, error: str = "") -> None:
        with self._lock:
            if job := self._jobs.get(job_id):
                job.result, job.http_status, job.error = result, http_status, error
                job.status = FAILED if error or http_status >= 400 else DONE
                job.updated = time.time()
