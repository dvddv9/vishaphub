# -*- coding: utf-8 -*-
"""
Tavily Web Search wrapper для Vishap.
Используется в Stage 2 (Analyst) для поиска свежих CVE, патчей, best practices.

ENABLE_WEB_SEARCH контролирует, выполняется ли поиск.
Если ключ не задан или поиск отключён — search() возвращает {"error": "..."}.
"""
import os
import time
import logging
import httpx

from src.config import (
    TAVILY_API_KEY,
    ENABLE_WEB_SEARCH,
    SEARCH_MAX_RESULTS,
    SEARCH_DEPTH,
    CUSTOM_LLM_KEY,
)

logger = logging.getLogger(__name__)

_client = None


# ============ DeepSeek Search / Fetch (v7.3) ============
DEEPSEEK_TOOLS_URL = os.getenv("DEEPSEEK_SEARCH_URL", "https://api.deepseek.com/v1/tools")


def _deepseek_key() -> str:
    """DeepSeek key for Search/Fetch.

    Priority:
      1. DEEPSEEK_SEARCH_KEY (explicit)
      2. DEEPSEEK_API_KEY
      3. CUSTOM_LLM_KEY (only if CUSTOM_LLM_URL points to api.deepseek.com)
    """
    explicit = os.getenv("DEEPSEEK_SEARCH_KEY", "").strip()
    if explicit:
        return explicit
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if deepseek_key:
        return deepseek_key
    from src.llm.client import require_user_key
    if require_user_key():
        return ""  # user-key-only mode: never spend the operator's LLM key
    llm_url = os.getenv("CUSTOM_LLM_URL", "").strip().lower()
    if "deepseek.com" in llm_url and CUSTOM_LLM_KEY:
        return CUSTOM_LLM_KEY
    return ""


def _deepseek_search(query: str, count: int = 5) -> dict:
    """POST /v1/tools/search (DeepSeek)."""
    key = _deepseek_key()
    if not key:
        return {"error": "no_deepseek_key", "query": query}
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{DEEPSEEK_TOOLS_URL}/search",
                headers={"Authorization": f"Bearer {key}"},
                json={"query": query, "count": min(count, 50), "need_content": False},
            )
            r.raise_for_status()
            data = r.json()
            return {
                "query": query,
                "results": [
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": item.get("summary") or item.get("snippet", ""),
                        "score": item.get("rerank_score", 0),
                    }
                    for item in data.get("results", [])
                ],
            }
    except Exception as e:
        logger.warning(f"[DeepSeekSearch] '{query}' failed: {e}")
        return {"error": str(e), "query": query}


def _deepseek_fetch(url: str) -> dict:
    """POST /v1/tools/fetch (DeepSeek) -> Markdown content."""
    key = _deepseek_key()
    if not key:
        return {"error": "no_deepseek_key", "url": url}
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{DEEPSEEK_TOOLS_URL}/fetch",
                headers={"Authorization": f"Bearer {key}"},
                json={"url": url},
            )
            r.raise_for_status()
            data = r.json()
            return {"url": url, "title": data.get("title", ""), "content": data.get("content", "")}
    except Exception as e:
        logger.warning(f"[DeepSeekFetch] '{url}' failed: {e}")
        return {"error": str(e), "url": url}



def _get_client():
    """Lazy-init Tavily client. None if disabled or no key."""
    global _client
    if _client is None:
        if not ENABLE_WEB_SEARCH:
            return None
        if not TAVILY_API_KEY:
            logger.warning("[WebSearch] TAVILY_API_KEY not set — search disabled")
            return None
        try:
            from tavily import TavilyClient
            _client = TavilyClient(api_key=TAVILY_API_KEY)
            logger.info("[WebSearch] Tavily client initialized")
        except Exception as e:
            logger.error(f"[WebSearch] Failed to init Tavily: {e}")
            return None
    return _client


def is_enabled() -> bool:
    """True if any search provider is available (Tavily or DeepSeek)."""
    if not ENABLE_WEB_SEARCH:
        return False
    return bool(TAVILY_API_KEY) or bool(_deepseek_key())


def search(query: str) -> dict:
    """
    Выполнить веб-поиск через Tavily.

    Returns:
        dict: {"results": [...], "query": "..."} при успехе.
              {"error": "...", "query": "..."} при ошибке.
    """
    if not is_enabled():
        return {"error": "web_search_disabled", "query": query}

    # 1. Tavily (if key)
    if TAVILY_API_KEY:
        client = _get_client()
        if client:
            try:
                response = client.search(
                    query=query,
                    max_results=SEARCH_MAX_RESULTS,
                    search_depth=SEARCH_DEPTH,
                )
                response["query"] = query
                return response
            except Exception as e:
                logger.warning(f"[WebSearch] Tavily '{query}' failed: {e} — fallback to DeepSeek")

    # 2. DeepSeek Search (fallback)
    if _deepseek_key():
        return _deepseek_search(query, count=SEARCH_MAX_RESULTS)

    return {"error": "no_search_provider", "query": query}


def search_many(queries: list, delay: float = 1.0) -> list:
    """
    Выполнить несколько запросов с задержкой (rate limit free tier).

    Args:
        queries: список поисковых запросов
        delay: секунд между запросами (free tier = 1 req/sec)

    Returns:
        list[dict]: список результатов (только успешные).
    """
    results = []
    for i, q in enumerate(queries):
        r = search(q)
        if "error" not in r:
            results.append(r)
        else:
            logger.warning(f"[WebSearch] query {i+1}/{len(queries)} failed: {r.get('error')}")
        if i < len(queries) - 1:
            time.sleep(delay)
    return results