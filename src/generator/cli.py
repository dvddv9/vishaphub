"""Command line.

    vishap-generator generate spec.yaml --out src/ [--gate] [--force] [--dry-run]
    vishap-generator init [spec.yaml]
    vishap-generator rollback RUN_ID --out src/ [--force]
    vishap-generator batch SPEC_OR_FOLDER... --out DIR [--workers N] [--gate] [--again]
    vishap-generator baseline spec.yaml [--list]
    vishap-generator history --out DIR [--limit N] [--json]
    vishap-generator info
    vishap-generator serve [--host 127.0.0.1] [--port 8787]

The model comes from the environment (CUSTOM_LLM_URL, CUSTOM_LLM_MODEL,
CUSTOM_LLM_KEY, see docs/HISTORY.md). Exit codes: 0 done, 1 gate blocked,
2 error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from generator.observability.logging import setup_logging
from generator.pipeline.deliver import DeliverError, rollback
from generator.pipeline.orchestrator import DEFAULT_REPAIRS, run_pipeline
from generator.tools.sarif import to_sarif


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
    if res.usage["llm_calls"]:
        print("usage       " + usage_line(res.usage))
    if args.json:
        _write_file(args.json, json.dumps(res.to_dict(), indent=2, ensure_ascii=False) + "\n")
    if args.sarif:
        _write_file(args.sarif, json.dumps(to_sarif(res, spec_file.name), indent=2) + "\n")
    if args.report:
        from generator.tools.report import render_markdown
        _write_file(args.report, render_markdown(res, spec_file.name))
    return res.exit_code


def usage_line(u: dict) -> str:
    """`3 model calls, 8120 tokens in / 2310 out, 41.2 s` and the cost when prices are set."""
    tokens = (f", {u['tokens_in']} tokens in / {u['tokens_out']} out" if u["tokens_in"] or u["tokens_out"]
              else ", tokens not reported by the endpoint")
    cost = f", ${u['cost_usd']:.4f}" if u["cost_usd"] else ""
    return f"{u['llm_calls']} model call(s){tokens}, {u['duration_s']:.1f} s{cost}"


def _default_analyzer():
    from generator.tools.analyzer import run_analyzer
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


def cmd_info(args) -> int:
    import platform

    from generator.config import validate_config
    from generator.llm import LLMConfigError, config_from_env
    from generator.pipeline.stages import STAGES
    from generator.tools.provenance import prompt_hashes
    from generator.version import __version__
    print(f"vishap-generator {__version__}   python {platform.python_version()}")
    print("stages      " + " -> ".join(f"{s.number} {s.title}" for s in STAGES))
    try:
        cfg = config_from_env()
        from urllib.parse import urlsplit
        print(f"model       {cfg.model} at {urlsplit(cfg.url).hostname} (key {'set' if cfg.key else 'not set'})")
    except LLMConfigError as e:
        print(f"model       not configured ({e})")
    print("prompts     " + ", ".join(f"{n}:{h}" for n, h in prompt_hashes().items()))
    errors, warnings = validate_config()
    for w in warnings:
        print(f"warning     {w}")
    for e in errors:
        print(f"error       {e}")
    return 2 if errors else 0


def cmd_history(args) -> int:
    from generator.storage.history import load_history
    entries = load_history(args.out)
    if args.limit:
        entries = entries[-args.limit:]
    if args.json:
        print(json.dumps(entries, indent=2, ensure_ascii=False))
        return 0
    if not entries:
        print(f"no runs recorded in {args.out}")
        return 0
    for e in entries:
        flags = " rolled-back" if e.get("rolled_back") else ""
        flags += " FORCED" if e.get("forced") else ""
        calls = (e.get("usage") or {}).get("llm_calls", 0)
        print(f"{e.get('timestamp', '?')}  {e.get('run_id', '?'):<22} {e.get('verdict', '?'):<8} "
              f"{e.get('spec', '?')}  repairs {e.get('repair_rounds', 0)}  calls {calls}{flags}")
    return 0


def cmd_baseline(args) -> int:
    from generator.pipeline.design import design
    from generator.pipeline.intake import requirements_from
    from generator.tools.baseline import DEFAULT_PATH, compute_fingerprint, load_baseline, save_baseline
    from generator.tools.spec import SpecError, load_spec
    try:
        spec = load_spec(args.spec)
    except (SpecError, OSError) as e:
        print(f"error: spec: {e}", file=sys.stderr)
        return 2
    path = Path(args.spec).resolve().parent / DEFAULT_PATH
    gaps = design(spec, requirements_from(spec)).critical_gaps
    if args.list:
        accepted = load_baseline(path)
        print(f"baseline    {path} ({len(accepted)} accepted)")
        for g in gaps:
            mark = "accepted" if compute_fingerprint(g) in accepted else "OPEN"
            print(f"  {mark:<9} {compute_fingerprint(g)}  {g.text}")
        return 0
    if not gaps:
        print("no critical gaps, nothing to accept")
        return 0
    prints = save_baseline(gaps, path)
    print(f"baseline    {path}")
    for g in gaps:
        print(f"  accepted  {compute_fingerprint(g)}  {g.text}")
    print(f"{len(prints)} critical gap(s) accepted on purpose; the gate now lists them instead of blocking")
    return 0


def cmd_batch(args) -> int:
    from generator.pipeline.batch import batch_exit_code, find_specs, run_batch
    specs = find_specs(args.specs)
    if not specs:
        print("error: no spec files found", file=sys.stderr)
        return 2
    if args.force and not args.gate:
        print("error: --force only makes sense with --gate", file=sys.stderr)
        return 2
    print(f"batch       {len(specs)} spec(s) -> {args.out}, {args.workers} worker(s)")

    def show(row) -> None:
        extra = f" {row.verdict}" if row.verdict else ""
        extra += f"  ({row.error})" if row.error else ""
        print(f"{row.status:<8} {Path(row.spec).name}{extra}", flush=True)

    rows = run_batch(specs, args.out, workers=args.workers, again=args.again, on_row=show,
                     gate=args.gate, force=args.force, repairs=args.repairs,
                     text_check=not args.no_text_check,
                     analyzer=None if args.no_analyzer else _default_analyzer())
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    print("summary     " + ", ".join(f"{n} {k}" for k, n in sorted(counts.items())))
    if args.json:
        _write_file(args.json, json.dumps([r.to_dict() for r in rows], indent=2, ensure_ascii=False) + "\n")
    return batch_exit_code(rows)


def cmd_serve(args) -> int:
    from generator.main import serve
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
    g.add_argument("--report", metavar="FILE", help="write a Markdown report of the run")
    g.set_defaults(func=cmd_generate)

    i = sub.add_parser("init", help="write a starting spec.yaml")
    i.add_argument("path", nargs="?", default="spec.yaml")
    i.set_defaults(func=cmd_init)

    r = sub.add_parser("rollback", help="undo a run")
    r.add_argument("run_id")
    r.add_argument("--out", metavar="DIR", required=True, help="the folder the run wrote to")
    r.add_argument("--force", action="store_true", help="roll back even if files changed since")
    r.set_defaults(func=cmd_rollback)

    inf = sub.add_parser("info", help="version, stages, model, prompts, configuration problems")
    inf.set_defaults(func=cmd_info)

    h = sub.add_parser("history", help="list the runs recorded in an output folder")
    h.add_argument("--out", metavar="DIR", required=True)
    h.add_argument("--limit", type=int, default=0, metavar="N", help="only the last N")
    h.add_argument("--json", action="store_true")
    h.set_defaults(func=cmd_history)

    bl = sub.add_parser("baseline", help="accept the spec's current critical gaps on purpose")
    bl.add_argument("spec")
    bl.add_argument("--list", action="store_true", help="show the gaps and which are accepted; write nothing")
    bl.set_defaults(func=cmd_baseline)

    b = sub.add_parser("batch", help="run several specs, one output folder each")
    b.add_argument("specs", nargs="+", help="spec files or folders of them")
    b.add_argument("--out", metavar="DIR", required=True, help="parent folder; each spec gets its own subfolder")
    b.add_argument("--workers", type=int, default=2, metavar="N")
    b.add_argument("--again", action="store_true", help="run specs that already have a finished run")
    b.add_argument("--gate", action="store_true")
    b.add_argument("--force", action="store_true")
    b.add_argument("--repairs", type=int, default=DEFAULT_REPAIRS, metavar="N")
    b.add_argument("--no-text-check", action="store_true")
    b.add_argument("--no-analyzer", action="store_true")
    b.add_argument("--json", metavar="FILE", help="write the rows as JSON")
    b.set_defaults(func=cmd_batch)

    s = sub.add_parser("serve", help="REST API and web form")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8787)
    s.set_defaults(func=cmd_serve)
    return ap


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    setup_logging()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
