"""Fail the build when a test that must run was skipped.

pytest reports a skip as a pass, so a security test that skips itself (no Postgres, no
bubblewrap, a role that bypasses RLS) looks green and proves nothing. This reads the
junit file and exits 1 when any skipped test belongs to one of the named modules.

    python assert_no_skips.py junit.xml test_rls test_scan_toolkit
"""
import sys
import xml.etree.ElementTree as ET


def skipped(path: str, modules: list[str]) -> list[str]:
    found = []
    for case in ET.parse(path).getroot().iter("testcase"):
        where = f"{case.get('classname', '')} {case.get('file', '')}"
        mark = case.find("skipped")
        if mark is not None and any(m in where for m in modules):
            found.append(f"{case.get('classname')}::{case.get('name')} - {(mark.get('message') or '').strip()}")
    return found


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    found = skipped(argv[1], argv[2:])
    for line in found:
        print(f"SKIPPED: {line}")
    if found:
        print(f"{len(found)} test(s) that must run were skipped.")
        return 1
    print("no skips in: " + ", ".join(argv[2:]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
