# -*- coding: utf-8 -*-
"""The skeptic: one structured verdict per finding, so noise can be removed by a program, not by taste.

    {"finding_id": "sqli-fstring@64", "skeptic_verdict": "false_positive", "reason": "...", "basis": "proof"}

Verdicts and who may give them:
  confirmed       only a probe (proof.CONFIRMED): running the code broke an invariant
  false_positive  a probe that did NOT reproduce it (NOT_REPRODUCED), dead code (a private function nothing
                  mentions), or a model that QUOTES the line of this function that stops the defect
  suspected       everything else: no probe applies, the probe could not reach the statement, nobody quoted
                  a guard. A suspicion is not removed and not promoted.

A model is allowed to argue against a finding, never to confirm one and never to overrule a probe. Its
"false_positive" counts only with a quote that really occurs in the function; without it the finding stays
suspected. That is the whole point of the structure: a skeptic that cannot be checked is an opinion.
"""
from __future__ import annotations

import re

from src.tools import callgraph

VERDICTS = ("confirmed", "false_positive", "suspected")


def finding_id(f: dict) -> str:
    return f"{f.get('id', '?')}@{f.get('line', 0)}"


def _verdict(f, verdict, reason, basis, **extra):
    return {"finding_id": finding_id(f), "skeptic_verdict": verdict, "reason": reason[:300], "basis": basis, **extra}


def _function_source(code: str, graph: dict, name: str | None) -> str:
    if not name:
        return ""
    i = graph["functions"][name]
    lines = code.splitlines()[i["start"] - 1:i["end"]]
    return "\n".join(f"{i['start'] + k:5d}| {ln}" for k, ln in enumerate(lines))


def deterministic(f: dict, graph: dict) -> dict:
    """The verdict that needs no model. Never raises."""
    status = f.get("status")
    proof = f.get("proof") or {}
    if status == "CONFIRMED":
        return _verdict(f, "confirmed", proof.get("evidence") or "confirmed by running the code", "proof")
    if status == "NOT_REPRODUCED":
        return _verdict(f, "false_positive", "running the code did not break the invariant: " + (proof.get("evidence") or ""), "proof")
    name = callgraph.function_at(graph, int(f.get("line") or 0))
    if name is None:
        return _verdict(f, "suspected", "module level: this code runs when the file is imported", "static", function=None, reach="import")
    info = graph["functions"][name]
    reach = callgraph.reaches(graph, name)
    if reach is None and not info["public"] and not info["referenced"]:
        return _verdict(f, "false_positive", f"dead code: {name}() is private and nothing in this file calls or mentions it",
                        "static", function=name, reach=None)
    why = {"public": f"{name}() is public: reachable by whoever imports this file",
           "http": f"{name}() is an HTTP handler", "main": f"{name}() runs from __main__",
           "decorated": f"{name}() is registered with a decorator, so a framework calls it",
           "referenced": f"{name}() is passed around as a value"}.get(reach or "", f"{name}() is called from {', '.join(info['callers']) or 'elsewhere'}")
    if proof.get("status") == "INCONCLUSIVE" and proof.get("evidence"):
        why += "; the probe could not decide: " + proof["evidence"]
    elif not proof:
        why += "; no probe applies to this kind of finding"
    return _verdict(f, "suspected", why, "static", function=name, reach=reach)


def _validate_llm(raw, f: dict, source: str, fallback: dict) -> dict:
    """A model's answer, held to the rules in the module docstring. Anything off keeps ``fallback``."""
    if not isinstance(raw, dict):
        return fallback
    verdict = str(raw.get("skeptic_verdict") or raw.get("verdict") or "").lower()
    reason = str(raw.get("reason") or "").strip()
    if verdict not in VERDICTS or not reason:
        return fallback
    if verdict == "confirmed":      # only a probe confirms
        return {**fallback, "reason": fallback["reason"] + " (a model called it real; only running the code can confirm)"}
    if verdict == "suspected":
        return _verdict(f, "suspected", reason, "llm", **{k: fallback[k] for k in ("function", "reach") if k in fallback})
    quote = str(raw.get("quote") or "").strip()
    flat = re.sub(r"\s+", " ", re.sub(r"^\s*\d+\|\s?", "", source, flags=re.M))
    if len(quote) < 8 or re.sub(r"\s+", " ", quote) not in flat:
        return {**fallback, "reason": fallback["reason"] + " (a model called it a false positive but did not quote a guard from the code)"}
    return _verdict(f, "false_positive", reason, "llm+quote", quote=quote[:200],
                    **{k: fallback[k] for k in ("function", "reach") if k in fallback})


def review(findings: list, code: str, *, runner=None, apply: bool = True) -> list:
    """One verdict per finding. ``runner(text, context) -> parsed JSON`` is optional; it is asked only about
    findings the code could not settle, one at a time, with the source of the function."""
    graph = callgraph.build(code)
    out = []
    for f in findings:
        try:
            v = deterministic(f, graph)
            if runner is not None and v["skeptic_verdict"] == "suspected" and v.get("function"):
                src = _function_source(code, graph, v["function"])
                ctx = {"finding": {k: f.get(k) for k in ("id", "title", "severity", "cwe", "line", "snippet")},
                       "finding_id": v["finding_id"], "function": v["function"], "entry": v.get("reach"),
                       "callers": graph["functions"][v["function"]]["callers"], "proof": f.get("proof"),
                       "questions": ["Is there a path from an entry point to this line?",
                                     "Does the function validate or bound the input before this line? Quote the line.",
                                     "Would a test of the invariant fail on this code?"]}
                try:
                    v = _validate_llm(runner(src, ctx), f, src, v)
                except Exception:
                    pass
        except Exception as e:   # one odd finding must not hide the others
            v = _verdict(f, "suspected", f"skeptic could not read this finding: {type(e).__name__}", "error")
        out.append(v)
        if apply:
            f["skeptic"] = {k: v[k] for k in ("skeptic_verdict", "reason", "basis")}
    return out


def split(findings: list) -> tuple:
    """(kept, dismissed): dismissed are the findings the skeptic refuted with proof, dead code or a quoted guard."""
    kept, dismissed = [], []
    for f in findings:
        (dismissed if (f.get("skeptic") or {}).get("skeptic_verdict") == "false_positive" else kept).append(f)
    return kept, dismissed


def render_md(findings: list, include_proof: bool = True) -> str:
    """Short block for a report: what was dropped and why, so nobody has to trust the dropping.
    ``include_proof=False`` leaves out what a probe refuted (the "Verified findings" block lists those)."""
    _, dismissed = split(findings)
    if not include_proof:
        dismissed = [f for f in dismissed if f["skeptic"]["basis"] != "proof"]
    if not dismissed:
        return ""
    out = ["## Dismissed by the skeptic", "",
           "_Each line names the finding and the reason; `proof` means the code was run and the invariant held._", ""]
    for f in dismissed:
        s = f["skeptic"]
        out.append(f"- {finding_id(f)} {f.get('title', '')[:70]} - {s['basis']}: {s['reason'][:200]}")
    out.append("")
    return "\n".join(out)
