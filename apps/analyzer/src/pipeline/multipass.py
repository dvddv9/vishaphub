# -*- coding: utf-8 -*-
"""Focused second pass over the code: logic, money and boundary bugs, a few functions at a time.

Stage 2 is one very wide prompt (risk nodes, STRIDE, SLO, tests ...). On a code file it spends most of
its output on injection and secrets, which the rule engine already finds, and runs out of room for the
bugs a reader must reason about: a negative transfer amount, a lost update, a naive datetime. This module
runs a narrow prompt (``vishap/02b_logic.md``) over chunks of the file and merges the result into
``stage2["security"]["findings"]`` without duplicates.

The model call is injected (``runner`` / ``arunner``) so the chunking and the merge are testable without a
network and the module has no dependency on the LLM client.
"""
from __future__ import annotations

import asyncio
import os
import re
from concurrent.futures import ThreadPoolExecutor

from src.tools.chunker import split_code

PROMPT_NAME = "02b_logic"
MAX_TOKENS = 3500
MAX_WORKERS = 4

_PRIORITY = {"critical": "критично", "high": "критично", "critical.": "критично",
             "important": "важно", "medium": "важно", "optional": "опционально", "low": "опционально"}
_PRIORITIES = ("критично", "важно", "опционально")
_STOP = {"the", "a", "an", "of", "in", "on", "is", "are", "to", "and", "or", "no", "not", "without",
         "for", "with", "при", "без", "в", "на", "и", "не", "по", "из", "для"}


def enabled() -> bool:
    return os.getenv("VISHAP_MULTIPASS", "1").strip().lower() not in ("0", "false", "off", "no")


def is_code(language: str) -> bool:
    return language in ("python", "javascript", "typescript", "java", "go", "php", "c", "cpp", "rust")


def _tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-zа-я_][a-zа-я_0-9]{2,}", (text or "").lower()) if w not in _STOP}


def _anchors(location: str) -> set:
    """Line numbers and identifiers named in a location string ('transfer_funds, lines 51-53')."""
    text = location or ""
    nums = set()
    for a, b in re.findall(r"(\d+)\s*[-–]\s*(\d+)", text):
        if 0 <= int(b) - int(a) <= 60:
            nums.update(range(int(a), int(b) + 1))
    nums.update(int(n) for n in re.findall(r"\d+", text))
    names = {w for w in re.findall(r"[A-Za-z_]\w{3,}", text)
             if w.lower() not in ("line", "lines", "function", "строка", "строки", "функция")}
    return {("n", n) for n in nums} | {("s", n.lower()) for n in names}


def _same(a: dict, b: dict) -> bool:
    """Two findings describe the same defect: same place and a similar claim."""
    ta = _tokens(a.get("title", "") + " " + a.get("issue", ""))
    tb = _tokens(b.get("title", "") + " " + b.get("issue", ""))
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    shared_place = bool(_anchors(a.get("location", "")) & _anchors(b.get("location", "")))
    same_cwe = bool(a.get("cwe")) and a.get("cwe") == b.get("cwe")
    if shared_place and (same_cwe or overlap >= 0.34):
        return True
    return overlap >= 0.75


def _norm(item: dict, n: int) -> dict | None:
    if not isinstance(item, dict):
        return None
    title = str(item.get("title") or "").strip()
    if not title:
        return None
    prio = str(item.get("priority") or "").strip().lower()
    prio = prio if prio in _PRIORITIES else _PRIORITY.get(prio, "важно")
    cwe = str(item.get("cwe") or "").strip().upper()
    cwe = cwe if re.fullmatch(r"CWE-\d+", cwe) else None
    loc = item.get("location")
    if isinstance(loc, (list, tuple)):
        loc = ", ".join(str(x) for x in loc)
    return {"id": f"LOG-{n}", "title": title[:140], "issue": str(item.get("issue") or "").strip()[:500],
            "priority": prio, "cwe": cwe, "location": str(loc or "").strip()[:120],
            "kind": "logic" if str(item.get("kind") or "logic").lower() != "security" else "security"}


def merge_findings(existing: list, new: list) -> list:
    """Return the items of ``new`` that are not already in ``existing`` (or earlier in ``new``)."""
    kept: list = []
    for item in new:
        if any(_same(item, e) for e in existing if isinstance(e, dict)):
            continue
        if any(_same(item, k) for k in kept):
            continue
        kept.append(item)
    return kept


def _chunks_for(material: str, language: str) -> list:
    return split_code(material, language) if enabled() and is_code(language) else []


def _context(chunk: dict, hint) -> dict:
    ctx = {"scope": f"lines {chunk['start']}-{chunk['end']}",
           "functions": chunk["functions"][:30]}
    if isinstance(hint, dict):
        known = [f for f in (hint.get("findings") or [])
                 if isinstance(f, dict) and chunk["start"] <= int(f.get("line") or 0) <= chunk["end"]]
        if known:
            ctx["static_checklist"] = {"findings": known}
    return ctx


def _findings_of(parsed) -> list:
    if not isinstance(parsed, dict) or parsed.get("_error"):
        return []
    items = parsed.get("findings")
    return items if isinstance(items, list) else []


def _collect(raw_by_chunk: list, existing: list) -> tuple:
    n = 0
    pooled = []
    for items in raw_by_chunk:
        for it in items:
            n += 1
            norm = _norm(it, n)
            if norm:
                pooled.append(norm)
    added = merge_findings(existing, pooled)
    for i, f in enumerate(added, start=1):
        f["id"] = f"LOG-{i}"
    return added, len(pooled)


def run_logic_passes(material: str, language: str, runner, hint=None, existing: list | None = None):
    """Run the focused pass over every chunk (threads). ``runner(text, context) -> parsed JSON dict``.

    Returns (added_findings, info). ``info`` never raises: a failed chunk is counted, not fatal.
    """
    chunks = _chunks_for(material, language)
    if not chunks:
        return [], {"passes": 0, "skipped": "not code or disabled"}

    def one(chunk):
        try:
            return runner(chunk["text"], _context(chunk, hint)), None
        except Exception as e:   # one bad chunk must not lose the others
            return None, f"{type(e).__name__}: {e}"

    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(chunks))) as pool:
        results = list(pool.map(one, chunks))
    return _finish(results, existing or [], chunks)


async def arun_logic_passes(material: str, language: str, arunner, hint=None, existing: list | None = None):
    """Async twin of ``run_logic_passes`` (``arunner`` is a coroutine function)."""
    chunks = _chunks_for(material, language)
    if not chunks:
        return [], {"passes": 0, "skipped": "not code or disabled"}

    async def one(chunk):
        try:
            return await arunner(chunk["text"], _context(chunk, hint)), None
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"

    sem = asyncio.Semaphore(MAX_WORKERS)

    async def guarded(chunk):
        async with sem:
            return await one(chunk)

    results = await asyncio.gather(*(guarded(c) for c in chunks))
    return _finish(list(results), existing or [], chunks)


def _finish(results: list, existing: list, chunks: list):
    raw, errors, tokens_in, tokens_out, cost = [], [], 0, 0, 0.0
    for parsed, err in results:
        if err:
            errors.append(err)
            continue
        raw.append(_findings_of(parsed))
        meta = (parsed or {}).get("_meta") or {}
        tokens_in += int(meta.get("tokens_in") or 0)
        tokens_out += int(meta.get("tokens_out") or 0)
        cost += float(meta.get("cost_usd") or 0.0)
        if isinstance(parsed, dict) and parsed.get("_error"):
            errors.append(str(parsed.get("_error")))
    added, pooled = _collect(raw, existing)
    info = {"passes": len(chunks), "chunks": [f"{c['start']}-{c['end']}" for c in chunks],
            "reported": pooled, "added": len(added), "errors": errors[:5],
            "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": round(cost, 6)}
    return added, info


def apply_to_stage2(stage2: dict, added: list, info: dict) -> dict:
    """Append the new findings to ``stage2["security"]["findings"]`` and fold the cost into ``_meta``."""
    if not isinstance(stage2, dict):
        return stage2
    sec = stage2.get("security")
    if not isinstance(sec, dict):
        sec = stage2["security"] = {"summary": "", "findings": []}
    if not isinstance(sec.get("findings"), list):
        sec["findings"] = []
    taken = {str(f.get("id")) for f in sec["findings"] if isinstance(f, dict)}
    for f in added:
        if f["id"] in taken:
            f["id"] = f"LOG-{len(taken) + 1}"
        taken.add(f["id"])
        sec["findings"].append(f)
    meta = stage2.get("_meta")
    if isinstance(meta, dict):
        meta["tokens_in"] = int(meta.get("tokens_in") or 0) + info.get("tokens_in", 0)
        meta["tokens_out"] = int(meta.get("tokens_out") or 0) + info.get("tokens_out", 0)
        meta["cost_usd"] = float(meta.get("cost_usd") or 0.0) + info.get("cost_usd", 0.0)
    stage2["_multipass"] = info
    return stage2
