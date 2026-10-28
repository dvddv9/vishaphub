"""The harness must see http.server handlers, not only Flask routes.

A stdlib service is a service all the same: a path, a method and a body from outside.
Before this, `prove` answered «no Flask-style HTTP handlers found» and every probe on
such a file was skipped — the coverage hole was in the tool, not in the code.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tools import proof  # noqa: E402

SOURCE = '''
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path != "/run":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length)
        name = body.decode("utf-8", "replace")
        cur = sqlite3.connect(":memory:").cursor()
        cur.execute("select * from users where name = '" + name + "'")
        self.send_response(200)
        self.end_headers()


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
'''


@pytest.fixture
def service():
    # prove() takes the source, not a path — the CLI reads the file for it.
    return SOURCE


def test_handlers_are_recognised(service):
    doc = proof.prove(service, force=True)
    assert doc.get("handlers", 0) >= 2, doc.get("notes")
    assert doc.get("framework") == "http.server"


def test_paths_come_from_the_source(service):
    doc = proof.prove(service, force=True)
    routes = {r.get("route") for r in doc.get("results", [])}
    assert any("/run" in str(route) for route in routes), routes


def test_sqli_on_a_stdlib_handler_is_reproduced(service):
    doc = proof.prove(service, force=True)
    produced = [r for r in doc.get("results", []) if r.get("status") == "CONFIRMED"]
    assert produced, [(r.get("id"), r.get("status"), r.get("evidence")) for r in doc.get("results", [])]


def test_a_relative_import_does_not_hide_the_handler(tmp_path):
    # A real service imports its neighbours; a plain exec of such a file used to raise
    # ImportError and the harness then reported «no handlers» instead of probing.
    path = tmp_path / "rel.py"
    path.write_text(
        "from .helpers import ping\n"
        "from http.server import BaseHTTPRequestHandler\n\n\n"
        "class H(BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        ping()\n"
        "        self.send_response(200)\n"
        "        self.end_headers()\n",
        encoding="utf-8",
    )
    doc = proof.prove(path.read_text(encoding="utf-8"), force=True)
    assert doc.get("handlers", 0) >= 1, doc.get("notes")
