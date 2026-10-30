"""Entry point inside a worker container: one deliverable in, one JSON report out.

The runner (`container.py`) mounts the deliverable read-only at /in and the spec at /spec.json, and
runs this with `--network none --read-only`. The deliverable is copied to a temporary directory
first because the checks write next to it (pytest cache, bytecode) and /in is read-only.
Isolation is demanded here, not assumed: `require_netns=True` means the process confirms from the
inside (see `safe.container_evidence`) that it is a cut-off container, or nothing runs.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile

from .engine import validate
from .models import Spec


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    src = args[0] if args else "/in"
    spec_path = args[1] if len(args) > 1 else "/spec.json"
    with open(spec_path, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    spec = Spec(
        language=data.get("language", "python"),
        files=list(data.get("files", [])),
        exports=list(data.get("exports", [])),
        tests=list(data.get("tests", [])),
        entry=data.get("entry", ""),
    )
    work = tempfile.mkdtemp(prefix="vishap-work-")
    try:
        root = shutil.copytree(src, work + "/deliverable")
        report = validate(root, spec, require_netns=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    payload = report.as_dict()
    print("VISHAP_REPORT:" + json.dumps(payload, ensure_ascii=False))
    return 0 if payload["verdict"] in ("PASS", "NEEDS_REVIEW") else 1


if __name__ == "__main__":
    sys.exit(main())