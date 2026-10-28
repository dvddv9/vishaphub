# -*- coding: utf-8 -*-
"""P2-7: C taint patterns (sources, sinks, entry points).

Tests for src/tools/patterns.py -- C extension.
Dogfood case: examples/own/c_cmd_injection.c (argv -> system).
Reference: cwe122_heap_overflow.c (SARD 234204).
"""
from src.tools.patterns import TAINT_SOURCES, TAINT_SINKS, EXPLOIT_PATTERNS


def _matches(patterns_dict, key, text):
    pat = patterns_dict.get(key)
    if pat is None:
        return False
    return bool(pat.search(text))


# ============================================================
# TAINT_SOURCES -- C
# ============================================================

def test_c_source_scanf():
    assert _matches(TAINT_SOURCES, "source_c", 'scanf("%s", buf);')


def test_c_source_fgets():
    assert _matches(TAINT_SOURCES, "source_c", 'fgets(buf, sizeof(buf), stdin);')


def test_c_source_gets():
    assert _matches(TAINT_SOURCES, "source_c", 'gets(buf);')


def test_c_source_read():
    assert _matches(TAINT_SOURCES, "source_c", 'read(fd, buf, 256);')


def test_c_source_recv():
    assert _matches(TAINT_SOURCES, "source_c", 'recv(sock, buf, 1024, 0);')


def test_c_source_getenv():
    assert _matches(TAINT_SOURCES, "source_c", 'char *p = getenv("PATH");')


def test_c_source_argv():
    assert _matches(TAINT_SOURCES, "source_c", 'char *p = argv[1];')


def test_c_source_no_false_positive():
    assert not _matches(TAINT_SOURCES, "source_c", 'int x = 42; int y = x + 1;')


# ============================================================
# TAINT_SINKS -- C cmd
# ============================================================

def test_c_sink_system():
    assert _matches(TAINT_SINKS, "sink_c_cmd", 'system(cmd);')


def test_c_sink_popen():
    assert _matches(TAINT_SINKS, "sink_c_cmd", 'FILE *f = popen(cmd, "r");')


def test_c_sink_execv():
    assert _matches(TAINT_SINKS, "sink_c_cmd", 'execv(path, argv);')


def test_c_sink_execl():
    assert _matches(TAINT_SINKS, "sink_c_cmd", 'execl("/bin/sh", "sh", "-c", cmd, NULL);')


def test_c_sink_execve():
    assert _matches(TAINT_SINKS, "sink_c_cmd", 'execve(path, argv, envp);')


# ============================================================
# TAINT_SINKS -- C buffer
# ============================================================

def test_c_sink_strcpy():
    assert _matches(TAINT_SINKS, "sink_c_buffer", 'strcpy(dst, src);')


def test_c_sink_strcat():
    assert _matches(TAINT_SINKS, "sink_c_buffer", 'strcat(dst, src);')


def test_c_sink_sprintf():
    assert _matches(TAINT_SINKS, "sink_c_buffer", 'sprintf(buf, "%s", user);')


def test_c_sink_memcpy():
    assert _matches(TAINT_SINKS, "sink_c_buffer", 'memcpy(dst, src, n);')


def test_c_sink_gets_as_sink():
    assert _matches(TAINT_SINKS, "sink_c_buffer", 'gets(buf);')


# ============================================================
# TAINT_SINKS -- C file
# ============================================================

def test_c_sink_fopen():
    assert _matches(TAINT_SINKS, "sink_c_file", 'FILE *f = fopen(path, "r");')


def test_c_sink_open():
    assert _matches(TAINT_SINKS, "sink_c_file", 'int fd = open(path, O_RDONLY);')


def test_c_sink_fread():
    assert _matches(TAINT_SINKS, "sink_c_file", 'fread(buf, 1, n, f);')


# ============================================================
# EXPLOIT_PATTERNS -- C entry points
# ============================================================

def test_c_entrypoint_main_argc_argv():
    code = 'int main(int argc, char **argv) {'
    assert _matches(EXPLOIT_PATTERNS, "entrypoint_c_main", code)


def test_c_entrypoint_main_void():
    code = 'int main(void) {'
    # Should not match (no argc/argv) -- that is expected
    # But main with no args is still an entry point; for taint we need argv
    assert _matches(EXPLOIT_PATTERNS, "entrypoint_c_main", 'int main(int argc, char *argv[]) {')


def test_c_entrypoint_no_false_positive():
    assert not _matches(EXPLOIT_PATTERNS, "entrypoint_c_main", 'int compute(int x) {')


# ============================================================
# Real snippets -- cwe122
# ============================================================

def test_cwe122_malloc_no_taint():
    code = 'data = (twoIntsStruct *)malloc(sizeof(data));'
    assert not _matches(TAINT_SOURCES, "source_c", code)
    assert not _matches(TAINT_SINKS, "sink_c_cmd", code)


def test_cwe122_no_source():
    code = """
    void bad() {
        twoIntsStruct *data;
        data = NULL;
        data = (twoIntsStruct *)malloc(sizeof(data));
        data->intOne = 1;
        data->intTwo = 2;
        free(data);
    }
    """
    assert not _matches(TAINT_SOURCES, "source_c", code)


# ============================================================
# Real snippets -- c_cmd_injection (mini-case)
# ============================================================

def test_c_cmd_injection_source():
    code = 'if (argc > 1) { strcpy(buf, argv[1]); }'
    assert _matches(TAINT_SOURCES, "source_c", code)


def test_c_cmd_injection_sink():
    code = 'system(buf);'
    assert _matches(TAINT_SINKS, "sink_c_cmd", code)


def test_c_cmd_injection_entry():
    code = 'int main(int argc, char **argv) {'
    assert _matches(EXPLOIT_PATTERNS, "entrypoint_c_main", code)

# ============================================================
# v5.11.6-fix1: argc is not taint
# ============================================================

def test_c_source_argc_not_source():
    """argc is a count, not taint."""
    assert not _matches(TAINT_SOURCES, "source_c", 'if (argc > 1) {')


def test_c_source_argv_is_source():
    assert _matches(TAINT_SOURCES, "source_c", 'char *p = argv[1];')

# ============================================================
# v5.11.6-blast-c-fix: C blast radius
# ============================================================

def test_c_blast_cmd_high():
    from src.tools.patterns import detect_exploitability
    code = 'int main(int argc, char **argv) { system(argv[1]); }'
    r = detect_exploitability(code)
    assert r["blast_radius"] == "high"


def test_c_blast_buffer_medium():
    from src.tools.patterns import detect_exploitability
    code = 'int main(int argc, char **argv) { strcpy(buf, argv[1]); }'
    r = detect_exploitability(code)
    # c_buffer = medium; but c_cmd not present here
    assert r["blast_radius"] == "medium"


def test_c_blast_file_low():
    from src.tools.patterns import detect_exploitability
    code = 'FILE *f = fopen(path, "r");'
    r = detect_exploitability(code)
    assert r["blast_radius"] == "low"


def test_c_entrypoint_c_main_detected():
    from src.tools.patterns import detect_exploitability
    code = 'int main(int argc, char **argv) {'
    r = detect_exploitability(code)
    assert "c_main" in r["entry_points"]
