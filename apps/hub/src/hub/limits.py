"""Limits for the public doors: a request budget per address and a cache for the voice.

Two things on this service cost something the moment a stranger presses a button:
speech is synthesised by an outside service, and a run spends a model call. Neither
had a ceiling. A hub that answers everything is a hub someone else can spend.

Every limit can be switched off with `0`: an operator running this behind their own
gate does not need a second one.
"""
from __future__ import annotations

import collections
import hashlib
import os
import threading
import time
from typing import NamedTuple

DEFAULT_PER_MINUTE = {"run": 6, "chat": 20, "speak": 20}
#: the whole process, whoever asks - a stranger behind a thousand addresses is still one bill
DEFAULT_GLOBAL_RUNS_PER_DAY = 200
DEFAULT_GLOBAL_CHARS_PER_DAY = 5_000_000
DAY = 86_400.0
DEFAULT_TTS_CHARS = 600
DEFAULT_TTS_ITEMS = 64
DEFAULT_TTS_BYTES = 8 * 1024 * 1024


def int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, default)))
    except (TypeError, ValueError):
        return default


def per_minute(kind: str) -> int:
    """Requests a minute from one address; 0 turns the limit off."""
    return int_env(f"VISHAP_HUB_RATE_{kind.upper()}", DEFAULT_PER_MINUTE.get(kind, 20))


def tts_max_chars() -> int:
    return int_env("VISHAP_HUB_TTS_MAX_CHARS", DEFAULT_TTS_CHARS)


def global_runs_per_day() -> int:
    """Runs the whole process allows itself in a sliding day; 0 turns the ceiling off."""
    return int_env("VISHAP_HUB_GLOBAL_RUNS_PER_DAY", DEFAULT_GLOBAL_RUNS_PER_DAY)


def global_chars_per_day() -> int:
    """Characters the whole process sends toward a model in a sliding day; 0 turns it off."""
    return int_env("VISHAP_HUB_GLOBAL_CHARS_PER_DAY", DEFAULT_GLOBAL_CHARS_PER_DAY)


def input_chars(args: dict) -> int:
    """How much one run sends in: material, question, spec and every file. Volume, not money."""
    total = len(str(args.get("material") or "")) + len(str(args.get("question") or ""))
    spec = args.get("spec")
    total += len(spec) if isinstance(spec, str) else len(str(spec or ""))
    files = args.get("files")
    if isinstance(files, dict):
        total += sum(len(text) for text in files.values() if isinstance(text, str))
    return total


class RateLimiter:
    """A sliding window per key (the client address). No proxy header is trusted."""

    def __init__(self, limit: int, window: float = 60.0, clock=time.monotonic):
        self.limit, self.window, self._clock = limit, window, clock
        self._hits: dict[str, collections.deque] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, float]:
        """``(True, 0)`` to go on, ``(False, seconds)`` to wait."""
        if self.limit <= 0:
            return True, 0.0
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, collections.deque())
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False, max(0.1, self.window - (now - hits[0]))
            hits.append(now)
            if len(self._hits) > 2000:
                for k in [k for k, h in self._hits.items() if not h or now - h[-1] >= self.window]:
                    del self._hits[k]
            return True, 0.0


class Spend(NamedTuple):
    allowed: bool
    wait: float = 0.0
    reason: str = ""
    #: the request alone is larger than the whole character budget: waiting will not help
    too_big: bool = False


class RunBudget:
    """A ceiling for the whole process: runs and characters in a sliding window (a day).

    The per-address window stops one visitor; it does not stop many. This is the sum. It is
    in memory, so a restart empties it - the ceiling bounds one process's day, not the
    account's bill. A request that does not fit is refused out loud (429 with the reason),
    never answered thinner. `0` turns either ceiling off.
    """

    def __init__(self, runs: int, chars: int, window: float = DAY, clock=time.monotonic):
        self.runs, self.chars, self.window, self._clock = runs, chars, window, clock
        self._spent: collections.deque[tuple[float, int]] = collections.deque(maxlen=50_000)
        self._lock = threading.Lock()

    def _forget(self, now: float) -> None:
        while self._spent and now - self._spent[0][0] >= self.window:
            self._spent.popleft()

    def take(self, chars: int) -> Spend:
        """Reserve one run of `chars` characters, or say why not and for how long."""
        now = self._clock()
        with self._lock:
            self._forget(now)
            if self.chars > 0 and chars > self.chars:
                return Spend(False, 0.0, f"this request is {chars} characters; the daily budget is "
                                         f"{self.chars}, so it can never fit", too_big=True)
            wait = max(0.1, self.window - (now - self._spent[0][0])) if self._spent else self.window
            if self.runs > 0 and len(self._spent) >= self.runs:
                return Spend(False, wait, f"the hub has used its budget of {self.runs} runs in the last "
                                          f"{int(self.window // 3600)} hours; try again later")
            if self.chars > 0 and sum(c for _t, c in self._spent) + chars > self.chars:
                return Spend(False, wait, f"the hub has used its budget of {self.chars} characters in the "
                                          f"last {int(self.window // 3600)} hours; try again later")
            self._spent.append((now, chars))
            return Spend(True)

    def used(self) -> dict:
        now = self._clock()
        with self._lock:
            self._forget(now)
            return {"runs": len(self._spent), "chars": sum(c for _t, c in self._spent)}


class TTSCache:
    """The voice is deterministic for the same words, so it is worth keeping.

    Bounded twice over (by item count and by bytes) because a page that speaks a
    greeting to every visitor should synthesise it once, not once per visitor.
    """

    def __init__(self, items: int = DEFAULT_TTS_ITEMS, max_bytes: int = DEFAULT_TTS_BYTES):
        self.items, self.max_bytes = items, max_bytes
        self._data: collections.OrderedDict[str, bytes] = collections.OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()

    @staticmethod
    def key(text: str, voice: str) -> str:
        return hashlib.sha256(f"{voice}\x00{text}".encode()).hexdigest()

    def get(self, key: str) -> bytes | None:
        with self._lock:
            value = self._data.get(key)
            if value is not None:
                self._data.move_to_end(key)
            return value

    def put(self, key: str, audio: bytes) -> None:
        if not audio or len(audio) > self.max_bytes:
            return
        with self._lock:
            if key in self._data:
                self._bytes -= len(self._data.pop(key))
            self._data[key] = audio
            self._bytes += len(audio)
            while self._data and (len(self._data) > self.items or self._bytes > self.max_bytes):
                _old_key, old = self._data.popitem(last=False)
                self._bytes -= len(old)

