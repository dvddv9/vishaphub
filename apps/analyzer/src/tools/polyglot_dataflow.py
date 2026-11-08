"""Bounded, intrafile source-to-sink analysis for common web languages.

This intentionally reports only direct assignments and simple identifier copies.
It is a deterministic aid, not a proof of exploitability or a replacement for a
language-specific compiler analysis.
"""
from __future__ import annotations

import re

_GRAMMARS = {
    "javascript": ("tree_sitter_javascript", "javascript"),
    "typescript": ("tree_sitter_typescript", "tsx"),
    "java": ("tree_sitter_java", "java"),
    "go": ("tree_sitter_go", "go"),
    "rust": ("tree_sitter_rust", "rust"),
}

_SOURCES = {
    "javascript": r"(?:req(?:uest)?\.(?:body|query|params|headers)|ctx\.(?:request\.)?(?:body|query|params))",
    "typescript": r"(?:req(?:uest)?\.(?:body|query|params|headers)|ctx\.(?:request\.)?(?:body|query|params))",
    "java": r"(?:request|req)\.getParameter\s*\([^)]*\)|(?:request|req)\.getHeader\s*\([^)]*\)",
    "go": r"(?:r|req)\.(?:URL\.Query\(\)\.Get|FormValue|PostForm\.Get|Header\.Get)\s*\([^)]*\)",
    "rust": r"(?:query|form|params|headers)\s*\.get\s*\([^)]*\)|(?:query|form)_param\s*\([^)]*\)",
}

_SINKS = {
    "javascript": [("CWE-78", "command", r"\b(?:exec|execSync|spawn|spawnSync)\s*\(([^;]*)"), ("CWE-89", "sql", r"\.(?:query|execute|raw)\s*\(([^;]*)"), ("CWE-79", "html", r"\.(?:innerHTML|outerHTML)\s*=\s*([^;]*)")],
    "typescript": [("CWE-78", "command", r"\b(?:exec|execSync|spawn|spawnSync)\s*\(([^;]*)"), ("CWE-89", "sql", r"\.(?:query|execute|raw)\s*\(([^;]*)"), ("CWE-79", "html", r"\.(?:innerHTML|outerHTML)\s*=\s*([^;]*)")],
    "java": [("CWE-78", "command", r"(?:Runtime\.getRuntime\(\)\.exec|new\s+ProcessBuilder)\s*\(([^;]*)"), ("CWE-89", "sql", r"\.(?:executeQuery|executeUpdate|execute)\s*\(([^;]*)"), ("CWE-79", "html", r"(?:getWriter\(\)\.)?(?:print|println|write)\s*\(([^;]*)")],
    "go": [("CWE-78", "command", r"exec\.Command(?:Context)?\s*\(([^;]*)"), ("CWE-89", "sql", r"\.(?:Query|QueryRow|Exec|Prepare)\s*\(([^;]*)")],
    "rust": [("CWE-78", "command", r"Command::new\s*\(([^;]*)"), ("CWE-89", "sql", r"(?:query|execute)\s*\(([^;]*)")],
}

_ASSIGN = re.compile(r"(?:\b(?:const|let|var|final|String|int|long|auto|:=)\s+)?([A-Za-z_$][\w$]*)\s*(?:=|:=)\s*(.+)")
_IDENT = re.compile(r"\b[A-Za-z_$][\w$]*\b")


def _parser(language: str):
    module_name, grammar_attr = _GRAMMARS[language]
    module = __import__(module_name)
    from tree_sitter import Language, Parser

    grammar = getattr(module, grammar_attr)()
    parser = Parser(Language(grammar))
    return parser


def analyze_dataflow(material: str, language: str) -> dict:
    """Return a conservative taint path when a parsed file has a simple flow."""
    if language not in _GRAMMARS or not material.strip():
        return {}
    try:
        tree = _parser(language).parse(material.encode("utf-8", errors="replace"))
        if tree.root_node.has_error:
            return {}
    except Exception:
        return {}

    lines = material.splitlines()
    src_rx = re.compile(_SOURCES[language])
    tainted: dict[str, tuple[int, str]] = {}
    # Fixed-point assignment propagation handles chains regardless of source order.
    assignments: list[tuple[int, str, str]] = []
    for number, line in enumerate(lines, 1):
        match = _ASSIGN.search(line)
        if match:
            assignments.append((number, match.group(1), match.group(2)))
            source = src_rx.search(match.group(2))
            if source:
                tainted[match.group(1)] = (number, source.group(0))
    for _ in range(min(8, len(assignments))):
        changed = False
        for number, target, expression in assignments:
            if target in tainted:
                continue
            for ident in _IDENT.findall(expression):
                if ident in tainted:
                    tainted[target] = tainted[ident]
                    changed = True
                    break
        if not changed:
            break

    for number, line in enumerate(lines, 1):
        for cwe, category, pattern in _SINKS[language]:
            for match in re.finditer(pattern, line):
                used = sorted(set(_IDENT.findall(match.group(1))) & tainted.keys())
                if not used:
                    continue
                origin_name = used[0]
                origin_line, origin_expr = tainted[origin_name]
                return {
                    "language": language,
                    "path": [
                        {"line": origin_line, "type": "source", "name": origin_expr, "content": lines[origin_line - 1][:240]},
                        {"line": number, "type": "sink", "name": category, "content": line[:240]},
                    ],
                    "source": {"line": origin_line, "name": origin_expr, "content": lines[origin_line - 1][:240]},
                    "sink": {"line": number, "name": category, "content": line[:240], "cwe": cwe},
                    "intermediate": [{"name": origin_name}],
                    "source_count": len(tainted), "sink_count": 1,
                }
    return {}
