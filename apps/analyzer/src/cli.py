# -*- coding: utf-8 -*-
"""Vishap CLI entry point.

Usage:
    vishap analyze <file>
    vishap analyze <file> --save-baseline .vishap-baseline.json
    vishap analyze <file> --baseline .vishap-baseline.json
    vishap info
    vishap --version
"""
import argparse
import sys
from pathlib import Path

from src.config import APP_NAME
from src.version import __version__
from src.pipeline.orchestrator import run_pipeline
from src.tools.diff import get_changed_files, get_uncommitted_files, is_changed
from src.tools.sbom import generate_sbom, parse_sbom, is_cyclonedx_available
from src.tools.sarif import to_sarif, write_sarif
from src.tools.quality_gate import load_quality_gate, evaluate_gate


def cmd_analyze(args):
    """Analyze a file."""
    path = Path(args.input)
    if not path.exists():
        print(f"Error: {path} not found", file=sys.stderr)
        sys.exit(1)

    # === Diff-aware (P0-2) ===
    if args.diff:
        changed = get_changed_files(args.diff)
        if not is_changed(args.input, changed):
            print(f"[Diff] {args.input} not changed since {args.diff} -- skip")
            if getattr(args, "gate", False):
                print("gate:          SKIPPED (file unchanged)", file=sys.stderr)
                sys.exit(3)
            sys.exit(0)
        if not args.quiet:
            print(f"[Diff] {args.input} changed since {args.diff} ({len(changed)} files)")

    if args.changed_only:
        changed = get_uncommitted_files()
        if not is_changed(args.input, changed):
            print(f"[Diff] {args.input} has no uncommitted changes -- skip")
            if getattr(args, "gate", False):
                print("gate:          SKIPPED (file unchanged)", file=sys.stderr)
                sys.exit(3)
            sys.exit(0)
        if not args.quiet:
            print(f"[Diff] {args.input} uncommitted ({len(changed)} files)")

    material = path.read_text(encoding="utf-8", errors="replace")
    result = run_pipeline(
        material, path.name,
        verbose=not args.quiet,
        baseline_path=args.baseline,
        save_baseline_path=args.save_baseline,
        context_root=getattr(args, "context_root", None),
    )

    md = result.get("final_markdown", "")
    audit = result.get("audit", {})
    stats = result.get("baseline_stats") or {}

    # === SARIF (P1-4) ===
    if getattr(args, "sarif", None):
        risk_nodes = (result.get("stage2") or {}).get("risk_nodes", []) or []
        sarif_data = to_sarif(
            audit=audit,
            sast_result=None,
            sca_result=None,
            source_file=path.name,
            risk_nodes=risk_nodes,
        )
        write_sarif(sarif_data, args.sarif)
        _n_results = len(sarif_data["runs"][0]["results"])
        print(f"sarif:         {args.sarif} ({_n_results} results)")

    # === SBOM (P0-3) ===
    if getattr(args, "sbom", None):
        if is_cyclonedx_available():
            sbom = generate_sbom(output_path=args.sbom)
            sbom_info = parse_sbom(sbom)
            if sbom:
                print(f"sbom:          {args.sbom} ({sbom_info['count']} components)")
            else:
                print("sbom:          generation failed")
        else:
            print("sbom:          cyclonedx-py not available")

    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
        print(f"Written: {args.output}")
    else:
        print(md)
        print()
        print(f"audit_id:      {audit.get('audit_id')}")
        print(f"material_hash: {audit.get('material_hash')}")
        print(f"verdict:       {audit.get('critique_verdict')} / {audit.get('risk_verdict')}")

    # === Quality Gate (P1-5) ===
    if getattr(args, "gate", False):
        _cfg = load_quality_gate(args.config)
        _risk_nodes = (result.get("stage2") or {}).get("risk_nodes", []) or []
        _reachable = bool(
            ((result.get("audit") or {}).get("exploitability") or {})
            .get("reachable", False)
        )
        _gate = evaluate_gate(
            _risk_nodes, _cfg, reachable=_reachable,
            verbose=not args.quiet,
        )
        if _gate["passed"]:
            print(f"gate:          PASSED "
                  f"(critical={_gate['critical']}, high={_gate['high']}, "
                  f"total={_gate['total']}, ignored={_gate['ignored']})")
        else:
            print("gate:          FAILED", file=sys.stderr)
            for _r in _gate["reasons"]:
                print(f"  - {_r}", file=sys.stderr)
            sys.exit(1)

    # Baseline summary (only if used)
    if stats.get("baseline_saved"):
        print(f"baseline_saved: {stats.get('baseline_saved_count', 0)} fingerprints "
              f"-> {stats.get('baseline_save_path', '')}")
    if stats.get("baseline_used"):
        print(f"baseline:      new={stats.get('baseline_new', 0)} "
              f"known={stats.get('baseline_known', 0)} "
              f"total={stats.get('baseline_total', 0)}")


def cmd_sbom(args):
    """Generate CycloneDX SBOM."""
    if not is_cyclonedx_available():
        print("Error: cyclonedx-py not found. Install: pip install cyclonedx-bom", file=sys.stderr)
        sys.exit(2)

    output = args.output or "sbom.json"
    source = args.source or "environment"
    sbom = generate_sbom(output_path=output, source=source)

    if not sbom:
        print("Error: SBOM generation failed (empty result)", file=sys.stderr)
        sys.exit(2)

    info = parse_sbom(sbom)
    print(f"SBOM written: {output}")
    print(f"  format:       {info['bom_format']}")
    print(f"  spec version: {info['spec_version']}")
    print(f"  components:   {info['count']}")
    print(f"  serial:       {info['serial_number']}")


def cmd_prove(args):
    """Run probes against the handlers in a file (and optionally compare a patched version)."""
    from src.tools.proof import prove_cli

    sys.exit(prove_cli(args.input, patched=args.patched, unisolated=args.unisolated, answers=args.answers))


def cmd_site(args):
    """Site checks. Shallow on purpose: a few polite requests, no exploitation."""
    from src.tools import site_scan
    report = site_scan.scan(args.url)
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(report.to_markdown())
    return 0 if report.verdict == "SAFE" else 1


def cmd_scan(args):
    """Scan a directory (or what a diff added) with the built-in rules: no LLM, no network unless --deps."""
    from src.tools.repo_scan import scan_cli

    sys.exit(scan_cli(
        args.path, baseline=args.baseline, save_baseline_path=args.save_baseline, diff_file=args.diff,
        deps=args.deps, sarif=args.sarif, json_out=args.json, output=args.output, fail_on=args.fail_on,
        prove_handlers=args.prove, exclude=tuple(args.exclude or ()), max_files=args.max_files,
    ))


def cmd_info(args):
    """Show info."""
    print(f"{APP_NAME} {__version__} - 6-stage LLM pipeline")
    print("Pipeline: Stage 0-5 (Orchestrator > Scanner > Analyst > Researcher > Synthesizer > Transmitter)")
    print("Features: audit trail, PII redaction, compliance flags, SAST/SCA, SARIF, retry, fallback, baseline")
    print()
    print("Commands:")
    print("  vishap analyze <file>   - analyze a file")
    print("  vishap prove <file>     - run probes against the handlers (needs bubblewrap, or --unisolated)")
    print("  vishap scan <dir>       - scan a repository or a diff (--baseline, --diff, --deps, --sarif, --fail-on)")
    print("  vishap info             - this help")
    print()
    print("Options for analyze:")
    print("  --save-baseline PATH    - save fingerprints of findings to PATH")
    print("  --baseline PATH         - compare against baseline, report only new findings")
    print("  --output, -o PATH       - write markdown report to file")
    print("  --quiet                 - suppress logs")
    print()
    print("API: python -m src.main   - FastAPI on :5001")


def main():
    # Windows: ensure UTF-8 output (cp1251 breaks on arrows, em-dash, etc.)
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    ap = argparse.ArgumentParser(prog="vishap", description=f"{APP_NAME} {__version__}")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")

    sub = ap.add_subparsers(dest="command")

    p_analyze = sub.add_parser("analyze", help="Analyze a file")
    p_analyze.add_argument("input", help="Path to file")
    p_analyze.add_argument("--quiet", action="store_true")
    p_analyze.add_argument("--output", "-o", help="Output markdown path")
    p_analyze.add_argument(
        "--save-baseline", metavar="PATH",
        help="Save fingerprints of findings to PATH (baseline v1.0)",
    )
    p_analyze.add_argument(
        "--baseline", metavar="PATH",
        help="Compare against baseline; report only new findings",
    )
    p_analyze.add_argument(
        "--diff", metavar="REF",
        help="Analyze only if input changed since REF (e.g. origin/main)",
    )
    p_analyze.add_argument(
        "--changed-only", action="store_true",
        help="Analyze only if input has uncommitted changes",
    )
    p_analyze.add_argument(
        "--sbom", metavar="PATH",
        help="Generate CycloneDX SBOM alongside analysis (path)",
    )
    p_analyze.add_argument(
        "--sarif", metavar="PATH",
        help="Generate SARIF 2.1.0 output for GitHub Code Scanning (path)",
    )
    p_analyze.add_argument(
        "--gate", action="store_true",
        help="Enable quality gate; exit 1 if thresholds fail (CI)",
    )
    p_analyze.add_argument(
        "--config", metavar="PATH", default=".vishap.yml",
        help="Quality gate config path (default: .vishap.yml)",
    )
    p_analyze.add_argument(
        "--context-root", metavar="DIR",
        help="Enable inter-file analysis: collect imports under DIR",
    )
    p_analyze.set_defaults(func=cmd_analyze)

    p_prove = sub.add_parser("prove", help="Run probes against the handlers in a file (executes the code, isolated)")
    p_prove.add_argument("input", help="Path to a Flask-style Python file")
    p_prove.add_argument("--patched", metavar="PATH", help="Compare with a patched version: did the fix close the exploits?")
    p_prove.add_argument("--unisolated", action="store_true",
                         help="Allow running without bubblewrap. Only for code you would run anyway.")
    p_prove.add_argument("--answers", metavar="FILE",
                         help="JSON with answers to the questions of an earlier run: {\"<question_id>\": \"<option key>\"}")
    p_prove.set_defaults(func=cmd_prove)

    p_scan = sub.add_parser("scan", help="Scan a directory or a diff with the built-in rules (no LLM)")
    p_scan.add_argument("path", help="Directory to scan")
    p_scan.add_argument("--baseline", metavar="FILE", help="Compare with a saved baseline: report only what is new/fixed")
    p_scan.add_argument("--save-baseline", metavar="FILE", help="Save the current findings as the baseline")
    p_scan.add_argument("--diff", metavar="FILE", help="Unified diff ('-' for stdin): keep only findings on added lines")
    p_scan.add_argument("--deps", action="store_true", help="Audit pinned dependencies against OSV (needs network)")
    p_scan.add_argument("--sarif", metavar="FILE", help="Write SARIF (one location per file)")
    p_scan.add_argument("--json", metavar="FILE", help="Write the full result as JSON")
    p_scan.add_argument("--output", "-o", metavar="FILE", help="Write the Markdown report to a file")
    p_scan.add_argument("--fail-on", choices=["critical", "high", "medium", "low"],
                        help="Exit 1 if a finding at/above this severity exists (only new ones with --baseline)")
    p_scan.add_argument("--prove", action="store_true", help="Run exploit probes on handler files (executes code, isolated)")
    p_scan.add_argument("--exclude", action="append", metavar="REGEX", help="Skip paths matching this regex (repeatable)")
    p_scan.add_argument("--max-files", type=int, default=2000)
    p_scan.set_defaults(func=cmd_scan)

    p_site = sub.add_parser("site", help="Check a deployed site: headers, cookies, exposed paths, certificate (no LLM)")
    p_site.add_argument("url", help="Site URL")
    p_site.add_argument("--json", action="store_true", help="Machine-readable report")
    p_site.set_defaults(func=cmd_site)

    p_sbom = sub.add_parser("sbom", help="Generate CycloneDX SBOM")
    p_sbom.add_argument("--output", "-o", default="sbom.json", help="Output SBOM path (default: sbom.json)")
    p_sbom.add_argument("--source", default="environment",
                        help="cyclonedx-py source: environment | requirements | pipenv | poetry")
    p_sbom.set_defaults(func=cmd_sbom)

    p_info = sub.add_parser("info", help="Show info")
    p_info.set_defaults(func=cmd_info)

    args = ap.parse_args()
    if not args.command:
        ap.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
