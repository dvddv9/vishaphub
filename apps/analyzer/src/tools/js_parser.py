# -*- coding: utf-8 -*-
"""JavaScript/TypeScript taint patterns (sources + sinks) for Vishap."""
JS_SOURCES = [
    "req.query", "req.body", "req.params", "req.headers",
    "request.query", "request.body", "request.params",
    "document.location", "window.location", "document.cookie",
    "process.argv", "process.env",
]

JS_SINKS = {
    "CWE-79": ["innerHTML", "outerHTML", "document.write", "dangerouslySetInnerHTML"],
    "CWE-89": ["db.query", "connection.query", "pool.query", "client.query", "execute"],
    "CWE-94": ["eval", "Function", "setTimeout", "setInterval"],
    "CWE-22": ["fs.readFile", "fs.readFileSync", "fs.createReadStream", "path.join"],
    "CWE-78": ["child_process.exec", "child_process.spawn", "execSync"],
}


def scan_js_patterns(source: str) -> list[dict]:
    """Quick regex/string scan for JS/TS taint candidates."""
    findings = []
    for cwe, sinks in JS_SINKS.items():
        for sink in sinks:
            if sink in source:
                for i, line in enumerate(source.splitlines(), 1):
                    if sink in line:
                        findings.append({
                            "cwe": cwe, "sink": sink, "line": i,
                            "snippet": line.strip()[:120],
                        })
    return findings
