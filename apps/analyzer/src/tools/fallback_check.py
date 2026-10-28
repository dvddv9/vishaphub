#!/usr/bin/env python3
"""Vishap V5.7 — loss_pct."""
import argparse, json

REQUIRED = {
    "D0": ["[CONCLUSION]", "[RISK]", "[FUNC:FULL]"],
    "D1": ["[CONCLUSION]", "[RISK]", "[ACTION]", "[QUESTION]", "[FUNC:FULL]"],
    "D2": ["[ECHO]", "[ROUTE]", "[CONCLUSION]", "[RISK_NODES]",
           "[ASSEMBLY]", "[REFACTORING]", "[PARALLELS]", "[TESTS]",
           "[ACTION]", "[QUESTIONS]", "[FUNC:FULL]", "[MANDATORY BASE]"],
    "D3": ["[ECHO]", "[ROUTE]", "[CONCLUSION]", "[RISK_NODES]",
           "[ASSEMBLY]", "[REFACTORING]", "[PARALLELS]", "[TESTS]",
           "[ACTION]", "[QUESTIONS]", "[FUNC:FULL]", "[MANDATORY BASE]"],
    "D4": ["[ECHO]", "[ROUTE]", "[CONCLUSION]", "[RISK_NODES]",
           "[ASSEMBLY]", "[REFACTORING]", "[PARALLELS]", "[TESTS]",
           "[ACTION]", "[QUESTIONS]", "[FUNC:FULL]", "[MANDATORY BASE]",
           "[COMPLEXITY]", "[STRUCTURE]", "[TEXTURE]", "[SHADOWS]",
           "[SECURITY]", "[TEST_ANALYSIS]", "[DEPENDENCIES]",
           "[FAILURE_POINTS]", "[EVOLVABILITY]", "[AUTHOR_SOLUTIONS]",
           "[REFACTORING_PLAN]", "[ECONOMICS]", "[FAILURE_SCENARIO]",
           "[CONFLICT_RESOLUTION]", "[FINAL_METRICS]", "[FINAL_CALCULATIONS]",
           "[COMPLETENESS_CHECK]", "[GRADUATED_CONCLUSION]"],
}
LOSS_THRESHOLD = 30.0
FORCED_BLOCKS = ("[FUNC:FULL]", "[MANDATORY BASE]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", required=True, choices=list(REQUIRED.keys()))
    ap.add_argument("--present", required=True)
    args = ap.parse_args()
    required = REQUIRED[args.level]
    present = {b.strip() for b in args.present.split(",") if b.strip()}
    missing = [b for b in required if b not in present]
    forced_missing = [b for b in missing if b in FORCED_BLOCKS]
    if forced_missing:
        loss_pct = 100.0
        verdict = "INCOMPLETE_FORCED"
    else:
        loss_pct = round(len(missing) / len(required) * 100, 1)
        verdict = "ACCEPTABLE" if loss_pct <= LOSS_THRESHOLD else "INCOMPLETE"
    print(json.dumps({
        "level": args.level,
        "required_count": len(required),
        "present_count": len(required) - len(missing),
        "missing": missing,
        "missing_count": len(missing),
        "loss_pct": loss_pct,
        "threshold": LOSS_THRESHOLD,
        "verdict": verdict,
        "forced_missing": forced_missing,
        "forced_override": bool(forced_missing),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
