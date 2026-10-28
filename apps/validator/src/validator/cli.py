"""CLI: `vishap-validator check <root> --spec spec.json [--json]`."""
from __future__ import annotations

import argparse
import json
import os
import sys

from .engine import validate
from .models import Spec
from .version import __version__


def _load_spec(path: str) -> Spec:
    with open(path, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    known = {"language", "files", "exports", "tests", "entry"}
    unknown = set(data) - known
    if unknown:
        raise SystemExit(f"unknown spec keys: {', '.join(sorted(unknown))}")
    return Spec(
        language=data.get("language", "python"),
        files=list(data.get("files", [])),
        exports=list(data.get("exports", [])),
        tests=list(data.get("tests", [])),
        entry=data.get("entry", ""),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vishap-validator", description="Validate generated code against its spec.")
    parser.add_argument("--version", action="version", version=f"vishap-validator {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="validate a deliverable")
    check.add_argument("root", help="directory with the generated code")
    check.add_argument("--spec", required=True, help="path to spec.json")
    check.add_argument("--json", action="store_true", help="machine-readable report")
    check.add_argument("--report-out", default="", help="write the report to this file")

    args = parser.parse_args(argv)

    if args.command == "check":
        if not os.path.isdir(args.root):
            raise SystemExit(f"not a directory: {args.root}")
        spec = _load_spec(args.spec)
        report = validate(args.root, spec)
        payload = report.as_dict()

        if args.report_out:
            with open(args.report_out, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"verdict: {payload['verdict']}")
            if payload["reason"]:
                print(f"reason:  {payload['reason']}")
            for check_result in payload["checks"]:
                state = "skip" if check_result["skipped"] else ("ok" if check_result["ok"] else "fail")
                print(f"  [{state}] {check_result['name']}")
                for finding in check_result["findings"]:
                    print(f"      {finding['severity']:<8} {finding['message']}")
        return 0 if payload["verdict"] in ("PASS", "NEEDS_REVIEW") else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
