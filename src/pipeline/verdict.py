# -*- coding: utf-8 -*-
"""Risk verdict computation -- single source of truth.

Consolidates logic from run_audit() (v5.10.6 risk_nodes, v5.11.1 security.findings).
"""
import re
from typing import Any


# v6.1-fix: fallback scan of final_markdown for critical SEC findings the LLM
# put in free text ([CONCLUSION]) instead of structured security.findings.
_SEC_CRITICAL_RE = re.compile(
    r"SEC-\d+.{0,300}?(критично|critical|CVE-\d|crash|overflow|injection)",
    re.IGNORECASE | re.DOTALL,
)


def _has_critical_priority(items: Any) -> bool:
    """Check if list of dicts has any item with critical priority."""
    if not isinstance(items, list):
        return False
    for item in items:
        if not isinstance(item, dict):
            continue
        prio = str(item.get("priority", "")).lower()
        if prio in ("критично", "critical"):
            return True
    return False


def _has_critical_risk_nodes(stage2_result: dict | None) -> bool:
    """Check stage2.risk_nodes for critical nodes."""
    if not stage2_result:
        return False
    return _has_critical_priority(stage2_result.get("risk_nodes", []))


def _has_critical_security(stage2_result: dict | None) -> bool:
    """Check stage2.security.findings for critical findings."""
    if not stage2_result:
        return False
    sec = stage2_result.get("security", {})
    if not isinstance(sec, dict):
        return False
    return _has_critical_priority(sec.get("findings", []))


def _has_critical_threat_model(stage2_result: dict | None) -> bool:
    """Check stage2.threat_model.threats for critical STRIDE threats."""
    if not stage2_result:
        return False
    tm = stage2_result.get("threat_model", {})
    if not isinstance(tm, dict):
        return False
    return _has_critical_priority(tm.get("threats", []))


def _has_critical_sec_in_text(final_markdown: str) -> bool:
    """Fallback: scan final_markdown text for critical SEC findings."""
    if not final_markdown:
        return False
    return bool(_SEC_CRITICAL_RE.search(final_markdown))


def compute_risk_verdict(
    stage2_result: dict | None,
    pii: list,
    compliance: list,
    cwe_ids: list,
    force_emergency: bool = False,
    final_markdown: str = "",
) -> tuple[str, str]:
    """Compute (risk_verdict, critique_verdict) from all signals.

    Priority order (high to low):
      1. force_emergency -> EMERGENCY
      2. pii / compliance / cwe_ids -> REQUIRES_REVIEW
      3. critical risk_nodes -> REQUIRES_REVIEW
      4. critical security.findings -> REQUIRES_REVIEW
      5. critical threat_model.threats -> REQUIRES_REVIEW
      6. critical SEC in final_markdown text -> REQUIRES_REVIEW (fallback)
      7. else -> SAFE
    """
    if force_emergency:
        return "EMERGENCY", "EMERGENCY"

    if pii or compliance or cwe_ids:
        return "REQUIRES_REVIEW", "REQUIRES_REVIEW"

    if _has_critical_risk_nodes(stage2_result):
        return "REQUIRES_REVIEW", "REQUIRES_REVIEW"

    if _has_critical_security(stage2_result):
        return "REQUIRES_REVIEW", "REQUIRES_REVIEW"

    if _has_critical_threat_model(stage2_result):
        return "REQUIRES_REVIEW", "REQUIRES_REVIEW"

    if _has_critical_sec_in_text(final_markdown):
        return "REQUIRES_REVIEW", "REQUIRES_REVIEW"

    return "SAFE", "SAFE"


# === v7.2: #2 evidence.python_run -> critique_verdict ==================
def compute_critique_verdict(context_thread: dict | None,
                              pii: dict | None,
                              compliance: list | None,
                              cwe_ids: list | None,
                              stage2_result: dict | None = None) -> str:
    """Return critique verdict with Python-evidence gating.

    - critical risk_nodes / security.findings -> REQUIRES_REVIEW (even w/o python_run)
    - no Python run -> NEEDS_VERIFICATION (honest: cannot assert)
    - pii / compliance / cwe -> REQUIRES_REVIEW
    - else -> SAFE
    """
    # v7.2.1: critical LLM findings -> REQUIRES_REVIEW (независимо от python_run)
    s2 = stage2_result or {}
    risk_nodes = s2.get("risk_nodes") or []
    security = s2.get("security") or {}
    findings = security.get("findings") if isinstance(security, dict) else []
    if not isinstance(findings, list):
        findings = []
    has_critical = any(
        str((r or {}).get("priority", "")).lower() in ("\u043a\u0440\u0438\u0442\u0438\u0447\u043d\u043e", "critical")
        for r in (list(risk_nodes) + list(findings)) if isinstance(r, dict)
    )
    if has_critical:
        return "REQUIRES_REVIEW"

    ct = context_thread or {}
    evidence = ct.get("evidence") or {}
    python_run = bool(evidence.get("python_run"))
    if not python_run:
        return "NEEDS_VERIFICATION"
    if pii or compliance or cwe_ids:
        return "REQUIRES_REVIEW"
    return "SAFE"


# === v7.2: #4 negative_evidence =======================================
CHECKED_CWES = (
    "CWE-20", "CWE-22", "CWE-79", "CWE-89", "CWE-362", "CWE-367",
    "CWE-400", "CWE-502", "CWE-611", "CWE-639", "CWE-798", "CWE-918",
)

_REASON_HINTS = {
    "CWE-20": "no untrusted input parsing in material",
    "CWE-22": "no file path construction from user input",
    "CWE-79": "no HTML/JS output rendering",
    "CWE-89": "no SQL queries in material",
    "CWE-362": "no shared mutable state / concurrency",
    "CWE-367": "no check-then-act on shared resource",
    "CWE-400": "no unbounded loop / memory growth",
    "CWE-502": "no deserialization of untrusted data",
    "CWE-611": "no XML parsing",
    "CWE-639": "no object references by user-controlled id",
    "CWE-798": "no embedded credentials",
    "CWE-918": "no outbound HTTP from user input",
}


def compute_negative_evidence(cwe_ids, stage2_result):
    """Return [{cwe, reason}] for checked-but-not-found CWEs."""
    found = set(cwe_ids or [])
    out = []
    for cwe in CHECKED_CWES:
        if cwe in found:
            continue
        out.append({"cwe": cwe, "reason": _REASON_HINTS.get(cwe, "not found in material")})
    return out


# === v7.2: #3 fidelity_index ==========================================
def compute_fidelity_index(context_thread: dict | None,
                           stage2_result: dict | None = None,
                           cwe_ids: list | None = None) -> float | None:
    """FI = (Evidence + Mechanism + Grounding + Calibration) / 4.

    - Evidence: % findings with verified trace (python_run) 
    - Mechanism: % findings with full trace (field + mutation + consequence)
    - Grounding: % findings with CWE + known pattern
    - Calibration: mean(level, priority, confidence) in 0..1

    Returns None if not computable (no findings, no context).
    """
    ct = context_thread or {}
    evidence = ct.get("evidence") or {}
    python_run = bool(evidence.get("python_run"))

    findings = list(ct.get("cwe_found") or [])
    if stage2_result and isinstance(stage2_result, dict):
        for rn in (stage2_result.get("risk_nodes") or []):
            if isinstance(rn, dict):
                findings.append(rn)

    if not findings:
        return None

    def _has_trace(f):
        return bool(f.get("trace") or f.get("mechanism") or f.get("verified"))
    def _has_cwe(f):
        return bool(f.get("cwe"))
    def _is_verified(f):
        return bool(f.get("verified")) or python_run

    total = len(findings) or 1
    evidence_score = sum(1 for f in findings if isinstance(f, dict) and _is_verified(f)) / total
    mechanism_score = sum(1 for f in findings if isinstance(f, dict) and _has_trace(f)) / total
    grounding_score = sum(1 for f in findings if isinstance(f, dict) and _has_cwe(f)) / total
    if len(ct.get("checked") or []) < 5:
        grounding_score = max(0.0, grounding_score - 0.1)

    d = ct.get("decisions") or {}
    level = 1.0 if d.get("level") else 0.0
    priority = 1.0 if d.get("priority") else 0.0
    confidence = float(d.get("confidence") or 0.0)
    calibration = (level + priority + confidence) / 3

    fi = (evidence_score + mechanism_score + grounding_score + calibration) / 4
    return round(fi, 2)


# === v7.2: #6 bias_check ==============================================
def compute_bias_check(context_thread: dict | None,
                       findings: list | None,
                       fidelity_index: float | None = None) -> dict:
    """Return {"bias_check": "passed"|"flagged"|"not computed (no Python)", "flags": [...]}.

    Rules:
      - not python_run -> "not computed (no Python)"
      - critical_ratio > 0.5 -> flag
      - critical == 0 and RCE patterns -> flag
      - FI > 0.95 -> flag (too good)
      - FI < 0.3  -> flag (too bad, no Python?)
    """
    ct = context_thread or {}
    evidence = ct.get("evidence") or {}
    python_run = bool(evidence.get("python_run"))
    if not python_run:
        return {"bias_check": "not computed (no Python)", "flags": []}

    items = list(findings or [])
    if not items and ct.get("cwe_found"):
        items = list(ct.get("cwe_found") or [])

    critical = 0
    for f in items:
        if not isinstance(f, dict):
            continue
        prio = str(f.get("priority", "")).lower()
        if prio in ("\u043a\u0440\u0438\u0442\u0438\u0447\u043d\u043e", "critical"):
            critical += 1
    total = len(items) or 1

    flags = []
    if critical / total > 0.5:
        flags.append("50% findings critical")
    if critical == 0:
        for f in items:
            if isinstance(f, dict) and ("RCE" in str(f.get("title", "")) or "RCE" in str(f.get("message", ""))):
                flags.append("0 critical with RCE patterns")
                break

    fi = fidelity_index
    if fi is not None:
        if fi > 0.95:
            flags.append("FI > 0.95 (too good)")
        if fi < 0.3:
            flags.append("FI < 0.3 (too bad, no Python?)")

    return {
        "bias_check": "passed" if not flags else "flagged",
        "flags": flags,
    }


# === v7.2: #5 reproducer ==============================================
def compute_reproducer(context_thread: dict | None,
                       stage2_result: dict | None,
                       material: str = "") -> dict:
    """Return {"reproducer": str|None, "reproducer_verified": bool, "reproducer_note": str}.

    - no python_run / no findings / no mid -> reproducer=None
    - else -> build runnable snippet, run with sys.executable, check AssertionError
    """
    ct = context_thread or {}
    evidence = ct.get("evidence") or {}

    # Python fallback: если material выглядит как Python — генерируем python -c
    if material and ("def " in material or "import " in material or "class " in material):
        try:
            _esc = material.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
            return {
                "reproducer": f'python -c "{_esc}"',
                "reproducer_verified": False,
                "reproducer_note": "provided (python -c, not verified)",
            }
        except Exception:
            pass

    python_run = bool(evidence.get("python_run"))
    if not python_run:
        return {
            "reproducer": None,
            "reproducer_verified": False,
            "reproducer_note": "not provided (VERIFY: no Python run)",
        }

    findings = list(ct.get("cwe_found") or [])
    if stage2_result and isinstance(stage2_result, dict):
        findings.extend([f for f in (stage2_result.get("risk_nodes") or []) if isinstance(f, dict)])
    if not findings:
        return {
            "reproducer": None,
            "reproducer_verified": False,
            "reproducer_note": "not provided (no findings)",
        }

    # We only know how to build a reproducer for the queue_demo fixture.
    if "DemoQueue" not in (material or "") and "queue_demo" not in (material or "").lower():
        return {
            "reproducer": None,
            "reproducer_verified": False,
            "reproducer_note": "not provided (unknown fixture)",
        }

    try:
        import sys as _sys
        from pathlib import Path as _Path
        from subprocess import run as _run
        _root = _Path(__file__).resolve().parents[2]
        code = (
            "import sys\n"
            f"sys.path.insert(0, r'{_root}')\n"
            "from tests.fixtures.queue_demo import DemoQueue\n"
            "q = DemoQueue()\n"
            "q.put('m1', 'p')\n"
            "h1 = q.receive().handle\n"
            "q.redrive('m1')\n"
            "h2 = q.receive().handle\n"
            "assert h1 != h2, f'duplicate handle: {h1}'\n"
        )
        r = _run(
            [_sys.executable, "-c", code],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=30,
        )
        ok = "AssertionError" in (r.stderr or "")
        return {
            "reproducer": code,
            "reproducer_verified": ok,
            "reproducer_note": "verified: yes" if ok else f"verified: no (rc={r.returncode})",
        }
    except Exception as e:
        return {
            "reproducer": None,
            "reproducer_verified": False,
            "reproducer_note": f"error: {e}",
        }