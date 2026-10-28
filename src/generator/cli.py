"""Command line.

    vishap-generator generate spec.yaml --out src/ [--gate] [--force] [--dry-run]
    vishap-generator init [spec.yaml]
    vishap-generator rollback RUN_ID --out src/ [--force]
    vishap-generator serve [--host 127.0.0.1] [--port 8787]

The model comes from the environment (CUSTOM_LLM_URL, CUSTOM_LLM_MODEL,
CUSTOM_LLM_KEY, see docs/plan.md). Exit codes: 0 done, 1 gate blocked,
2 error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .deliver import DeliverError, rollback
from .pipeline import DEFAULT_REPAIRS, run_pipeline
from .sarif import to_sarif


def _write_file(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def cmd_generate(args) -> int:
    if args.force and not args.gate:
        print("error: --force only makes sense with --gate", file=sys.stderr)
        return 2
    if args.require_coverage and not args.gate:
        print("error: --require-coverage only makes sense with --gate", file=sys.stderr)
        return 2
    if not args.out and not args.no_llm:
        print("error: --out DIR is required", file=sys.stderr)
        return 2
    spec_file = Path(args.spec)
    print(f"spec        {spec_file}")
    res = run_pipeline(
        spec_file, out_dir=args.out, gate=args.gate, force=args.force, dry_run=args.dry_run,
        no_llm=args.no_llm, repairs=args.repairs, require_coverage=args.require_coverage, text_check=not args.no_text_check,
        analyzer=None if args.no_analyzer else _default_analyzer(),
        log=print)
    if res.error:
        print(f"\nerror: {res.error}", file=sys.stderr)
    elif res.verify:
        v = res.verify
        print()
        print(f"verdict     {v.code_verdict.upper()}")
        open_items = []
        if res.design and res.design.critical_gaps:
            open_items.append(f"{len(res.design.critical_gaps)} critical gap(s)")
        if v.spec_stale:
            open_items.append("spec stale")
        if open_items:
            print("open        " + ", ".join(open_items))
        if res.deliver and res.deliver.dry_run and res.deliver.diff:
            print("\n" + res.deliver.diff.rstrip())
        if not args.gate and not res.error and (open_items or v.code_verdict != "passed"):
            print("note        without --gate the files are written; the problems stay in the report")
    if args.json:
        _write_file(args.json, json.dumps(res.to_dict(), indent=2, ensure_ascii=False) + "\n")
    if args.sarif:
        _write_file(args.sarif, json.dumps(to_sarif(res, spec_file.name), indent=2) + "\n")
    return res.exit_code


def _default_analyzer():
    from .analyzer import run_analyzer
    return run_analyzer


TEMPLATE = """\
# spec.yaml for vishap-generator. Change the text and the lists, keep the keys.
version: 1
updated: {today}          # the day you last reviewed this spec; older than 90 days counts as stale

text: |
  Describe in plain words what to build, who calls it, and what it must not do.

target: python/flask      # language/framework
kind: http-endpoint       # function | http-endpoint | module | config
output: handlers/thing.py # where the code goes: relative path, forward slashes
caller: public            # public | signed-in | internal (needed for http-endpoint)
route: GET /thing

inputs:
  - name: name
    in: query
    rule: "1-64 letters and digits"

outputs:
  - status: 200
    body: "json: id, name only"
  - status: 404
    when: "no such item"
  - status: 400
    when: "invalid name"

profile: owasp-asvs-2
constraints: [include-tests, validate-inputs]

must_never:
  - id: sql-from-input
    text: "SQL is never built from the input"
  - id: log-raw-input
    text: "Raw input is never logged"

check: analyzer
"""


def cmd_init(args) -> int:
    import datetime as dt
    path = Path(args.path)
    if path.exists():
        print(f"error: {path} already exists, not overwriting", file=sys.stderr)
        return 2
    path.write_text(TEMPLATE.format(today=dt.date.today().isoformat()), encoding="utf-8")
    print(f"wrote {path}")
    print(f"next: vishap-generator generate {path} --no-llm   (check the spec, no model)")
    return 0


def cmd_rollback(args) -> int:
    try:
        out = rollback(args.out, args.run_id, force=args.force)
    except DeliverError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    for p in out.restored:
        print(f"restored    {p}")
    for p in out.removed:
        print(f"removed     {p}")
    print(f"run {out.run_id} rolled back")
    return 0


def cmd_serve(args) -> int:
    from .server import serve
    return serve(args.host, args.port)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="vishap-generator",
                                 description="Generate code from a specification and prove it.")
    sub = ap.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="run the five stages on a spec file")
    g.add_argument("spec", help="path to spec.yaml")
    g.add_argument("--out", metavar="DIR", help="where to write the files")
    g.add_argument("--gate", action="store_true",
                   help="block the write on a failed critical/high requirement, coverage under 80%%, "
                        "an open critical gap, or a stale spec; exit 1")
    g.add_argument("--force", action="store_true", help="with --gate: write anyway, trace says forced")
    g.add_argument("--dry-run", action="store_true", help="show the diff, write nothing")
    g.add_argument("--no-llm", action="store_true", help="Intake and the spec check only")
    g.add_argument("--no-text-check", action="store_true",
                   help="do not ask the model to compare the free text with the requirements")
    g.add_argument("--no-analyzer", action="store_true", help="skip the Vishap Analyzer")
    g.add_argument("--repairs", type=int, default=DEFAULT_REPAIRS, metavar="N",
                   help=f"repair rounds when Verify finds problems (default {DEFAULT_REPAIRS})")
    g.add_argument("--require-coverage", action="store_true",
                   help="with --gate: coverage that could not be measured (no `coverage` package) blocks too")
    g.add_argument("--json", metavar="FILE", help="write the full result as JSON")
    g.add_argument("--sarif", metavar="FILE", help="write SARIF 2.1.0 for the result")
    g.set_defaults(func=cmd_generate)

    i = sub.add_parser("init", help="write a starting spec.yaml")
    i.add_argument("path", nargs="?", default="spec.yaml")
    i.set_defaults(func=cmd_init)

    r = sub.add_parser("rollback", help="undo a run")
    r.add_argument("run_id")
    r.add_argument("--out", metavar="DIR", required=True, help="the folder the run wrote to")
    r.add_argument("--force", action="store_true", help="roll back even if files changed since")
    r.set_defaults(func=cmd_rollback)

    s = sub.add_parser("serve", help="REST API and web form")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8787)
    s.set_defaults(func=cmd_serve)
    return ap


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
