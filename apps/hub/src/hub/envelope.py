"""Envelope carried between the hub and the three services.

One shape for every hop, so a new participant (or a replay tool) does not need to
know who is talking to whom. ``trace`` keeps the chain auditable: each hop appends
its own line, nothing rewrites the past.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class Kind(str, Enum):
    QUESTION = "question"
    ANSWER = "answer"
    REPORT = "report"
    PATCH = "patch"
    VERDICT = "verdict"


PARTICIPANTS = ("client", "hub", "analyser", "generator", "validator")


@dataclass
class Envelope:
    sender: str
    recipient: str
    kind: Kind
    payload: dict = field(default_factory=dict)
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    trace: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def hop(self, note: str) -> Envelope:
        """Return a copy with one more trace line — never mutate the original."""
        return Envelope(
            sender=self.sender,
            recipient=self.recipient,
            kind=self.kind,
            payload=self.payload,
            session_id=self.session_id,
            trace=[*self.trace, f"{time.strftime('%H:%M:%S')} {note}"],
            created_at=self.created_at,
        )

    def as_dict(self) -> dict:
        return {
            "sender": self.sender,
            "recipient": self.recipient,
            "kind": self.kind.value,
            "payload": self.payload,
            "session_id": self.session_id,
            "trace": self.trace,
            "created_at": self.created_at,
        }

    @staticmethod
    def build(sender: str, recipient: str, kind: Kind, payload: dict, session_id: str = "") -> Envelope:
        if sender not in PARTICIPANTS or recipient not in PARTICIPANTS:
            raise ValueError(f"unknown participant: {sender!r} -> {recipient!r}")
        env = Envelope(sender=sender, recipient=recipient, kind=kind, payload=payload)
        if session_id:
            env.session_id = session_id
        return env
