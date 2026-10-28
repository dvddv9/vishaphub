# -*- coding: utf-8 -*-
"""
Асинхронные стадии pipeline Vishap.

Полная копия stages.py, но через async_chat().
Логика (parse_json_response, retry, _meta) — идентична.
"""
from src.llm.async_client import async_chat
from src.pipeline.prompts import build_prompt
from src.pipeline.stages import parse_json_response
from src.config import MAX_TOKENS, MAX_TOKENS_STAGE4


async def async_run_stage(stage_name: str, prompt_name: str, material: str,
                          context: dict | None = None,
                          temperature: float = 0.0,
                          max_tokens: int | None = None,
                          retry_on_json_fail: bool = True,
                          web_search_results: list | None = None) -> dict:
    if max_tokens is None:
        max_tokens = MAX_TOKENS

    system, user = build_prompt(prompt_name, material, context, web_search_results)

    result = await async_chat(system, user, temperature=temperature, max_tokens=max_tokens)
    parsed = parse_json_response(result["text"])

    if retry_on_json_fail and "_error" in parsed and parsed["_error"] == "JSON parse failed":
        print(f"  [!] {stage_name}: JSON parse failed, retry...")
        retry_user = (
            user
            + "\n\n## IMPORTANT\n\n"
            + "Return only valid JSON without Markdown, without comments, "
            + "without any text before or after. Only { ... }."
        )
        result = await async_chat(system, retry_user, temperature=temperature, max_tokens=max_tokens)
        parsed = parse_json_response(result["text"])

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
    return parsed


async def async_stage0_orchestrator(material: str, filename: str) -> dict:
    return await async_run_stage(
        stage_name="stage0_orchestrator",
        prompt_name="00_orchestrator",
        material=f"# File: {filename}\n\n{material}",
        temperature=0.0,
        max_tokens=2000,
    )


async def async_stage1_scanner(material: str, context: dict) -> dict:
    return await async_run_stage(
        stage_name="stage1_scanner",
        prompt_name="01_scanner",
        material=material,
        context=context,
        temperature=0.0,
    )


async def async_stage2_analyst(material: str, context: dict,
                                search_queries: list | None = None) -> dict:
    """Async Stage 2: Analyst с опциональным web search."""
    from src.pipeline.stages import _generate_default_queries
    from src.tools.web_search import search_many, is_enabled as web_search_enabled
    from src.config import ENABLE_WEB_SEARCH

    web_search_results = None
    queries_used = []

    if ENABLE_WEB_SEARCH and web_search_enabled():
        queries_used = search_queries or _generate_default_queries(material)
        if queries_used:
            print(f"  [Web Search] {len(queries_used)} queries...")
            web_search_results = search_many(queries_used)
            print(f"  [Web Search] {len(web_search_results)} results")

    result = await async_run_stage(
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
    await _async_apply_multipass(result, material, context)
    return result


async def _async_logic_runner(text: str, ctx: dict) -> dict:
    from src.pipeline.multipass import MAX_TOKENS as LOGIC_MAX_TOKENS
    return await async_run_stage(stage_name="stage2_logic", prompt_name="02b_logic", material=text,
                                 context=ctx, temperature=0.0, max_tokens=LOGIC_MAX_TOKENS)


async def _async_apply_multipass(result: dict, material: str, context: dict | None) -> None:
    """Async twin of stages._apply_multipass: chunks run concurrently, a failure never breaks stage 2."""
    try:
        from src.pipeline import multipass
        if not multipass.enabled() or not isinstance(result, dict) or result.get("mode") == "error":
            return
        from src.tools.static_scan import detect_language
        sec = result.get("security")
        existing = sec.get("findings") if isinstance(sec, dict) and isinstance(sec.get("findings"), list) else []
        added, info = await multipass.arun_logic_passes(
            material, detect_language("", material), _async_logic_runner,
            hint=(context or {}).get("static_checklist"), existing=existing)
        multipass.apply_to_stage2(result, added, info)
    except Exception as e:   # noqa: BLE001
        if isinstance(result, dict):
            result["_multipass"] = {"error": f"{type(e).__name__}: {e}"}


async def async_stage3_researcher(material: str, context: dict) -> dict:
    return await async_run_stage(
        stage_name="stage3_researcher",
        prompt_name="03_researcher",
        material=material,
        context=context,
        temperature=0.3,
    )


async def async_stage4_synthesizer(material: str, context: dict) -> dict:
    return await async_run_stage(
        stage_name="stage4_synthesizer",
        prompt_name="04_synthesizer",
        material=material,
        context=context,
        temperature=0.0, 
        max_tokens=MAX_TOKENS_STAGE4,
    )


async def async_stage5_transmitter(material: str, context: dict) -> str:
    system, user = build_prompt("05_transmitter", material, context)
    result = await async_chat(system, user, temperature=0.0, max_tokens=MAX_TOKENS)
    return result["text"]