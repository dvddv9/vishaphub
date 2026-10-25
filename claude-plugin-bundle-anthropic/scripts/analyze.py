# -*- coding: utf-8 -*-
"""Vishap MCP stdio server — Claude API (Anthropic SDK)."""
import os
from fastmcp import FastMCP
from anthropic import Anthropic

mcp = FastMCP("Vishap Claude")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")


@mcp.tool(
    name="vishap_analyze",
    title="Vishap Security Analysis",
    description="Analyze code, spec, logs, or config for security risks (SQLi, XSS, RCE). Read-only.",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
def vishap_analyze(material: str, filename: str) -> str:
    """Analyze code / text for security risks via Claude API (Anthropic SDK)."""
    if not ANTHROPIC_API_KEY:
        return "Error: ANTHROPIC_API_KEY is not set. Configure it in extension settings."

    prompt = (
        "You are a security analyzer. Analyze the following material for security risks.\n"
        f"Filename: {filename}\n"
        "Material:\n"
        "```\n"
        f"{material}\n"
        "```\n"
        "Return a structured Markdown report:\n"
        "- Summary (1-2 lines)\n"
        "- Critical risks (with CWE, line numbers, exploitability)\n"
        "- Recommended fixes (parameterized queries, input validation, etc.)\n"
        "- STRIDE threat model (if applicable)\n"
    )

    try:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=8192,
            system="You are a security analyzer. Return structured Markdown.",
            messages=[{"role": "user", "content": prompt}],
        )
        # content — список блоков; берём текст
        parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        return "\n".join(parts) if parts else "(empty response)"
    except Exception as e:
        return f"Anthropic error: {e}"


if __name__ == "__main__":
    mcp.run()
