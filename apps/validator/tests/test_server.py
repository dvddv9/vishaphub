"""POST /check runs someone else's tests: closed by default, authenticated before the body is read, bounded."""
import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from validator import server
from validator.models import Report, Verdict

TOKEN = "t" * 32
BODY = {"files": {"calc/__init__.py": "def add(a, b):\n    return a + b\n",
                  "test_calc.py": "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"},
        "spec": {"files": ["calc/__init__.py", "test_calc.py"], "entry": "calc", "exports": ["add"],
                 "tests": ["test_calc.py"]}}


@pytest.fixture
def port():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def call(port, body=None, token=None, path="/check", method="POST"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    headers = {"content-type": "application/json"}
    if token is not None:
        headers["authorization"] = "Bearer " + token
    payload = json.dumps(body).encode() if body is not None else None
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    data = json.loads(resp.read().decode() or "{}")
    conn.close()
    return resp.status, data


def test_check_is_closed_until_a_token_is_configured(port, monkeypatch):
    monkeypatch.delenv(server.TOKEN_ENV, raising=False)
    status, data = call(port, BODY, token=TOKEN)
    assert status == 503 and "disabled" in data["error"]


def test_a_short_token_does_not_open_it(port, monkeypatch):
    monkeypatch.setenv(server.TOKEN_ENV, "short")
    assert call(port, BODY, token="short")[0] == 503


def test_without_the_token_or_with_a_wrong_one_nothing_runs(port, monkeypatch):
    monkeypatch.setenv(server.TOKEN_ENV, TOKEN)
    assert call(port, BODY)[0] == 401
    assert call(port, BODY, token="x" * 32)[0] == 401


def test_the_right_token_runs_the_check_only_with_strict_network_isolation(port, monkeypatch):
    monkeypatch.setenv(server.TOKEN_ENV, TOKEN)
    called = {}

    def fake_validate(root, spec, *, require_netns=False):
        called["require_netns"] = require_netns
        return Report(verdict=Verdict.PASS)

    monkeypatch.setattr(server, "validate", fake_validate)
    status, data = call(port, BODY, token=TOKEN)
    assert status == 200 and data["verdict"] == "PASS"
    assert called["require_netns"] is True


def test_the_body_is_not_read_for_an_anonymous_caller(port, monkeypatch):
    monkeypatch.setenv(server.TOKEN_ENV, TOKEN)
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.putrequest("POST", "/check")
    conn.putheader("content-length", "7999999")        # promises 8 MB, sends none
    conn.endheaders()
    resp = conn.getresponse()
    assert resp.status == 401
    conn.close()


def test_health_and_the_page_stay_open(port, monkeypatch):
    monkeypatch.delenv(server.TOKEN_ENV, raising=False)
    assert call(port, path="/health", method="GET")[0] == 200


def test_too_many_files_are_refused(port, monkeypatch):
    monkeypatch.setenv(server.TOKEN_ENV, TOKEN)
    many = {"files": {f"f{i}.py": "x = 1\n" for i in range(server.MAX_FILES + 1)}, "spec": {}}
    status, data = call(port, many, token=TOKEN)
    assert status == 400 and "too many files" in data["error"]


def test_a_garbage_content_length_is_a_400_not_a_crash(port, monkeypatch):
    monkeypatch.setenv(server.TOKEN_ENV, TOKEN)
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.putrequest("POST", "/check")
    conn.putheader("authorization", "Bearer " + TOKEN)
    conn.putheader("content-length", "abc")
    conn.endheaders()
    assert conn.getresponse().status == 400
    conn.close()


def test_only_so_many_checks_run_at_once(port, monkeypatch):
    monkeypatch.setenv(server.TOKEN_ENV, TOKEN)
    slots = threading.BoundedSemaphore(1)
    slots.acquire()                                    # one check is "running"
    monkeypatch.setattr(server, "SLOTS", slots)
    status, data = call(port, BODY, token=TOKEN)
    assert status == 503 and "busy" in data["error"]
