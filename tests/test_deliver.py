import dataclasses
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import EXAMPLE, write_spec
from tests.test_verify import DOLLAR_BUG, GOOD, TODAY
from tests.test_verify import TESTS as TESTS_5

from generator import deliver as deliver_mod
from generator.build import check_build
from generator.deliver import DeliverError, deliver, gate_check, rollback
from generator.design import design
from generator.intake import requirements_from
from generator.spec import load_spec
from generator.verify import verify

NOW = dt.datetime(2026, 10, 28, 12, 0, 0)

# The example spec has no 400/422 output, so Design reports a critical gap.
# These tests need a spec without open gaps.
TESTS = TESTS_5 + """
    def test_r6(self):
        self.assertEqual(call({"name": "bad!"}), 400)
"""
CLEAN_SPEC = write_spec(EXAMPLE.read_text(encoding="utf-8").replace(
    '  - status: 404\n    when: "no such user"\n',
    '  - status: 404\n    when: "no such user"\n  - status: 400\n    when: "invalid name"\n'))


def prepare(code=GOOD, *, spec_path=CLEAN_SPEC):
    spec = load_spec(spec_path)
    reqs = requirements_from(spec)
    d = design(spec, reqs)
    files = {"handlers/__init__.py": "", "handlers/user.py": code,
             "tests/__init__.py": "", "tests/test_user.py": TESTS}
    b = check_build(d, reqs, files)
    v = verify(spec, reqs, d, files, today=TODAY)
    return dict(spec=spec, requirements=reqs, design=d, files=files, build=b, verify=v)


def tree(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


class TmpCase(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.root = Path(self._t.name) / "out"


class GateTests(unittest.TestCase):
    def test_good_run_is_not_blocked(self):
        p = prepare()
        g = gate_check(p["design"], p["build"], p["verify"])
        self.assertFalse(g.blocked, g.reasons)

    def test_failed_high_requirement_blocks(self):
        p = prepare(DOLLAR_BUG)
        g = gate_check(p["design"], p["build"], p["verify"])
        self.assertTrue(g.blocked)
        self.assertTrue(any(r.startswith("R1 (high)") for r in g.reasons))

    def test_stale_spec_blocks(self):
        p = prepare()
        v = dataclasses.replace(p["verify"], spec_stale=True, spec_age_days=208)
        g = gate_check(p["design"], p["build"], v)
        self.assertTrue(any("stale" in r for r in g.reasons))

    def test_low_coverage_blocks(self):
        p = prepare()
        v = dataclasses.replace(p["verify"], coverage_status="below", coverage_percent=61.0)
        g = gate_check(p["design"], p["build"], v)
        self.assertTrue(any("coverage 61%" in r for r in g.reasons))

    def test_skipped_coverage_does_not_block(self):
        p = prepare()
        v = dataclasses.replace(p["verify"], coverage_status="skipped", coverage_percent=None)
        self.assertFalse(gate_check(p["design"], p["build"], v).blocked)

    def test_critical_gap_blocks(self):
        p = prepare(spec_path=EXAMPLE)      # no 400/422 output: gap G1
        g = gate_check(p["design"], p["build"], p["verify"])
        self.assertTrue(any(r.startswith("open critical gap G1") for r in g.reasons), g.reasons)


class WriteTests(TmpCase):
    def test_writes_files_and_trace(self):
        res = deliver(**prepare(), out_root=self.root, now=NOW)
        self.assertTrue(res.written)
        self.assertEqual(tree(self.root), [
            ".vishap/runs/%s/manifest.json" % res.run_id,
            ".vishap/user.trace.json",
            "handlers/__init__.py", "handlers/user.py",
            "tests/__init__.py", "tests/test_user.py"])
        self.assertEqual((self.root / "handlers/user.py").read_text(encoding="utf-8"), GOOD)
        self.assertEqual([a.action for a in res.actions], ["created"] * 5)

    def test_trace_links_requirement_to_code_test_and_evidence(self):
        res = deliver(**prepare(), out_root=self.root, now=NOW)
        trace = json.loads((self.root / ".vishap/user.trace.json").read_text(encoding="utf-8"))
        r1 = trace["requirements"][0]
        self.assertEqual(r1["id"], "R1")
        self.assertEqual(r1["code"], ["handlers/user.py"])
        self.assertIn("test_r1", r1["tests"])
        self.assertEqual(r1["status"], "passed")
        self.assertFalse(trace["forced"])
        self.assertEqual(trace["run"]["id"], res.run_id)
        self.assertEqual(len(trace["spec"]["sha256"]), 64)
        self.assertEqual(len(trace["files"]["handlers/user.py"]["sha256"]), 64)

    def test_second_run_marks_unchanged_and_rewrites_trace(self):
        deliver(**prepare(), out_root=self.root, now=NOW)
        res = deliver(**prepare(), out_root=self.root, now=NOW + dt.timedelta(seconds=5))
        acts = {a.path: a.action for a in res.actions}
        self.assertEqual(acts["handlers/user.py"], "unchanged")
        self.assertEqual(acts[".vishap/user.trace.json"], "overwritten")
        self.assertEqual(res.diff, "")

    def test_dry_run_writes_nothing_and_shows_diff(self):
        res = deliver(**prepare(), out_root=self.root, dry_run=True, now=NOW)
        self.assertFalse(res.written)
        self.assertFalse(self.root.exists())
        self.assertIn("+++ b/handlers/user.py", res.diff)
        self.assertIn("--- /dev/null", res.diff)

    def test_diff_against_an_existing_file(self):
        (self.root / "handlers").mkdir(parents=True)
        (self.root / "handlers/user.py").write_text("old = 1\n", encoding="utf-8")
        res = deliver(**prepare(), out_root=self.root, dry_run=True, now=NOW)
        self.assertIn("--- a/handlers/user.py", res.diff)
        self.assertIn("-old = 1", res.diff)


class GateWriteTests(TmpCase):
    def test_gate_blocks_and_writes_nothing(self):
        res = deliver(**prepare(DOLLAR_BUG), out_root=self.root, gate=True, now=NOW)
        self.assertTrue(res.blocked)
        self.assertFalse(res.written)
        self.assertFalse(self.root.exists())
        self.assertTrue(any("R1" in r for r in res.gate.reasons))

    def test_force_writes_and_marks_the_trace(self):
        res = deliver(**prepare(DOLLAR_BUG), out_root=self.root, gate=True, force=True, now=NOW)
        self.assertTrue(res.written and res.forced)
        trace = json.loads((self.root / ".vishap/user.trace.json").read_text(encoding="utf-8"))
        self.assertTrue(trace["forced"])
        self.assertTrue(trace["gate"]["blocked"])

    def test_without_gate_bad_code_is_written_and_reported(self):
        res = deliver(**prepare(DOLLAR_BUG), out_root=self.root, now=NOW)
        self.assertTrue(res.written)
        self.assertFalse(res.blocked)
        self.assertFalse(res.forced)
        trace = json.loads((self.root / ".vishap/user.trace.json").read_text(encoding="utf-8"))
        self.assertEqual(trace["requirements"][0]["status"], "failed")

    def test_good_run_passes_the_gate_and_is_not_forced(self):
        res = deliver(**prepare(), out_root=self.root, gate=True, force=True, now=NOW)
        self.assertTrue(res.written)
        self.assertFalse(res.forced)


class SafetyTests(TmpCase):
    def with_path(self, path):
        p = prepare()
        plans = list(p["design"].files)
        plans[1] = dataclasses.replace(plans[1], path=path)
        p["design"] = dataclasses.replace(p["design"], files=tuple(plans))
        p["files"] = {**{k: v for k, v in p["files"].items() if k != "handlers/user.py"}, path: GOOD}
        return p

    def test_path_traversal_is_refused(self):
        for bad in ("../evil.py", "/etc/evil.py", "a/../../evil.py", "C:/evil.py", "a\\b.py"):
            with self.subTest(path=bad):
                with self.assertRaises(DeliverError):
                    deliver(**self.with_path(bad), out_root=self.root, now=NOW)
        self.assertFalse((self.root.parent / "evil.py").exists())

    def test_symlink_is_refused(self):
        self.root.mkdir()
        outside = Path(self._t.name) / "outside"
        outside.mkdir()
        try:
            os.symlink(outside, self.root / "handlers", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not available")
        with self.assertRaises(DeliverError):
            deliver(**prepare(), out_root=self.root, now=NOW)
        self.assertEqual(list(outside.iterdir()), [])

    def test_failure_half_way_undoes_the_run(self):
        (self.root / "handlers").mkdir(parents=True)
        (self.root / "handlers/user.py").write_text("old = 1\n", encoding="utf-8")
        real = deliver_mod._write_text
        calls = {"n": 0}

        def flaky(target, content):
            calls["n"] += 1
            if calls["n"] == 4:         # after the manifest and two files
                raise OSError("disk full")
            return real(target, content)

        with mock.patch.object(deliver_mod, "_write_text", flaky):
            with self.assertRaises(DeliverError):
                deliver(**prepare(), out_root=self.root, now=NOW)
        self.assertEqual(tree(self.root), ["handlers/user.py"])
        self.assertEqual((self.root / "handlers/user.py").read_text(encoding="utf-8"), "old = 1\n")

    def test_same_second_runs_get_different_ids(self):
        a = deliver(**prepare(), out_root=self.root, now=NOW)
        b = deliver(**prepare(DOLLAR_BUG), out_root=self.root, now=NOW)
        self.assertNotEqual(a.run_id, b.run_id)
        self.assertTrue((self.root / ".vishap/runs" / a.run_id / "manifest.json").exists())


class RollbackTests(TmpCase):
    def test_rollback_removes_created_files_and_folders(self):
        res = deliver(**prepare(), out_root=self.root, now=NOW)
        out = rollback(self.root, res.run_id)
        self.assertEqual(len(out.removed), 5)
        self.assertEqual([p for p in tree(self.root) if "runs/" not in p], [])
        self.assertFalse((self.root / "handlers").exists())

    def test_rollback_restores_overwritten_files(self):
        (self.root / "handlers").mkdir(parents=True)
        (self.root / "handlers/user.py").write_text("old = 1\n", encoding="utf-8")
        res = deliver(**prepare(), out_root=self.root, now=NOW)
        self.assertEqual((self.root / "handlers/user.py").read_text(encoding="utf-8"), GOOD)
        out = rollback(self.root, res.run_id)
        self.assertIn("handlers/user.py", out.restored)
        self.assertEqual((self.root / "handlers/user.py").read_text(encoding="utf-8"), "old = 1\n")

    def test_rollback_restores_the_previous_trace(self):
        first = deliver(**prepare(), out_root=self.root, now=NOW)
        before = (self.root / ".vishap/user.trace.json").read_text(encoding="utf-8")
        second = deliver(**prepare(DOLLAR_BUG), out_root=self.root, now=NOW + dt.timedelta(seconds=9))
        rollback(self.root, second.run_id)
        self.assertEqual((self.root / ".vishap/user.trace.json").read_text(encoding="utf-8"), before)
        self.assertEqual((self.root / "handlers/user.py").read_text(encoding="utf-8"), GOOD)
        self.assertEqual(first.run_id, json.loads(before)["run"]["id"])

    def test_refuses_when_a_file_changed_since(self):
        res = deliver(**prepare(), out_root=self.root, now=NOW)
        (self.root / "handlers/user.py").write_text("edited by hand\n", encoding="utf-8")
        with self.assertRaises(DeliverError) as cm:
            rollback(self.root, res.run_id)
        self.assertIn("handlers/user.py", str(cm.exception))
        self.assertTrue((self.root / "handlers/user.py").exists())
        rollback(self.root, res.run_id, force=True)
        self.assertFalse((self.root / "handlers/user.py").exists())

    def test_cannot_roll_back_twice(self):
        res = deliver(**prepare(), out_root=self.root, now=NOW)
        rollback(self.root, res.run_id)
        with self.assertRaises(DeliverError):
            rollback(self.root, res.run_id)

    def test_unknown_or_malicious_run_id(self):
        self.root.mkdir()
        for bad in ("nope", "../x", ""):
            with self.subTest(run=bad):
                with self.assertRaises(DeliverError):
                    rollback(self.root, bad)


if __name__ == "__main__":
    unittest.main()


class RequireCoverageTests(TmpCase):
    def skipped(self):
        p = prepare()
        v = dataclasses.replace(p["verify"], coverage_status="skipped", coverage_percent=None,
                                coverage_note="coverage is not installed")
        return p, v

    def test_skipped_coverage_blocks_only_when_required(self):
        p, v = self.skipped()
        self.assertFalse(gate_check(p["design"], p["build"], v).blocked)
        g = gate_check(p["design"], p["build"], v, require_coverage=True)
        self.assertTrue(g.blocked)
        self.assertIn("coverage was not measured (coverage is not installed)", g.reasons)

    def test_measured_coverage_passes_when_required(self):
        p = prepare()
        v = dataclasses.replace(p["verify"], coverage_status="ok", coverage_percent=91.0)
        self.assertFalse(gate_check(p["design"], p["build"], v, require_coverage=True).blocked)

    def test_deliver_passes_the_flag_through(self):
        p, v = self.skipped()
        p["verify"] = v
        res = deliver(**p, out_root=self.root, gate=True, require_coverage=True, now=NOW)
        self.assertTrue(res.blocked)
        self.assertFalse(self.root.exists())
