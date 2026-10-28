# -*- coding: utf-8 -*-
"""Demo queue with planted D1/D2/D3."""
import heapq, time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

@dataclass
class Message:
    mid: str
    payload: str
    version: int = 0
    visible_at: float = 0.0
    handle: Optional[str] = None

class DemoQueue:
    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._messages: Dict[str, Message] = {}
        self._heap: List[Tuple[float, int, str]] = []
        self.receives: int = 0

    def put(self, mid, payload):
        msg = Message(mid=mid, payload=payload, version=1, visible_at=self._clock())
        self._messages[mid] = msg
        heapq.heappush(self._heap, (msg.visible_at, msg.version, mid))

    def receive(self):
        now = self._clock()
        while self._heap:
            visible_at, version, mid = heapq.heappop(self._heap)
            msg = self._messages.get(mid)
            if msg is None or msg.version != version:
                continue
            if visible_at > now:
                heapq.heappush(self._heap, (visible_at, version, mid))
                return None
            self.receives += 1
            msg.handle = f"h-{self.receives}"
            msg.visible_at = now + 30.0
            msg.version = version + 1
            heapq.heappush(self._heap, (msg.visible_at, msg.version, mid))
            return msg
        return None

    def redrive(self, mid):
        msg = self._messages.get(mid)
        if msg is None:
            return
        self.receives = 0
        msg.version += 1
        msg.visible_at = self._clock()
        heapq.heappush(self._heap, (msg.visible_at, msg.version, mid))

    def extend(self, mid, extra=30.0):
        msg = self._messages.get(mid)
        if msg is None:
            return
        msg.visible_at = self._clock() + extra

    def nack(self, mid):
        msg = self._messages.get(mid)
        if msg is None:
            return
        msg.version += 1
        msg.visible_at = self._clock()
        heapq.heappush(self._heap, (msg.visible_at, msg.version, mid))

    def _current(self, mid):
        msg = self._messages.get(mid)
        if msg is None:
            return None
        return (msg.visible_at, msg.version)
