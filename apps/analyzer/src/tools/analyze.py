#!/usr/bin/env python3
"""
Vishap V5.7 — статический анализ и расчёты.
"""
import argparse
import ast
import json
import re
import sys
from pathlib import Path

try:
    from radon.complexity import cc_visit
    RADON = True
except ImportError:
    RADON = False

try:
    from radon.metrics import mi_visit
    RADON_MI = True
except ImportError:
    RADON_MI = False


def _read_input(path: str) -> str:
    if not path:
        return sys.stdin.read()
    p = Path(path)
    if not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def mode_static(code: str) -> dict:
    if not code.strip():
        return {"empty": True, "note": "input is empty or unreadable"}
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {"error": f"SyntaxError: {e}"}

    functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

    def count_branches(node):
        return sum(
            1 for c in ast.walk(node)
            if isinstance(c, (ast.If, ast.For, ast.While, ast.Try, ast.With))
        )

    lengths = [len(ast.unparse(f).split(chr(10))) for f in functions]
    branches_per_fn = [count_branches(f) for f in functions]
    branches_module = count_branches(tree) - sum(branches_per_fn)

    result = {
        "functions": len(functions),
        "classes": len(classes),
        "avg_function_length": round(sum(lengths) / len(lengths), 1) if lengths else 0,
        "branch_count_per_function_avg": (
            round(sum(branches_per_fn) / len(branches_per_fn), 1) if branches_per_fn else 0
        ),
        "branch_count_total": count_branches(tree),
        "branch_count_module_level": max(branches_module, 0),
        "branch_count_note": (
            "branch_count is an approximation, NOT true cyclomatic complexity. "
            "Install radon for true CC." if not RADON else "radon available"
        ),
    }

    if RADON:
        try:
            cc = cc_visit(code)
            result["cyclomatic_complexity"] = [{"name": b.name, "cc": b.complexity} for b in cc]
            result["cyclomatic_avg"] = (
                round(sum(b.complexity for b in cc) / len(cc), 1) if cc else 0
            )
        except Exception as e:
            result["radon_error"] = str(e)

    if RADON_MI:
        try:
            result["maintainability_index"] = round(mi_visit(code, True), 1)
        except Exception:
            pass

    return result


def mode_security(code: str) -> dict:
    if not code.strip():
        return {"empty": True, "verdict": "clean"}

    dangerous = ["eval(", "exec(", "__import__", "os.system", "subprocess"]
    found = [d for d in dangerous if d in code]

    secret_re = re.compile(
        r"""(?ix)
        \b(password|passwd|secret|api_key|apikey|token|access_key)\b
        \s*[:=]\s*
        ["'][^"'\s]{6,}["']
        """
    )
    secrets_lines = []
    for i, line in enumerate(code.splitlines(), 1):
        if secret_re.search(line):
            low = line.lower()
            if not any(x in low for x in ("getenv", "environ", "config", "vault", "settings")):
                secrets_lines.append({"line": i, "text": line.strip()[:80]})

    injection_markers = [
        "ignore previous", "ignore all previous", "system:", "you are now",
        "override protocol", "disregard previous",
    ]
    injections = []
    for i, line in enumerate(code.splitlines(), 1):
        low = line.lower()
        if any(m in low for m in injection_markers):
            stripped = line.strip()
            is_comment = stripped.startswith(("#", "//", "/*", "*", "--", "<!--"))
            injections.append({"line": i, "in_comment": is_comment, "text": stripped[:100]})

    return {
        "dangerous_constructs": found,
        "possible_hardcoded_secrets": secrets_lines,
        "injection_in_comments": injections,
        "verdict": "review needed" if (found or secrets_lines or injections) else "clean",
    }


def mode_metrics(code: str) -> dict:
    if not code.strip():
        return {"empty": True, "total_lines": 0}
    lines = code.splitlines()
    total = len(lines)
    blank = sum(1 for l in lines if not l.strip())
    comments = sum(1 for l in lines if l.strip().startswith(("#", "//", "/*", "*", "--")))
    return {
        "total_lines": total,
        "code_lines": total - blank - comments,
        "comment_lines": comments,
        "blank_lines": blank,
        "comment_density": round(comments / total * 100, 1) if total else 0,
    }


def mode_deps(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"error": "file not found", "path": str(p)}
    name = p.name.lower()
    if name in ("package.json", "pom.xml"):
        return {
            "error": "unsupported manifest",
            "path": str(p),
            "note": "package.json / pom.xml require dedicated parsers",
        }
    text = p.read_text(encoding="utf-8", errors="replace")
    deps = []
    if name == "requirements.txt" or name.endswith(".txt"):
        for line in text.splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                deps.append(s)
    elif name == "go.mod":
        in_require = False
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("require ("):
                in_require = True
                continue
            if in_require and s == ")":
                in_require = False
                continue
            if in_require and s and not s.startswith("//"):
                deps.append(s.split()[0])
            elif s.startswith("require ") and not s.startswith("require ("):
                deps.append(s.split()[1])
    elif name == "cargo.toml":
        in_deps = False
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("[") and s.endswith("]"):
                in_deps = s in ("[dependencies]", "[dev-dependencies]")
                continue
            if in_deps and "=" in s and not s.startswith("#"):
                deps.append(s.split("=")[0].strip())
    else:
        for line in text.splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                deps.append(s)
    return {
        "file": path,
        "total": len(deps),
        "deps": deps[:200],
        "note": "CVE check requires external tool (pip-audit, npm audit, govulncheck)",
    }


def mode_tests(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"error": "path not found", "path": str(p)}
    files = list(p.rglob("test_*.py")) + list(p.rglob("*_test.py"))
    total_tests = 0
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
            total_tests += sum(
                1 for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
            )
        except (SyntaxError, OSError):
            continue
    return {
        "path": str(p),
        "test_files": len(files),
        "test_functions": total_tests,
        "note": "covers Python only; other languages require dedicated runners",
    }


def mode_calc(spec: dict) -> dict:
    out = {}
    rps = spec.get("rps")
    latency_ms = spec.get("latency_ms")
    latency_type = spec.get("latency_type")

    if rps and latency_ms:
        if not latency_type:
            out["error"] = "latency_type is required: p50 / p95 / p99 / mean"
        else:
            out["concurrent_requests"] = round(rps * (latency_ms / 1000), 1)
            out["concurrent_requests_note"] = (
                f"L = lambda x W, W = latency ({latency_type}). "
                "For p99 use queueing model (M/M/c)."
            )

    workers = spec.get("workers")
    if workers and rps:
        out["rps_per_worker"] = round(rps / workers, 2)

    if "pool_size" in spec and rps and latency_ms and latency_type:
        concurrent = rps * (latency_ms / 1000)
        safety = spec.get("safety_factor", 1.2)
        recommended = max(spec["pool_size"], int(concurrent * safety) + 1)
        out["recommended_pool_size"] = recommended
        out["recommended_pool_size_note"] = (
            f"max(current, concurrent_requests x {safety}) + 1"
        )
    return out


def mode_cost(spec: dict) -> dict:
    count = spec.get("count", 1)
    hours = spec.get("hours", 730)
    price = spec.get("price_per_hour", 0)
    monthly = round(count * hours * price, 2)
    return {
        "monthly_usd": monthly,
        "annual_usd": round(monthly * 12, 2),
        "inputs": {"count": count, "hours": hours, "price_per_hour": price},
    }


def mode_migrate(spec: dict) -> dict:
    rows = spec.get("rows")
    size_gb = spec.get("size_gb")
    throughput_mb_s = spec.get("throughput_mb_s", 10)
    out = {}
    if rows and size_gb:
        out["estimated_minutes"] = round((size_gb * 1024) / throughput_mb_s / 60, 1)
        out["estimated_minutes_note"] = (
            f"{size_gb} GB / {throughput_mb_s} MB/s, without indexes and checks"
        )
    if size_gb and size_gb > 100:
        out["recommendation"] = "online migration (expand-contract), not offline"
    return out


# === v6.1: concurrency + contracts (AST, Python only) ===

_LOCK_NAMES = {"Lock", "RLock", "Semaphore", "BoundedSemaphore", "Condition", "Event"}


def analyze_concurrency(code: str) -> dict:
    """Detect concurrency constructs (locks, shared state, async) via AST.

    Python only. Fail-open: parse errors return empty lists + "error", never raise.
    """
    result = {
        "mode": "concurrency",
        "locks": [],
        "shared_state": [],
        "async_constructs": [],
    }
    if not code.strip():
        result["empty"] = True
        return result
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        result["error"] = f"SyntaxError: {e}"
        return result

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute) and fn.attr in _LOCK_NAMES:
                obj = fn.value
                name = f"{obj.id}.{fn.attr}" if isinstance(obj, ast.Name) else fn.attr
                if name not in result["locks"]:
                    result["locks"].append(name)
            elif isinstance(fn, ast.Name) and fn.id in _LOCK_NAMES:
                if fn.id not in result["locks"]:
                    result["locks"].append(fn.id)
        elif isinstance(node, ast.Global):
            for name in node.names:
                if name not in result["shared_state"]:
                    result["shared_state"].append(name)
        elif isinstance(node, ast.Await):
            if "await" not in result["async_constructs"]:
                result["async_constructs"].append("await")
        elif isinstance(node, ast.AsyncFunctionDef):
            if "async def" not in result["async_constructs"]:
                result["async_constructs"].append("async def")

    return result


def analyze_contracts(code: str) -> dict:
    """Detect reliability contracts (error handling, retry, timeout, idempotency).

    Heuristic AST check, Python only. Fail-open like other deterministic tools.
    """
    result = {
        "mode": "contracts",
        "error_handling": False,
        "retry": False,
        "timeout": False,
        "idempotency": False,
    }
    if not code.strip():
        result["empty"] = True
        return result
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        result["error"] = f"SyntaxError: {e}"
        return result

    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            result["error_handling"] = True
        elif isinstance(node, ast.Name):
            low = node.id.lower()
            if low == "retry":
                result["retry"] = True
            elif low in ("idempotency", "idempotency_key"):
                result["idempotency"] = True
        elif isinstance(node, ast.Attribute):
            if node.attr == "retry":
                result["retry"] = True
            elif node.attr in ("idempotency", "idempotency_key"):
                result["idempotency"] = True
        elif isinstance(node, ast.arg):
            if node.arg.lower() in ("idempotency", "idempotency_key"):
                result["idempotency"] = True
        elif isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "timeout":
                    result["timeout"] = True
                elif kw.arg in ("idempotency_key", "idempotency"):
                    result["idempotency"] = True
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "idempotency" in node.value.lower():
                result["idempotency"] = True

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True,
                    choices=["static", "security", "metrics", "deps", "tests",
                             "calc", "cost", "migrate", "concurrency", "contracts"])
    ap.add_argument("--input")
    ap.add_argument("--spec")
    args = ap.parse_args()

    if args.mode in ("static", "security", "metrics"):
        code = _read_input(args.input)
        fn = {"static": mode_static, "security": mode_security, "metrics": mode_metrics}[args.mode]
        print(json.dumps(fn(code), indent=2, ensure_ascii=False))
    elif args.mode == "deps":
        print(json.dumps(mode_deps(args.input), indent=2, ensure_ascii=False))
    elif args.mode == "tests":
        print(json.dumps(mode_tests(args.input), indent=2, ensure_ascii=False))
    elif args.mode in ("concurrency", "contracts"):
        code = _read_input(args.input)
        fn = {"concurrency": analyze_concurrency, "contracts": analyze_contracts}[args.mode]
        print(json.dumps(fn(code), indent=2, ensure_ascii=False))
    elif args.mode in ("calc", "cost", "migrate"):
        if not args.spec:
            print(json.dumps({"error": "--spec required"}))
            return
        spec = json.loads(Path(args.spec).read_text())
        fn = {"calc": mode_calc, "cost": mode_cost, "migrate": mode_migrate}[args.mode]
        print(json.dumps(fn(spec), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
