#!/usr/bin/env python3
"""Vishap V5.7 — [LINES: a-b]."""
import argparse, json, sys
from pathlib import Path


def parse_slices(spec: str, total: int):
    result = []
    for part in spec.split(","):
        part = part.strip()
        if "-" not in part:
            raise ValueError(f"Invalid slice '{part}'")
        a, b = part.split("-", 1)
        a, b = int(a), int(b)
        if a < 1:
            raise ValueError(f"Slice start must be >= 1: {part}")
        if b < a:
            raise ValueError(f"Slice end < start: {part}")
        if b > total:
            raise ValueError(f"Slice end {b} > total lines {total}")
        result.append((a, b))
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--slice", dest="slice_spec")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    p = Path(args.input)
    if not p.exists():
        print(json.dumps({"error": "file not found", "path": str(p)}))
        sys.exit(1)

    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    total = len(lines)

    if args.count:
        print(json.dumps({"total_lines": total}) if args.json else total)
        return

    if not args.slice_spec:
        if args.json:
            print(json.dumps({"lines": lines, "meta": {"total": total}}))
        else:
            sys.stdout.write("\n".join(lines))
            if lines:
                sys.stdout.write("\n")
        return

    try:
        ranges = parse_slices(args.slice_spec, total)
    except ValueError as e:
        print(json.dumps({"error": str(e), "total_lines": total}))
        sys.exit(1)

    out = []
    for a, b in ranges:
        out.extend(lines[a - 1:b])

    if args.json:
        print(json.dumps({"lines": out, "meta": {"total": total,
                                                  "sliced": len(out)}}))
    else:
        sys.stdout.write("\n".join(out))
        if out:
            sys.stdout.write("\n")
        if not args.quiet:
            print(f"# Sliced {len(out)} lines from {total} total", file=sys.stderr)


if __name__ == "__main__":
    main()
