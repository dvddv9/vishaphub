import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

from tests import helpers  # noqa: F401  (puts src on the path)
from generator.tools.analyzer import AnalyzerFinding, AnalyzerResult, parse_sarif, run_analyzer

FAKE = '''\
import json, sys
args = sys.argv[1:]
assert args[0] == "analyze"
out = args[args.index("--sarif") + 1]
mode = open(args[1], encoding="utf-8").read()
if "CRASH" in mode:
    sys.exit(2)
if "BADJSON" in mode:
    open(out, "w").write("not json")
    sys.exit(0)
results = []
if "BAD" in mode:
    results.append({"ruleId": "X1", "level": "error", "message": {"text": "bad thing"}})
results.append({"ruleId": "N1", "level": "note", "message": {"text": "fyi"}})
json.dump({"runs": [{"results": results}]}, open(out, "w"))
'''


class AnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        script = Path(self.dir.name) / "fake_vishap.py"
        script.write_text(FAKE, encoding="utf-8")
        self.cmd = f'"{sys.executable}" "{script}"'

    def test_parse_sarif(self):
        data = {"runs": [{"results": [{"ruleId": "A", "level": "error", "message": {"text": "m"}}]}]}
        self.assertEqual(parse_sarif(data, "f.py"), [AnalyzerFinding("f.py", "error", "A", "m")])
        self.assertEqual(parse_sarif({}, "f.py"), [])

    def test_clean_code_passes(self):
        res = run_analyzer({"a.py": "x = 1"}, command=self.cmd)
        self.assertEqual(res.status, "passed")
        self.assertEqual([f.level for f in res.findings], ["note"])

    def test_error_finding_fails(self):
        res = run_analyzer({"a.py": "# BAD"}, command=self.cmd)
        self.assertEqual(res.status, "failed")
        self.assertEqual(res.findings[0].rule, "X1")

    def test_crash_is_an_error_not_a_pass(self):
        res = run_analyzer({"a.py": "# CRASH"}, command=self.cmd)
        self.assertEqual(res.status, "error")
        self.assertIn("no SARIF", res.note)

    def test_bad_sarif_is_an_error(self):
        self.assertEqual(run_analyzer({"a.py": "# BADJSON"}, command=self.cmd).status, "error")

    def test_missing_command_is_skipped_and_says_so(self):
        res = run_analyzer({"a.py": "x"}, command="no-such-analyzer-command")
        self.assertEqual(res.status, "skipped")
        self.assertIn("not found", res.note)

    def test_no_files_is_skipped(self):
        self.assertEqual(run_analyzer({}, command=self.cmd).status, "skipped")

    def test_command_from_environment(self):
        os.environ["VISHAP_ANALYZER_CMD"] = self.cmd
        self.addCleanup(os.environ.pop, "VISHAP_ANALYZER_CMD", None)
        self.assertEqual(run_analyzer({"a.py": "x"}).status, "passed")

    def test_timeout(self):
        script = Path(self.dir.name) / "slow.py"
        script.write_text("import time; time.sleep(30)", encoding="utf-8")
        res = run_analyzer({"a.py": "x"}, command=f'"{sys.executable}" "{script}"', timeout=1)
        self.assertEqual(res.status, "error")
        self.assertIn("timeout", res.note)


if __name__ == "__main__":
    unittest.main()
