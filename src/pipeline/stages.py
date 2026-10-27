# -*- coding: utf-8 -*-
"""
Стадии pipeline Vishap.
v2: улучшенный JSON-парсинг + max_tokens из config.
"""
import json
import re
from src.llm.client import chat as llm_chat
from src.pipeline.prompts import build_prompt, wrap_material
from src.config import MAX_TOKENS, MAX_TOKENS_STAGE4, ENABLE_WEB_SEARCH
from src.tools.web_search import search_many, is_enabled as web_search_enabled


def _clean_json_string(text: str) -> str:
    result = []
    in_string = False
    escape = False
    i = 0
    while i < len(text):
        ch = text[i]

        if escape:
            result.append(ch)
            escape = False
            i += 1
            continue

        if ch == "\\":
            result.append(ch)
            escape = True
            i += 1
            continue

        if ch == '"':
            in_string = not in_string
            result.append(ch)
            i += 1
            continue

        if not in_string:
            if ch == "/" and i + 1 < len(text) and text[i + 1] == "/":
                while i < len(text) and text[i] != "\n":
                    i += 1
                continue
            if ch == "/" and i + 1 < len(text) and text[i + 1] == "*":
                i += 2
                while i + 1 < len(text) and not (text[i] == "*" and text[i + 1] == "/"):
                    i += 1
                i += 2
                continue

        result.append(ch)
        i += 1

    return "".join(result)


def _recover_truncated_json(text: str) -> dict | None:
    """v7.3.4: Восстановить обрезанный JSON (DeepSeek-flash игнорирует max_tokens).

    Стратегии:
    1) Закрыть все незакрытые { и [ в правильном порядке.
    2) Обрезать до последнего валидного } и закрыть оставшиеся скобки.
    """
    if not isinstance(text, str):
        return None
    start = text.find("{")
    if start == -1:
        return None
    text = text[start:]

    # Стратегия 1: закрыть незакрытые скобки (в правильном порядке: сначала ], потом })
    # Идём по тексту, считаем стек открытых скобок
    stack = []
    in_string = False
    escape = False
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch == "}":
            if stack and stack[-1] == "{":
                stack.pop()
        elif ch == "]":
            if stack and stack[-1] == "[":
                stack.pop()

    if stack:
        # закрываем в обратном порядке
        closers = ""
        for opener in reversed(stack):
            closers += "]" if opener == "[" else "}"
        try:
            return json.loads(text + closers)
        except json.JSONDecodeError:
            pass

    # Стратегия 2: обрезать до последнего } и закрыть оставшиеся скобки
    for i in range(len(text) - 1, 0, -1):
        if text[i] == "}":
            candidate = text[:i + 1]
            # считаем незакрытые скобки в candidate
            st = []
            in_s = False
            esc = False
            for ch in candidate:
                if esc:
                    esc = False
                    continue
                if ch == "\\":
                    esc = True
                    continue
                if ch == '"':
                    in_s = not in_s
                    continue
                if in_s:
                    continue
                if ch in "{[":
                    st.append(ch)
                elif ch == "}":
                    if st and st[-1] == "{":
                        st.pop()
                elif ch == "]":
                    if st and st[-1] == "[":
                        st.pop()
            if st:
                closers = "".join("]" if o == "[" else "}" for o in reversed(st))
                candidate += closers
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

    return None


def _try_parse(text: str) -> dict | None:
    if not text or not text.strip():
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    cleaned = _clean_json_string(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    no_trailing = re.sub(r",\s*([}\]])", r"\1", cleaned)
    try:
        return json.loads(no_trailing)
    except json.JSONDecodeError:
        pass

    start = no_trailing.find("{")
    end = no_trailing.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(no_trailing[start:end + 1])
        except json.JSONDecodeError:
            pass

    start = no_trailing.find("[")
    end = no_trailing.rfind("]")
    if start >= 0 and end > start:
        try:
            return json.loads(no_trailing[start:end + 1])
        except json.JSONDecodeError:
            pass

    # v7.3.4: recovery для обрезанного JSON
    recovered = _recover_truncated_json(text)
    if recovered is not None:
        return recovered
    return None


def parse_json_response(text: str) -> dict:
    text = text.strip()

    code_block_patterns = [
        r"```json\s*\n?(.*?)\n?```",
        r"```\s*\n?(.*?)\n?```",
    ]
    for pattern in code_block_patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            candidate = match.group(1).strip()
            parsed = _try_parse(candidate)
            if parsed is not None:
                return parsed
            break

    parsed = _try_parse(text)
    if parsed is not None:
        return parsed

    return {
        "_raw": text[:5000],
        "_error": "JSON parse failed",
        "_raw_length": len(text),
    }


def run_stage(stage_name: str, prompt_name: str, material: str,
              context: dict | None = None,
              temperature: float = 0.0,
              max_tokens: int | None = None,
              retry_on_json_fail: bool = True,
              web_search_results: list | None = None) -> dict:
    if max_tokens is None:
        max_tokens = MAX_TOKENS

    system, user = build_prompt(prompt_name, material, context, web_search_results)

    result = llm_chat(system, user, temperature=temperature, max_tokens=max_tokens)
    parsed = parse_json_response(result["text"])

    # parse_json_response may return None / True / 42 for a bare JSON scalar, so the
    # dict guard has to run before the membership test (`"_error" in None` raised).
    if not isinstance(parsed, dict):
        parsed = {"_raw": parsed, "_error": "expected dict"}

    if retry_on_json_fail and parsed.get("_error") == "JSON parse failed":
        print(f"  [!] {stage_name}: JSON parse failed, retry...")
        retry_user = (
            user
            + "\n\n## ВАЖНО\n\n"
            + "Return ONLY valid JSON without Markdown, without comments, "
            + "without any text before or after. Only { ... }."
        )
        result = llm_chat(system, retry_user, temperature=temperature, max_tokens=max_tokens)
        parsed = parse_json_response(result["text"])
        if not isinstance(parsed, dict):
            parsed = {"_raw": parsed, "_error": "expected dict"}

    from src.pipeline.cost import estimate_cost

    parsed["_meta"] = {
        "stage": stage_name,
        "tokens_in": result["tokens_in"],
        "tokens_out": result["tokens_out"],
        "model": result["model"],
        "mode": result["mode"],
        "json_ok": "_error" not in parsed,
        "cost_usd": estimate_cost(
            result["model"], result["tokens_in"], result["tokens_out"]
        ),
    }
    if "_error" in parsed:
        parsed["mode"] = "error"
        parsed["_error_text"] = f"[LLM error] {stage_name}: {parsed['_error']}"
    return parsed




def stage0_orchestrator(material: str, filename: str) -> dict:
    return run_stage(
        stage_name="stage0_orchestrator",
        prompt_name="00_orchestrator",
        material=f"# File: {filename}\n\n{material}",
        temperature=0.0,
        max_tokens=4000,
    )


def stage1_scanner(material: str, context: dict) -> dict:
    return run_stage(
        stage_name="stage1_scanner",
        prompt_name="01_scanner",
        material=material,
        context=context,
        temperature=0.0,
    )


def stage1_5_translator(material: str, context: dict, async_mode: bool = False, verbose: bool = False) -> dict:
    """v7.3.13: cross-language translator (one DeepSeek, all languages).

    Input:  stage1 (scanner) findings.
    Output: {"cross_language": [...], "mode": "custom"}

    Prompt: "Here is SQLi in Python. How does it look in Java / C / Go?
             Find analogs in the material."

    Enabled by VISHAP_TRANSLATOR=1 (default: off).
    """
    import os
    import json as _json
    if os.getenv("VISHAP_TRANSLATOR", "0").strip() not in ("1", "true", "yes"):
        return {"cross_language": [], "mode": "skipped", "reason": "VISHAP_TRANSLATOR!=1"}

    stage1 = context.get("stage1") or {}
    findings = stage1.get("findings", []) if isinstance(stage1, dict) else []
    if not findings:
        return {"cross_language": [], "mode": "skipped", "reason": "no stage1 findings"}

    findings_json = _json.dumps(findings[:10], ensure_ascii=False)[:4000]
    system = (
        "You are a cross-language security translator. "
        "You will receive security findings (JSON) from one language. "
        "Your task: for each finding, describe the SAME PATTERN in other languages "
        "(Java, C, Go, JavaScript/TypeScript). "
        "Look for analogs in the material. "
        "Return ONLY valid JSON: "
        '{"cross_language": [{"cwe": "CWE-XXX", "pattern": "...", "languages": ["Java", "C", "Go"], '
        '"analogs": ["...", "..."], "confidence": "high|medium|low"}]}'
    )
    user = (
        "Findings (JSON):\n" + findings_json + "\n\n"
        "Material (first 3000 chars):\n" + wrap_material(material, 3000)
    )

    try:
        if async_mode:
            from src.llm.async_client import async_chat as llm_achat
            result = llm_achat(system, user)
        else:
            from src.llm.client import chat as llm_chat
            result = llm_chat(system, user, temperature=0.2, max_tokens=1200)
        text = result.get("text", "") or ""
        try:
            parsed = _json.loads(text)
        except _json.JSONDecodeError:
            try:
                from src.pipeline.stages import parse_json_response
                parsed = parse_json_response(text)
            except Exception:
                parsed = {}
        cross = parsed.get("cross_language", []) if isinstance(parsed, dict) else []
        return {
            "cross_language": cross if isinstance(cross, list) else [],
            "mode": "custom",
            "tokens_in": result.get("tokens_in", 0),
            "tokens_out": result.get("tokens_out", 0),
        }
    except Exception as e:
        return {"cross_language": [], "mode": "error", "error": str(e)}


def stage2_analyst(material: str, context: dict,
                   search_queries: list | None = None) -> dict:
    """Stage 2: Analyst с опциональным web search."""
    web_search_results = None
    queries_used = []

    if ENABLE_WEB_SEARCH and web_search_enabled():
        queries_used = search_queries or _generate_default_queries(material)
        if queries_used:
            print(f"  [Web Search] {len(queries_used)} queries...")
            web_search_results = search_many(queries_used)
            print(f"  [Web Search] {len(web_search_results)} results")

    result = run_stage(
        stage_name="stage2_analyst",
        prompt_name="02_analyst",
        material=material,
        context=context,
        temperature=0.0,
        web_search_results=web_search_results,
    )

    result["_web_search"] = {
        "used": bool(web_search_results),
        "queries": queries_used,
        "credits": len(queries_used),
    }
    return result


def _generate_default_queries(material: str) -> list:
    """Простая эвристика — 1-3 запроса из материала."""
    queries = []
    m = material.lower()

    if "sql" in m or "cwe-89" in m:
        queries.append("SQL injection prevention best practices 2026")
    if "xss" in m or "cwe-79" in m:
        queries.append("XSS prevention Content Security Policy best practices")
    if "buffer overflow" in m or "cwe-122" in m:
        queries.append("heap buffer overflow mitigation best practices")
    if "kafka" in m:
        queries.append("Kafka at-least-once deduplication best practices")
    if "redis" in m:
        queries.append("Redis idempotency anti-patterns")
    if "gdpr" in m:
        queries.append("GDPR Article 17 right to erasure implementation")
    if "pci" in m:
        queries.append("PCI DSS requirement 6.5 secure coding")

    if not queries:
        queries.append("recent CVEs and security best practices")

    return queries[:3]


def stage2_5_redteam(material: str, context: dict, async_mode: bool = False, verbose: bool = False) -> dict:
    """v7.3.11: self-adversarial red team (one DeepSeek, second pass).

    - analyst_json truncated to 4000 chars (LLM context limit).
    - "Не выдумывай" — anti-hallucination.
    - async_mode: uses achat (async_stages) if True.
    - Enabled by VISHAP_REDTEAM=1 (default: off).
    """
    import os
    import json as _json
    if os.getenv("VISHAP_REDTEAM", "0").strip() not in ("1", "true", "yes"):
        return {"missed": [], "critique": "", "mode": "skipped", "reason": "VISHAP_REDTEAM!=1"}

    stage2 = context.get("stage2") or {}
    analyst_json = _json.dumps(
        {"risk_nodes": stage2.get("risk_nodes", []), "security": stage2.get("security", {})},
        ensure_ascii=False,
    )[:4000]

    system = (
        "You are a red team. Here is the Analyst report (JSON):\n" + analyst_json + "\n\n"
        "⚠️ If the report > 4000 tokens — analyze only risk_nodes, not the whole JSON.\n\n"
        "Your task:\n"
        "1. Find what the Analyst MISSED (CWE, edge cases, trust boundaries).\n"
        "2. Do not agree with the Analyst. If it says \"SAFE\" — look for what is wrong.\n"
        "3. Return JSON: {\"missed\": [{\"cwe\": \"...\", \"reason\": \"...\", \"severity\": \"...\"}]}\n\n"
        "⚠️ Do not hallucinate. If unsure — do not include in missed.\n"
        "Return ONLY valid JSON, no markdown, no comments."
    )
    user = "Material (first 3000 chars):\n" + wrap_material(material, 3000)

    try:
        if async_mode:
            from src.llm.async_client import async_chat as llm_achat
            result = llm_achat(system, user)
        else:
            from src.llm.client import chat as llm_chat
            result = llm_chat(system, user, temperature=0.3, max_tokens=1500)
        text = result.get("text", "") or ""
        try:
            parsed = _json.loads(text)
        except _json.JSONDecodeError:
            try:
                from src.pipeline.stages import parse_json_response
                parsed = parse_json_response(text)
            except Exception:
                parsed = {}
        missed = parsed.get("missed", []) if isinstance(parsed, dict) else []
        critique = parsed.get("critique", "") if isinstance(parsed, dict) else ""
        return {
            "missed": missed if isinstance(missed, list) else [],
            "critique": critique,
            "mode": "custom",
            "tokens_in": result.get("tokens_in", 0),
            "tokens_out": result.get("tokens_out", 0),
        }
    except Exception as e:
        return {"missed": [], "critique": "", "mode": "error", "error": str(e)}


def stage3_researcher(material: str, context: dict) -> dict:
    return run_stage(
        stage_name="stage3_researcher",
        prompt_name="03_researcher",
        material=material,
        context=context,
        temperature=0.3,
    )


def stage3_5_tester(material: str, context: dict, async_mode: bool = False, verbose: bool = False) -> dict:
    """v7.3.14: test-first loop (live pytest in sandbox).

    Input:  stage2 (risk_nodes, security).
    Output: {"confirmed": [...], "false_positives": [...], "mode": "custom"}

    For each critical/high risk_node: generate pytest, run in sandbox.
    - pass  -> confirmed (defect is real)
    - fail  -> false_positive (or test is wrong)

    Enabled by VISHAP_TESTER=1 (default: off; RCE risk).
    """
    import os
    if os.getenv("VISHAP_TESTER", "0").strip() not in ("1", "true", "yes"):
        return {"confirmed": [], "false_positives": [], "mode": "skipped", "reason": "VISHAP_TESTER!=1"}

    stage2 = context.get("stage2") or {}
    risk_nodes = stage2.get("risk_nodes", []) if isinstance(stage2, dict) else []
    critical = [
        r for r in risk_nodes
        if isinstance(r, dict) and str(r.get("priority", "")).lower() in ("критично", "critical", "high")
    ]
    if not critical:
        return {"confirmed": [], "false_positives": [], "mode": "skipped", "reason": "no critical risk_nodes"}

    from src.pipeline.sandbox import run_pytest_in_sandbox
    from src.llm.client import chat as llm_chat

    confirmed = []
    false_positives = []
    for rn in critical[:3]:  # limit: max 3 tests
        cwe = rn.get("cwe", "")
        desc = rn.get("node", "") or rn.get("description", "")
        system = (
            "You are a test generator. Write ONE pytest test that reproduces the given defect. "
            "Return ONLY the Python test code (imports + def test_...), no markdown, no comments. "
            "The test must FAIL if the defect is present, PASS if it is fixed."
        )
        user = (
            f"Defect: {cwe} — {desc}\n"
            f"Material (first 2000 chars):\n{wrap_material(material, 2000)}"
        )
        try:
            result = llm_chat(system, user, temperature=0.1, max_tokens=500)
            test_code = (result.get("text") or "").strip()
            # strip markdown fences if any
            if test_code.startswith("```"):
                test_code = test_code.split("```")[1]
                if test_code.startswith("python"):
                    test_code = test_code[6:]
            sandbox = run_pytest_in_sandbox(test_code, timeout=5)
            # The generated test FAILS when the defect is present (see the prompt
            # above), so a non-zero exit means the defect reproduced. Treating a
            # passing test as "confirmed" inverted this: real defects landed in
            # false_positives and a vacuous `assert True` counted as proof.
            if sandbox["ok"]:
                false_positives.append({"cwe": cwe, "test_ok": False, "reason": sandbox["reason"]})
            else:
                confirmed.append({"cwe": cwe, "test_ok": True, "reason": sandbox["reason"]})
        except Exception as e:
            false_positives.append({"cwe": cwe, "test_ok": False, "reason": f"error: {e}"})

    return {
        "confirmed": confirmed,
        "false_positives": false_positives,
        "mode": "custom",
    }


def stage4_synthesizer(material: str, context: dict) -> dict:
    return run_stage(
        stage_name="stage4_synthesizer",
        prompt_name="04_synthesizer",
        material=material,
        context=context,
        temperature=0.0,
        max_tokens=MAX_TOKENS_STAGE4,
    )


def stage4_5_fixer(material: str, context: dict, async_mode: bool = False, verbose: bool = False) -> dict:
    """v7.3.15: fix-loop (LLM writes fix, sandbox verifies).

    Input:  stage4 (options — fixes) + material.
    Output: {"accepted": [...], "rejected": [...], "mode": "custom"}

    For each fix in stage4.options (max 3):
    - LLM writes fixed code
    - sandbox (ruff + pytest + mypy) verifies
    - accepted (no new defects) / rejected (new defects)

    Enabled by VISHAP_FIXER=1 (default: off; RCE risk).
    """
    import os
    if os.getenv("VISHAP_FIXER", "0").strip() not in ("1", "true", "yes"):
        return {"accepted": [], "rejected": [], "mode": "skipped", "reason": "VISHAP_FIXER!=1"}

    stage4 = context.get("stage4") or {}
    options = stage4.get("options", []) if isinstance(stage4, dict) else []
    if not options:
        return {"accepted": [], "rejected": [], "mode": "skipped", "reason": "no stage4 options"}

    from src.pipeline.sandbox import apply_fix_and_verify
    from src.llm.client import chat as llm_chat

    accepted = []
    rejected = []
    for opt in options[:3]:  # limit: max 3 fixes
        if not isinstance(opt, dict):
            continue
        title = opt.get("title", "") or opt.get("name", "")
        fix_desc = opt.get("fix", "") or opt.get("description", "")
        system = (
            "You are a code fixer. Apply the given fix to the material. "
            "Return ONLY the fixed Python code (no markdown, no comments). "
            "The code must be syntactically valid, pass ruff, and not break existing behavior."
        )
        user = (
            f"Fix: {title} — {fix_desc}\n"
            f"Material (first 3000 chars):\n{wrap_material(material, 3000)}"
        )
        try:
            result = llm_chat(system, user, temperature=0.1, max_tokens=1500)
            fixed_code = (result.get("text") or "").strip()
            if fixed_code.startswith("```"):
                fixed_code = fixed_code.split("```")[1]
                if fixed_code.startswith("python"):
                    fixed_code = fixed_code[6:]
            verdict = apply_fix_and_verify(material, fixed_code, timeout=10)
            entry = {
                "title": title,
                "ok": verdict.get("ok"),
                "reason": verdict.get("reason"),
                "ruff_out": (verdict.get("ruff_out") or "")[:300],
                "pytest_out": (verdict.get("pytest_out") or "")[:300],
            }
            if verdict.get("ok"):
                accepted.append(entry)
            else:
                rejected.append(entry)
        except Exception as e:
            rejected.append({"title": title, "ok": False, "reason": f"error: {e}"})

    return {
        "accepted": accepted,
        "rejected": rejected,
        "mode": "custom",
    }


def stage5_transmitter(material: str, context: dict) -> str:
    system, user = build_prompt("05_transmitter", material, context)
    result = llm_chat(system, user, temperature=0.0, max_tokens=MAX_TOKENS)
    return result["text"]




