"""STRIDE as a coverage table, not a story.

The analog of the `threat_model` of Vishap's analyst prompt. A model-written threat list is an opinion; this is a
check of what the spec says. For each of the six categories it answers three things: does it apply to this
endpoint, which requirements of the spec address it, and so is it `covered`, `partial`, `not_covered` or
`not_applicable`. After Verify, `with_proof` adds whether those requirements were proven.

It reads the spec, never the code: "covered" means the spec has a requirement that Verify will check, not that
the code is safe. The keyword tests (audit, role, rate limit) are plain and listed here so nobody is surprised.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from generator.pipeline.intake import Requirement
from generator.tools.spec import REQUIREMENT_LISTS, Spec

LETTERS = (("S", "Spoofing"), ("T", "Tampering"), ("R", "Repudiation"),
           ("I", "Information disclosure"), ("D", "Denial of service"), ("E", "Elevation of privilege"))
STATUSES = ("covered", "partial", "not_covered", "not_applicable")
MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
BOUND_RE = re.compile(r"\d+\s*-\s*\d+|\bmax(?:imum)?\b|\bat most\b|\bup to\b|не более", re.I)
ROLE_RE = re.compile(r"\b(?:role|permission|owner|authoriz\w*|admin\w*|own)\b", re.I)


@dataclass(frozen=True)
class Threat:
    letter: str
    name: str
    status: str
    reason: str
    requirements: tuple[str, ...] = ()

    @property
    def applies(self) -> bool:
        return self.status != "not_applicable"

    def to_dict(self) -> dict:
        return {"letter": self.letter, "name": self.name, "status": self.status,
                "reason": self.reason, "requirements": list(self.requirements)}


def _pairs(spec: Spec, reqs: tuple[Requirement, ...]):
    items = [(f, item) for f in REQUIREMENT_LISTS for item, _ in spec.items.get(f, [])]
    return list(zip(reqs, items))


def stride_table(spec: Spec, reqs: tuple[Requirement, ...]) -> tuple[Threat, ...]:
    data = spec.data
    pairs = _pairs(spec, reqs)
    kind, caller = data.get("kind"), data.get("caller")
    method = (data.get("route") or "").split(" ")[0]
    mutating = method in MUTATING

    def ids(pred) -> tuple[str, ...]:
        return tuple(r.id for r, (field, item) in pairs if pred(field, item))

    def words(item: dict) -> str:
        return f"{item.get('id', '')} {item.get('text', '')}".lower()

    out: dict[str, Threat] = {}

    def put(letter: str, status: str, reason: str, refs: tuple[str, ...] = ()) -> None:
        out[letter] = Threat(letter, dict(LETTERS)[letter], status, reason, refs)

    if kind != "http-endpoint":
        for letter, _ in LETTERS:
            put(letter, "not_applicable", f"kind {kind or 'not given'} has no HTTP boundary to model")
        return tuple(out[letter] for letter, _ in LETTERS)

    # S
    if caller != "signed-in":
        put("S", "not_applicable", f"caller is {caller or 'not given'}: no identity to spoof")
    else:
        refs = ids(lambda f, i: f == "outputs" and i.get("status") in (401, 403))
        put("S", "covered" if refs else "not_covered",
            "an answer for a missing or wrong identity is specified (401/403)" if refs
            else "signed-in caller, but no 401 or 403 answer is specified", refs)

    # T
    inputs = [i for f, i in ((f, i) for _, (f, i) in pairs) if f == "inputs"]
    if not inputs:
        put("T", "not_applicable", "no inputs to tamper with")
    else:
        ruled = [i for i in inputs if i.get("rule")]
        answers = ids(lambda f, i: f == "outputs" and i.get("status") in (400, 422))
        refs = ids(lambda f, i: f == "inputs") + answers
        if len(ruled) == len(inputs) and answers:
            put("T", "covered", "every input has a rule and invalid input has an answer (400/422)", refs)
        elif ruled or answers:
            put("T", "partial", "some inputs have no rule, or invalid input has no answer", refs)
        else:
            put("T", "not_covered", "no input has a rule and invalid input has no answer", refs)

    # R
    if not (mutating or caller == "signed-in"):
        put("R", "not_applicable", "read-only call by an anonymous or internal caller")
    else:
        refs = ids(lambda f, i: f != "inputs" and f != "outputs" and "audit" in words(i))
        put("R", "covered" if refs else "not_covered",
            "an audit requirement is given" if refs else "no requirement says the action is recorded (audit)", refs)

    # I
    logs = ids(lambda f, i: f == "must_never" and i.get("id") == "log-raw-input")
    shape = ids(lambda f, i: f == "outputs" and i.get("body") and 200 <= int(i.get("status", 0)) < 300)
    refs = logs + shape
    if logs and shape:
        put("I", "covered", "the response body is limited to named fields and raw input is not logged", refs)
    elif refs:
        put("I", "partial", "only one of: response fields are named, raw input is never logged", refs)
    else:
        put("I", "not_covered", "neither the response fields nor logging of input is specified", refs)

    # D
    bounds = ids(lambda f, i: f == "inputs" and BOUND_RE.search(str(i.get("rule", ""))))
    rate = ids(lambda f, i: f in ("must_never", "should", "may") and "rate" in words(i) and "limit" in words(i))
    refs = bounds + rate
    if bounds and rate:
        put("D", "covered", "input length is bounded and a rate limit is required", refs)
    elif refs:
        put("D", "partial", "only one of: input length is bounded, a rate limit is required", refs)
    else:
        put("D", "not_covered", "no bound on input size and no rate limit is specified", refs)

    # E
    refs = ids(lambda f, i: f in ("must_never", "should", "may") and ROLE_RE.search(words(i)))
    if not (caller == "signed-in" or mutating or refs):
        put("E", "not_applicable", "public read-only endpoint: no privilege levels are given")
    else:
        put("E", "covered" if refs else "not_covered",
            "a role, owner or permission requirement is given" if refs
            else "no requirement says who may do what (role, owner, permission)", refs)

    return tuple(out[letter] for letter, _ in LETTERS)


def with_proof(threats, verify) -> list[dict]:
    """The table as dicts, each with `proof`: proven / failed / not proven / - (nothing linked)."""
    status = {r.id: r.status for r in verify.requirements} if verify else {}
    rows = []
    for t in threats:
        row = t.to_dict()
        linked = [status[i] for i in t.requirements if i in status]
        if not linked:
            row["proof"] = "-"
        elif any(s == "failed" for s in linked):
            row["proof"] = "failed"
        elif all(s == "passed" for s in linked):
            row["proof"] = "proven"
        else:
            row["proof"] = "not proven"
        rows.append(row)
    return rows
