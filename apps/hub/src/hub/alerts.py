"""A warning before a budget is spent, not after.

`check(scope, used, limit)` says something once when a count first reaches 80% of its limit and once at
100%, per scope per UTC day. "Says" is a line on stderr (the Render log) and, if VISHAP_HUB_ALERT_WEBHOOK is
set, a POST of {"text": ...} to it (the shape Slack and most chat webhooks accept). A webhook that is down
or slow never delays or fails a request: it is posted from a thread and its failure is only logged.

The memory of what was already said is the process's: after a restart the next crossing says it again.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import threading
import urllib.request

THRESHOLDS = (0.8, 1.0)


class Alerter:
    def __init__(self, webhook: str = ""):
        self.webhook = webhook
        self._said: set[tuple[str, float, str]] = set()
        self._lock = threading.Lock()

    def check(self, scope: str, used: int, limit: int, label: str = "") -> list[str]:
        """Messages said just now (usually none)."""
        if limit <= 0:
            return []
        today = datetime.datetime.now(datetime.UTC).date().isoformat()
        said = []
        for threshold in THRESHOLDS:
            if used < threshold * limit:
                continue
            with self._lock:
                key = (scope, threshold, today)
                if key in self._said:
                    continue
                self._said.add(key)
            said.append(f"{label or scope}: {used} of {limit} used ({int(threshold * 100)}% of the daily limit)")
        for message in said:
            self.emit(message)
        return said

    def emit(self, message: str) -> None:
        print(f"ALERT {message}", file=sys.stderr, flush=True)
        if self.webhook:
            threading.Thread(target=self._post, args=(message,), daemon=True).start()

    def _post(self, message: str) -> None:
        try:
            request = urllib.request.Request(self.webhook, data=json.dumps({"text": f"VishapHub: {message}"}).encode(),
                                             headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(request, timeout=5).read()
        except Exception as exc:  # noqa: BLE001 - an alert that cannot be delivered must not hurt a request
            print(f"alert webhook failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)


def from_env() -> Alerter:
    return Alerter(os.getenv("VISHAP_HUB_ALERT_WEBHOOK", ""))
