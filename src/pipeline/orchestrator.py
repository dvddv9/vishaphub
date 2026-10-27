import asyncio
import uuid
# -*- coding: utf-8 -*-
"""
Vishap V6.0.1 — главный pipeline.
v3: исправлен DeprecationWarning (datetime.utcnow → datetime.now(UTC)).
"""
import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, UTC, timedelta
from pathlib import Path

from src.config import DATA_DIR, ENABLE_WEB_SEARCH
from src.pipeline.stages import (
    stage0_orchestrator,
    stage1_scanner,
    stage2_analyst,
    stage1_5_translator,
    stage2_5_redteam,
    stage3_researcher,
    stage3_5_tester,
    stage4_synthesizer,
    stage4_5_fixer,
    stage5_transmitter,
)
from src.storage.history import add_entry
from src.tools.fallback_check import REQUIRED as REQUIRED_BLOCKS, LOSS_THRESHOLD
from src.pipeline.cost import sum_stage_costs
from src.tools.redact import redact_pii  # dogfood P0: pre-LLM PII redaction
from src.tools.sast import run_sast  # dogfood P1: deterministic SAST
from src.tools.static_scan import RULES as STATIC_RULES, scan_material, render_markdown as render_static_md  # built-in rules, no LLM
from src.tools.provenance import get_provenance  # dogfood P2: source tracking
from src.tools.sca import run_sca  # dogfood P1: dependency audit
from src.tools.patterns import PII_PATTERNS, COMPLIANCE_TRIGGERS
from src.tools.compliance import enrich_compliance  # P2-8
from src.tools.runbook import enrich_runbook  # P2-9
from src.tools.patterns import cwe_to_owasp
from src.tools.patterns import detect_exploitability
from src.tools.reachability import enrich_exploitability  # P2-7
from src.tools.dataflow import enrich_dataflow  # P2-7b
from src.tools.anomaly import enrich_anomaly  # P2-12
from src.tools.patterns import CRITICAL_RISK_PATTERNS
from src.tools.baseline import apply_baseline
from src.tools.deps import build_import_graph, collect_context_files
from src.pipeline.verdict import (
    compute_risk_verdict,  # v5.11.2: consolidated verdict
    compute_critique_verdict,  # v7.2: #2 evidence.python_run -> critique
    compute_negative_evidence,  # v7.2: #4 negative_evidence
    compute_fidelity_index,  # v7.2: #3
    compute_bias_check,  # v7.2: #6
    compute_reproducer,  # v7.2: #5
)
from src.version import __version__

#: What `src.llm.client.chat()` returns when the custom endpoint cannot be reached.
LLM_ERROR_PREFIX = "[LLM error]"

#: Shown instead of a silent "SAFE" report when no stage ever reached the model.
LLM_UNAVAILABLE_BANNER = (
    "## Анализ не выполнен: LLM недоступен\n\n"
    "LLM did not respond, so the stages did not produce a report — "
    "below is an empty result, and audit is marked `critique_verdict: ERROR`.\n\n"
    "Check `CUSTOM_LLM_URL` / `CUSTOM_LLM_KEY` (OpenAI-compatible endpoint; "
    "Check `CUSTOM_LLM_URL` / `CUSTOM_LLM_KEY` (OpenAI-compatible endpoint).\n\n"
    "```\n{error}\n```\n\n---\n\n"
)


def llm_error_of(stage) -> str | None:
    """The stage's LLM error text, when that stage never reached the model."""
    if isinstance(stage, str):
        text = stage
        return text if text.lstrip().startswith(LLM_ERROR_PREFIX) else None
    if not isinstance(stage, dict):
        return None
    text = str(stage.get("text") or "")
    if stage.get("mode") == "error" or text.startswith(LLM_ERROR_PREFIX):
        return text or "LLM error"
    return None


from src.observability.logging import get_logger
from src.observability.tracing import span

log = get_logger(__name__)


def format_runbook_md(audit: dict) -> str:
    """P2-9: render [RUNBOOK] section for Markdown report."""
    rb = (audit or {}).get("runbook", {}) or {}
    if not rb:
        return ""

    lines = ["\n\n[RUNBOOK]\n"]
    for cwe in sorted(rb.keys()):
        entry = rb[cwe]
        title = entry.get("title", "")
        sev = entry.get("severity", "")
        lines.append(f"\n## {cwe} — {title} ({sev})\n")

        immediate = entry.get("immediate", [])
        if immediate:
            lines.append("\n**IMMEDIATE (0-1h):**\n")
            for i, step in enumerate(immediate, 1):
                lines.append(f"  {i}. {step}\n")

        short_term = entry.get("short_term", [])
        if short_term:
            lines.append("\n**SHORT-TERM (1-3 days):**\n")
            for i, step in enumerate(short_term, 1):
                lines.append(f"  {i}. {step}\n")

        long_term = entry.get("long_term", [])
        if long_term:
            lines.append("\n**LONG-TERM (1-4 weeks):**\n")
            for i, step in enumerate(long_term, 1):
                lines.append(f"  {i}. {step}\n")

        escalation = entry.get("escalation", "")
        if escalation:
            lines.append(f"\n**ESCALATION:** {escalation}\n")

    return "".join(lines)


def _safe_escalation_note(stage) -> str:
    """Extract escalation note from stage4, tolerant to dict/list/None."""
    if not stage or not isinstance(stage, dict):
        return ""
    collision = stage.get('collision')
    if isinstance(collision, dict):
        return str(collision.get('note', '') or '')
    if isinstance(collision, list):
        parts = []
        for c in collision:
            if isinstance(c, dict):
                parts.append(str(c.get('note', '')))
            else:
                parts.append(str(c))
        return '; '.join(x for x in parts if x)
    return ""


MAX_CHARS = 12000   # ~3000 токенов


# === Audit (встроенный compliance-scan) ===

def detect_material_complete(material: str, final_markdown: str = "") -> bool:
    """DEPRECATED (v5.8): use `not truncated` from run_pipeline instead."""
    markers = ["truncated", "усечён", "усечен", "slice truncated", "слайс усеч"]
    text = (material or "")[:2000] + " " + (final_markdown or "")[:2000]
    low = text.lower()
    for m in markers:
        if m in low:
            return False
    return True


def compute_hash(material: str, context: str = "") -> str:
    """Compute SHA-256 hash of material, bound to the caller's context.

    ``context`` is ``f"{filename}:{session_id}"`` at every call site; ignoring it
    made identical bytes from different files/sessions collapse to one key.
    """
    payload = material if not context else f"{context}\x00{material}"
    h = hashlib.sha256(payload.encode("utf-8", errors="replace"))
    return f"sha256:{h.hexdigest()}"


def strip_llm_audit_blocks(md: str) -> str:
    """Remove [AUDIT_TRAIL] and [COMPLETENESS] from LLM output."""
    md = re.sub(
        r'\n*\[AUDIT_TRAIL\].*?(?=\n\[|\Z)',
        '', md, flags=re.DOTALL
    ).strip()
    md = re.sub(
        r'\n*\[COMPLETENESS\].*?(?=\n\[|\Z)',
        '', md, flags=re.DOTALL
    ).strip()
    return md


def _filter_copyright_emails(text: str, pattern) -> list:
    """Return emails NOT in copyright/license/author headers."""
    # Only real attribution markers. A bare "by " used to match any line like
    # "# contact sec@corp.ru (used by the billing job)" and hid the PII.
    _MARKERS = (
        "copyright", "(c)", "\u00a9", "author", "maintainer",
        "license", "licence", "written by",
        "@wireshark.org", "@gnu.org", "@fsf.org", "@apache.org",
        "@python.org", "@gnome.org", "@kernel.org",
    )
    cleaned = []
    for m in pattern.finditer(text):
        email = m.group()
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        if line_end == -1:
            line_end = len(text)
        line = text[line_start:line_end].lower()
        if not any(marker in line for marker in _MARKERS):
            cleaned.append(email)
    return cleaned


def detect_pii(text: str) -> dict:
    found = {}
    for name, pattern in PII_PATTERNS.items():
        matches = pattern.findall(text)
        if not matches:
            continue
        if name == "email":
            matches = _filter_copyright_emails(text, pattern)
            if not matches:
                continue
        found[name] = len(matches)
    return found


def detect_compliance(text: str, pii: dict | None = None) -> list:
    low = text.lower()
    flags = []
    for flag, triggers in COMPLIANCE_TRIGGERS.items():
        if any(t in low for t in triggers):
            flags.append(flag)

    if pii:
        if any(k in pii for k in ("email", "phone_ru", "passport_ru", "snils", "iban")):
            if "GDPR" not in flags:
                flags.append("GDPR")
            if "152-ФЗ" not in flags:
                flags.append("152-ФЗ")

        secret_keys = ("aws_access_key", "aws_secret_key", "stripe_live_key",
                       "stripe_test_key", "github_token", "slack_token",
                       "google_api_key", "private_key", "hardcoded_password",
                       "hardcoded_secret")
        if any(k in pii for k in secret_keys):
            if "SECRETS" not in flags:
                flags.append("SECRETS")

    return flags


def generate_audit_id() -> str:
    now = datetime.now(UTC)
    today = now.strftime("%Y-%m-%d")
    rand = hashlib.md5(str(now.timestamp()).encode()).hexdigest()[:6]
    return f"audit-{today}-{rand}"


def detect_language(filename: str) -> str:
    """Detect language from filename for SAST tool selection."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "py": "python", "go": "go", "js": "javascript", "ts": "typescript",
        "java": "java", "rs": "rust",
        "jsx": "javascript", "mjs": "javascript", "cjs": "javascript",
        "tsx": "typescript",
    }.get(ext, "other")


def detect_cwe(text: str) -> list:
    """Detect CWE IDs mentioned in material (CWE-XXX format)."""
    import re as _re
    matches = _re.findall(r"\bCWE-(\d+)\b", text)
    seen = []
    for m in matches:
        cwe = f"CWE-{m}"
        if cwe not in seen:
            seen.append(cwe)
    return seen


def collect_findings_cwe(stage2_result: dict | None) -> list:
    """Collect CWE IDs from LLM security.findings[].cwe (v6.1-fix)."""
    import re as _re
    if not stage2_result:
        return []
    sec = stage2_result.get("security", {})
    findings = sec.get("findings", []) if isinstance(sec, dict) else []
    cwes = []
    for f in findings or []:
        if not isinstance(f, dict):
            continue
        cwe = str(f.get("cwe", "") or "")
        m = _re.match(r"CWE-\d+", cwe)
        if m and m.group() not in cwes:
            cwes.append(m.group())
    return cwes


def map_cwe_to_owasp(cwe_ids: list, year: str = "2025") -> list:
    """Map list of CWE IDs to unique OWASP Top 10 categories."""
    owasp = []
    for cwe in cwe_ids:
        cat = cwe_to_owasp(cwe, year=year)
        if cat and cat not in owasp:
            owasp.append(cat)
    return owasp


def sanitize_session_id(text: str, real_session_id: str) -> str:
    """Replace hallucinated session_id with real one."""
    import re as _re
    if not text or not real_session_id:
        return text
    text = _re.sub(r"sess-20\d{2}-\d{2}-\d{2}-[a-z0-9]+", real_session_id, text)
    return text



def _is_d0(material: str) -> tuple[bool, str]:
    """True when the material is too small to analyse at all.

    'parse_error' is deliberately NOT D0: a file that fails ``ast.parse`` is
    exactly the case a scanner must still look at (Python 2 syntax, templates), so
    it falls through to SAST + the LLM pipeline. Classifying it as D0 used to answer
    SAFE for unparsable code that contained ``os.system(user_input)``.
    """
    if not material or not material.strip():
        return True, 'empty'
    if len(material.strip()) < 10:
        return True, 'trivial'
    return False, ''

def run_audit(material: str, session_id: str, model: str = "custom",
              truncated: bool = False, original_size: int = 0,
              material_hash_full: str = None,
              force_emergency: bool = False,
              context: str = "",
              redaction_map: dict = None,
              sast_result: dict = None,
              sca_result: dict = None,
              web_search_queries: list = None,
              escalation_level: str = "",
              stage2_result: dict = None,
              final_markdown: str = "",
              llm_error: str = "",
              context_thread: dict | None = None,
              analysis_mode: str = "llm") -> dict:
    """Собирает audit-запись."""
    pii = detect_pii(material)
    compliance = detect_compliance(material, pii)
    cwe_ids = detect_cwe(material)
    cwe_ids = cwe_ids + [c for c in collect_findings_cwe(stage2_result) if c not in cwe_ids]
    # CWEs found by the built-in rule engine (src.tools.static_scan) count as evidence too
    cwe_ids += [c for c in ((sast_result or {}).get("cwe_ids") or []) if c not in cwe_ids]
    # PII -> CWE-359 (patch-drift): если pii_detected, CWE-359 обязателен
    if pii and "CWE-359" not in cwe_ids:
        cwe_ids.append("CWE-359")
    risk_verdict, critique = compute_risk_verdict(
        stage2_result=stage2_result,
        pii=pii,
        compliance=compliance,
        cwe_ids=cwe_ids,
        force_emergency=force_emergency,
        final_markdown=final_markdown,
    )
    # v7.2: #2 evidence.python_run -> critique_verdict
    if not force_emergency and not llm_error:
        critique = compute_critique_verdict(
            context_thread=context_thread,
            pii=pii,
            compliance=compliance,
            cwe_ids=cwe_ids,
            stage2_result=stage2_result,
        )
    if llm_error:
        risk_verdict, critique = "REQUIRES_REVIEW", "ERROR"
    owasp_categories = map_cwe_to_owasp(cwe_ids, year="2025")
    exploitability = detect_exploitability(material)
    exploitability = enrich_exploitability(material, exploitability)
    dataflow_result = enrich_dataflow(material)
    anomaly_result = enrich_anomaly(material)
    provenance = get_provenance()

    audit = {
        "audit_id": generate_audit_id(),
        "session_id": session_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "material_hash": compute_hash(material, context=context),
        "material_hash_full": material_hash_full or compute_hash(material, context=context),
        "material_size": {
            "lines": len(material.splitlines()),
            "chars": len(material),
        },
        "model": model,
        "critique_verdict": critique,
        "risk_verdict": risk_verdict,
        "llm_error": bool(llm_error),
        "llm_error_text": (llm_error or "")[:500],
        "cwe_ids": cwe_ids,
        "owasp_categories": owasp_categories,
        "exploitability": exploitability,
        "dataflow": dataflow_result.get("dataflow", {}),
        "anomaly": anomaly_result.get("anomaly", {}),
        "provenance": provenance,
        "pii_detected": bool(pii),
        "pii_details": pii,
        **enrich_compliance(cwe_ids, compliance),
        **enrich_runbook(cwe_ids),
        "redaction_applied": bool(redaction_map),
        "redaction_map": redaction_map or {},
        "analysis_mode": analysis_mode,
        "sast_engine": (sast_result or {}).get("engine", ""),
        "static_findings": ((sast_result or {}).get("findings") or [])[:200] if (sast_result or {}).get("engine") else [],
        "sast_findings": (sast_result or {}).get("total_findings", 0),
        "sast_high_priority": (sast_result or {}).get("high_priority", 0),
        "sast_tools": {
            "bandit": ((sast_result or {}).get("bandit") or {}).get("summary", {}),
            "semgrep": ((sast_result or {}).get("semgrep") or {}).get("summary", {}),
        } if sast_result else {},
        "sca_vulnerabilities": ((sca_result or {}).get("pip_audit") or {}).get("summary", {}).get("total", 0),
        "truncated": truncated,
        "original_size": original_size,
        "web_search_used": ENABLE_WEB_SEARCH,
        "web_search_queries": web_search_queries or [],
        "web_search_credits": len(web_search_queries or []),
        "escalation_level": escalation_level,
    }
    # v7.2: #4 negative_evidence
    _checked_cwes = sorted({r.cwe for r in STATIC_RULES if getattr(r, "cwe", "")})
    if isinstance(context_thread, dict):
        context_thread["checked"] = _checked_cwes
    audit["negative_evidence"] = compute_negative_evidence(
        cwe_ids=cwe_ids,
        stage2_result=stage2_result,
        checked=_checked_cwes,
    )
    # v7.2: #8 report_date / valid_until
    # timezone-aware (UTC): a naive timestamp is shown shifted by the viewer's UTC offset
    audit["report_date"] = datetime.now(UTC).isoformat()
    audit["valid_until"] = (datetime.now(UTC) + timedelta(days=90)).isoformat()
    audit["report_date_source"] = "system clock"

    # v7.2: #3 fidelity_index
    audit["fidelity_index"] = compute_fidelity_index(
        context_thread=context_thread,
        stage2_result=stage2_result,
        cwe_ids=cwe_ids,
    )
    if audit["fidelity_index"] is None:
        audit["fidelity_index_note"] = "not provided (VERIFY: not computed)"
    # v7.2: #6 bias_check
    audit["bias_check"] = compute_bias_check(
        context_thread=context_thread,
        findings=stage2_result.get("risk_nodes", []) if isinstance(stage2_result, dict) else [],
        fidelity_index=audit.get("fidelity_index"),
    )
    # v7.2: #5 reproducer
    _rep = compute_reproducer(
        context_thread=context_thread,
        stage2_result=stage2_result,
        material=material,
    )
    audit["reproducer"] = _rep.get("reproducer")
    audit["reproducer_verified"] = _rep.get("reproducer_verified", False)
    audit["reproducer_note"] = _rep.get("reproducer_note", "")
    audit_file = DATA_DIR / f"audit_{session_id}.json"
    try:
        audit_file.write_text(
            json.dumps(audit, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except PermissionError as e:
        import logging
        logging.getLogger(__name__).warning(
            "audit file write skipped: %s (%s)", audit_file, e
        )

    return audit


# === Pipeline ===

def _timed_stage(log, stage: str, session_id: str, fn, *args, **kwargs):
    """Run one pipeline stage with structlog timing + OTel span."""
    t0 = time.time()
    log.info("stage_started", stage=stage, session_id=session_id)
    try:
        with span(f"stage.{stage}"):
            result = fn(*args, **kwargs)
    except Exception as e:
        log.error("stage_failed", stage=stage, error=str(e), exc_info=True)
        raise
    log.info("stage_done", stage=stage, duration_ms=round((time.time() - t0) * 1000, 2))
    return result


def run_pipeline(material: str, filename: str, verbose: bool = True, api_key: str | None = None,
                 session_suffix: str = "",
                 baseline_path: str = None,
                 save_baseline_path: str = None,
                 context_root: str = None) -> dict:
    """Запускает полный pipeline Vishap."""
    truncated = False
    llm_error = ""
    original_size = len(material)
    session_id = f"sess-{datetime.now(UTC).strftime('%Y-%m-%d-%H%M%S')}-{uuid.uuid4().hex[:8]}{session_suffix}"
    _pipeline_start = time.time()
    material_hash_full = compute_hash(material, context=f"{filename}:{session_id}")
    if original_size > MAX_CHARS:
        material = material[:MAX_CHARS]
        truncated = True
        if verbose:
            print(f"[!] Материал {original_size} символов > {MAX_CHARS} — обрезан")

    if verbose:
        print("=== Vishap Pipeline ===")
        print(f"Session: {session_id}")
        print(f"File: {filename}")
        print(f"Material: {len(material)} символов")
        print()

    if verbose:
        print("[Stage 0] Orchestrator...")
    material_original = material
    material, redaction_map = redact_pii(material)
    if redaction_map:
        if verbose:
            print(f"[Redact] PII/secrets redacted: {redaction_map}")
        original_audit_pii = detect_pii(material_original)
        original_audit_compliance = detect_compliance(material_original, original_audit_pii)
    else:
        original_audit_pii = {}
        original_audit_compliance = []

    context_thread = {
        "material_hash": material_hash_full,
        "metrics": {},
        "cwe_found": [],
        "evidence": {"python_run": False, "tests_run": False, "ast_parsed": False},
        "decisions": {"level": None, "priority": None, "confidence": None, "fix_class": None},
        "assumptions": [],
        "open_questions": [],
        "checked": [],
        "not_found": [],
        "negative_evidence": [],
    }

    stage0 = _timed_stage(log, "stage0", session_id, stage0_orchestrator, material, filename)
    if isinstance(stage0, dict):
        stage0["session_id"] = session_id
    route = stage0.get("route", [])
    level = stage0.get("level", "D3")
    research_first = stage0.get("research_first", False)
    subst_count = stage0.get("subst_count", 0)

    if verbose:
        print(f"  → level: {level}, route: {route}")
        print(f"  → research_first: {research_first}, subst_count: {subst_count}")
        print()

    flags = stage0.get("flags", [])

    if "EMERGENCY_INTERRUPT" in flags:
        _audit_material = material_original if "material_original" in dir() else material
        _pii = detect_pii(_audit_material)
        _comp = detect_compliance(_audit_material, _pii)
        _secret_keys = (
            "aws_access_key", "aws_secret_key", "stripe_live_key",
            "stripe_test_key", "github_token", "slack_token",
            "google_api_key", "private_key", "hardcoded_password",
            "hardcoded_secret",
        )
        _has_secrets_or_pii = any(k in _pii for k in _secret_keys) or bool(_pii) or bool(_comp)

        _critical_hits = []
        for _risk_name, _risk_pattern in CRITICAL_RISK_PATTERNS.items():
            if _risk_pattern.search(_audit_material):
                _critical_hits.append(_risk_name)

        _has_real_emergency = _has_secrets_or_pii or bool(_critical_hits)

        if not _has_real_emergency:
            flags = [f for f in flags if f != "EMERGENCY_INTERRUPT"]
            flags.append("WARNING: llm_emergency_downgraded")
            if verbose:
                print("[!] EMERGENCY от LLM понижен до WARNING (audit: SAFE, no critical patterns)")
                print(f"    flags: {flags}")
        else:
            if verbose:
                reason = []
                if _has_secrets_or_pii:
                    reason.append("secrets/PII")
                if _critical_hits:
                    reason.append(f"critical patterns: {_critical_hits}")
                print(f"[!] EMERGENCY подтверждён audit ({', '.join(reason)})")

    if "EMERGENCY_INTERRUPT" in flags:
        if verbose:
            print("[!] EMERGENCY_INTERRUPT — стоп (подтверждено audit)")

        if verbose:
            print("[Audit] Сбор audit-записи (emergency)...")
        audit = run_audit(material_original, session_id, truncated=truncated, original_size=original_size, material_hash_full=material_hash_full, force_emergency=True, context=f"{filename}:{session_id}", redaction_map=redaction_map if "redaction_map" in dir() else {}, sast_result=_sast_result if "_sast_result" in dir() else None, sca_result=_sca_result if "_sca_result" in dir() else None, web_search_queries=(stage2.get("_web_search", {}) or {}).get("queries", []) if "stage2" in dir() else [], escalation_level=_safe_escalation_note(stage4) if "stage4" in dir() else "", stage2_result=stage2 if "stage2" in dir() else None, llm_error=llm_error, context_thread=context_thread)
        if verbose:
            print(f"  → audit_id: {audit['audit_id']}")
            print(f"  → material_hash: {audit['material_hash']}")
            print(f"  → pii_detected: {audit['pii_detected']}")
            print(f"  → compliance_flags: {audit['compliance_flags']}")
            print(f"  → critique_verdict: {audit['critique_verdict']}")
            print()

        emergency_md = (
            "⛔ INTERRUPTED: EMERGENCY\n\n"
            "[EMERGENCY]\n"
            "Stage 0 обнаружил критический риск → pipeline остановлен.\n"
            f"[TRIGGER] flags: {flags}\n"
            f"[REASON] level: {level}, route: {route}\n"
        )
        audit_block = (
            "\n\n[AUDIT_TRAIL]\n"
            f"generator: Vishap {__version__}\n"
            f"audit_id: {audit['audit_id']}\n"
            f"material_hash: {audit['material_hash']}\n"
            f"material_hash_full: {audit.get('material_hash_full', audit['material_hash'])}\n"
            f"pii_detected: {str(audit['pii_detected']).lower()}\n"
            f"compliance_flags: {audit['compliance_flags']}\n"
            f"compliance_controls: {audit.get('compliance_controls', {})}\n"
            f"compliance_standards: {audit.get('compliance_standards', [])}\n"
            f"critique_verdict: {audit['critique_verdict']}\n"
            f"risk_verdict: {audit.get('risk_verdict', 'SAFE')}\n"
            f"cwe_ids: {audit.get('cwe_ids', [])}\n"
            f"owasp_categories: {audit.get('owasp_categories', [])}\n"
            f"exploitability_reachable: {audit.get('exploitability', {}).get('reachable', False)}\n"
            f"exploitability_auth_required: {audit.get('exploitability', {}).get('auth_required', False)}\n"
            f"exploitability_blast_radius: {audit.get('exploitability', {}).get('blast_radius', 'none')}\n"
            f"exploitability_source_count: {audit.get('exploitability', {}).get('source_count', 0)}\n"
            f"exploitability_path: {audit.get('exploitability', {}).get('exploit_path', [])}\n"
            f"dataflow_path: {audit.get('dataflow', {}).get('path', [])}\n"
            f"dataflow_source_count: {audit.get('dataflow', {}).get('source_count', 0)}\n"
            f"anomaly_verdict: {audit.get('anomaly', {}).get('verdict', 'NORMAL')}\n"
            f"anomaly_count: {audit.get('anomaly', {}).get('count', 0)}\n"
            f"anomaly_method: {audit.get('anomaly', {}).get('method', 'none')}\n"
            f"anomaly_top: {audit.get('anomaly', {}).get('anomalies', [])[:3]}\n"
            f"provenance_source: {audit.get('provenance', {}).get('source', 'unknown')}\n"
            f"provenance_commit: {audit.get('provenance', {}).get('git_commit_short', '')}\n"
            f"llm_error: {str(audit.get('llm_error', False)).lower()}\n"
        )
        emergency_md = emergency_md + audit_block

        add_entry({
            "session_id": session_id,
            "filename": filename,
            "level": level,
            "route": route,
            "material_size": len(material),
            "verdict": audit["critique_verdict"],
            "pii_detected": audit["pii_detected"],
            "material_hash": audit["material_hash"],
        })

        result_file = DATA_DIR / f"result_{session_id}.json"
        result_file.write_text(
            json.dumps({
                "session_id": session_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "filename": filename,
                "material_size": len(material),
                "stage0": stage0,
                "audit": audit,
                "emergency": True,
                "critique_verdict": audit.get("critique_verdict", "SAFE"),
                "cost_usd": 0.0,
                "final_markdown": emergency_md,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if verbose:
            print("=== Pipeline завершён (EMERGENCY) ===")
            print(f"Результат: {result_file}")
            print()

        log.info(
            "pipeline_done",
            session_id=session_id,
            level=level,
            emergency=True,
            duration_ms=round((time.time() - _pipeline_start) * 1000, 2),
        )

        return {
            "session_id": session_id,
            "stage0": stage0,
            "audit": audit,
            "emergency": True,
            "final_markdown": emergency_md,
        }

    if verbose:
        print("[Stage 1] Scanner...")
    stage1 = _timed_stage(log, "stage1", session_id, stage1_scanner, material, {"stage0": stage0})
    # v7.3.13: cross-language translator (VISHAP_TRANSLATOR=1)
    stage1_5 = _timed_stage(log, "stage1_5", session_id, stage1_5_translator, material, {"stage0": stage0, "stage1": stage1})
    if verbose and stage1_5.get("cross_language"):
        print(f"  → cross-language: {len(stage1_5['cross_language'])}")
    _stage1_5_ctx = stage1_5 if stage1_5.get("cross_language") else None

    _lang = detect_language(filename)
    _sast_result = None
    _sca_result = None
    if _lang in ("python", "go", "javascript", "typescript", "java", "rust"):
        try:
            _sast_result = run_sast(filename, language=_lang)
            if verbose:
                print(f"[SAST] {_lang}: {_sast_result.get('total_findings', 0)} findings "
                      f"({_sast_result.get('high_priority', 0)} high)")
        except Exception as _e:
            if verbose:
                print(f"[SAST] error: {_e}")
    if filename.endswith("requirements.txt"):
        try:
            _sca_result = run_sca(filename)
            if verbose:
                _n = _sca_result.get("pip_audit", {}).get("summary", {}).get("total", 0)
                print(f"[SCA] pip-audit: {_n} vulnerabilities")
        except Exception as _e:
            if verbose:
                print(f"[SCA] error: {_e}")
    if verbose:
        print()

    # v7.2: #1 context_thread (after stage1)
    context_thread["metrics"] = stage1.get("metrics", {}) if isinstance(stage1, dict) else {}
    context_thread["evidence"]["python_run"] = True
    context_thread["evidence"]["ast_parsed"] = True

    if verbose:
        print("[Stage 2] Analyst...")
    _ctx_files = None
    if context_root:
        try:
            _graph = build_import_graph(context_root)
            _ctx_files = collect_context_files(
                context_root, filename, depth=2, graph=_graph,
            )
            if verbose and _ctx_files:
                print(f"  [Inter-file] {len(_ctx_files)} related files")
        except Exception as _e:
            if verbose:
                print(f"  [Inter-file] error: {_e}")
    _stage2_ctx = {"stage0": stage0, "stage1": stage1}
    if "_stage1_5_ctx" in locals() and _stage1_5_ctx:
        _stage2_ctx["stage1_5"] = _stage1_5_ctx
    if _ctx_files:
        _stage2_ctx["context_files"] = _ctx_files
    stage2 = _timed_stage(log, "stage2", session_id, stage2_analyst, material, _stage2_ctx)
    # v7.3.11: self-adversarial red team (VISHAP_REDTEAM=1), deduplicated
    # fail-fast: if stage2 already failed, skip red team (no wasted LLM call)
    _s2_err = (stage2 or {}).get("mode") == "error" or bool((stage2 or {}).get("_error"))
    if _s2_err:
        stage2_5 = {"missed": [], "critique": "", "mode": "skipped", "reason": "stage2 error"}
        if verbose:
            print("  → red team skipped (stage2 error)")
    else:
        stage2_5 = _timed_stage(log, "stage2_5", session_id, stage2_5_redteam, material, {"stage0": stage0, "stage1": stage1, "stage2": stage2})
    _existing_cwes = set()
    for _r in (stage2.get("risk_nodes") or []):
        if isinstance(_r, dict):
            _c = str(_r.get("cwe", "") or "")
            if _c:
                _existing_cwes.add(_c)
    _new_missed = [
        m for m in (stage2_5.get("missed") or [])
        if isinstance(m, dict) and str(m.get("cwe", "") or "") not in _existing_cwes
    ]
    # red-team entries carry "severity"; every verdict check reads "priority", so
    # a critical miss used to add no escalation at all. Map it, then merge safely
    # (a model that answers "risk_nodes": null must not crash the run).
    for _m in _new_missed:
        if "priority" not in _m and _m.get("severity"):
            _m["priority"] = _m["severity"]
    if _new_missed:
        _nodes = stage2.get("risk_nodes")
        if not isinstance(_nodes, list):
            _nodes = []
        _nodes.extend(_new_missed)
        stage2["risk_nodes"] = _nodes
    if verbose and _new_missed:
        print(f"  → red team missed (new): {len(_new_missed)}")
    risk_nodes = stage2.get("risk_nodes") or []
    # v7.2: #1 context_thread (after stage2)
    context_thread["cwe_found"] = list(risk_nodes)
    context_thread["decisions"]["level"] = level
    context_thread["decisions"]["priority"] = "критично" if any(
        str(r.get("priority", "")).lower() in ("критично", "critical")
        for r in risk_nodes if isinstance(r, dict)
    ) else "важно"
    context_thread["decisions"]["confidence"] = 0.8

    if verbose:
        print(f"  → risk nodes: {len(risk_nodes)}")
        print()

    # v7.2: #1 context_thread (async, after stage2)
    _rn = stage2.get("risk_nodes", []) if isinstance(stage2, dict) else []
    context_thread["cwe_found"] = list(_rn)
    context_thread["decisions"]["level"] = level
    context_thread["decisions"]["priority"] = "критично" if any(
        str(r.get("priority", "")).lower() in ("критично", "critical")
        for r in _rn if isinstance(r, dict)
    ) else "важно"
    context_thread["decisions"]["confidence"] = 0.8
    stage3 = None
    if research_first:
        if verbose:
            print("[Stage 3] Researcher...")
        stage3 = _timed_stage(log, "stage3", session_id, stage3_researcher, material, {"stage0": stage0, "stage1": stage1, "stage2": stage2})
        if verbose:
            print()

    # v7.3.14: test-first loop (VISHAP_TESTER=1)
    stage3_5 = _timed_stage(log, "stage3_5", session_id, stage3_5_tester, material, {"stage0": stage0, "stage1": stage1, "stage2": stage2})
    if verbose and stage3_5.get("confirmed"):
        print(f"  → confirmed: {len(stage3_5['confirmed'])}")
    if verbose and stage3_5.get("false_positives"):
        print(f"  → false positives: {len(stage3_5['false_positives'])}")

    if verbose:
        print("[Stage 4] Synthesizer...")
    context_4 = {"stage0": stage0, "stage1": stage1, "stage2": stage2, "stage2_5": stage2_5 if "stage2_5" in locals() else {}, "stage3_5": stage3_5 if "stage3_5" in locals() and (stage3_5.get("confirmed") or stage3_5.get("false_positives")) else {}}
    if stage3:
        context_4["stage3"] = stage3
    stage4 = _timed_stage(log, "stage4", session_id, stage4_synthesizer, material, context_4)
    if verbose:
        print(f"  → options: {len(stage4.get('options') or [])}")
        print()

    # v7.3.15: fix-loop (VISHAP_FIXER=1)
    stage4_5 = _timed_stage(log, "stage4_5", session_id, stage4_5_fixer, material, {"stage0": stage0, "stage4": stage4})
    if verbose and stage4_5.get("accepted"):
        print(f"  → fix accepted: {len(stage4_5['accepted'])}")
    if verbose and stage4_5.get("rejected"):
        print(f"  → fix rejected: {len(stage4_5['rejected'])}")

    if verbose:
        print("[Stage 5] Transmitter...")
    context_5 = {
        "stage0": stage0, "stage1": stage1, "stage2": stage2,
        "stage4": stage4,
        "task_type": stage0.get("task_type", "other"),
    }
    if stage3:
        context_5["stage3"] = stage3
    final_markdown = _timed_stage(log, "stage5", session_id, stage5_transmitter, material, context_5)
    final_markdown = strip_llm_audit_blocks(final_markdown)
    final_markdown = sanitize_session_id(final_markdown, session_id)

    llm_error = (
        llm_error_of(stage0) or llm_error_of(stage2) or llm_error_of(stage4)
        or llm_error_of(final_markdown) or ""
    )
    if llm_error:
        final_markdown = LLM_UNAVAILABLE_BANNER.format(error=llm_error.strip()[:600]) + final_markdown

    if verbose:
        print("[Audit] Сбор audit-записи...")
    force_emergency = bool(stage0.get('force_emergency', False))
    _escalation = _safe_escalation_note(stage4)

    audit = run_audit(material_original, session_id, truncated=truncated, original_size=original_size, material_hash_full=material_hash_full, force_emergency=force_emergency, context=f"{filename}:{session_id}", redaction_map=redaction_map, sast_result=_sast_result if "_sast_result" in dir() else None, sca_result=_sca_result if "_sca_result" in dir() else None, web_search_queries=(stage2.get("_web_search", {}) or {}).get("queries", []) if "stage2" in dir() else [], escalation_level=_safe_escalation_note(stage4) if "stage4" in dir() else "", stage2_result=stage2 if "stage2" in dir() else None, final_markdown=final_markdown, llm_error=llm_error, context_thread=context_thread)
    if verbose:
        print(f"  → audit_id: {audit['audit_id']}")
        print(f"  → material_hash: {audit['material_hash']}")
        print(f"  → pii_detected: {audit['pii_detected']}")
        print(f"  → compliance_flags: {audit['compliance_flags']}")
        print(f"  → critique_verdict: {audit['critique_verdict']}")
        print()

    audit_block = (
        "\n\n[AUDIT_TRAIL]\n"
        f"generator: Vishap {__version__}\n"
        f"audit_id: {audit['audit_id']}\n"
        f"material_hash: {audit['material_hash']}\n"
        f"material_hash_full: {audit.get('material_hash_full', audit['material_hash'])}\n"
        f"pii_detected: {str(audit['pii_detected']).lower()}\n"
        f"compliance_flags: {audit['compliance_flags']}\n"
        f"compliance_controls: {audit.get('compliance_controls', {})}\n"
        f"compliance_standards: {audit.get('compliance_standards', [])}\n"
        f"critique_verdict: {audit['critique_verdict']}\n"
        f"risk_verdict: {audit.get('risk_verdict', 'SAFE')}\n"
        f"cwe_ids: {audit.get('cwe_ids', [])}\n"
        f"owasp_categories: {audit.get('owasp_categories', [])}\n"
        f"exploitability_reachable: {audit.get('exploitability', {}).get('reachable', False)}\n"
        f"exploitability_auth_required: {audit.get('exploitability', {}).get('auth_required', False)}\n"
        f"exploitability_blast_radius: {audit.get('exploitability', {}).get('blast_radius', 'none')}\n"
        f"exploitability_source_count: {audit.get('exploitability', {}).get('source_count', 0)}\n"
        f"exploitability_path: {audit.get('exploitability', {}).get('exploit_path', [])}\n"
        f"dataflow_path: {audit.get('dataflow', {}).get('path', [])}\n"
        f"dataflow_source_count: {audit.get('dataflow', {}).get('source_count', 0)}\n"
        f"anomaly_verdict: {audit.get('anomaly', {}).get('verdict', 'NORMAL')}\n"
        f"anomaly_count: {audit.get('anomaly', {}).get('count', 0)}\n"
        f"anomaly_method: {audit.get('anomaly', {}).get('method', 'none')}\n"
        f"anomaly_top: {audit.get('anomaly', {}).get('anomalies', [])[:3]}\n"
        f"provenance_source: {audit.get('provenance', {}).get('source', 'unknown')}\n"
        f"provenance_commit: {audit.get('provenance', {}).get('git_commit_short', '')}\n"
        f"llm_error: {str(audit.get('llm_error', False)).lower()}\n"
    )
    final_markdown = final_markdown + audit_block

    required = REQUIRED_BLOCKS.get(level, [])
    missing = [b for b in required if b not in final_markdown]
    loss_pct = round(len(missing) / len(required) * 100, 1) if required else 0.0
    completeness = {
        "level": level,
        "required_count": len(required),
        "missing": missing,
        "missing_count": len(missing),
        "loss_pct": loss_pct,
        "material_complete": not truncated,
        "threshold": LOSS_THRESHOLD,
        "llm_error": bool(llm_error),
        "verdict": (
            "ERROR" if llm_error
            else ("ACCEPTABLE" if loss_pct <= LOSS_THRESHOLD else "INCOMPLETE")
        ),
    }

    if verbose:
        print(f"[Completeness] level={level}, loss_pct={loss_pct}%, "
              f"missing={len(missing)}, verdict={completeness['verdict']}")
        print()

    completeness_block = (
        "\n\n[COMPLETENESS]\n"
        f"level: {level}\n"
        f"required: {len(required)}\n"
        f"missing: {missing}\n"
        f"loss_pct: {loss_pct}%\n"
        f"material_complete: {completeness.get('material_complete', not truncated)}\n"
        f"verdict: {completeness['verdict']}\n"
    )
    final_markdown = final_markdown + completeness_block
    final_markdown = final_markdown + format_runbook_md(audit)

    result = {
        "session_id": session_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "filename": filename,
        "material_size": len(material),
        "stage0": stage0,
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3,
        "stage4": stage4, "stage4_5": stage4_5 if "stage4_5" in locals() else {},
        "audit": audit,
        "completeness": completeness,
        "critique_verdict": audit["critique_verdict"],
        "cost_usd": sum_stage_costs([stage0, stage1, stage2, stage3, stage4]),
        "final_markdown": final_markdown,
    }

    add_entry({
        "session_id": session_id,
        "filename": filename,
        "level": level,
        "route": route,
        "material_size": len(material),
        "verdict": audit["critique_verdict"],
        "pii_detected": audit["pii_detected"],
        "material_hash": audit["material_hash"],
    })

    apply_baseline(
        result,
        baseline_path=baseline_path,
        save_baseline_path=save_baseline_path,
        filename=filename,
        verbose=verbose,
    )

    _bs = result.get("baseline_stats") or {}
    if _bs.get("baseline_used") or _bs.get("baseline_saved"):
        _baseline_lines = ["\n\n[BASELINE]"]
        if _bs.get("baseline_saved"):
            _baseline_lines.append(f"baseline_saved: {_bs.get('baseline_saved_count', 0)}")
        if _bs.get("baseline_used"):
            _baseline_lines.append("baseline_used: true")
            _baseline_lines.append(f"baseline_new: {_bs.get('baseline_new', 0)}")
            _baseline_lines.append(f"baseline_known: {_bs.get('baseline_known', 0)}")
        final_markdown += "\n".join(_baseline_lines)
        result["final_markdown"] = final_markdown

    result_file = DATA_DIR / f"result_{session_id}.json"
    result_file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if verbose:
        print("=== Pipeline завершён ===")
        print(f"Результат: {result_file}")
        print()

    log.info(
        "pipeline_done",
        session_id=session_id,
        level=level,
        duration_ms=round((time.time() - _pipeline_start) * 1000, 2),
    )

    return result


async def run_pipeline_async(material: str, filename: str, verbose: bool = False, api_key: str | None = None,
                              session_suffix: str = "",
                              baseline_path: str = None,
                              save_baseline_path: str = None,
                              static_only: bool = False) -> dict:
    """Async pipeline.

    ``static_only``: skip every LLM stage and report what the built-in rule engine
    (src.tools.static_scan) found. Used when the visitor brought no LLM key.
    """
    # D0 fast path (v7.4.4) -- async
    _d0, _d0_reason = _is_d0(material)
    if _d0:
        _d0_sid = f"sess-{datetime.now(UTC).strftime('%Y-%m-%d-%H%M%S')}-{uuid.uuid4().hex[:8]}{session_suffix}"
        return {
            'session_id': _d0_sid,
            'final_markdown': f'[ECHO] Material: {_d0_reason} (D0, no LLM)',
            'audit': {
                'material_hash': compute_hash(material),
                'material_hash_full': compute_hash(material),
                'pii_detected': False,
                'compliance_flags': [],
                'compliance_controls': {},
                'compliance_standards': [],
                'critique_verdict': 'SAFE',
                'risk_verdict': 'SAFE',
                'cwe_ids': [],
                'owasp_categories': [],
                'exploitability': {'reachable': False, 'auth_required': False, 'blast_radius': 'none', 'exploit_path': []},
                'level': 'D0',
                'd0_reason': _d0_reason,
                'session_id': _d0_sid,
            },
            'stage0': {'level': 'D0', 'reason': _d0_reason},
            'stage1': None, 'stage2': None, 'stage3': None, 'stage4': None,
        }

    truncated = False
    original_size = len(material)
    _full_material = material   # the static scan sees the whole upload, the LLM only MAX_CHARS
    session_id = f"sess-{datetime.now(UTC).strftime('%Y-%m-%d-%H%M%S')}-{uuid.uuid4().hex[:8]}{session_suffix}"
    material_hash_full = compute_hash(material, context=f"{filename}:{session_id}")
    # v7.2: #1 context_thread (async)
    context_thread = {
        "material_hash": material_hash_full,
        "metrics": {},
        "cwe_found": [],
        "evidence": {"python_run": False, "tests_run": False, "ast_parsed": False},
        "decisions": {"level": None, "priority": None, "confidence": None, "fix_class": None},
        "assumptions": [],
        "open_questions": [],
        "checked": [],
        "not_found": [],
        "negative_evidence": [],
    }
    if original_size > MAX_CHARS:
        material = material[:MAX_CHARS]
        truncated = True

    from src.pipeline.async_stages import (
        async_stage0_orchestrator, async_stage1_scanner, async_stage2_analyst,
        async_stage3_researcher, async_stage4_synthesizer, async_stage5_transmitter,
    )
    material_original = material
    material, redaction_map = redact_pii(material)
    if redaction_map:
        original_audit_pii = detect_pii(material_original)
        original_audit_compliance = detect_compliance(material_original, original_audit_pii)
    else:
        original_audit_pii = {}
        original_audit_compliance = []

    # Built-in rule engine: deterministic, no LLM, scans the submitted text itself.
    _sast_result = await asyncio.get_running_loop().run_in_executor(
        None, scan_material, _full_material, filename)
    _sca_result = None
    if static_only:
        level = "STATIC"
        route = ["static"]
        research_first = False
        stage0 = {"level": level, "route": route, "mode": "static", "session_id": session_id}
        stage1, stage2, stage3, stage4 = {}, {}, None, {}
        final_markdown = render_static_md(
            _sast_result, filename,
            note=("No LLM key was supplied, so only the built-in rule engine ran. "
                  "Choose a provider and add your key for the full six-stage LLM analysis."))
    else:
        stage0 = await async_stage0_orchestrator(material, filename)
        if isinstance(stage0, dict):
            stage0["session_id"] = session_id
        route = stage0.get("route", [])
        level = stage0.get("level", "D3")
        research_first = stage0.get("research_first", False)
        stage1 = await async_stage1_scanner(material, {"stage0": stage0})
        # v7.2: #1 context_thread (async, after stage1)
        context_thread["metrics"] = stage1.get("metrics", {}) if isinstance(stage1, dict) else {}
        context_thread["evidence"]["python_run"] = True
        context_thread["evidence"]["ast_parsed"] = True
        stage2 = await async_stage2_analyst(material, {"stage0": stage0, "stage1": stage1})
        # v7.3.11: self-adversarial red team (async)
        _stage2_5 = {"stage0": stage0, "stage1": stage1, "stage2": stage2}
        stage2_5 = _stage2_5  # placeholder (async red team optional; skip to keep cost low)
        stage3 = None
        if research_first:
            stage3 = await async_stage3_researcher(
                material, {"stage0": stage0, "stage1": stage1, "stage2": stage2})
        context_4 = {"stage0": stage0, "stage1": stage1, "stage2": stage2, "stage2_5": stage2_5 if "stage2_5" in locals() else {}}
        if stage3:
            context_4["stage3"] = stage3
        stage4 = await async_stage4_synthesizer(material, context_4)
        context_5 = {"stage0": stage0, "stage1": stage1, "stage2": stage2, "stage4": stage4}
        if stage3:
            context_5["stage3"] = stage3
        final_markdown = await async_stage5_transmitter(material, context_5)
        final_markdown = strip_llm_audit_blocks(final_markdown)
        final_markdown = sanitize_session_id(final_markdown, session_id)
        if _sast_result.get("total_findings"):
            final_markdown += "\n\n" + render_static_md(
                _sast_result, filename, heading="Static analysis (built-in rules, no LLM)")
    llm_error = (
        llm_error_of(stage0) or llm_error_of(stage2) or llm_error_of(stage4)
        or llm_error_of(final_markdown) or ""
    )
    if llm_error:
        final_markdown = LLM_UNAVAILABLE_BANNER.format(error=llm_error.strip()[:600]) + final_markdown
    force_emergency = bool(stage0.get('force_emergency', False))
    _escalation = _safe_escalation_note(stage4)

    audit = run_audit(material_original, session_id, truncated=truncated, original_size=original_size, material_hash_full=material_hash_full, force_emergency=force_emergency, context=f"{filename}:{session_id}", redaction_map=redaction_map, sast_result=_sast_result if "_sast_result" in dir() else None, sca_result=_sca_result if "_sca_result" in dir() else None, web_search_queries=(stage2.get("_web_search", {}) or {}).get("queries", []) if "stage2" in dir() else [], escalation_level=_safe_escalation_note(stage4) if "stage4" in dir() else "", stage2_result=stage2 if "stage2" in dir() else None, final_markdown=final_markdown, llm_error=llm_error, context_thread=context_thread, analysis_mode="static" if static_only else "llm")
    final_markdown += (
        "\n\n[AUDIT_TRAIL]\n"
        f"generator: Vishap {__version__}\n"
        f"audit_id: {audit['audit_id']}\n"
        f"material_hash: {audit['material_hash']}\n"
        f"material_hash_full: {audit.get('material_hash_full', audit['material_hash'])}\n"
        f"pii_detected: {str(audit['pii_detected']).lower()}\n"
        f"compliance_flags: {audit['compliance_flags']}\n"
        f"compliance_controls: {audit.get('compliance_controls', {})}\n"
        f"compliance_standards: {audit.get('compliance_standards', [])}\n"
        f"critique_verdict: {audit['critique_verdict']}\n"
        f"risk_verdict: {audit.get('risk_verdict', 'SAFE')}\n"
        f"cwe_ids: {audit.get('cwe_ids', [])}\n"
        f"owasp_categories: {audit.get('owasp_categories', [])}\n"
        f"exploitability_reachable: {audit.get('exploitability', {}).get('reachable', False)}\n"
        f"exploitability_auth_required: {audit.get('exploitability', {}).get('auth_required', False)}\n"
        f"exploitability_blast_radius: {audit.get('exploitability', {}).get('blast_radius', 'none')}\n"
        f"exploitability_source_count: {audit.get('exploitability', {}).get('source_count', 0)}\n"
        f"exploitability_path: {audit.get('exploitability', {}).get('exploit_path', [])}\n"
        f"dataflow_path: {audit.get('dataflow', {}).get('path', [])}\n"
        f"dataflow_source_count: {audit.get('dataflow', {}).get('source_count', 0)}\n"
        f"anomaly_verdict: {audit.get('anomaly', {}).get('verdict', 'NORMAL')}\n"
        f"anomaly_count: {audit.get('anomaly', {}).get('count', 0)}\n"
        f"anomaly_method: {audit.get('anomaly', {}).get('method', 'none')}\n"
        f"anomaly_top: {audit.get('anomaly', {}).get('anomalies', [])[:3]}\n"
        f"provenance_source: {audit.get('provenance', {}).get('source', 'unknown')}\n"
        f"provenance_commit: {audit.get('provenance', {}).get('git_commit_short', '')}\n"
        f"llm_error: {str(audit.get('llm_error', False)).lower()}\n"
    )
    required = REQUIRED_BLOCKS.get(level, [])
    missing = [b for b in required if b not in final_markdown]
    loss_pct = round(len(missing) / len(required) * 100, 1) if required else 0.0
    completeness = {"level": level, "required_count": len(required), "missing": missing,
                    "missing_count": len(missing), "loss_pct": loss_pct,
                    "material_complete": not truncated,
                    "threshold": LOSS_THRESHOLD,
                    "llm_error": bool(llm_error),
                    "verdict": "ERROR" if llm_error else ("ACCEPTABLE" if loss_pct <= LOSS_THRESHOLD else "INCOMPLETE")}
    final_markdown += (
        "\n\n[COMPLETENESS]\n"
        f"level: {level}\nrequired: {len(required)}\nmissing: {missing}\n"
        f"loss_pct: {loss_pct}%\n"
        f"material_complete: {completeness.get('material_complete', not truncated)}\n"
        f"verdict: {completeness['verdict']}\n"
    )
    final_markdown += format_runbook_md(audit)
    result = {"session_id": session_id, "timestamp": datetime.now(UTC).isoformat(),
              "mode": "static" if static_only else "llm",
              "filename": filename, "material_size": len(material), "stage0": stage0,
              "stage1": stage1, "stage2": stage2, "stage3": stage3, "stage4": stage4,
              "stage4_5": stage4_5 if "stage4_5" in locals() else {},
              "audit": audit, "completeness": completeness,
              "cost_usd": sum_stage_costs([stage0, stage1, stage2, stage3, stage4]),
              "final_markdown": final_markdown}
    if not static_only:   # a rules-only result must never be served later as the cached LLM answer
        add_entry({"session_id": session_id, "filename": filename, "level": level,
                   "route": route, "material_size": len(material),
                   "verdict": audit["critique_verdict"], "pii_detected": audit["pii_detected"],
                   "material_hash": audit["material_hash"]})
    apply_baseline(
        result,
        baseline_path=baseline_path,
        save_baseline_path=save_baseline_path,
        filename=filename,
        verbose=verbose,
    )

    _bs = result.get("baseline_stats") or {}
    if _bs.get("baseline_used") or _bs.get("baseline_saved"):
        _baseline_lines = ["\n\n[BASELINE]"]
        if _bs.get("baseline_saved"):
            _baseline_lines.append(f"baseline_saved: {_bs.get('baseline_saved_count', 0)}")
        if _bs.get("baseline_used"):
            _baseline_lines.append("baseline_used: true")
            _baseline_lines.append(f"baseline_new: {_bs.get('baseline_new', 0)}")
            _baseline_lines.append(f"baseline_known: {_bs.get('baseline_known', 0)}")
        final_markdown += "\n".join(_baseline_lines)
        result["final_markdown"] = final_markdown

    result_file = DATA_DIR / f"result_{session_id}.json"
    result_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Путь к файлу")
    ap.add_argument("--quiet", action="store_true", help="Без логов")
    args = ap.parse_args()

    path = Path(args.input)
    if not path.exists():
        print(f"ERROR: файл не найден: {path}")
        sys.exit(1)

    material = path.read_text(encoding="utf-8", errors="replace")
    result = run_pipeline(material, path.name, verbose=not args.quiet)

    if not args.quiet:
        print("=" * 60)
        print("ФИНАЛЬНЫЙ MARKDOWN:")
        print("=" * 60)
        print(result["final_markdown"][:3000])


if __name__ == "__main__":
    main()