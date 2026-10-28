import json
import threading
import time
import unittest
from http.server import ThreadingHTTPServer

from tests import helpers  # noqa: F401
from tests.test_pipeline import Stub, answer
from tests.test_server import SPEC_TEXT, ServerCase
from tests.test_verify import GOOD, TODAY

from generator.api.job_store import DONE, FAILED, QUEUED, RUNNING
from generator.api.job_store_memory import MemoryJobStore
from generator.api.jobs import start_job
from generator.api.rate_limit import RUN_LOCK, RateLimiter, per_minute
from generator.config import LOOPBACK
from generator.main import make_handler
from generator.tools.report import render_markdown


class JobStoreTests(unittest.TestCase):
    def test_lifecycle_and_log_since(self):
        store = MemoryJobStore()
        job = store.create()
        self.assertEqual(job.status, QUEUED)
        store.start(job.id)
        store.append_log(job.id, "[Intake] a", "Intake")
        store.append_log(job.id, "[Design] b", "Design")
        got = store.get(job.id)
        self.assertEqual((got.status, got.stage), (RUNNING, "Design"))
        self.assertEqual(got.to_dict(1)["log"], ["[Design] b"])
        self.assertNotIn("result", got.to_dict())
        store.finish(job.id, {"x": 1}, 200)
        self.assertEqual(store.get(job.id).status, DONE)
        self.assertEqual(store.get(job.id).to_dict()["result"], {"x": 1})

    def test_error_or_http_error_is_failed(self):
        store = MemoryJobStore()
        a, b = store.create(), store.create()
        store.finish(a.id, None, 500, "boom")
        store.finish(b.id, {}, 502)
        self.assertEqual((store.get(a.id).status, store.get(b.id).status), (FAILED, FAILED))

    def test_ids_are_unguessable_and_unknown_is_none(self):
        store = MemoryJobStore()
        ids = {store.create().id for _ in range(20)}
        self.assertEqual(len(ids), 20)
        self.assertTrue(all(len(i) >= 20 for i in ids))
        self.assertIsNone(store.get("nope"))

    def test_old_finished_jobs_are_dropped_but_running_ones_are_not(self):
        store = MemoryJobStore(keep_seconds=0.0, max_jobs=3)
        old, running = store.create(), store.create()
        store.finish(old.id, {}, 200)
        store.start(running.id)
        time.sleep(0.01)
        store.create()
        self.assertIsNone(store.get(old.id))
        self.assertIsNotNone(store.get(running.id))

    def test_log_is_capped(self):
        store = MemoryJobStore()
        job = store.create()
        for i in range(800):
            store.append_log(job.id, str(i))
        self.assertEqual(len(store.get(job.id).log), 500)


class RateLimiterTests(unittest.TestCase):
    def test_window_and_keys(self):
        now = [0.0]
        lim = RateLimiter(2, 60.0, clock=lambda: now[0])
        self.assertEqual(lim.check("a"), 0.0)
        self.assertEqual(lim.check("a"), 0.0)
        self.assertGreater(lim.check("a"), 0.0)
        self.assertEqual(lim.check("b"), 0.0)           # another address has its own window
        now[0] = 61.0
        self.assertEqual(lim.check("a"), 0.0)

    def test_zero_turns_it_off(self):
        lim = RateLimiter(0)
        self.assertTrue(all(lim.check("a") == 0.0 for _ in range(100)))

    def test_env_value(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"GENERATOR_RATE_LIMIT": "7"}):
            self.assertEqual(per_minute(), 7)
        with mock.patch.dict(os.environ, {"GENERATOR_RATE_LIMIT": "junk"}):
            self.assertEqual(per_minute(), 30)


class AsyncApiTests(ServerCase):
    def wait(self, job_id, seconds=30):
        end = time.time() + seconds
        while time.time() < end:
            status, out = self.post_get(f"/api/jobs/{job_id}")
            self.assertEqual(status, 200)
            if out["status"] in ("done", "failed"):
                return out
            time.sleep(0.05)
        self.fail("job did not finish")

    def post_get(self, path, **kw):
        status, data = self.req(path, **kw)
        return status, json.loads(data)

    def test_start_poll_and_get_the_same_answer_as_sync(self):
        status, out = self.post("/api/generate/async", {"spec": SPEC_TEXT})
        self.assertEqual(status, 202, out)
        done = self.wait(out["job"])
        self.assertEqual(done["status"], "done")
        result = done["result"]
        self.assertEqual(result["verify"]["code_verdict"], "passed")
        self.assertIn("handlers/user.py", result["files"])
        self.assertTrue(any(line.startswith("[Build]") for line in done["log"]))
        self.assertIn("# Vishap Generator report", result["markdown"])
        self.assertEqual(done["stage"], "Deliver")
        self.assertFalse(RUN_LOCK.locked())

    def test_since_returns_only_new_lines(self):
        _, out = self.post("/api/generate/async", {"spec": SPEC_TEXT})
        done = self.wait(out["job"])
        status, rest = self.post_get(f"/api/jobs/{out['job']}?since={done['log_total'] - 1}")
        self.assertEqual(len(rest["log"]), 1)

    def test_bad_request_makes_no_job(self):
        status, out = self.post("/api/generate/async", {"spec": ""})
        self.assertEqual(status, 400)
        self.assertNotIn("job", out)
        self.assertFalse(RUN_LOCK.locked())

    def test_unknown_job_is_404(self):
        self.assertEqual(self.req("/api/jobs/nope")[0], 404)

    def test_a_run_in_progress_gives_429(self):
        RUN_LOCK.acquire()
        try:
            self.assertEqual(self.post("/api/generate/async", {"spec": SPEC_TEXT})[0], 429)
        finally:
            RUN_LOCK.release()

    def test_response_has_a_request_id(self):
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health") as r:
            self.assertEqual(len(r.headers["X-Request-Id"]), 8)


class JobFailureTests(unittest.TestCase):
    def test_a_crashing_run_still_finishes_the_job_and_frees_the_lock(self):
        def boom(path, **kw):
            raise RuntimeError("model library crashed")
        store = MemoryJobStore()
        job_id = start_job({"spec": SPEC_TEXT}, store, run=boom)
        end = time.time() + 10
        while time.time() < end and store.get(job_id).status not in (DONE, FAILED):
            time.sleep(0.02)
        job = store.get(job_id)
        self.assertEqual(job.status, FAILED)
        self.assertIn("model library crashed", job.error)
        time.sleep(0.05)
        self.assertFalse(RUN_LOCK.locked())


class TokenAndLimitTests(unittest.TestCase):
    def serve(self, token, limit):
        handler = make_handler(token, set(LOOPBACK), limiter=RateLimiter(limit),
                               run_kwargs={"chat_fn": Stub(answer(GOOD)), "analyzer": None, "today": TODAY})
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (httpd.shutdown(), httpd.server_close()))
        return httpd.server_address[1]

    def call(self, port, path, body=None, headers=None):
        import urllib.error
        import urllib.request
        data = json.dumps(body).encode() if body is not None else None
        h = {"Content-Type": "application/json", **(headers or {})} if data else (headers or {})
        try:
            with urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                                               headers=h)) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_jobs_need_the_token(self):
        port = self.serve("tok", 100)
        self.assertEqual(self.call(port, "/api/jobs/x")[0], 401)
        self.assertEqual(self.call(port, "/api/jobs/x", headers={"Authorization": "Bearer tok"})[0], 404)

    def test_over_the_limit_gives_429_with_retry_after(self):
        port = self.serve(None, 2)
        codes = [self.call(port, "/api/check", {"spec": SPEC_TEXT})[0] for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])
        status, headers, _ = self.call(port, "/api/check", {"spec": SPEC_TEXT})
        self.assertIn("Retry-After", headers)
        self.assertEqual(self.call(port, "/health")[0], 200)       # the form and health are not limited


class MarkdownTests(unittest.TestCase):
    def test_report_has_the_sections_and_is_stable(self):
        from tests.test_deliver import CLEAN_SPEC
        from generator.pipeline.orchestrator import run_pipeline
        res = run_pipeline(CLEAN_SPEC, chat_fn=Stub(answer(GOOD)), today=TODAY, analyzer=None, allow_write=False)
        md = render_markdown(res, "spec.yaml")
        for part in ("# Vishap Generator report: spec.yaml", "**Verdict:** PASSED", "## Requirements",
                     "## Gate", "## Stages", "## Provenance"):
            self.assertIn(part, md)
        self.assertEqual(md, render_markdown(res, "spec.yaml"))

    def test_error_report(self):
        from generator.pipeline.orchestrator import PipelineResult
        md = render_markdown(PipelineResult(exit_code=2, error="build: down"))
        self.assertIn("**Error:** build: down", md)


if __name__ == "__main__":
    unittest.main()
