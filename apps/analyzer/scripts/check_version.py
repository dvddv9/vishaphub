# -*- coding: utf-8 -*-
"""CI check: all version files must match src/version.py."""
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
VER = (ROOT / "src" / "version.py").read_text(encoding="utf-8")
m = re.search(r'__version__\s*=\s*"([^"]+)"', VER)
if not m:
    print("FAIL: cannot parse src/version.py"); sys.exit(1)
expected = m.group(1)
print(f"expected version: {expected}")

def check_pyproject():
    p = ROOT / "pyproject.toml"
    if not p.exists(): return None
    t = p.read_text(encoding="utf-8")
    mm = re.search(r'^version\s*=\s*"([^"]+)"', t, re.MULTILINE)
    return mm.group(1) if mm else None

def check_package_json():
    p = ROOT / "ui-next" / "package.json"
    if not p.exists(): return None
    return json.loads(p.read_text(encoding="utf-8")).get("version")

def check_readme():
    """v7.3.4: берём версию из бейджа (badge/version-X.Y.Z-blue), а не первое vX.Y.Z.

    История релизов в README (например, "Version sync: 7.2.2") не должна ломать проверку.
    """
    p = ROOT / "README.md"
    if not p.exists(): return None
    t = p.read_text(encoding="utf-8")
    # 1) badge/version-7.3.4-blue или badge/version-7.3.4
    mm = re.search(r'badge/version-(\d+\.\d+\.\d+)', t)
    if mm:
        return mm.group(1)
    # 2) fallback: releases/tag/vX.Y.Z
    mm = re.search(r'releases/tag/v(\d+\.\d+\.\d+)', t)
    if mm:
        return mm.group(1)
    # 3) fallback: "Version: X.Y.Z"
    mm = re.search(r'Version:\s*(\d+\.\d+\.\d+)', t)
    if mm:
        return mm.group(1)
    # 4) last resort: первое vX.Y.Z
    mm = re.search(r'v(\d+\.\d+\.\d+)', t)
    return mm.group(1) if mm else None

fails = []
for name, fn in [("pyproject.toml", check_pyproject),
                 ("ui-next/package.json", check_package_json),
                 ("README.md", check_readme)]:
    got = fn()
    if got is None:
        print(f"SKIP {name} (not found)")
    elif got != expected:
        fails.append((name, got))
        print(f"MISMATCH {name}: {got} != {expected}")
    else:
        print(f"OK {name}: {got}")

if fails:
    print(f"FAIL: {len(fails)} mismatches"); sys.exit(1)
print("PASS: all versions match")
