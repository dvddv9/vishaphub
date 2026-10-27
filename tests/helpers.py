import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

EXAMPLE = ROOT / "examples" / "spec.yaml"

BASE = """\
version: 1
updated: 2026-10-27
text: |
  Read one user.
inputs:
  - name: name
    in: query
    rule: "1-64 letters and digits"
outputs:
  - status: 200
    body: "json: id, name only"
must_never:
  - id: sql-from-input
    text: "SQL is never built from the input"
"""


def write_spec(text: str) -> Path:
    d = Path(tempfile.mkdtemp(prefix="spec-test-"))
    p = d / "spec.yaml"
    p.write_text(text, encoding="utf-8")
    return p
