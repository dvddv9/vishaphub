"""Declared file recognition and analysis depth for the deterministic scanner.

Being recognized is not the same as having comprehensive rules or benchmark evidence.
Keep those distinctions machine-readable for the CLI and hub's language endpoint.
"""
from __future__ import annotations

LANGUAGE_EXTENSIONS = {
    ".py": "python", ".pyw": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".cjs": "javascript", ".ts": "typescript", ".tsx": "typescript", ".java": "java", ".c": "c", ".h": "c",
    ".cc": "cpp", ".cpp": "cpp", ".hpp": "cpp", ".go": "go", ".php": "php", ".rb": "ruby", ".rs": "rust",
    ".cs": "csharp", ".kt": "kotlin", ".kts": "kotlin", ".swift": "swift", ".scala": "scala", ".sc": "scala",
    ".tf": "terraform", ".tfvars": "terraform", ".hcl": "terraform", ".yaml": "yaml", ".yml": "yaml",
    ".sh": "shell", ".bash": "shell", ".sql": "sql", ".log": "log",
}

REPOSITORY_EXTENSIONS = frozenset(ext for ext in LANGUAGE_EXTENSIONS if ext != ".log")
DOCKERFILE_NAMES = frozenset({"dockerfile"})

_CAPABILITIES = {
    "python": {"category": "programming", "static_analysis": "pattern rules + AST intrafile taint + bounded interfile taint"},
    "javascript": {"category": "programming", "static_analysis": "pattern rules + source/sink pattern candidates"},
    "typescript": {"category": "programming", "static_analysis": "pattern rules + source/sink pattern candidates"},
    "java": {"category": "programming", "static_analysis": "pattern rules"},
    "c": {"category": "programming", "static_analysis": "pattern rules"},
    "cpp": {"category": "programming", "static_analysis": "pattern rules"},
    "go": {"category": "programming", "static_analysis": "pattern rules"},
    "php": {"category": "programming", "static_analysis": "pattern rules"},
    "ruby": {"category": "programming", "static_analysis": "generic rules + shell interpolation rule"},
    "rust": {"category": "programming", "static_analysis": "generic rules + shell invocation rule"},
    "csharp": {"category": "programming", "static_analysis": "generic rules + dynamic process rule"},
    "kotlin": {"category": "programming", "static_analysis": "generic rules + dynamic process rule"},
    "swift": {"category": "programming", "static_analysis": "generic rules + shell launch rule"},
    "scala": {"category": "programming", "static_analysis": "generic rules + shell invocation rule"},
    "sql": {"category": "query", "static_analysis": "pattern rules"},
    "shell": {"category": "command", "static_analysis": "generic rules"},
    "terraform": {"category": "infrastructure", "static_analysis": "pattern rules"},
    "yaml": {"category": "configuration", "static_analysis": "pattern rules"},
    "dockerfile": {"category": "configuration", "static_analysis": "pattern rules"},
    "log": {"category": "operations", "static_analysis": "attack-pattern scan; not source-code analysis"},
}


def capabilities() -> dict[str, dict[str, str]]:
    """Return a copy so callers cannot mutate the declared capability table."""
    return {name: dict(value) for name, value in _CAPABILITIES.items()}
