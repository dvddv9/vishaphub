"""The pilot corpus: synthetic functions with a known truth (vulnerable or not), our own, no real data.

Every case is a module `app.py` and a test `test_app.py` that the deliverable's own checks run. The truth is
fixed by construction: a case is vulnerable if an attacker-controlled argument reaches the sink unescaped,
and its safe twin does the same job without that. The pilot runs the rules and the trusted exploit probes over
them and counts where they disagree with the truth.
"""
from __future__ import annotations

SQLI_TEST = '''import sqlite3

from app import find


def test_find_returns_the_row():
    con = sqlite3.connect(":memory:")
    cur = con.cursor()
    cur.execute("create table users (id integer, name text, secret text)")
    cur.execute("insert into users values (1, 'ann', 's')")
    assert find(cur, "ann") == [(1,)]
'''

PATH_TEST = '''from app import read


def test_read_returns_the_file(tmp_path):
    (tmp_path / "hello.txt").write_text("hello", encoding="utf-8")
    assert read(str(tmp_path), "hello.txt") == "hello"
'''

CMD_TEST = '''from app import echo


def test_echo_runs():
    echo("hello")
'''


def _sql(body: str) -> str:
    return "def find(cur, name):\n" + body + "    return cur.fetchall()\n"


def _path(body: str, head: str = "import os\n\n\n") -> str:
    return head + "def read(base, name):\n" + body


def _cmd(body: str, head: str = "import os\nimport subprocess\n\n\n") -> str:
    return head + "def echo(text):\n" + body


SQLI_TARGET = {"class": "sqli", "entry": "app:find", "args": ["$cursor", "$payload"]}
PATH_TARGET = {"class": "path_traversal", "entry": "app:read", "args": ["$base", "$payload"]}
CMD_TARGET = {"class": "command_injection", "entry": "app:echo", "args": ["$payload"]}

#: id, class, vulnerable?, app.py
CASES = [
    # --- SQL injection -------------------------------------------------------------------------
    {"id": "sqli-concat", "class": "sqli", "vulnerable": True,
     "app": _sql("    cur.execute(\"select id from users where name = '\" + name + \"'\")\n")},
    {"id": "sqli-fstring", "class": "sqli", "vulnerable": True,
     "app": _sql("    cur.execute(f\"select id from users where name = '{name}'\")\n")},
    {"id": "sqli-format", "class": "sqli", "vulnerable": True,
     "app": _sql("    cur.execute(\"select id from users where name = '{}'\".format(name))\n")},
    {"id": "sqli-percent", "class": "sqli", "vulnerable": True,
     "app": _sql("    cur.execute(\"select id from users where name = '%s'\" % name)\n")},
    {"id": "sqli-pluseq", "class": "sqli", "vulnerable": True,
     "app": _sql("    sql = \"select id from users where name = '\"\n    sql += name\n    sql += \"'\"\n"
                 "    cur.execute(sql)\n")},
    {"id": "sqli-join", "class": "sqli", "vulnerable": True,
     "app": _sql("    sql = \"\".join([\"select id from users where name = '\", name, \"'\"])\n"
                 "    cur.execute(sql)\n")},
    {"id": "sqli-param", "class": "sqli", "vulnerable": False,
     "app": _sql("    cur.execute(\"select id from users where name = ?\", (name,))\n")},
    {"id": "sqli-named", "class": "sqli", "vulnerable": False,
     "app": _sql("    cur.execute(\"select id from users where name = :n\", {\"n\": name})\n")},
    # --- path traversal ------------------------------------------------------------------------
    {"id": "path-join", "class": "path_traversal", "vulnerable": True,
     "app": _path("    with open(os.path.join(base, name), encoding=\"utf-8\") as fh:\n        return fh.read()\n")},
    {"id": "path-fstring", "class": "path_traversal", "vulnerable": True,
     "app": _path("    with open(f\"{base}/{name}\", encoding=\"utf-8\") as fh:\n        return fh.read()\n")},
    {"id": "path-startswith", "class": "path_traversal", "vulnerable": True,
     "app": _path("    full = os.path.join(base, name)\n    if not full.startswith(base):\n"
                  "        raise ValueError(\"outside\")\n"
                  "    with open(full, encoding=\"utf-8\") as fh:\n        return fh.read()\n")},
    {"id": "path-realpath", "class": "path_traversal", "vulnerable": False,
     "app": _path("    root = os.path.realpath(base)\n    full = os.path.realpath(os.path.join(base, name))\n"
                  "    if os.path.commonpath([root, full]) != root:\n        raise ValueError(\"outside\")\n"
                  "    with open(full, encoding=\"utf-8\") as fh:\n        return fh.read()\n")},
    {"id": "path-basename", "class": "path_traversal", "vulnerable": False,
     "app": _path("    with open(os.path.join(base, os.path.basename(name)), encoding=\"utf-8\") as fh:\n"
                  "        return fh.read()\n")},
    # --- command injection ---------------------------------------------------------------------
    {"id": "cmd-system", "class": "command_injection", "vulnerable": True,
     "app": _cmd("    os.system(\"echo \" + text)\n")},
    {"id": "cmd-shell-fstring", "class": "command_injection", "vulnerable": True,
     "app": _cmd("    subprocess.run(f\"echo {text}\", shell=True, check=False)\n")},
    {"id": "cmd-popen", "class": "command_injection", "vulnerable": True,
     "app": _cmd("    return os.popen(\"echo \" + text).read()\n")},
    {"id": "cmd-sh-c", "class": "command_injection", "vulnerable": True,
     "app": _cmd("    subprocess.run([\"sh\", \"-c\", \"echo \" + text], check=False)\n")},
    {"id": "cmd-list", "class": "command_injection", "vulnerable": False,
     "app": _cmd("    subprocess.run([\"echo\", text], check=False)\n")},
    {"id": "cmd-quote", "class": "command_injection", "vulnerable": False,
     "app": _cmd("    subprocess.run(\"echo \" + shlex.quote(text), shell=True, check=False)\n",
                 head="import shlex\nimport subprocess\n\n\n")},
]

TESTS = {"sqli": SQLI_TEST, "path_traversal": PATH_TEST, "command_injection": CMD_TEST}
TARGETS = {"sqli": SQLI_TARGET, "path_traversal": PATH_TARGET, "command_injection": CMD_TARGET}
#: the safe twin whose code is the proper fix for every vulnerable case of its class
FIX_WITH = {"sqli": "sqli-param", "path_traversal": "path-realpath", "command_injection": "cmd-list"}


def by_id(case_id: str) -> dict:
    return next(c for c in CASES if c["id"] == case_id)


def files_of(case: dict) -> dict:
    return {"app.py": case["app"], "test_app.py": TESTS[case["class"]]}


def spec_of(case: dict, *, with_target: bool = True) -> dict:
    spec = {"entry": "app", "files": ["app.py", "test_app.py"],
            "exports": [{"sqli": "find", "path_traversal": "read", "command_injection": "echo"}[case["class"]]],
            "tests": ["test_app.py"]}
    if with_target:
        spec["exploit_targets"] = [TARGETS[case["class"]]]
    return spec