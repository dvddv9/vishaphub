import io
import json
import os
import unittest
from unittest import mock

from tests import helpers  # noqa: F401

from generator.observability.logging import (bind_request_id, bind_run_id, clear_context, get_logger,
                                             setup_logging)


class LoggingTests(unittest.TestCase):
    def tearDown(self):
        clear_context()
        setup_logging("WARNING")

    def capture(self, fmt="pretty", level="INFO"):
        buf = io.StringIO()
        setup_logging(level, fmt, stream=buf)
        return buf

    def test_run_id_is_in_every_line(self):
        buf = self.capture()
        bind_run_id("abc123")
        get_logger("x").info("hello")
        self.assertIn("run_id=abc123", buf.getvalue())

    def test_json_format(self):
        buf = self.capture("json")
        bind_request_id("r1")
        get_logger("x").warning("careful", extra={"fields": {"stage": "build"}})
        row = json.loads(buf.getvalue())
        self.assertEqual((row["level"], row["message"], row["request_id"], row["stage"]),
                         ("warning", "careful", "r1", "build"))

    def test_the_model_key_never_reaches_the_log(self):
        buf = self.capture()
        with mock.patch.dict(os.environ, {"CUSTOM_LLM_KEY": "plainsecretvalue"}):
            get_logger("x").error("failed with plainsecretvalue and sk-abcdefghijklmnopqrstuvwx")
        self.assertNotIn("plainsecretvalue", buf.getvalue())
        self.assertNotIn("sk-abcdefghijkl", buf.getvalue())

    def test_default_level_is_quiet(self):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LOG_LEVEL", None)
            setup_logging(stream=buf)
        get_logger("x").info("chatty")
        self.assertEqual(buf.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
