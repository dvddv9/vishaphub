# -*- coding: utf-8 -*-
"""Run Vishap's exploit probes on one file and print the JSON document (used by analyze.py, also inside WSL)."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["VISHAP_PROVE"] = "1"

from src.tools.proof import prove  # noqa: E402

if __name__ == "__main__":
    code = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
    print(json.dumps(prove(code), default=str))
