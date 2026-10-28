"""CLI: `vishap-hub run --intent generate+validate+analyse --material file.py`."""
from __future__ import annotations

import argparse
import json
import os
import sys

from .pipeline import run_plan
from .router import RouteError, plan_for
from .services import ServiceConfig
from .version import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vishap-hub", description="Carry a request through the Vishap services.")
    parser.add_argument("--version", action="version", version=f"vishap-hub {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="plan and execute")
    run.add_argument("--intent", required=True,
                     help="analyse | generate | validate | generate+validate | validate+analyse | generate+validate+analyse")
    run.add_argument("--material", default="", help="file to analyse")
    run.add_argument("--spec", default="", help="spec file for the generator")
    run.add_argument("--validator-spec", default="", help="spec.json for the validator")
    run.add_argument("--out", default="", help="output directory for generated code")
    run.add_argument("--iterations", type=int, default=1)
    run.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    if args.command != "run":
        return 2

    try:
        plan = plan_for(args.intent, args.iterations)
    except RouteError as exc:
        print(f"cannot route: {exc}", file=sys.stderr)
        return 2

    material = ""
    if args.material:
        if not os.path.isfile(args.material):
            print(f"no such file: {args.material}", file=sys.stderr)
            return 2
        with open(args.material, encoding="utf-8", errors="replace") as fh:
            material = fh.read()

    spec_text = ""
    if args.spec:
        with open(args.spec, encoding="utf-8-sig", errors="replace") as fh:
            spec_text = fh.read()

    validator_spec = {}
    if args.validator_spec:
        with open(args.validator_spec, encoding="utf-8-sig") as fh:
            validator_spec = json.load(fh)

    result = run_plan(
        ServiceConfig(),
        plan,
        material=material,
        spec=spec_text,
        filename=os.path.basename(args.material) if args.material else "input.txt",
        out_dir=args.out,
        validator_spec=validator_spec,
    )

    payload = {"plan": plan.as_dict(), "result": result.as_dict()}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"plan:    {' -> '.join(plan.as_dict()['stages'])} x{plan.iterations}")
        if plan.note:
            print(f"note:    {plan.note}")
        print(f"verdict: {result.verdict}" + (f" ({result.reason})" if result.reason else ""))
        for step in result.steps:
            state = "ok" if step.ok else "fail"
            print(f"  [{state}] {step.stage:<10} {step.verdict:<18} {step.detail}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
