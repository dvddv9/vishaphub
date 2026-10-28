# -*- coding: utf-8 -*-
"""Questions for the person, only where the answer changes a priority.

The skeptic leaves some findings `suspected`: the code alone cannot say whether they matter. Whether
`get_user_profile()` is reachable from the internet or only from an admin script, whether the string on line 8
is a real key or an example - a person knows, a tool does not. This module turns exactly those gaps into at most
five multiple-choice questions and applies the answers to the findings.

    question  {question_id, kind, text, options: [{key, label, impact}], function, finding_ids}
    answer    {question_id, answer: "b", impact: "lower"}
    impact    raise | lower | lower2 | critical | low | dismiss | keep   (what happens to the severity)

A question is asked once: answers are stored (``save_store``) under a stable id, so the next run applies them
and does not ask again. Nothing here hides a probe result: severity moves, `status`/`proof` stay as they were;
only "dismiss" (an example value that is not a secret) turns a finding into a false positive, labelled with its
basis `answer`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from src.tools import callgraph, skeptic

LADDER = ["low", "medium", "high", "critical"]
WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1}
MAX_QUESTIONS = 5

OPTIONS = {
    "exposure": [
        ("a", "The public: a web app or a public API", "raise"),
        ("b", "An internal service, callers are trusted", "lower"),
        ("c", "Only an administrator or an operator script", "lower2"),
        ("d", "I do not know", "keep"),
    ],
    "secret_kind": [
        ("a", "A real credential used in production", "critical"),
        ("b", "A real credential, but for development or test only", "low"),
        ("c", "An example or placeholder, not a secret", "dismiss"),
        ("d", "I do not know", "keep"),
    ],
    "rowcount_consumer": [
        ("a", "The caller tells a user it worked, or moves money, based on the result", "raise"),
        ("b", "The caller ignores the result", "lower"),
        ("c", "I do not know", "keep"),
    ],
}

_SECRET = re.compile(r"^(secret-hardcoded|hardcoded)")
_SKIP_EXPOSURE = re.compile(r"^(secret-|hardcoded|func-unchecked-rowcount)")


def _sev(f) -> str:
    return (f.get("severity_asked") or {}).get("from") or f.get("severity") or "low"


def _name_of(f) -> str:
    m = re.match(r"\s*([A-Za-z_]\w*)\s*=", f.get("snippet", ""))
    return m.group(1) if m else f"line{f.get('line', 0)}"


def candidates(findings: list, code: str, scope: str = "") -> list:
    """Every question the open findings could raise, strongest first, one per (kind, target)."""
    if any("skeptic" not in f for f in findings):
        skeptic.review(findings, code)
    graph = callgraph.build(code)
    prefix = f"{scope}:" if scope else ""
    groups: dict = {}

    def add(kind, target, text, f, fn):
        key = f"{prefix}{kind}:{target}"
        g = groups.setdefault(key, {"question_id": key, "kind": kind, "text": text, "function": fn, "findings": []})
        g["findings"].append(f)

    for f in findings:
        if (f.get("skeptic") or {}).get("skeptic_verdict") != "suspected":
            continue
        fid, line = f.get("id", ""), int(f.get("line") or 0)
        fn = callgraph.function_at(graph, line)
        if _SECRET.match(fid):
            n = _name_of(f)
            add("secret_kind", n, f"Is the value assigned to {n} (line {line}) a real credential?", f, None)
        elif fn and fid == "func-unchecked-rowcount":
            add("rowcount_consumer", fn, f"What does the caller do with the result of {fn}()? It never checks whether a row was affected.", f, fn)
        elif fn and not _SKIP_EXPOSURE.match(fid) and graph["functions"][fn]["entry"] not in ("http",):
            add("exposure", fn, f"Who can call {fn}() (line {graph['functions'][fn]['start']})? "
                                f"The answer decides how urgent the findings inside it are.", f, fn)
    out = []
    for g in groups.values():
        fs = g.pop("findings")
        g["finding_ids"] = [skeptic.finding_id(f) for f in fs]
        g["top_severity"] = max((_sev(f) for f in fs), key=lambda s: WEIGHT.get(s, 0))
        g["options"] = [{"key": k, "label": lab, "impact": imp} for k, lab, imp in OPTIONS[g["kind"]]]
        out.append(g)
    # a low finding is not worth a person's time unless the answer could make it a secret that matters
    out = [g for g in out if g["top_severity"] != "low" or g["kind"] == "secret_kind"]
    out.sort(key=lambda g: (-WEIGHT.get(g["top_severity"], 0), -len(g["finding_ids"]), g["question_id"]))
    return out


def _new_severity(old: str, impact: str) -> str:
    i = LADDER.index(old) if old in LADDER else 0
    if impact == "raise":
        return LADDER[min(i + 1, len(LADDER) - 1)]
    if impact == "lower":
        return LADDER[max(i - 1, 0)]
    if impact == "lower2":
        return LADDER[max(i - 2, 0)]
    if impact in ("critical", "low"):
        return impact
    return old


def _norm_answer(a):
    if isinstance(a, str):
        return {"answer": a}
    return a if isinstance(a, dict) and isinstance(a.get("answer"), str) else None


def apply_answers(findings: list, questions: list, answers) -> list:
    """Apply ``answers`` ({question_id: "b"} or [{question_id, answer}]) to the findings the questions name.
    Idempotent: severity is always computed from the severity before any answer. Returns the applied answers."""
    if isinstance(answers, list):
        answers = {a.get("question_id"): a for a in answers if isinstance(a, dict)}
    by_id = {skeptic.finding_id(f): f for f in findings}
    applied = []
    for q in questions:
        a = _norm_answer((answers or {}).get(q["question_id"]))
        opt = next((o for o in q["options"] if a and o["key"] == a["answer"].strip().lower()), None)
        if not opt:
            continue
        for fid in q["finding_ids"]:
            f = by_id.get(fid)
            if not f:
                continue
            old = _sev(f)
            new = _new_severity(old, opt["impact"])
            f["severity_asked"] = {"from": old, "to": new, "question_id": q["question_id"], "answer": opt["key"], "impact": opt["impact"]}
            f["severity"] = new
            if opt["impact"] == "dismiss":
                f["skeptic"] = {"skeptic_verdict": "false_positive", "basis": "answer",
                                "reason": f"answered {opt['key']}) {opt['label']}"}
        applied.append({"question_id": q["question_id"], "answer": opt["key"], "impact": opt["impact"],
                        "finding_ids": q["finding_ids"]})
    return applied


def load_store(path) -> dict:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return {k: _norm_answer(v) for k, v in raw.items() if _norm_answer(v)} if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def save_store(path, answers: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({k: _norm_answer(v) for k, v in answers.items() if _norm_answer(v)}, indent=1, ensure_ascii=False), encoding="utf-8")


def ask(findings: list, code: str, *, store: dict | None = None, scope: str = "", max_n: int = MAX_QUESTIONS) -> dict:
    """The whole step: apply what is already known, return the (at most ``max_n``) questions still open.
    {"applied": [...], "questions": [...]}"""
    cands = candidates(findings, code, scope)
    store = store or {}
    known = [q for q in cands if q["question_id"] in store]
    applied = apply_answers(findings, known, store) if known else []
    open_q = [q for q in cands if q["question_id"] not in store][:max_n]
    return {"applied": applied, "questions": open_q}


def render_md(questions: list) -> str:
    if not questions:
        return ""
    out = ["## Questions (the answers change priorities)", ""]
    for n, q in enumerate(questions, 1):
        out.append(f"**Q{n}** `{q['question_id']}` {q['text']}  ")
        out.append(f"_affects: {', '.join(q['finding_ids'][:6])}_")
        out += [f"- {o['key']}) {o['label']}" for o in q["options"]]
        out.append("")
    return "\n".join(out)
