import tempfile
import threading
import unittest
from pathlib import Path

from tests import helpers  # noqa: F401

from generator.storage.history import (add_entry, clear_history, find_done_by_hash, history_path,
                                       load_history, mark_rolled_back)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.root = Path(self._t.name)

    def test_empty_and_broken_files_read_as_empty(self):
        self.assertEqual(load_history(self.root), [])
        history_path(self.root).parent.mkdir(parents=True)
        history_path(self.root).write_text("{not json", encoding="utf-8")
        self.assertEqual(load_history(self.root), [])

    def test_add_stamps_and_keeps_order(self):
        add_entry(self.root, {"run_id": "a"})
        add_entry(self.root, {"run_id": "b"})
        entries = load_history(self.root)
        self.assertEqual([e["run_id"] for e in entries], ["a", "b"])
        self.assertIn("timestamp", entries[0])

    def test_find_done_needs_passed_written_and_not_rolled_back(self):
        add_entry(self.root, {"run_id": "a", "spec_sha256": "s", "verdict": "passed", "written": True})
        add_entry(self.root, {"run_id": "b", "spec_sha256": "s", "verdict": "failed", "written": True})
        add_entry(self.root, {"run_id": "c", "spec_sha256": "t", "verdict": "passed", "written": False})
        self.assertEqual(find_done_by_hash(self.root, "s")["run_id"], "a")
        self.assertIsNone(find_done_by_hash(self.root, "t"))
        self.assertIsNone(find_done_by_hash(self.root, ""))
        self.assertTrue(mark_rolled_back(self.root, "a"))
        self.assertIsNone(find_done_by_hash(self.root, "s"))
        self.assertFalse(mark_rolled_back(self.root, "zzz"))

    def test_threads_do_not_lose_entries(self):
        ts = [threading.Thread(target=add_entry, args=(self.root, {"run_id": str(i)})) for i in range(20)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(len(load_history(self.root)), 20)

    def test_clear(self):
        add_entry(self.root, {"run_id": "a"})
        self.assertEqual(clear_history(self.root), 1)
        self.assertEqual(load_history(self.root), [])


if __name__ == "__main__":
    unittest.main()
