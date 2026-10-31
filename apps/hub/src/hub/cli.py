"""CLI: `vishap-hub run --intent generate+validate+analyse --spec spec.yaml --material app.py`.

The same path the HTTP face takes — `run_plan` — so a run from the terminal and a run
from the page cannot disagree about what a verdict means.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import ci, egress, patchcheck, selfhost
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


EXIT_FOR_FIX = {"FIX_VERIFIED": 0, "FIX_PARTIAL": 3, "FIX_REJECTED": 4, "FIX_UNVERIFIED": 5}


def _patch_check(args) -> int:
    """`vishap-hub patch-check --snapshot DIR --diff PATCH --spec spec.json`: no model, same result every time."""
    if not os.path.isdir(args.snapshot):
        print(f"no such directory: {args.snapshot}", file=sys.stderr)
        return 2
    if not os.path.isfile(args.diff) or not os.path.isfile(args.spec):
        print("--diff and --spec must be files", file=sys.stderr)
        return 2
    try:
        spec = json.loads(_read(args.spec))
    except json.JSONDecodeError as exc:
        print(f"the spec is not JSON: {exc}", file=sys.stderr)
        return 2
    out = patchcheck.check(_deliverable(args.snapshot), diff=_read(args.diff), spec=spec)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{out['status']}: {out['reason']}")
        if out.get("rules"):
            r = out["rules"]
            print(f"  rules: {r['before']} -> {r['after']} finding(s); fixed {len(r['fixed'])}, new {len(r['new'])}")
        if out.get("validator"):
            v = out["validator"]
            print(f"  validator: {v.get('verdict') or '-'}; tests ran: {v.get('tests_ran', False)}")
        if out.get("removed") and (out["removed"]["files"] or out["removed"]["symbols"]):
            print("  removed: " + ", ".join(out["removed"]["files"] + out["removed"]["symbols"]))
    return EXIT_FOR_FIX[out["status"]]

def main(argv: list[str] | None = None) -> int:
    egress.install()                                 # acts only while VISHAP_HUB_OFFLINE is set
    parser = argparse.ArgumentParser(prog="vishap-hub", description="Carry a request through one plan.")
    parser.add_argument("--version", action="version", version=f"vishap-hub {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    ini = sub.add_parser("init", help="set this machine up: model, privacy, how code is run")
    ini.add_argument("--provider", choices=["anthropic", "deepseek", "openai", "none"])
    ini.add_argument("--url", default="")
    ini.add_argument("--model", default="")
    ini.add_argument("--key", default=None, help="model key (prefer the prompt: a flag stays in shell history)")
    ini.add_argument("--offline", dest="offline", action="store_true", default=None)
    ini.add_argument("--online", dest="offline", action="store_false")
    ini.add_argument("--isolation", choices=["host", "auto", "docker"])
    ini.add_argument("--worker-image", default="")
    ini.add_argument("--port", type=int, default=0)
    ini.add_argument("--force", action="store_true", help="replace an existing settings file")
    sub.add_parser("doctor", help="say what this installation will do and what cannot work")
    sub.add_parser("serve", help="start the hub on this machine (127.0.0.1 unless VISHAP_HUB_HOST says otherwise)")

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
    run.add_argument("--provider", default="", help="anthropic or deepseek, to use that provider's key and address")
    run.add_argument("--json", action="store_true")
    run.add_argument("--fail-on", choices=ci.FAIL_ON, default=ci.DEFAULT_FAIL_ON,
                     help="the lowest verdict that fails the check (default: fail)")
    run.add_argument("--require-measured", action="store_true",
                     help="exit 3 when the rules are not measured well enough (labelled examples) for a language the run read")
    run.add_argument("--require-complete", action="store_true",
                     help="exit 3 when the verdict is fine but the checking was incomplete (a run that checked nothing is not a pass)")

    pc = sub.add_parser("patch-check", help="apply a patch to a copy of a snapshot and say what it is worth")
    pc.add_argument("--snapshot", required=True, help="directory with the original code")
    pc.add_argument("--diff", required=True, help="a unified diff against the snapshot")
    pc.add_argument("--spec", required=True, help="the validator spec as JSON (entry, files, exports, tests)")
    pc.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "init":
        return selfhost.init(args)
    if args.command == "doctor":
        return selfhost.doctor()
    if args.command == "serve":
        return selfhost.serve()
    selfhost.load()                                  # `run` honours the same settings file
    if args.command == "patch-check":
        return _patch_check(args)
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
                      question=args.question, api_key=args.api_key, model=args.model, preset=args.provider)

    data = result.as_dict()
    decision = ci.decide(data, args.fail_on, args.require_complete, args.require_measured)
    payload = {"plan": plan.as_dict(), "result": data, "ci": decision}
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
        st = data["statuses"]
        print(f"fix:     {st['fix']['status']}   verification: {st['verification']['status']}")
        print(f"ci:      {'pass' if decision['pass'] else 'FAIL'} (exit {decision['exit_code']})"
              + "".join(f"\n         - {why}" for why in decision["reasons"]))
    return decision["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
