"""What the code under test may see and reach: a clean environment, paths that stay inside the deliverable,
a green run that ran something, and markers that are really markers."""
import os

import pytest

from validator.checks import behavior, conformance
from validator.engine import validate
from validator.models import Severity, Spec, Verdict


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


@pytest.fixture
def root(tmp_path):
    base = tmp_path / "deliverable"
    write(base / "calc" / "__init__.py", "def add(a, b):\n    return a + b\n")
    write(base / "test_calc.py", "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n")
    return str(base)


# the environment ---------------------------------------------------------------

def test_the_code_under_test_does_not_inherit_the_hosts_secrets(root, monkeypatch):
    monkeypatch.setenv("VISHAP_HUB_LLM_KEY", "sk-ant-should-never-be-seen")
    monkeypatch.setenv("VISHAP_HUB_DATABASE_URL", "postgresql://u:pw@host/db")
    write(os.path.join(root, "test_env.py"),
          "import os\n\n\ndef test_clean():\n"
          "    leaked = [k for k in os.environ if k.startswith('VISHAP_')]\n"
          "    assert not leaked, leaked\n")
    result = behavior.run(root, Spec(tests=["test_env.py"]))
    assert result.ok is True, [f.message for f in result.findings]


def test_the_entry_point_is_imported_without_the_hosts_secrets(root, monkeypatch):
    monkeypatch.setenv("VISHAP_HUB_LLM_KEY", "sk-ant-should-never-be-seen")
    write(os.path.join(root, "calc", "__init__.py"),
          "import os\n\nassert 'VISHAP_HUB_LLM_KEY' not in os.environ\n\n\ndef add(a, b):\n    return a + b\n")
    report = validate(root, Spec(files=["calc/__init__.py"], entry="calc", exports=["add"]))
    assert report.verdict is Verdict.PASS, [f.message for f in report.findings]


# paths that leave the deliverable ---------------------------------------------

@pytest.mark.parametrize("field,value", [
    ("files", ["../outside.txt"]),
    ("files", ["/etc/passwd"]),
    ("files", ["calc/../../outside.txt"]),
    ("files", [7]),
    ("tests", ["../outside/test_evil.py"]),
    ("tests", ["/tmp/test_evil.py"]),
    ("entry", "../.."),
    ("entry", "calc; import os"),
])
def test_a_spec_that_points_outside_the_deliverable_fails_and_runs_nothing(root, field, value):
    report = validate(root, Spec(**{field: value}))
    assert report.verdict is Verdict.FAIL
    assert report.reason and "outside" in report.reason
    assert [c.name for c in report.checks] == ["spec"]


def test_a_test_file_outside_the_deliverable_is_never_run(root, tmp_path):
    outside = tmp_path / "outside"
    marker = tmp_path / "ran.txt"
    write(outside / "test_evil.py", f"open({str(marker)!r}, 'w').write('x')\n\n\ndef test_x():\n    pass\n")
    report = validate(root, Spec(tests=["../outside/test_evil.py"]))
    assert report.verdict is Verdict.FAIL and not marker.exists()


def test_a_legitimate_nested_path_is_still_fine(root):
    write(os.path.join(root, "calc", "sub", "x.py"), "def one():\n    return 1\n")
    report = validate(root, Spec(files=["calc/sub/x.py", "test_calc.py"], entry="calc", exports=["add"],
                                 tests=["test_calc.py"]))
    assert report.verdict is Verdict.PASS and len(report.checks) == 6


# a green run that ran nothing ---------------------------------------------------

def test_tests_that_are_all_skipped_are_not_a_pass(root):
    write(os.path.join(root, "test_skip.py"),
          "import pytest\n\n\n@pytest.mark.skip(reason='later')\ndef test_a():\n    assert False\n")
    result = behavior.run(root, Spec(tests=["test_skip.py"]))
    assert result.ok is False
    assert result.findings[0].severity is Severity.HIGH and "no test passed" in result.findings[0].message


def test_one_real_pass_beside_a_skip_is_a_pass(root):
    write(os.path.join(root, "test_mix.py"),
          "import pytest\n\n\n@pytest.mark.skip(reason='later')\ndef test_a():\n    assert False\n\n\n"
          "def test_b():\n    assert True\n")
    assert behavior.run(root, Spec(tests=["test_mix.py"])).ok is True


# markers ------------------------------------------------------------------------

def test_a_todo_app_is_not_a_placeholder(root):
    write(os.path.join(root, "calc", "__init__.py"),
          "todos = []\n\n\ndef add_todo(text):\n    todos.append(text)\n    return len(todos)\n\n\n"
          "def stubborn(x):\n    return x\n")
    result = conformance.run(root, Spec(files=["calc/__init__.py"]))
    assert result.ok is True, [f.message for f in result.findings]


def test_a_marker_in_a_comment_is_still_flagged_once_with_its_line(root):
    write(os.path.join(root, "calc", "__init__.py"),
          "def add(a, b):\n    # TODO: real sum\n    # TODO: and tests\n    return a + b\n")
    result = conformance.run(root, Spec(files=["calc/__init__.py"]))
    found = [f for f in result.findings if "TODO" in f.message]
    assert len(found) == 1 and found[0].severity is Severity.LOW and found[0].location.endswith(":2")