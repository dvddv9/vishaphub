# -*- coding: utf-8 -*-
"""Built-in static analysis: no LLM, no external binaries, no files on disk.

Why this exists
---------------
The web pipeline used to call ``run_sast(filename)``, which *opens a file by name*
on the server. An uploaded ``example.py`` does not exist there, so the "deterministic
SAST" step silently found nothing; the async pipeline never called it at all. This
module scans the submitted **text** in memory, so it works for every request and
for visitors who bring no LLM key.

Output is a plain dict (``scan_material``) plus a Markdown renderer
(``render_markdown``). Findings are line-based pattern rules with a CWE and a fix,
plus the AST taint flow for Python. Secrets are masked in every snippet.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MAX_LINE = 600          # longer lines are cut before matching (regex DoS guard)
MAX_FINDINGS = 200

SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    severity: str
    cwe: str
    pattern: re.Pattern
    fix: str
    langs: frozenset | None = None   # None = any language
    secret: bool = False             # mask the matched text in snippets


def _r(rid, title, sev, cwe, rx, fix, langs=None, flags=0, secret=False):
    return Rule(rid, title, sev, cwe, re.compile(rx, flags),
                fix, frozenset(langs) if langs else None, secret)


_PY = ("python",)
_JS = ("javascript", "typescript")
_JAVA = ("java",)
_C = ("c", "cpp")
_PHP = ("php",)
_GO = ("go",)

RULES: tuple[Rule, ...] = (
    # ---- injection -------------------------------------------------------
    _r("sqli-concat", "SQL query built by string concatenation", "critical", "CWE-89",
       r"""\b(select|insert\s+into|update|delete\s+from|drop)\b[^\n]{0,200}["']\s*(\+|%|\.format\()|"""
       r"""\.(execute|executemany|query|raw)\s*\(\s*["'][^"']*["']\s*(\+|%)""",
       "Use parameterized queries (cursor.execute(sql, params)) or an ORM with bound parameters.",
       flags=re.I),
    _r("sqli-fstring", "SQL query built with an f-string / template literal", "critical", "CWE-89",
       r"""(?i)\.(execute|executemany|query|raw)\s*\(\s*(f["']|`[^`]*\$\{)""",
       "Pass user data as bound parameters, never interpolate it into the SQL text."),
    _r("cmd-injection-py", "OS command executed from Python", "high", "CWE-78",
       r"""\b(os\.system|os\.popen|subprocess\.(call|run|Popen|check_output|check_call)|commands\.getoutput)\s*\(""",
       "Avoid the shell: pass an argument list to subprocess.run([...], shell=False) and validate input.",
       _PY),
    _r("shell-true", "subprocess with shell=True", "high", "CWE-78",
       r"""shell\s*=\s*True""",
       "Remove shell=True and pass the command as a list of arguments.", _PY),
    _r("cmd-injection-js", "Child process spawned from Node.js", "high", "CWE-78",
       r"""\b(child_process\.)?(exec|execSync|spawn|spawnSync)\s*\(\s*[`"'][^)]*(\$\{|["']\s*\+)""",
       "Use execFile/spawn with an argument array and no shell; validate input.", _JS),
    _r("cmd-injection-java", "Runtime.exec / ProcessBuilder with dynamic input", "high", "CWE-78",
       r"""Runtime\.getRuntime\(\)\.exec\s*\(|new\s+ProcessBuilder\s*\(""",
       "Pass fixed argument arrays, never a concatenated command string; allow-list inputs.", _JAVA),
    _r("cmd-injection-c", "system()/popen() call", "high", "CWE-78",
       r"""\b(system|popen|execl|execlp|execvp)\s*\(""",
       "Do not build shell commands from input; use execve with a fixed argv and validate input.", _C),
    _r("eval-py", "eval()/exec() of dynamic code", "critical", "CWE-95",
       r"""(?<![\w.])(eval|exec)\s*\(""",
       "Remove eval/exec; use ast.literal_eval for literals or a dispatch table.", _PY),
    _r("eval-js", "eval() / new Function() of dynamic code", "critical", "CWE-95",
       r"""(?<![\w.])eval\s*\(|new\s+Function\s*\(|setTimeout\s*\(\s*["'`]""",
       "Never evaluate strings as code; parse data with JSON.parse.", _JS),
    _r("ssti", "Server-side template built from a string", "high", "CWE-1336",
       r"""render_template_string\s*\(|Template\s*\([^)]*\)\s*\.render""",
       "Render fixed template files and pass data as context variables.", _PY),
    _r("path-traversal", "File path built from input without normalization", "medium", "CWE-22",
       r"""open\s*\([^)]*\+|open\s*\([^)]*\.\.[/\\]|os\.path\.join\s*\([^)]*(request|input|argv|params)""",
       "Resolve the path and verify it stays inside an allowed base directory.", _PY),
    _r("path-traversal-js", "File path built from request data", "high", "CWE-22",
       r"""\b(readFile|readFileSync|createReadStream|sendFile|writeFile|writeFileSync)\s*\([^)]*(req\.|\+)""",
       "Normalize with path.resolve and check the result starts with the allowed base directory.", _JS),
    _r("xss-innerhtml", "Raw HTML sink (innerHTML / document.write / dangerouslySetInnerHTML)", "high", "CWE-79",
       r"""\.innerHTML\s*=|\.outerHTML\s*=|document\.write\s*\(|dangerouslySetInnerHTML|insertAdjacentHTML\s*\(""",
       "Use textContent or a sanitizer (DOMPurify); never insert unescaped user data as HTML.", _JS),
    _r("xss-flask", "Response returned with unescaped HTML (Markup / |safe)", "medium", "CWE-79",
       r"""\bMarkup\s*\(|\|\s*safe\b|mark_safe\s*\(""",
       "Let the template engine auto-escape; only mark verified-safe content.", _PY),
    _r("ssrf", "Outbound request to a URL taken from input", "medium", "CWE-918",
       r"""\b(requests\.(get|post|put|delete|head)|urllib\.request\.urlopen|httpx\.(get|post)|fetch|axios\.(get|post))\s*\(\s*(request\.|req\.|input\s*\(|params\b)""",
       "Allow-list hosts/schemes and block private address ranges before fetching.", None),
    _r("xxe", "XML parser with external entities enabled", "high", "CWE-611",
       r"""resolve_entities\s*=\s*True|XMLParser\s*\([^)]*resolve_entities|setFeature\s*\([^)]*external-general-entities[^)]*true""",
       "Disable DTDs and external entities (defusedxml, or resolve_entities=False).", None),
    # ---- deserialization --------------------------------------------------
    _r("deser-pickle", "Unsafe deserialization (pickle / marshal / shelve)", "critical", "CWE-502",
       r"""\b(pickle|cPickle|dill|marshal|shelve)\.(loads?|Unpickler)\s*\(""",
       "Never unpickle untrusted data; use JSON or a schema-validated format.", _PY),
    _r("deser-yaml", "yaml.load without a safe loader", "high", "CWE-502",
       r"""yaml\.load\s*\((?![^)]*Loader\s*=\s*(yaml\.)?(Safe|CSafe)Loader)""",
       "Use yaml.safe_load.", _PY),
    _r("deser-java", "Java ObjectInputStream deserialization", "high", "CWE-502",
       r"""new\s+ObjectInputStream\s*\(|\.readObject\s*\(""",
       "Avoid native deserialization of untrusted data; use JSON with an allow-list of types.", _JAVA),
    _r("deser-php", "PHP unserialize() on input", "high", "CWE-502",
       r"""\bunserialize\s*\(""",
       "Use json_decode; never unserialize untrusted data.", _PHP),
    # ---- crypto / secrets -------------------------------------------------
    _r("weak-hash", "Weak hash (MD5 / SHA-1)", "medium", "CWE-327",
       r"""(?i)\b(hashlib\.(md5|sha1)|MessageDigest\.getInstance\(\s*["'](MD5|SHA-?1)["']|createHash\(\s*["'](md5|sha1)["']|\bMD5\s*\(|\bSHA1\s*\()""",
       "Use SHA-256+ for integrity and bcrypt/scrypt/argon2 for passwords."),
    _r("weak-cipher", "Weak cipher or mode (DES / RC4 / ECB)", "medium", "CWE-327",
       r"""(?i)\b(DES|RC4|Blowfish)\b\s*[.(]|MODE_ECB|["']AES/ECB|["']DES["']""",
       "Use AES-GCM or ChaCha20-Poly1305."),
    _r("insecure-random", "Non-cryptographic random (check it is not used for tokens / keys)", "low", "CWE-338",
       r"""\brandom\.(random|randint|choice|randrange)\s*\(|Math\.random\s*\(|\bnew\s+Random\s*\(|\brand\s*\(\s*\)""",
       "Use secrets (Python), crypto.randomBytes (Node) or SecureRandom (Java) for tokens and keys."),
    _r("tls-verify-off", "TLS certificate verification disabled", "high", "CWE-295",
       r"""verify\s*=\s*False|rejectUnauthorized\s*:\s*false|InsecureSkipVerify\s*:\s*true|CERT_NONE|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*["']?0""",
       "Keep certificate verification on; pin or install the proper CA instead."),
    _r("secret-aws", "AWS access key id in source", "critical", "CWE-798",
       r"""\bAKIA[0-9A-Z]{16}\b""",
       "Revoke the key, remove it from history, load credentials from the environment or a secret manager.",
       secret=True),
    _r("secret-token", "API token in source (GitHub / Slack / Stripe / Google)", "critical", "CWE-798",
       r"""\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bxox[baprs]-[A-Za-z0-9-]{10,}\b|\bsk_live_[A-Za-z0-9]{20,}\b|\bAIza[0-9A-Za-z_-]{35}\b|\bsk-ant-[A-Za-z0-9_-]{20,}""",
       "Revoke the token, purge it from history and read it from the environment.", secret=True),
    _r("secret-private-key", "Private key material in source", "critical", "CWE-321",
       r"""-----BEGIN (RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----""",
       "Remove and rotate the key; store keys in a secret manager.", secret=True),
    _r("secret-hardcoded", "Hard-coded password / secret", "high", "CWE-798",
       r"""(?i)\b(passwd|password|pwd|secret|api[_-]?key|access[_-]?key|auth[_-]?token|token)\b\s*[:=]\s*["'][^"'\s]{6,}["']""",
       "Read secrets from the environment or a secret manager; never commit them.", secret=True),
    # ---- configuration ----------------------------------------------------
    _r("debug-on", "Debug mode enabled", "medium", "CWE-489",
       r"""\bdebug\s*=\s*True\b|app\.run\s*\([^)]*debug\s*=\s*True|\bDEBUG\s*=\s*True\b""",
       "Disable debug in production (it exposes an interactive console / stack traces).", _PY),
    _r("bind-all", "Service bound to all interfaces", "low", "CWE-668",
       r"""host\s*=\s*["']0\.0\.0\.0["']|ListenAndServe\s*\(\s*["']:""",
       "Bind to localhost or put the service behind an authenticated reverse proxy."),
    _r("cors-any", "CORS allows any origin", "medium", "CWE-942",
       r"""(?i)allow_origins\s*=\s*\[\s*["']\*["']|Access-Control-Allow-Origin["']?\s*[:,]\s*["']\*|origin\s*:\s*["']\*["']|cors\(\s*\)""",
       "List the exact trusted origins; never combine * with credentials."),
    _r("jwt-none", "JWT signature verification disabled", "high", "CWE-347",
       r"""(?i)verify_signature["']?\s*:\s*False|algorithms\s*=\s*\[\s*["']none["']|jwt\.decode\([^)]*verify\s*=\s*False""",
       "Always verify the signature and pin the expected algorithm."),
    _r("tmp-insecure", "Predictable temporary file", "medium", "CWE-377",
       r"""\btempfile\.mktemp\s*\(|open\s*\(\s*["']/tmp/""",
       "Use tempfile.NamedTemporaryFile / mkstemp.", _PY),
    _r("assert-security", "assert used for a runtime check", "low", "CWE-617",
       r"""^\s*assert\s+(?!False\b)""",
       "assert is stripped with -O; raise an explicit exception instead.", _PY),
    _r("bare-except", "Bare except swallows errors", "low", "CWE-703",
       r"""^\s*except\s*:\s*(pass)?\s*$""",
       "Catch specific exceptions and log them.", _PY),
    _r("open-redirect", "Redirect to a user-supplied URL", "medium", "CWE-601",
       r"""\bredirect\s*\(\s*(request\.|req\.|url\b|next\b)|res\.redirect\s*\(\s*req\.""",
       "Validate the target against an allow-list of relative paths or hosts."),
    _r("sql-star", "SELECT * returns every column", "low", "CWE-200",
       r"""(?i)\bselect\s+\*\s+from\b""",
       "Select only the columns you need (avoid leaking password hashes and PII)."),
    # ---- memory safety (C / C++) -----------------------------------------
    _r("c-gets", "gets() - unbounded read", "critical", "CWE-242",
       r"""\bgets\s*\(""", "Use fgets with a size limit.", _C),
    _r("c-strcpy", "Unbounded string copy (strcpy / strcat / sprintf)", "high", "CWE-120",
       r"""\b(strcpy|strcat|sprintf|vsprintf|wcscpy)\s*\(""",
       "Use snprintf / strlcpy / strncat with explicit sizes.", _C),
    _r("c-scanf", "scanf %s without width", "high", "CWE-120",
       r"""\bscanf\s*\(\s*"[^"]*%s""", "Add a field width (%63s) or use fgets.", _C),
    _r("c-printf-fmt", "printf with a non-literal format string", "high", "CWE-134",
       r"""\b(printf|fprintf|syslog)\s*\(\s*(?!")[A-Za-z_]\w*\s*\)""",
       'Use printf("%s", value).', _C),
    # ---- infrastructure as code ------------------------------------------
    _r("tf-open-cidr", "Security group open to 0.0.0.0/0", "high", "CWE-284",
       r"""cidr_blocks\s*=\s*\[\s*"0\.0\.0\.0/0"|"0\.0\.0\.0/0\"""",
       "Restrict ingress to known CIDR ranges.", ("terraform",)),
    _r("tf-public-s3", "Public S3 bucket ACL", "high", "CWE-732",
       r"""acl\s*=\s*"public-read(-write)?\"""", "Use private ACL and block public access.", ("terraform",)),
    _r("tf-unencrypted", "Storage encryption disabled", "medium", "CWE-311",
       r"""(storage_encrypted|encrypted)\s*=\s*false""", "Enable encryption at rest.", ("terraform",)),
    _r("k8s-privileged", "Privileged container", "high", "CWE-250",
       r"""privileged:\s*true|allowPrivilegeEscalation:\s*true|hostNetwork:\s*true|runAsUser:\s*0\b""",
       "Drop privileges: runAsNonRoot, no privilege escalation, no hostNetwork.", ("yaml",)),
    _r("docker-root", "Container runs as root / uses :latest", "low", "CWE-250",
       r"""(?im)^\s*USER\s+root\b|^\s*FROM\s+\S+:latest\b""",
       "Run as an unprivileged USER and pin image versions.", ("dockerfile",)),
    # ---- logs -------------------------------------------------------------
    _r("log-sqli", "SQL injection pattern in log line", "high", "CWE-89",
       r"""(?i)(union\s+select|or\s+1\s*=\s*1|'\s*or\s*'1'\s*=\s*'1|;\s*drop\s+table)""",
       "Block the source, review the endpoint for injection, rotate credentials if data was read.", ("log",)),
    _r("log-traversal", "Path traversal attempt in log line", "medium", "CWE-22",
       r"""(\.\./){2,}|%2e%2e%2f|/etc/passwd""",
       "Reject the request pattern at the edge and review file-serving code.", ("log",)),
)

# CWE -> short human title for the dataflow section / unknowns
_CWE_TITLES = {"CWE-89": "SQL injection", "CWE-78": "OS command injection", "CWE-79": "Cross-site scripting",
               "CWE-22": "Path traversal", "CWE-502": "Unsafe deserialization", "CWE-95": "Code injection"}


def detect_language(filename: str, code: str = "") -> str:
    name = (filename or "").lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    base = name.rsplit("/", 1)[-1]
    if base == "dockerfile" or base.startswith("dockerfile."):
        return "dockerfile"
    by_ext = {
        "py": "python", "pyw": "python", "js": "javascript", "jsx": "javascript", "mjs": "javascript",
        "cjs": "javascript", "ts": "typescript", "tsx": "typescript", "java": "java", "c": "c", "h": "c",
        "cc": "cpp", "cpp": "cpp", "hpp": "cpp", "go": "go", "php": "php", "tf": "terraform",
        "tfvars": "terraform", "yaml": "yaml", "yml": "yaml", "log": "log", "sql": "sql", "sh": "shell",
    }
    if ext in by_ext:
        return by_ext[ext]
    head = code[:4000]
    if re.search(r"^\s*(def|import|from|class)\s+\w", head, re.M) and "{" not in head[:200]:
        return "python"
    if re.search(r"\bpublic\s+(class|interface)\b", head):
        return "java"
    if re.search(r"#include\s*<", head):
        return "c"
    if re.search(r"\b(const|let|var|function)\b.*[=({]", head) or "require(" in head:
        return "javascript"
    if re.search(r'^\s*resource\s+"', head, re.M):
        return "terraform"
    if re.search(r"^\s*apiVersion:\s*\S+", head, re.M):
        return "yaml"
    if re.match(r"\s*\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", head):
        return "log"
    return "unknown"


_NON_CODE = frozenset({"terraform", "yaml", "dockerfile", "log"})


def _applies(rule: Rule, lang: str) -> bool:
    if rule.langs is None or lang in rule.langs:
        return True
    # language not detected: still try the generic *code* rules, never IaC / log rules
    return lang == "unknown" and not (rule.langs & _NON_CODE)


def _comment_line(line: str, lang: str) -> bool:
    s = line.lstrip()
    if lang in ("python", "yaml", "terraform", "dockerfile", "shell"):
        return s.startswith("#")
    if lang in ("javascript", "typescript", "java", "c", "cpp", "go", "php"):
        return s.startswith(("//", "*", "/*"))
    return False


def _mask(text: str) -> str:
    t = text.strip()
    return (t[:4] + "…" + "*" * 6) if len(t) > 8 else "*" * len(t)


def _snippet(line: str, rule: Rule, m: re.Match) -> str:
    s = line.strip()
    if rule.secret:
        if rule.id == "secret-hardcoded":   # keep the variable name, hide only the value
            s = re.sub(r"([\"'])([^\"']{6,})\1", lambda q: q.group(1) + _mask(q.group(2)) + q.group(1), s)
        else:
            s = s.replace(m.group(0), _mask(m.group(0)))
    return s[:160]


def scan_material(material: str, filename: str = "") -> dict:
    """Scan submitted text. Never raises; always returns a result dict."""
    material = material or ""
    lang = detect_language(filename, material)
    findings: list[dict] = []
    seen: set[tuple[str, int]] = set()
    base = (filename or "").lower().rsplit("/", 1)[-1]
    skip = {"assert-security"} if (base.startswith("test_") or "_test." in base or base.startswith("test.")) else set()
    try:
        lines = material.splitlines()
        # whole-file scan for the line-agnostic rules happens per line (cheap, bounded)
        for i, raw in enumerate(lines, start=1):
            if len(findings) >= MAX_FINDINGS:
                break
            line = raw[:MAX_LINE]
            if not line.strip() or _comment_line(line, lang):
                continue
            for rule in RULES:
                if not _applies(rule, lang) or rule.id in skip:
                    continue
                m = rule.pattern.search(line)
                if not m or (rule.id, i) in seen:
                    continue
                seen.add((rule.id, i))
                findings.append({
                    "id": rule.id, "title": rule.title, "severity": rule.severity, "cwe": rule.cwe,
                    "line": i, "snippet": _snippet(line, rule, m), "fix": rule.fix,
                })
    except Exception as e:  # pragma: no cover - defensive: a scan bug must not kill a job
        return _result(lang, [], {}, error=f"{type(e).__name__}: {e}")

    flow: dict = {}
    if lang == "python":
        try:
            from src.tools.dataflow import analyze_dataflow
            flow = analyze_dataflow(material, language="python") or {}
        except Exception:
            flow = {}
        if flow and flow.get("sink"):
            sink_line = flow["sink"].get("line")
            hit = next((f for f in findings if f["line"] == sink_line), None)
            if hit:
                hit["tainted"] = True
                if hit["severity"] in ("medium", "low"):
                    hit["severity"] = "high"
            else:
                findings.append({
                    "id": "taint-flow", "title": "Untrusted input reaches a dangerous call",
                    "severity": "high", "cwe": "CWE-20", "line": int(sink_line or 1),
                    "snippet": str(flow["sink"].get("content", ""))[:160],
                    "fix": "Validate/escape the value or use a safe API at this sink.", "tainted": True,
                })
    findings.sort(key=lambda f: (SEV_ORDER.get(f["severity"], 9), f["line"]))
    return _result(lang, findings, flow)


def _result(lang: str, findings: list, flow: dict, error: str = "") -> dict:
    by_sev = {s: 0 for s in SEV_ORDER}
    for f in findings:
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1
    cwes: list[str] = []
    for f in findings:
        if f["cwe"] not in cwes:
            cwes.append(f["cwe"])
    owasp: list[str] = []
    try:
        from src.tools.patterns import cwe_to_owasp
        for c in cwes:
            o = cwe_to_owasp(c)
            if o and o not in owasp:
                owasp.append(o)
    except Exception:
        pass
    rules_view = [{"test_id": f["id"], "msg": f"{f['title']} ({f['cwe']})", "severity": f["severity"],
                   "line": f["line"], "confidence": "medium"} for f in findings]
    return {
        "engine": "vishap-static", "language": lang, "findings": findings,
        "total_findings": len(findings), "count": len(findings),
        "high_priority": by_sev["critical"] + by_sev["high"], "by_severity": by_sev,
        "cwe_ids": cwes, "owasp_categories": owasp, "dataflow": flow, "error": error,
        # shape consumed by tools.sarif.to_sarif
        "vishap_rules": {"available": True, "findings": rules_view,
                         "summary": {"total": len(findings), **by_sev}},
        "bandit": {}, "semgrep": {},
    }


_ICON = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}


def verdict_of(result: dict) -> str:
    sev = result.get("by_severity", {})
    if sev.get("critical"):
        return "CRITICAL"
    if sev.get("high"):
        return "HIGH RISK"
    if sev.get("medium"):
        return "REVIEW"
    return "NO ISSUES FOUND" if not result.get("total_findings") else "LOW RISK"


def render_markdown(result: dict, filename: str = "", *, heading: str = "Static analysis (built-in rules)",
                    note: str = "") -> str:
    """Human-readable report section."""
    out = [f"## {heading}", ""]
    if note:
        out += [f"> {note}", ""]
    n = result.get("total_findings", 0)
    sev = result.get("by_severity", {})
    out.append(f"**File:** `{filename or 'input'}` · **Language:** {result.get('language', 'unknown')} · "
               f"**Verdict:** {verdict_of(result)}")
    out.append("")
    out.append(f"**Findings:** {n} — " + ", ".join(f"{sev.get(s, 0)} {s}" for s in SEV_ORDER))
    if result.get("cwe_ids"):
        out.append("")
        out.append("**CWE:** " + ", ".join(result["cwe_ids"]))
    if result.get("owasp_categories"):
        out.append("")
        out.append("**OWASP:** " + "; ".join(result["owasp_categories"]))
    out.append("")
    if not n:
        out += ["No known risky patterns were found by the built-in rules. This is not a proof of safety:",
                "the rules are pattern-based and cover common issues only.", ""]
        return "\n".join(out)

    out += ["### Findings", ""]
    for f in result["findings"]:
        tag = " · tainted input reaches this call" if f.get("tainted") else ""
        out.append(f"#### {_ICON.get(f['severity'], '•')} {f['title']} — line {f['line']}")
        out.append(f"- **Severity:** {f['severity']} · **{f['cwe']}**{tag}")
        if f.get("snippet"):
            code = f["snippet"].replace("`", "'")
            out.append("- **Code:** `" + code + "`")
        out.append(f"- **Fix:** {f['fix']}")
        out.append("")
    flow = result.get("dataflow") or {}
    if flow.get("source") and flow.get("sink"):
        out += ["### Taint flow (Python AST)", "",
                f"`{flow['source'].get('name', 'source')}` (line {flow['source'].get('line')}) → "
                f"`{flow['sink'].get('name', 'sink')}` (line {flow['sink'].get('line')})", ""]
    return "\n".join(out)
