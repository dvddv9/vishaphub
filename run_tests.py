"""Run the tests of vishap-generator.

    python run_tests.py          # all tests, no network, no model
    python run_tests.py --lint   # also: ruff check, and the version check
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(*cmd) -> int:
    print("\n$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=ROOT).returncode


def main() -> int:
    rc = run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".")
    if "--lint" in sys.argv:
        rc |= run(sys.executable, "scripts/check_version.py")
        rc |= run(sys.executable, "-m", "ruff", "check", "src", "tests", "scripts")
    print("\nOK" if rc == 0 else "\nFAILED")
    return 1 if rc else 0


if __name__ == "__main__":
    sys.exit(main())
