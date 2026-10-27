"""Run Verify on files saved by try_generate.py.

    python scripts/try_verify.py examples/spec.yaml .generated/<time>

No model is called. Development helper, not Deliver.
"""

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from generator.design import design  # noqa: E402
from generator.intake import requirements_from  # noqa: E402
from generator.spec import load_spec  # noqa: E402
from generator.verify import verify  # noqa: E402


def main(spec_path: str, folder: str) -> int:
    spec = load_spec(spec_path)
    reqs = requirements_from(spec)
    d = design(spec, reqs)
    base = Path(folder)
    files = {}
    for f in d.files:
        p = base / f.path
        if p.exists():
            files[f.path] = p.read_text(encoding="utf-8")
        elif f.role == "package":
            files[f.path] = ""
            print(f"note: {f.path} was not in the folder, using an empty file")
        else:
            print(f"missing: {f.path}")
            return 2
    res = verify(spec, reqs, d, files, today=dt.date.today())
    print(json.dumps(res.to_dict(), indent=2, ensure_ascii=False))
    return 0 if res.code_verdict == "passed" else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
