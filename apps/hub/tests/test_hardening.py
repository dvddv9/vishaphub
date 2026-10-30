"""What a hostile or unlucky client must not be able to do to the hub's threads.

A run that raises is answered, not dropped; a body length that is not a number is a 400, not a dead socket; a
connection that goes silent is closed; and only so many runs are in flight at once.
"""
import json
import socket
import threading
import time
import unittest
from unittest import mock

from test_service import ServerCase, _Done

from hub import server


def _boom(**_kw):
    raise RuntimeError("secret detail from inside")


def _slot_comes_back(slots, seconds=3.0) -> bool:
    """The slot is given back after the reply is written, so the client can be a moment ahead of it."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if slots.acquire(blocking=False):
            return True
        time.sleep(0.02)
    return False


class RunFailureTests(ServerCase):
    def test_a_run_that_raises_is_a_500_with_no_internals(self):
        with mock.patch.object(server, "run_plan", _boom):
            status, _headers, raw = self.post("/run", {"material": "a = 1"})
        assert status == 500, raw
        body = json.loads(raw)
        assert body["ok"] is False and "secret detail" not in raw.decode()

    def test_a_stream_that_raises_says_so_without_the_exception_text(self):
        with mock.patch.object(server, "run_plan", _boom):
            status, _headers, raw = self.post("/run/stream", {"material": "a = 1"})
        text = raw.decode()
        assert status == 200 and "event: error" in text and "secret detail" not in text

    def test_a_failed_run_gives_its_slot_back(self):
        slots = threading.BoundedSemaphore(1)
        with mock.patch.object(server, "RUN_SLOTS", slots), mock.patch.object(server, "run_plan", _boom):
            self.post("/run", {"material": "a = 1"})
        assert _slot_comes_back(slots), "the slot was not released after a failed run"


class BodyLengthTests(ServerCase):
    def raw(self, request: bytes) -> bytes:
        with socket.create_connection(("127.0.0.1", self.port), timeout=5) as sock:
            sock.sendall(request)
            chunks = []
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                chunks.append(data)
        return b"".join(chunks)

    def test_a_length_that_is_not_a_number_is_a_400(self):
        reply = self.raw(b"POST /run HTTP/1.0\r\nHost: x\r\nContent-Length: abc\r\n\r\n")
        assert reply.startswith(b"HTTP/1.0 400"), reply[:80]

    def test_a_negative_length_is_a_400(self):
        reply = self.raw(b"POST /run HTTP/1.0\r\nHost: x\r\nContent-Length: -5\r\n\r\n")
        assert reply.startswith(b"HTTP/1.0 400"), reply[:80]

    def test_the_login_form_refuses_a_bad_length_too(self):
        reply = self.raw(b"POST /login HTTP/1.0\r\nHost: x\r\nContent-Length: x1\r\n\r\n")
        assert reply.startswith(b"HTTP/1.0 400"), reply[:80]


class SilentConnectionTests(ServerCase):
    def test_the_default_is_a_timeout_not_for_ever(self):
        assert server.READ_TIMEOUT > 0 and server.Handler.timeout == server.READ_TIMEOUT

    def test_a_client_that_stops_sending_is_cut_off(self):
        with mock.patch.object(server.Handler, "timeout", 0.3), \
                socket.create_connection(("127.0.0.1", self.port), timeout=5) as sock:
            # promises a body and never sends it
            sock.sendall(b"POST /run HTTP/1.1\r\nHost: x\r\nContent-Length: 100\r\n\r\n{")
            sock.settimeout(5)
            assert sock.recv(4096) == b"", "the hub kept waiting for a body that never came"


class RunSlotTests(ServerCase):
    def test_with_no_free_slot_a_run_is_a_503_and_spends_nothing(self):
        slots = threading.BoundedSemaphore(1)
        assert slots.acquire(blocking=False)
        calls = []
        with mock.patch.object(server, "RUN_SLOTS", slots), \
                mock.patch.object(server, "run_plan", lambda **kw: calls.append(kw) or _Done()):
            status, headers, raw = self.post("/run", {"material": "a = 1"})
        assert status == 503, raw
        assert {k.lower(): v for k, v in headers.items()}["retry-after"] == "5"
        assert calls == [], "a refused run must not reach run_plan"

    def test_a_finished_run_gives_its_slot_back(self):
        slots = threading.BoundedSemaphore(1)
        with mock.patch.object(server, "RUN_SLOTS", slots), mock.patch.object(server, "run_plan", lambda **kw: _Done()):
            status, _headers, raw = self.post("/run", {"material": "a = 1"})
            assert status == 200, raw
            assert _slot_comes_back(slots), "the slot was not given back"

    def test_zero_turns_the_ceiling_off(self):
        with mock.patch.object(server, "RUN_SLOTS", None), mock.patch.object(server, "run_plan", lambda **kw: _Done()):
            status, _headers, raw = self.post("/run", {"material": "a = 1"})
        assert status == 200, raw


if __name__ == "__main__":
    unittest.main()
