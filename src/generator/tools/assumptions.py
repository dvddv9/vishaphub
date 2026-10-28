"""The `# assumption:` comments the model left in its code.

The build prompt asks for one at every place where the spec is silent. Collected here they become an audit list:
what the model decided on its own, where, and why. Only real comments count (found with the tokenizer), not the
same words inside a string.
"""

from __future__ import annotations

import io
import re
import tokenize

MARK = re.compile(r"#\s*assumption\s*:\s*(.*)", re.IGNORECASE)
MAX_TEXT = 300


def find_assumptions(files: dict[str, str]) -> list[dict]:
    """[{file, line, text}] in file order. A comment that continues on the next `#` line is joined to it."""
    out: list[dict] = []
    for path in sorted(files):
        if not path.endswith(".py"):
            continue
        last, end = None, 0
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(files[path]).readline))
        except (tokenize.TokenError, IndentationError, SyntaxError):
            continue
        for tok in tokens:
            if tok.type != tokenize.COMMENT:
                continue
            m = MARK.match(tok.string)
            if m:
                last = {"file": path, "line": tok.start[0], "text": m.group(1).strip()[:MAX_TEXT]}
                end = tok.start[0]
                out.append(last)
            elif last and tok.start[0] == end + 1 and tok.line.strip().startswith("#"):
                more = tok.string.lstrip("#").strip()
                if more and len(last["text"]) < MAX_TEXT:
                    last["text"] = (last["text"] + " " + more)[:MAX_TEXT]
                end = tok.start[0]
            else:
                last = None
    return out
