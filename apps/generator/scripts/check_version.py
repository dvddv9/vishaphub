"""The version must be the same in version.py, pyproject.toml and CHANGELOG.md."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    code = re.search(r'__version__ = "([^"]+)"', (ROOT / "src/generator/version.py").read_text("utf-8")).group(1)
    toml = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text("utf-8"), re.M).group(1)
    log = re.search(r"^## \[(\d[^\]]*)\]", (ROOT / "CHANGELOG.md").read_text("utf-8"), re.M).group(1)
    print(f"version.py {code}, pyproject.toml {toml}, CHANGELOG.md {log}")
    if not code == toml == log:
        print("error: the three versions differ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
