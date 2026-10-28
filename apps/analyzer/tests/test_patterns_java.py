# -*- coding: utf-8 -*-
"""P2-7: Java taint patterns (sources, sinks, entry points).

Tests for src/tools/patterns.py -- java extension.
Dogfood cases: DbConnection.java (SQL injection), log4shell_JndiLookup.java (JNDI).
"""
from src.tools.patterns import TAINT_SOURCES, TAINT_SINKS, EXPLOIT_PATTERNS


def _matches(patterns_dict, key, text):
    pat = patterns_dict.get(key)
    if pat is None:
        return False
    return bool(pat.search(text))


# ============================================================
# TAINT_SOURCES -- Java
# ============================================================

def test_java_source_getParameter():
    assert _matches(TAINT_SOURCES, "source_java", 'String id = request.getParameter("id");')

def test_java_source_getHeader():
    assert _matches(TAINT_SOURCES, "source_java", 'String token = request.getHeader("Authorization");')

def test_java_source_getCookies():
    assert _matches(TAINT_SOURCES, "source_java", 'Cookie[] cookies = request.getCookies();')

def test_java_source_system_getenv():
    assert _matches(TAINT_SOURCES, "source_java", 'String path = System.getenv("PATH");')

def test_java_source_system_getProperty():
    assert _matches(TAINT_SOURCES, "source_java", 'String home = System.getProperty("user.home");')

def test_java_source_scanner():
    assert _matches(TAINT_SOURCES, "source_java", 'Scanner sc = new Scanner(System.in);')

def test_java_source_bufferedreader():
    assert _matches(TAINT_SOURCES, "source_java", 'BufferedReader br = new BufferedReader(new InputStreamReader(System.in));')

def test_java_source_spring_requestparam():
    assert _matches(TAINT_SOURCES, "source_java", '@RequestParam("id") String id')

def test_java_source_no_false_positive():
    assert not _matches(TAINT_SOURCES, "source_java", 'int x = 42; String s = "hello";')


# ============================================================
# TAINT_SINKS -- Java SQL
# ============================================================

def test_java_sink_executeQuery():
    assert _matches(TAINT_SINKS, "sink_java_sql", 'ResultSet rs = stmt.executeQuery(sql);')

def test_java_sink_executeUpdate():
    assert _matches(TAINT_SINKS, "sink_java_sql", 'int rows = ps.executeUpdate();')

def test_java_sink_createStatement():
    assert _matches(TAINT_SINKS, "sink_java_sql", 'Statement stmt = conn.createStatement();')

def test_java_sink_execute():
    assert _matches(TAINT_SINKS, "sink_java_sql", 'boolean ok = stmt.execute(sql);')


# ============================================================
# TAINT_SINKS -- Java cmd
# ============================================================

def test_java_sink_runtime_exec():
    assert _matches(TAINT_SINKS, "sink_java_cmd", 'Process p = Runtime.getRuntime().exec(cmd);')

def test_java_sink_processbuilder():
    assert _matches(TAINT_SINKS, "sink_java_cmd", 'ProcessBuilder pb = new ProcessBuilder("ls", "-la");')


# ============================================================
# TAINT_SINKS -- Java file
# ============================================================

def test_java_sink_new_file():
    assert _matches(TAINT_SINKS, "sink_java_file", 'File f = new File(userPath);')

def test_java_sink_fileinputstream():
    assert _matches(TAINT_SINKS, "sink_java_file", 'FileInputStream fis = new FileInputStream(filename);')

def test_java_sink_paths_get():
    assert _matches(TAINT_SINKS, "sink_java_file", 'Path p = Paths.get(userInput);')


# ============================================================
# TAINT_SINKS -- Java reflection
# ============================================================

def test_java_sink_class_forname():
    assert _matches(TAINT_SINKS, "sink_java_reflect", 'Class<?> clazz = Class.forName(className);')

def test_java_sink_method_invoke():
    assert _matches(TAINT_SINKS, "sink_java_reflect", 'method.invoke(obj, args);')


# ============================================================
# TAINT_SINKS -- Java deserialization
# ============================================================

def test_java_sink_readObject():
    assert _matches(TAINT_SINKS, "sink_java_deser", 'Object obj = ois.readObject();')

def test_java_sink_objectinputstream():
    assert _matches(TAINT_SINKS, "sink_java_deser", 'ObjectInputStream ois = new ObjectInputStream(fis);')


# ============================================================
# TAINT_SINKS -- Java JNDI (Log4Shell!)
# ============================================================

def test_java_sink_jndi_lookup():
    assert _matches(TAINT_SINKS, "sink_java_jndi", 'Object o = ctx.lookup(name);')

def test_java_sink_jndi_initial_context():
    assert _matches(TAINT_SINKS, "sink_java_jndi", 'InitialContext ctx = new InitialContext(); ctx.lookup(url);')


# ============================================================
# EXPLOIT_PATTERNS -- Java entry points
# ============================================================

def test_java_entrypoint_main():
    assert _matches(EXPLOIT_PATTERNS, "entrypoint_java_main", 'public static void main(String[] args) {')

def test_java_entrypoint_spring_restcontroller():
    assert _matches(EXPLOIT_PATTERNS, "entrypoint_java_spring", '@RestController')

def test_java_entrypoint_spring_getmapping():
    assert _matches(EXPLOIT_PATTERNS, "entrypoint_java_spring", '@GetMapping("/users/{id}")')

def test_java_entrypoint_servlet_doget():
    assert _matches(EXPLOIT_PATTERNS, "entrypoint_java_servlet", 'protected void doGet(HttpServletRequest req, HttpServletResponse resp)')

def test_java_entrypoint_servlet_dopost():
    assert _matches(EXPLOIT_PATTERNS, "entrypoint_java_servlet", 'protected void doPost(HttpServletRequest req, HttpServletResponse resp)')


# ============================================================
# Real snippets -- DbConnection.java
# ============================================================

def test_dbconnection_real_snippet():
    code = """
    public User getUser(String id) {
        Statement stmt = conn.createStatement();
        ResultSet rs = stmt.executeQuery("SELECT name FROM users WHERE id = " + id);
        return mapUser(rs);
    }
    """
    assert _matches(TAINT_SINKS, "sink_java_sql", code)


def test_dbconnection_prepared_statement_safe():
    code = 'PreparedStatement ps = conn.prepareStatement("INSERT INTO users(name) VALUES (?)");'
    assert not _matches(TAINT_SINKS, "sink_java_sql", code)


# ============================================================
# Real snippets -- log4shell_JndiLookup.java
# ============================================================

def test_log4shell_jndi_lookup():
    code = 'return JndiManager.getJndiManager().lookup(name);'
    assert _matches(TAINT_SINKS, "sink_java_jndi", code)

def test_log4shell_lookup_generic():
    code = 'ctx.lookup(name);'
    assert _matches(TAINT_SINKS, "sink_java_jndi", code)

# ============================================================
# Comment stripping (v5.11.5-strip-comments)
# ============================================================

def test_is_comment_line_double_slash():
    from src.tools.reachability import _is_comment_line
    assert _is_comment_line("// some comment") is True


def test_is_comment_line_hash():
    from src.tools.reachability import _is_comment_line
    assert _is_comment_line("# python comment") is True


def test_is_comment_line_block():
    from src.tools.reachability import _is_comment_line
    assert _is_comment_line("/* block comment */") is True


def test_is_comment_line_asterisk():
    from src.tools.reachability import _is_comment_line
    assert _is_comment_line(" * javadoc line") is True


def test_is_comment_line_code():
    from src.tools.reachability import _is_comment_line
    assert _is_comment_line("String id = req.getParameter(\"id\");") is False


def test_is_comment_line_leading_whitespace():
    from src.tools.reachability import _is_comment_line
    assert _is_comment_line("   // indented comment") is True


def test_find_taint_sources_skips_comments():
    from src.tools.reachability import find_taint_sources
    code = '// req.getParameter("id")\nString id = req.getParameter("id");'
    srcs = find_taint_sources(code)
    # comment skipped, only real code matched
    assert len(srcs) == 1
    assert srcs[0]["line"] == 2


def test_find_taint_sinks_skips_comments():
    from src.tools.reachability import find_taint_sinks
    code = '// stmt.executeQuery(x)\nResultSet rs = stmt.executeQuery(x);'
    snks = find_taint_sinks(code)
    assert len(snks) == 1
    assert snks[0]["line"] == 2
