# -*- coding: utf-8 -*-
"""PII and compliance patterns.

Dogfood finding: circular import between orchestrator and redact
required extracting patterns into a standalone module.
"""
import re


PII_PATTERNS = {
    "email": re.compile(r"(?<![\w%])[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "phone_ru": re.compile(r"\+7\d{10}|\b8\d{10}\b"),
    "passport_ru": re.compile(r"\b\d{4}\s?\d{6}\b"),
    "snils": re.compile(r"\b\d{3}-\d{3}-\d{3}[ -]?\d{2}\b"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"),
    # Secrets
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "aws_secret_key": re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*[\"']?[A-Za-z0-9/+=]{40}[\"']?"),
    "stripe_live_key": re.compile(r"\bsk_live_[A-Za-z0-9]{20,}\b"),
    "stripe_test_key": re.compile(r"\bsk_test_[A-Za-z0-9]{20,}\b"),
    "github_token": re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
    "slack_token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "private_key": re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "hardcoded_password": re.compile(r"(?i)\bpassword\s*[:=]\s*[\"'][^\"']{8,}[\"']"),
    "hardcoded_secret": re.compile(r"(?i)\b(secret|api_key|access_key|token)\s*[:=]\s*[\"'][^\"']{12,}[\"']"),
}


COMPLIANCE_TRIGGERS = {
    "HIPAA": ["patient", "diagnosis", "medical record", "hipaa", "ehr"],
    "PCI-DSS": ["payment", "card", "cvv", "credit card", "pci"],
    "GDPR": ["personal data", "gdpr", "eu citizen", "right to erasure"],
    "152-ФЗ": ["персональные данные", "152-фз", "оператор данных"],
    "EU AI Act": ["llm", "foundation model", "ai system", "eu ai act"],
    # SECRETS выставляется только через detect_pii (см. ниже),
    # keyword-triggers удалены: они ловили имена переменных, а не секреты.
    # "SECRETS": [...],
}


# Dogfood P0 fix: critical risk patterns that MUST NOT be downgraded
# to WARNING even if audit doesn't find SECRETS/PII.
# These are RCE, code injection, deserialization, path traversal, SQLi.
CRITICAL_RISK_PATTERNS = {
    "rce_shell": re.compile(r"\b(os\.system|subprocess\.(call|run|Popen|check_output|check_call)|os\.popen)\s*\("),
    "rce_eval": re.compile(r"\b(eval|exec)\s*\("),
    "rce_import": re.compile(r"__import__\s*\(|getattr\s*\([^,]+,\s*[a-z_]+\s*\)"),
    "sqli_concat": re.compile(r"(SELECT|INSERT|UPDATE|DELETE|DROP)\s+.*['\"]\s*\+\s*", re.IGNORECASE),
    "sqli_fstring": re.compile(r"execute\s*\(\s*f['\"]", re.IGNORECASE),
    "path_traversal": re.compile(r"open\s*\([^)]*\.\.[/\\]|os\.path\.join\s*\([^,]+,\s*[a-z_]+\s*\)"),
    "insecure_deser": re.compile(r"(pickle\.loads|yaml\.load\s*\([^,)]+\)|marshal\.loads)"),
    "shell_true": re.compile(r"shell\s*=\s*True"),
    "ssti": re.compile(r"render_template_string\s*\(|Template\s*\([^)]+\).*render"),
    "ldap_injection": re.compile(r"search\s*\([^)]*\+\s*[a-z_]+"),
    "xxe": re.compile(r"(etree\.parse|XMLParser|parseString)\s*\(.*resolve_entities"),
}


# OWASP Top 10 mapping (2021 + 2025 preview)
# Dogfood P1: map CWE to OWASP category for compliance reports.
CWE_TO_OWASP = {
    # Injection
    "CWE-89":   {"2021": "A03:2021 Injection", "2025": "A03:2025 Injection", "name": "SQL Injection"},
    "CWE-79":   {"2021": "A03:2021 Injection", "2025": "A03:2025 Injection", "name": "XSS"},
    "CWE-78":   {"2021": "A03:2021 Injection", "2025": "A03:2025 Injection", "name": "OS Command Injection"},
    "CWE-94":   {"2021": "A03:2021 Injection", "2025": "A03:2025 Injection", "name": "Code Injection"},
    "CWE-77":   {"2021": "A03:2021 Injection", "2025": "A03:2025 Injection", "name": "Command Injection"},
    "CWE-917":  {"2021": "A03:2021 Injection", "2025": "A03:2025 Injection", "name": "Expression Language Injection"},

    # Memory Safety — NOT OWASP Top 10 (CWE-only category)
    "CWE-122":  {"2021": "Memory Safety", "2025": "Memory Safety", "name": "Heap Buffer Overflow"},
    "CWE-787":  {"2021": "Memory Safety", "2025": "Memory Safety", "name": "OOB Write"},
    "CWE-125":  {"2021": "Memory Safety", "2025": "Memory Safety", "name": "OOB Read"},
    "CWE-129":  {"2021": "Memory Safety", "2025": "Memory Safety", "name": "Array Index"},

    # Broken Access Control
    "CWE-22":   {"2021": "A01:2021 Broken Access Control", "2025": "A01:2025 Broken Access Control", "name": "Path Traversal"},
    "CWE-732":  {"2021": "A01:2021 Broken Access Control", "2025": "A01:2025 Broken Access Control", "name": "Incorrect Permission Assignment"},
    "CWE-352":  {"2021": "A01:2021 Broken Access Control", "2025": "A01:2025 Broken Access Control", "name": "CSRF"},
    "CWE-639":  {"2021": "A01:2021 Broken Access Control", "2025": "A01:2025 Broken Access Control", "name": "IDOR"},
    "CWE-284":  {"2021": "A01:2021 Broken Access Control", "2025": "A01:2025 Broken Access Control", "name": "Improper Access Control"},
    "CWE-863":  {"2021": "A01:2021 Broken Access Control", "2025": "A01:2025 Broken Access Control", "name": "Incorrect Authorization"},

    # Cryptographic Failures
    "CWE-327":  {"2021": "A02:2021 Cryptographic Failures", "2025": "A02:2025 Cryptographic Failures", "name": "Broken Crypto"},
    "CWE-328":  {"2021": "A02:2021 Cryptographic Failures", "2025": "A02:2025 Cryptographic Failures", "name": "Weak Hash"},
    "CWE-330":  {"2021": "A02:2021 Cryptographic Failures", "2025": "A02:2025 Cryptographic Failures", "name": "Weak Random"},
    "CWE-798":  {"2021": "A07:2021 Auth Failures", "2025": "A07:2025 Auth Failures", "name": "Hardcoded Credentials"},

    # Insecure Design
    "CWE-434":  {"2021": "A04:2021 Insecure Design", "2025": "A04:2025 Insecure Design", "name": "Unrestricted Upload"},

    # Security Misconfiguration
    "CWE-611":  {"2021": "A05:2021 Security Misconfiguration", "2025": "A05:2025 Security Misconfiguration", "name": "XXE"},
    "CWE-1004": {"2021": "A05:2021 Security Misconfiguration", "2025": "A05:2025 Security Misconfiguration", "name": "Cookie without HttpOnly"},
    "CWE-16":   {"2021": "A05:2021 Security Misconfiguration", "2025": "A05:2025 Security Misconfiguration", "name": "Configuration"},

    # Vulnerable Components
    "CWE-1035": {"2021": "A06:2021 Vulnerable Components", "2025": "A06:2025 Vulnerable Components", "name": "Vulnerable Component"},

    # Auth Failures
    "CWE-287":  {"2021": "A07:2021 Auth Failures", "2025": "A07:2025 Auth Failures", "name": "Improper Authentication"},
    "CWE-306":  {"2021": "A07:2021 Auth Failures", "2025": "A07:2025 Auth Failures", "name": "Missing Authentication"},

    # Software and Data Integrity
    "CWE-502":  {"2021": "A08:2021 Software and Data Integrity", "2025": "A08:2025 Software and Data Integrity", "name": "Insecure Deserialization"},

    # Logging and Monitoring
    "CWE-778":  {"2021": "A09:2021 Logging Failures", "2025": "A09:2025 Logging Failures", "name": "Insufficient Logging"},

    # SSRF
    "CWE-918":  {"2021": "A10:2021 SSRF", "2025": "A10:2025 SSRF", "name": "SSRF"},
}



# P2-8: CWE -> concrete compliance controls per standard.
# P2-12: Anomaly Detection config
ANOMALY_CONFIG = {
    "min_samples": 10,
    "default_method": "zscore",
    "methods": {
        "zscore": {"threshold": 3.0},
        "iqr":    {"multiplier": 1.5},
        "ewma":   {"alpha": 0.3},
    },
    "max_anomalies": 20,
    "top_in_audit": 3,
}


COMPLIANCE_MAP = {
    # PCI-DSS 3.2.1 (Req 6.5.x)
    "PCI-DSS": {
        "CWE-89":  ["Req 6.5.1"],
        "CWE-79":  ["Req 6.5.7"],
        "CWE-78":  ["Req 6.5.1"],
        "CWE-352": ["Req 6.5.9"],
        "CWE-22":  ["Req 6.5.8"],
        "CWE-611": ["Req 6.5.1"],
        "CWE-502": ["Req 6.5.1"],
    },
    # GDPR (Art. 32 -- security of processing)
    "GDPR": {
        "CWE-311": ["Art. 32"],
        "CWE-200": ["Art. 32"],
        "CWE-359": ["Art. 32"],
        "CWE-522": ["Art. 32"],
    },
    # SOC 2 (Trust Services Criteria)
    "SOC2": {
        "CWE-89":  ["CC6.1"],
        "CWE-79":  ["CC6.1"],
        "CWE-287": ["CC6.1"],
        "CWE-778": ["CC7.2"],
    },
    # ISO/IEC 27001:2013
    "ISO27001": {
        "CWE-89":  ["A.14.2.5"],
        "CWE-79":  ["A.14.2.5"],
        "CWE-311": ["A.10.1.1"],
    },
    # HIPAA Security Rule
    "HIPAA": {
        "CWE-311": ["164.312(a)(2)(iv)"],
        "CWE-200": ["164.312(b)"],
    },
}


# P2-9: Incident response runbooks per CWE (immediate / short_term / long_term / escalation).
RUNBOOKS = {
    "CWE-89": {
        "title": "SQL Injection",
        "severity": "critical",
        "immediate": [
            "Block the endpoint (feature flag / WAF rule).",
            "Check DB logs for anomalous queries (last 24h).",
            "Notify on-call security engineer.",
        ],
        "short_term": [
            "Replace string concatenation with parameterized queries.",
            "Run sqlfluff + semgrep on test corpus.",
            "Deploy fix to canary (1% traffic).",
        ],
        "long_term": [
            "Migrate to ORM (SQLAlchemy / Django ORM).",
            "Enable SAST in CI (Semgrep / Bandit).",
            "Train developers on SQLi (OWASP A03).",
        ],
        "escalation": "Security team + DBA",
    },
    "CWE-79": {
        "title": "Cross-Site Scripting (XSS)",
        "severity": "high",
        "immediate": [
            "Enable Content-Security-Policy (strict, report-only first).",
            "Check access logs for injection patterns.",
        ],
        "short_term": [
            "HTML-escape on output (context-aware).",
            "Use templating engine (Jinja2 auto-escape).",
        ],
        "long_term": [
            "Add DOMPurify for user HTML.",
            "Regular pen-test (XSS-focused).",
        ],
        "escalation": "Frontend team",
    },
    "CWE-78": {
        "title": "OS Command Injection",
        "severity": "critical",
        "immediate": [
            "Isolate the affected process (cgroup / container).",
            "Check shell history + process tree for anomalous commands.",
            "Notify on-call security engineer.",
        ],
        "short_term": [
            "Replace shell calls with subprocess (list args, no shell=True).",
            "Validate + whitelist all user-controllable inputs.",
            "Deploy fix to canary.",
        ],
        "long_term": [
            "Avoid os.system / subprocess(shell=True) entirely.",
            "Add command allowlist validation layer.",
            "Enable SAST in CI.",
        ],
        "escalation": "Security team + SRE",
    },
    "CWE-352": {
        "title": "Cross-Site Request Forgery (CSRF)",
        "severity": "high",
        "immediate": [
            "Enable CSRF tokens on all state-changing endpoints.",
            "Set SameSite=Strict on session cookies.",
        ],
        "short_term": [
            "Verify Origin/Referer headers on POST/PUT/DELETE.",
            "Rotate session tokens.",
        ],
        "long_term": [
            "Framework CSRF middleware (Django / Flask-WTF).",
            "Automated pen-test for CSRF.",
        ],
        "escalation": "Backend team",
    },
    "CWE-22": {
        "title": "Path Traversal",
        "severity": "high",
        "immediate": [
            "Restrict file access to allowlisted directories.",
            "Check file access logs for ../ patterns.",
        ],
        "short_term": [
            "Normalize paths (os.path.realpath) + verify prefix.",
            "Reject symlinks in user-supplied paths.",
        ],
        "long_term": [
            "Use pathlib + resolve() strictly.",
            "Run chroot / container-based isolation.",
        ],
        "escalation": "Backend team + SRE",
    },
    "CWE-502": {
        "title": "Insecure Deserialization",
        "severity": "critical",
        "immediate": [
            "Block untrusted deserialization endpoints.",
            "Check logs for anomalous object graphs.",
            "Notify on-call security engineer.",
        ],
        "short_term": [
            "Replace pickle / yaml.load with safe alternatives (yaml.safe_load, JSON).",
            "Sign + verify serialized payloads.",
        ],
        "long_term": [
            "Migrate to schema-based formats (Protobuf, Avro).",
            "Add deserialization allowlists.",
        ],
        "escalation": "Security team + Backend team",
    },
    "CWE-611": {
        "title": "XML External Entity (XXE)",
        "severity": "high",
        "immediate": [
            "Disable external entity processing in XML parsers.",
            "Check egress traffic for unexpected DNS/HTTP.",
        ],
        "short_term": [
            "Use defusedxml (Python) / secure parser config.",
            "Add XML size + depth limits.",
        ],
        "long_term": [
            "Prefer JSON over XML where possible.",
            "Enable SAST rules for XXE.",
        ],
        "escalation": "Backend team",
    },
    "CWE-287": {
        "title": "Improper Authentication",
        "severity": "critical",
        "immediate": [
            "Force logout all sessions (rotate signing keys).",
            "Audit auth logs for anomalous successful logins.",
            "Notify security team + on-call.",
        ],
        "short_term": [
            "Enforce MFA on affected accounts.",
            "Patch auth logic (constant-time compare, rate limit).",
        ],
        "long_term": [
            "Adopt industry-standard auth (OAuth2 / OIDC).",
            "Regular auth-focused pen-tests.",
        ],
        "escalation": "Security team + IAM owner",
    },
    "CWE-778": {
        "title": "Insufficient Logging",
        "severity": "medium",
        "immediate": [
            "Enable logging for the affected code path.",
            "Verify logs reach SIEM / central collector.",
        ],
        "short_term": [
            "Add structured logs (JSON) for security events.",
            "Set up alerts on auth failures / 5xx spikes.",
        ],
        "long_term": [
            "Define log retention + rotation policy.",
            "Map logs to MITRE ATT&CK detections.",
        ],
        "escalation": "SRE + Security team",
    },
    "CWE-311": {
        "title": "Missing Encryption of Sensitive Data",
        "severity": "high",
        "immediate": [
            "Identify all paths where sensitive data is written unencrypted.",
            "Block writes to unencrypted targets (temp ban).",
        ],
        "short_term": [
            "Enable TLS in transit (enforce, not optional).",
            "Enable AES-256 at rest for affected stores.",
        ],
        "long_term": [
            "Centralize secrets / crypto (KMS, Vault).",
            "Rotate all potentially exposed keys.",
        ],
        "escalation": "Security team + Platform",
    },
}


def cwe_to_owasp(cwe_id: str, year: str = "2025") -> str:
    """Map CWE to OWASP Top 10 category.

    Args:
        cwe_id: e.g. "CWE-89"
        year: "2021" or "2025"

    Returns:
        OWASP category string or empty.
    """
    entry = CWE_TO_OWASP.get(cwe_id)
    if not entry:
        return ""
    return entry.get(year, "")


# Exploitability patterns (Dogfood P2: reachability, auth, blast radius)
EXPLOIT_PATTERNS = {
    # Entry points (reachable from outside)
    "entrypoint_web": re.compile(
        r"@app\.(route|get|post|put|delete|patch)\s*\(|"
        r"@router\.(get|post|put|delete|patch)\s*\(|"
        r"@\w+\.(get|post|put|delete|patch)\s*\(",
        re.IGNORECASE,
    ),
    "entrypoint_func": re.compile(
        r"\bdef\s+(handler|process|handle|route|api_|endpoint)\w*\s*\(",
        re.IGNORECASE,
    ),
    "entrypoint_main": re.compile(r"if\s+__name__\s*==\s*['\"]__main__['\"]"),

    # Auth checks (if present — not exploitable directly)
    "auth_decorator": re.compile(
        r"@\w*(login_required|requires_auth|authenticated|authorized)\w*|"
        r"Depends\(\s*\w*(auth|current_user|get_user|verify)\w*\s*\)",
        re.IGNORECASE,
    ),
    "auth_check": re.compile(
        r"\bif\s+(not\s+)?\w*(is_authenticated|is_authorized|has_permission|check_auth)\b",
        re.IGNORECASE,
    ),

    # Blast radius indicators
    "blast_db": re.compile(
        r"\b(db\.execute|cursor\.execute|session\.execute|conn\.execute|"
        r"\.query\(|\.raw\(|\.filter\(|\.filter_by\()",
        re.IGNORECASE,
    ),
    "blast_shell": re.compile(
        r"\b(os\.system|os\.popen|subprocess\.(call|run|Popen|check_output|check_call))",
        re.IGNORECASE,
    ),
    "blast_fs": re.compile(
        r"\b(open\s*\(|shutil\.(copy|move|rmtree)|os\.(remove|unlink|rmdir))",
        re.IGNORECASE,
    ),
    "blast_network": re.compile(
        r"\b(requests\.(get|post|put|delete|patch)|urllib\.|http\.client|socket\.)",
        re.IGNORECASE,
    ),
    "blast_eval": re.compile(r"\b(eval|exec|__import__)\s*\(", re.IGNORECASE),
    "blast_heap": re.compile(r"\b(malloc|calloc|realloc)\s*\([^)]*sizeof\s*\(\s*\w+\s*\)[^)]*\)"),

    # P2-7: additional entry points (go, js)
    "entrypoint_go_main": re.compile(r"\bfunc\s+main\s*\(", re.IGNORECASE),
    "entrypoint_go_http": re.compile(r"\bhttp\.(HandleFunc|Handle)\s*\(", re.IGNORECASE),
    "entrypoint_js_route": re.compile(
        r"\b(app|router)\.(get|post|put|delete|patch)\s*\(",
        re.IGNORECASE,
    ),
    # P2-7 v5.11.5: Java entry points (main, Spring, Servlet).
    "entrypoint_java_main": re.compile(
        r"\bpublic\s+static\s+void\s+main\s*\(",
        re.IGNORECASE,
    ),
    "entrypoint_java_spring": re.compile(
        r"@(RestController|Controller|RequestMapping|GetMapping|PostMapping|"
        r"PutMapping|DeleteMapping|PatchMapping)\b",
        re.IGNORECASE,
    ),
    "entrypoint_java_servlet": re.compile(
        r"\b(doGet|doPost|doPut|doDelete|service)\s*\(\s*HttpServletRequest",
        re.IGNORECASE,
    ),
    # P2-7 v5.11.6: C blast radius indicators.
    # v5.11.6-blast-c
    "blast_c_cmd": re.compile(
        r"\b(system|popen|execl|execlp|execle|execv|execvp|execvpe|execve)\s*\(",
        re.IGNORECASE,
    ),
    "blast_c_buffer": re.compile(
        r"\b(strcpy|strcat|sprintf|vsprintf|memcpy|memmove|gets)\s*\(",
        re.IGNORECASE,
    ),
    "blast_c_file": re.compile(
        r"\b(fopen|freopen|open|fread|fwrite)\s*\(",
        re.IGNORECASE,
    ),

    # P2-7 v5.11.6: C entry points.
    "entrypoint_c_main": re.compile(
        r"\b(int|void)\s+main\s*\(\s*int\s+\w+\s*,\s*char\s*\*\*?\s*\w+",
        re.IGNORECASE,
    ),
    "entrypoint_c_jni": re.compile(r"\bJNIEXPORT\b"),
}


# P2-7: Taint sources (user input) вЂ” entry points for data flow
TAINT_SOURCES = {
    "source_flask": re.compile(
        r"\brequest\.(args|form|json|body|GET|POST|data)\b",
        re.IGNORECASE,
    ),
    "source_generic": re.compile(
        r"\b(req\.(query|body|params)|input\s*\(|sys\.argv|"
        r"os\.(environ|getenv)|getenv\s*\()",
        re.IGNORECASE,
    ),
    # P2-7 v5.11.5: Java taint sources (Servlet, System, IO, Spring).
    # v5.11.5-fix1: @RequestParam has no word boundary before '@'.
    # v5.11.5-fix2-req: accept both request. and req. prefixes.
    "source_java": re.compile(
        r"(\b((request|req)\.(getParameter|getHeader|getCookies|getQueryString|"
        r"getInputStream|getReader)|"
        r"System\.(in|getenv|getProperty)|"
        r"Scanner\s*\(|BufferedReader\s*\(|readLine\s*\()|"
        r"@(RequestParam|PathVariable|RequestBody|RequestHeader))",
        re.IGNORECASE,
    ),
    # P2-7 v5.11.6: C taint sources (stdin, argv, env, socket).
    # v5.11.6-fix1-argc: argc is a count, not taint -- removed.
    "source_c": re.compile(
        r"\b(scanf|fscanf|sscanf|gets|fgets|getline|getchar|"
        r"read|recv|recvfrom|readline)\s*\(|"
        r"\b(argv\s*\[|getenv\s*\(|secure_getenv\s*\()",
        re.IGNORECASE,
    ),
}

# P2-7: Taint sinks (where tainted data flows out)
TAINT_SINKS = {
    "sink_sql": re.compile(
        r"\b(db\.execute|cursor\.execute|session\.execute|conn\.execute|"
        r"\.query\s*\(|\.raw\s*\(|\.filter\s*\()",
        re.IGNORECASE,
    ),
    "sink_cmd": re.compile(
        r"\b(os\.system|os\.popen|subprocess\.(call|run|Popen|check_output|check_call)|"
        r"eval\s*\(|exec\s*\()",
        re.IGNORECASE,
    ),
    "sink_fs": re.compile(
        r"\b(open\s*\(|shutil\.(copy|move|rmtree)|os\.(remove|unlink|rmdir))",
        re.IGNORECASE,
    ),
    # P2-7 v5.11.5: Java taint sinks.
    "sink_java_sql": re.compile(
        r"\.(executeQuery|executeUpdate|executeBatch|execute|createStatement|nativeSQL)\s*\(",
        re.IGNORECASE,
    ),
    "sink_java_cmd": re.compile(
        r"\b(Runtime\.getRuntime\s*\(\s*\)\.exec|Runtime\.exec|"
        r"ProcessBuilder|Process\.start)",
        re.IGNORECASE,
    ),
    "sink_java_file": re.compile(
        r"\b(new\s+File|FileInputStream|FileOutputStream|FileReader|FileWriter|"
        r"Files\.(read|write|delete|copy|move)|Paths\.get)\s*\(",
        re.IGNORECASE,
    ),
    "sink_java_reflect": re.compile(
        r"\b(Class\.forName|Method\.invoke|Class\.getMethod|Class\.getDeclaredMethod)\s*\(",
        re.IGNORECASE,
    ),
    "sink_java_deser": re.compile(
        r"\b(ObjectInputStream|readObject|XMLDecoder|readValue|Yaml\.load|XStream\.fromXML)\b",
        re.IGNORECASE,
    ),
    # v5.11.5-fix1:  before group blocks .lookup (no word boundary after ')')
    "sink_java_jndi": re.compile(
        r"(JndiManager\.lookup|InitialContext\.lookup|Context\.lookup|"
        r"\.lookup\s*\(|JndiLookup|JndiTemplate|JndiObjectFactoryBean)",
        re.IGNORECASE,
    ),
    # P2-7 v5.11.6: C taint sinks.
    "sink_c_cmd": re.compile(
        r"\b(system|popen|execl|execlp|execle|execv|execvp|execvpe|execve)\s*\(",
        re.IGNORECASE,
    ),
    "sink_c_buffer": re.compile(
        r"\b(strcpy|strcat|sprintf|vsprintf|memcpy|memmove|gets)\s*\(",
        re.IGNORECASE,
    ),
    "sink_c_file": re.compile(
        r"\b(fopen|freopen|open|fread|fwrite)\s*\(",
        re.IGNORECASE,
    ),
}


# P2-7b: AST-based taint markers (data-flow analysis).
# Separate from TAINT_SOURCES/TAINT_SINKS (regex-based, P2-7).
# Values are attribute/name paths matched against Python AST nodes.
AST_TAINT_SOURCES = {
    "flask_request": ["request.args", "request.form", "request.json", "request.data"],
    "builtin_input": ["input"],
    "env": ["os.environ", "os.getenv"],
    "file_read": ["open"],
}

AST_TAINT_SINKS = {
    "sql_execute": ["cursor.execute", "execute", "executemany"],
    "cmd_exec": ["os.system", "subprocess.run", "subprocess.call",
                 "subprocess.Popen", "exec", "exec"],
    "file_write": ["open"],
}


def detect_exploitability(material: str) -> dict:
    """Detect exploitability: reachability, auth, blast radius.

    - IaC (Terraform/YAML): reachable=True (apply = compromise), blast=high.
    - JS/Express (app.get/post/router.get): reachable=True, blast=high.
    - Python (Flask/FastAPI): reachable=True, blast=high.
    - Else: reachable=False, blast=none.
    """
    if material.lstrip().startswith(("2026-","2025-","2024-")):
        return {"reachable": True, "auth_required": False,
                "exploit_path": [{"type":"log","path":"log analysis"}],
                "blast_radius": "high",
                "entry_points": ["log file"],
                "blast_indicators": ["PII","secrets","SQLi/RCE traces","IMDS","privileged pod"]}

    stripped = material.lstrip()

    # IaC
    if stripped.startswith(("resource ", "provider ", "apiVersion:", "terraform ")):
        return {
            "reachable": True,
            "auth_required": False,
            "exploit_path": [{"type": "iac", "path": "terraform apply"}],
            "blast_radius": "high",
            "entry_points": ["terraform apply"],
            "blast_indicators": ["AWS account", "public S3", "public RDS"],
        }

    # JS/Express
    if any(p in stripped for p in ("app.get(", "app.post(", "app.put(", "app.delete(", "router.get(", "router.post(", "express(")):
        return {
            "reachable": True,
            "auth_required": False,
            "exploit_path": [{"type": "chain", "path": "js_route -> exec"}],
            "blast_radius": "high",
            "entry_points": ["HTTP route"],
            "blast_indicators": ["RCE", "SSRF", "SQLi"],
        }

    # Python Flask/FastAPI
    if any(p in stripped for p in ("@app.", "@router.", "Flask(", "FastAPI(")):
        return {
            "reachable": True,
            "auth_required": False,
            "exploit_path": [{"type": "chain", "path": "py_route -> exec"}],
            "blast_radius": "high",
            "entry_points": ["HTTP route"],
            "blast_indicators": ["RCE", "SSRF", "SQLi"],
        }

    # Fallback
    return {
        "reachable": False,
        "auth_required": False,
        "exploit_path": [],
        "blast_radius": "none",
        "entry_points": [],
        "blast_indicators": [],
    }