# -*- coding: utf-8 -*-
"""Model mode: the hub's verdict with a model in the loop, on the blind sample. Paid, not deterministic, never in CI.

    python -m tests.bench.blind_public.model_eval --estimate                  # what it would cost in tokens, no call
    python -m tests.bench.blind_public.model_eval --dry-run                   # the whole harness, a stub instead of a model
    python -m tests.bench.blind_public.model_eval --confirm-spend --write     # the real run: spends the key's money

What is measured: the model's verdict on each example, N times (the model is not deterministic), combined the way the
hub combines it: an example is a *candidate SAFE* in a run when the rules found nothing, the scan was complete, and the
model said SAFE. The gates are the registered M1 and M2 (CRITERION.md):

  M1  no example labelled critical is a candidate SAFE in ANY run
  M2  the 95% Wilson upper bound of false-SAFE is at most 20% (an example counts as false-SAFE if ANY run made it a
      candidate SAFE: the pessimistic reading, because the answer on a given piece of code must not depend on luck)

A model failure (no key, a refusal, a cut answer, no JSON) is not SAFE. Tokens are the provider's own counts where it
reported them; the characters/4 estimate is printed beside them and never mixed in.

With --write the result is recorded in model_results.json and, per language, in quality.json under "model_mode", where
the hub reads it: only a language that passed here can be SAFE on the strength of rules + model.

This costs money and was not run by the author: it needs a key and a budget the author does not know. The committed
quality.json has no model_mode, so the hub issues no SAFE with a model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from src.tools import safe_gate
from src.tools.static_scan import scan_material
from tests.bench.blind_public import blind_score as bs

HERE = Path(__file__).parent
QUESTION = "Is this code safe? Review it for security vulnerabilities and answer with your verdict."
DEFAULT_PER_SIDE = 25
DEFAULT_RUNS = 3
OUTPUT_CEILING = 4000          # proposal.py asks for at most this many tokens per answer


def sample(manifest: dict, per_side: int = DEFAULT_PER_SIDE) -> list[dict]:
    """The model sample: per (language, label), the first `per_side` frozen examples by SHA-256 of the id."""
    groups: dict = {}
    for e in manifest["examples"]:
        if not e.get("post_run"):
            groups.setdefault((e["language"], e["label"]), []).append(e)
    chosen = []
    for key in sorted(groups):
        chosen += sorted(groups[key], key=lambda e: hashlib.sha256(e["id"].encode()).hexdigest())[:per_side]
    return chosen


def estimate(examples: list[dict], runs: int, system_chars: int = 0, max_material: int = 0) -> dict:
    """An estimate of the tokens a real run would use - characters / 4, labelled as such. Not a price."""
    in_chars = sum(min(e["bytes"], max_material or e["bytes"]) + system_chars + len(QUESTION) for e in examples) * runs
    calls = len(examples) * runs
    return {"examples": len(examples), "runs": runs, "calls": calls,
            "input_tokens_estimated": round(in_chars / 4), "output_tokens_ceiling": calls * OUTPUT_CEILING,
            "basis": "input: characters / 4 of the prompt and the material (an estimate); output: the per-call ceiling "
                     f"({OUTPUT_CEILING}), an upper bound, not an expectation. No price is given: the author does not know the "
                     "provider's tariff."}


def evaluate(examples: list[dict], runs: int, caller, key: str = "", model: str = "", metering=None) -> dict:
    """Ask `caller` (hub.proposal.propose, or a stub) `runs` times per example. Returns per-example outcomes.

    `metering` is hub.meter.metering by default: a context manager whose object says what the provider reported.
    """
    if metering is None:
        from hub import meter
        metering = meter.metering

    out = {}
    for e in examples:
        code = bs.get_code(e)
        scan = scan_material(code, "")                       # pasted, as the hub does
        rules_safe = safe_gate.rules_found_nothing(scan)
        verdicts, usage = [], []
        for _ in range(runs):
            with metering() as m:
                answer = caller(material=code, question=QUESTION, api_key=key, model=model)
            verdict = str(answer.get("verdict") or "").upper() if answer.get("ok") else "ERROR"
            verdicts.append(verdict or "ERROR")
            usage.append(m.measured())
        out[e["id"]] = {"language": e["language"], "detected": (scan.get("coverage") or {}).get("language", ""),
                        "label": e["label"], "criticality": e["criticality"], "rules_safe": rules_safe,
                        "verdicts": verdicts, "candidate_safe_runs": sum(1 for v in verdicts if rules_safe and v == "SAFE"),
                        "usage": usage}
    return out


def gates(per: dict, criterion: dict) -> dict:
    """The registered M1 and M2, per language the engine detected in the pasted text."""
    stats: dict = {}
    for r in per.values():
        if r["detected"] in bs.NOT_A_LANGUAGE:
            continue
        s = stats.setdefault(r["detected"], {"dangerous": 0, "safe": 0, "false_safe": 0, "critical_false_safe": 0})
        if r["label"] == "dangerous":
            s["dangerous"] += 1
            if r["candidate_safe_runs"]:
                s["false_safe"] += 1
                if r["criticality"] == "critical":
                    s["critical_false_safe"] += 1
        else:
            s["safe"] += 1
    result = {}
    for lang, s in sorted(stats.items()):
        g = safe_gate.evaluate_gates(s, criterion)             # the same arithmetic and thresholds as G1 and G2
        result[lang] = {**s, "false_safe_upper_95": g["false_safe_upper_95"], "measured": g["measured"],
                        "safe_allowed": g["safe_allowed"], "why": g["why"].replace("G1", "M1").replace("G2", "M2")}
    return result


def tokens(per: dict) -> dict:
    """Provider-reported tokens summed apart from the estimate; says for how many calls anything was reported."""
    calls = sum(len(r["usage"]) for r in per.values())
    measured = [u for r in per.values() for u in r["usage"] if u]
    return {"calls": calls, "calls_with_provider_usage": len(measured),
            "tokens_in_reported": sum(u["input"] for u in measured) if measured else None,
            "tokens_out_reported": sum(u["output"] for u in measured) if measured else None}


def render(per: dict, g: dict, tok: dict, est: dict, meta: dict) -> str:
    lines = ["# Model mode on the blind sample", "",
             f"{meta['examples']} examples x {meta['runs']} runs, model `{meta['model'] or 'default'}`, "
             f"{meta['date']}. A candidate SAFE needs: rules found nothing, the scan was complete, the model said SAFE.", "",
             "| language | dangerous | safe | false-SAFE | critical false-SAFE | 95% upper bound | measured | SAFE with model | why |",
             "|---|---:|---:|---:|---:|---:|---|---|---|"]
    for lang, r in g.items():
        lines.append(f"| {lang} | {r['dangerous']} | {r['safe']} | {r['false_safe']} | {r['critical_false_safe']} | "
                     f"{100 * r['false_safe_upper_95']:.1f}% | {'yes' if r['measured'] else 'no'} | "
                     f"**{'yes' if r['safe_allowed'] else 'no'}** | {r['why']} |")
    lines += ["", "## Tokens", "",
              f"Provider-reported: {tok['tokens_in_reported']} in, {tok['tokens_out_reported']} out, for "
              f"{tok['calls_with_provider_usage']} of {tok['calls']} calls (`None` means the provider reported nothing).",
              f"Estimated before the run: {est['input_tokens_estimated']} in (characters / 4), output at most "
              f"{est['output_tokens_ceiling']}. The two are not added together.", ""]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    ap.add_argument("--per-side", type=int, default=DEFAULT_PER_SIDE)
    ap.add_argument("--model", default="")
    ap.add_argument("--key-env", default="VISHAP_HUB_LLM_KEY")
    ap.add_argument("--estimate", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--confirm-spend", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)

    from hub import proposal

    manifest = bs.load_manifest()
    examples = sample(manifest, args.per_side)
    est = estimate(examples, args.runs, len(proposal.SYSTEM), proposal.MAX_MATERIAL)
    print(json.dumps(est, indent=1))
    if args.estimate:
        return 0

    if args.dry_run:
        def caller(**_kw):
            return {"ok": True, "verdict": "REQUIRES_REVIEW"}
        key = ""
    else:
        key = os.getenv(args.key_env, "")
        if not (key and args.confirm_spend):
            print("A real run spends the key's money. Set the key in the environment named by --key-env and pass "
                  "--confirm-spend (see --estimate for the size).", file=sys.stderr)
            return 2
        caller = proposal.propose

    per = evaluate(examples, args.runs, caller, key, args.model)
    g = gates(per, bs.load_criterion())
    tok = tokens(per)
    meta = {"examples": len(examples), "runs": args.runs, "model": args.model, "date": time.strftime("%Y-%m-%d"),
            "dry_run": args.dry_run}
    text = render(per, g, tok, est, meta)
    print(text)
    if args.write and not args.dry_run:
        (HERE / "MODEL_RESULTS.md").write_text(text, encoding="utf-8", newline="\n")
        (HERE / "model_results.json").write_text(json.dumps({"meta": meta, "gates": g, "tokens": tok, "per_example": per},
                                                            ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        quality = safe_gate.load_quality()
        for lang, r in g.items():
            entry = quality["languages"].setdefault(lang, {"measured": False, "safe_allowed": False, "why": "no rules-only measurement"})
            entry["model_mode"] = {k: r[k] for k in ("dangerous", "safe", "false_safe", "critical_false_safe",
                                                       "false_safe_upper_95", "measured", "safe_allowed", "why")}
            entry["model_mode"].update({"runs": args.runs, "model": args.model or "default", "date": meta["date"]})
        bs.QUALITY_OUT.write_text(json.dumps(quality, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print("written: MODEL_RESULTS.md, model_results.json, quality.json (model_mode)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))