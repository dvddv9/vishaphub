"""CLI: `vishap-hub run --intent generate+validate+analyse --spec spec.yaml --material app.py`.

The same path the HTTP face takes — `run_plan` — so a run from the terminal and a run
from the page cannot disagree about what a verdict means.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .pipeline import run_plan
from .router import RouteError, plan_for
from .version import __version__

TEXT_SUFFIXES = (".py", ".js", ".ts", ".tsx", ".go", ".java", ".rb", ".php", ".sql", ".sh", ".yaml", ".yml", ".json", ".md")


def _read(path: str) -> str:
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        return fh.read()


def _deliverable(root: str) -> dict:
    """Every text file under a directory, keyed by its relative path."""
    files: dict[str, str] = {}
    for base, _dirs, names in os.walk(root):
        for name in names:
            if not name.lower().endswith(TEXT_SUFFIXES):
                continue
            full = os.path.join(base, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            try:
                files[rel] = _read(full)
            except OSError as exc:
                print(f"skip {rel}: {exc}", file=sys.stderr)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vishap-hub", description="Carry a request through one plan.")
    parser.add_argument("--version", action="version", version=f"vishap-hub {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="plan and execute")
    run.add_argument("--intent", required=True,
                     help="ask | analyse | generate | validate | generate+validate | "
                          "validate+analyse | generate+validate+analyse")
    run.add_argument("--material", default="", help="file or directory to analyse")
    run.add_argument("--spec", default="", help="spec file (YAML text) for the generator")
    run.add_argument("--question", default="", help="a question for the model")
    run.add_argument("--deliverable", default="", help="directory of code to validate as the deliverable")
    run.add_argument("--iterations", type=int, default=1)
    run.add_argument("--api-key", default="", help="model key; defaults to VISHAP_HUB_LLM_KEY")
    run.add_argument("--model", default="", help="model name; defaults to the hub's own choice")
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
        if os.path.isdir(args.material):
            print(f"--material is a directory; use --deliverable for code: {args.material}", file=sys.stderr)
            return 2
        if not os.path.isfile(args.material):
            print(f"no such file: {args.material}", file=sys.stderr)
            return 2
        material = _read(args.material)

    spec_text = _read(args.spec) if args.spec and os.path.isfile(args.spec) else ""

    files = _deliverable(args.deliverable) if args.deliverable else {}

    result = run_plan(plan, material=material, files=files, spec=spec_text,
                      question=args.question, api_key=args.api_key, model=args.model)

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
