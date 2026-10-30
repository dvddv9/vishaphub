"""Review every entry of .gitleaksignore one by one, without showing a secret.

    python .github/scripts/review_gitleaksignore.py

For each fingerprint (commit:file:rule:line) it reads that line from that commit and prints what a reviewer needs to
decide whether the value was ever a real credential: when and by whom it was committed, the file, the rule that
fired, the shape of the value (length, character classes, the first four characters) and the surrounding words. A
value is never printed in full. The decision is the reviewer's: this script removes nothing.

Hints are only hints: a short value with EXAMPLE / FAKE / TEST in it, in a test file, is probably a fixture; a value
that is long, random and in a config file deserves a person.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_WORDS = re.compile(r"example|fake|dummy|test|sample|placeholder|changeme|xxxx|1234|abcde|hunter2|demo", re.IGNORECASE)
REAL_LENGTH = {"aws-access-token": 20, "stripe-access-token": 99, "private-key": 1000, "github-pat": 40}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=False, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace").stdout


def shape(value: str) -> str:
    classes = [n for n, ok in (("lower", re.search("[a-z]", value)), ("upper", re.search("[A-Z]", value)),
                               ("digit", re.search("[0-9]", value)), ("symbol", re.search(r"[^A-Za-z0-9]", value))) if ok]
    return f"{len(value)} chars, {'+'.join(classes)}, starts {value[:4]!r}"


def entries():
    for line in (ROOT / ".gitleaksignore").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            commit, rest = line.split(":", 1)
            path, rule, number = rest.rsplit(":", 2)
            yield commit, path, rule, int(number), line


def main() -> int:
    for n, (commit, path, rule, number, fingerprint) in enumerate(entries(), 1):
        meta = git("show", "-s", "--format=%an | %ad | %s", "--date=short", commit).strip()[:110]
        text = git("show", f"{commit}:{path}").splitlines()
        line = text[number - 1] if 0 < number <= len(text) else ""
        quoted = re.findall(r"""["']([^"']{6,})["']|=\s*([^\s"']{6,})""", line)
        value = next((a or b for a, b in quoted), "")
        context = re.sub(r"[A-Za-z0-9+/=_\-]{12,}", lambda m: f"<{len(m.group(0))}-char token>", line.strip())[:110]
        words = FIXTURE_WORDS.findall(line + " " + path)
        want = REAL_LENGTH.get(rule)
        hint = []
        if words:
            hint.append(f"fixture words: {sorted({w.lower() for w in words})}")
        if want and value and len(value) < want * 0.5:
            hint.append(f"much shorter than a real {rule} value (~{want})")
        print(f"{n:2}. {rule}  {path}:{number}")
        print(f"    commit {commit[:8]}  {meta}")
        print(f"    value  {shape(value) if value else 'not isolated on the line'}")
        print(f"    line   {context}")
        print(f"    hints  {'; '.join(hint) if hint else 'none: needs a person'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())