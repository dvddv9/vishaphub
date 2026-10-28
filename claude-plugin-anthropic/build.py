# -*- coding: utf-8 -*-
"""Build the .mcpb: copy Vishap's engine (stdlib only) from the repo into scripts/src and zip.

    python claude-plugin-anthropic/build.py
"""
import json
import shutil
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ENGINE = ["static_scan.py", "route_checklist.py", "findings_diff.py", "dataflow.py", "patterns.py",
          "proof.py", "proof_harness.py"]


def main() -> Path:
    dst = HERE / "scripts" / "src"
    (dst / "tools").mkdir(parents=True, exist_ok=True)
    (dst / "__init__.py").write_text("", encoding="utf-8")
    (dst / "tools" / "__init__.py").write_text("", encoding="utf-8")
    for name in ENGINE:
        shutil.copy2(REPO / "src" / "tools" / name, dst / "tools" / name)
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    out = HERE / f"vishap-claude-{manifest['version']}.mcpb"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(HERE / "manifest.json", "manifest.json")
        for p in sorted((HERE / "scripts").rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                z.write(p, p.relative_to(HERE).as_posix())
    return out


if __name__ == "__main__":
    print(f"built {main()}")
