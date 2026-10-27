"""Try the first four stages on a spec, with a real model.

    python scripts/try_generate.py examples/spec.yaml

Needs CUSTOM_LLM_URL, CUSTOM_LLM_MODEL and CUSTOM_LLM_KEY in the
environment. Writes the generated files under .generated/<time>/ for a
look; nothing outside that folder is touched. This is a development
helper, not Deliver.
"""

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from generator.design import design  # noqa: E402
from generator.generate import generate_code  # noqa: E402
from generator.intake import requirements_from  # noqa: E402
from generator.spec import load_spec  # noqa: E402


def main(path: str) -> int:
    spec = load_spec(path)
    reqs = requirements_from(spec)
    counts = {}
    for r in reqs:
        counts[r.priority] = counts.get(r.priority, 0) + 1
    split = ", ".join(f"{n} {p}" for p, n in counts.items())
    print(f"[Intake]  {len(reqs)} requirements ({split})")

    d = design(spec, reqs)
    print(f"[Design]  {len(d.files)} files, gaps: {len(d.critical_gaps)} critical")
    for g in d.gaps:
        print(f"          {g.id} {g.severity}: {g.text}")

    res = generate_code(spec, reqs, d)
    tests = sum(len(f.tests_found) for f in res.check.files)
    print(f"[Build]   {len(res.files)} files + {tests} tests, check: {'ok' if res.ok else 'errors'}")
    for e in res.check.errors:
        print(f"          {e}")
    for f in res.check.files:
        print(f"          {f.path}: syntax {f.syntax}, ruff {f.lint}")
        for e in f.errors:
            print(f"            - {e}")

    out = ROOT / ".generated" / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    planned = {f.path for f in d.files}
    for rel, content in res.files.items():
        if rel not in planned:
            continue
        target = (out / rel).resolve()
        if out.resolve() not in target.parents:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    (out / "check.json").write_text(json.dumps(res.check.to_dict(), indent=2), encoding="utf-8")
    print(f"saved to {out}")
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "examples/spec.yaml"))
