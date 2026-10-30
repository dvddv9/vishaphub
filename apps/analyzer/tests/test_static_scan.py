# -*- coding: utf-8 -*-
"""Built-in rule engine (src/tools/static_scan.py): no LLM, no files on disk."""
import asyncio
from pathlib import Path

import pytest

from src.tools.static_scan import detect_language, render_markdown, scan_material, verdict_of

SQLI = (
    "import sqlite3\n"
    "from flask import request\n"
    "def u(conn):\n"
    "    name = request.args.get('name')\n"
    "    conn.execute(\"SELECT * FROM users WHERE name = '\" + name + \"'\")\n"
)


def _ids(result):
    return {f["id"] for f in result["findings"]}


def test_sql_injection_is_found_with_cwe_and_line():
    r = scan_material(SQLI, "example_sqli.py")
    hit = next(f for f in r["findings"] if f["id"] == "sqli-concat")
    assert hit["cwe"] == "CWE-89" and hit["line"] == 5 and hit["severity"] == "critical"
    assert r["high_priority"] >= 1 and "CWE-89" in r["cwe_ids"]
    assert verdict_of(r) == "CRITICAL"


def test_clean_code_has_no_findings():
    r = scan_material("def add(a, b):\n    return a + b\n", "ok.py")
    assert r["total_findings"] == 0 and verdict_of(r) == "NO ISSUES FOUND"
    assert "not a proof of safety" in render_markdown(r, "ok.py")


def test_secrets_are_found_and_never_echoed():
    code = 'KEY = "AKIAABCDEFGHIJKLMNOP"\npassword = "correct-horse-battery"\n'
    r = scan_material(code, "cfg.py")
    assert {"secret-aws", "secret-hardcoded"} <= _ids(r)
    md = render_markdown(r, "cfg.py")
    assert "AKIAABCDEFGHIJKLMNOP" not in md and "correct-horse-battery" not in md
    assert "AKIAABCDEFGHIJKLMNOP" not in str(r)


@pytest.mark.parametrize("name,code,expected", [
    ("a.c", "int main(){char b[8]; gets(b); strcpy(b, x);}", {"c-gets", "c-strcpy"}),
    ("a.js", "el.innerHTML = q; eval(body);", {"xss-innerhtml", "eval-js"}),
    ("a.tf", 'cidr_blocks = ["0.0.0.0/0"]\nacl = "public-read"\n', {"tf-open-cidr", "tf-public-s3"}),
    ("a.yaml", "securityContext:\n  privileged: true\n", {"k8s-privileged"}),
    ("a.py", "import pickle\npickle.loads(data)\nyaml.load(s)\n", {"deser-pickle", "deser-yaml"}),
    ("a.py", "requests.get(u, verify=False)\nhashlib.md5(x)\n", {"tls-verify-off", "weak-hash"}),
    ("x.log", "2026-10-26 10:00:00 GET /?id=1 UNION SELECT pw FROM users\n", {"log-sqli"}),
])
def test_rules_per_language(name, code, expected):
    assert expected <= _ids(scan_material(code, name))


# the PHP and Go rules written after the labelled benchmark -------------------------------

_LABELLED = Path(__file__).parent / "bench" / "labelled"
_PHP_SHELL = ("system", "exec", "shell_exec", "passthru", "popen", "proc_open", "pcntl_exec")
_GO_SHELLS = ("sh", "bash", "zsh", "/bin/sh", "/usr/bin/bash")


@pytest.mark.parametrize("path,rule", [
    ("php/php_cmd_system.php", "cmd-injection-php"),
    ("php/php_eval_post.php", "eval-php"),
    ("go/go_cmd_sh_c.go", "cmd-injection-go"),
])
def test_the_labelled_critical_examples_are_no_longer_safe(path, rule):
    code = (_LABELLED / path).read_text(encoding="utf-8")
    result = scan_material(code, Path(path).name)
    assert rule in _ids(result)
    assert verdict_of(result) != "NO ISSUES FOUND"


@pytest.mark.parametrize("fn", _PHP_SHELL)
def test_every_php_shell_function_is_flagged(fn):
    found = scan_material(f"<?php\n{fn}($cmd);\n", "a.php")
    assert "cmd-injection-php" in _ids(found)


@pytest.mark.parametrize("code", ["eval($code);", "  eval ( $code );", "$r = eval($code);", "if (eval($code)) { run(); }"])
def test_php_eval_is_flagged_and_critical(code):
    found = scan_material(f"<?php\n{code}\n", "a.php")
    assert "eval-php" in _ids(found)
    assert found["by_severity"]["critical"] >= 1


@pytest.mark.parametrize("code", [
    '$pdo->exec("CREATE TABLE t (x int)");',          # a database method, not the shell
    "$this->system($a);",
    "Runner::exec($a);",
    "my_system($a);",                                  # a longer name that ends in the word
    "$value = retrieval($a);",
    "$obj->eval($a);",
    'shell_exec("ping " . escapeshellarg($h));',      # the standard mitigation, on the same line
    'passthru("ls " . escapeshellcmd($dir));',
    "// system($a);",                                  # a comment
])
def test_php_rules_stay_quiet_on_safe_calls(code):
    found = _ids(scan_material(f"<?php\n{code}\n", "a.php"))
    assert not ({"cmd-injection-php", "eval-php"} & found), code


@pytest.mark.parametrize("shell", _GO_SHELLS)
@pytest.mark.parametrize("call", ['exec.Command("{s}", "-c", cmd)', 'exec.Command("{s}", "-c", "ping "+host)',
                                  'exec.CommandContext(ctx, "{s}", "-c", cmd)'])
def test_go_shell_invocations_are_flagged(shell, call):
    code = "package main\n\nfunc run() {\n\t" + call.format(s=shell) + ".Run()\n}\n"
    assert "cmd-injection-go" in _ids(scan_material(code, "a.go"))


@pytest.mark.parametrize("call", [
    'exec.Command("ping", "-c", "1", host)',          # the program is not a shell
    'exec.Command("sh", "script.sh")',                # a shell running a file: no -c string
    'exec.Command("sha256sum", "-c", file)',          # a checksum tool whose name starts with sh
    'exec.Command("shutdown", "-c")',
    '// exec.Command("sh", "-c", cmd)',               # a comment
])
def test_go_rule_stays_quiet_on_safe_calls(call):
    code = "package main\n\nfunc run() {\n\t" + call + "\n}\n"
    assert "cmd-injection-go" not in _ids(scan_material(code, "a.go"))


def test_comments_and_language_specific_rules_do_not_leak():
    assert scan_material("# os.system(cmd)\n", "a.py")["total_findings"] == 0
    assert "c-gets" not in _ids(scan_material("gets(b)\n", "a.py"))     # C rule on Python
    assert "tf-open-cidr" not in _ids(scan_material('x = "0.0.0.0/0"\n', "a.py"))


def test_detect_language():
    assert detect_language("Dockerfile") == "dockerfile"
    assert detect_language("x.tsx") == "typescript"
    assert detect_language("noext", "import os\n") == "python"
    assert detect_language("noext", "plain words") == "unknown"


def test_huge_and_hostile_input_is_bounded():
    r = scan_material(("a = '" + "x" * 5000 + "'\n") * 2000, "big.py")
    assert r["total_findings"] <= 200
    assert scan_material("", "e.py")["total_findings"] == 0
    assert scan_material(None, "e.py")["total_findings"] == 0


def test_sarif_accepts_the_rule_engine_findings():
    from src.tools.sarif import to_sarif
    r = scan_material(SQLI, "example_sqli.py")
    sarif = to_sarif(audit={}, sast_result=r, source_file="example_sqli.py")
    ids = [x["ruleId"] for x in sarif["runs"][0]["results"]]
    assert "vishap_rules/sqli-concat" in ids


def test_pipeline_static_only_never_calls_the_llm(monkeypatch):
    import src.pipeline.async_stages as stages
    from src.pipeline.orchestrator import run_pipeline_async
    calls = []
    monkeypatch.setattr(stages, "async_chat", lambda *a, **k: calls.append(1))
    result = asyncio.run(run_pipeline_async(SQLI, "example_sqli.py", static_only=True))
    assert not calls
    assert result["mode"] == "static" and result["audit"]["analysis_mode"] == "static"
    assert "CWE-89" in result["audit"]["cwe_ids"]
    assert result["audit"]["risk_verdict"] == "REQUIRES_REVIEW"
    assert "Built-in" in result["final_markdown"] or "built-in" in result["final_markdown"]
    assert result["completeness"]["verdict"] == "ACCEPTABLE"
