"""Submitted code that reaches for the network must fail, and the failure must be shown, not assumed.

Each case lists a way out and a server that would see it. The control run switches the guard off and
the very same code connects: without it these tests could pass on a machine where nothing was ever
listening.
"""
import os
import socket
import threading

import pytest

from validator import safe
from validator.checks import behavior, contract
from validator.engine import validate
from validator.models import Spec, Verdict


class Listener:
    """A TCP server on loopback that counts who got through."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self.accepted = 0
        self._stop = False
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    def _loop(self):
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                continue
            self.accepted += 1
            conn.close()

    def close(self):
        self._stop = True
        self._t.join(2)
        self.sock.close()


@pytest.fixture
def listener():
    srv = Listener()
    yield srv
    srv.close()


@pytest.fixture
def root(tmp_path):
    return str(tmp_path)


@pytest.fixture(autouse=True)
def guard_on(monkeypatch):
    monkeypatch.delenv("VISHAP_VALIDATOR_NO_NETWORK", raising=False)
    monkeypatch.delenv("VISHAP_VALIDATOR_REQUIRE_NETNS", raising=False)
    monkeypatch.setattr(safe, "_NET_OFF", [])        # no namespace: the guard is what is under test


def write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


WAYS_OUT = {
    "create_connection": "import socket\nsocket.create_connection(('127.0.0.1', {port}), timeout=3)\n",
    "plain_socket": ("import socket\ns = socket.socket()\ns.settimeout(3)\n"
                     "s.connect(('127.0.0.1', {port}))\n"),
    "connect_ex": ("import socket\ns = socket.socket()\ns.settimeout(3)\n"
                   "assert s.connect_ex(('127.0.0.1', {port})) == 0\n"),
    "urllib": "import urllib.request\nurllib.request.urlopen('http://127.0.0.1:{port}/', timeout=3)\n",
    "udp": ("import socket\ns = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)\n"
            "s.sendto(b'x', ('127.0.0.1', {port}))\n"),
    "dns": "import socket\nsocket.getaddrinfo('example.com', 80)\n",
    "listen": "import socket\ns = socket.socket()\ns.bind(('127.0.0.1', 0))\ns.listen(1)\n",
}


def _behavior_with(root, body):
    write(os.path.join(root, "test_net.py"), f"def test_reaches_out():\n    exec({body!r})\n")
    return behavior.run(root, Spec(tests=["test_net.py"]))


@pytest.mark.parametrize("name", sorted(WAYS_OUT))
def test_code_that_reaches_for_the_network_fails_and_nothing_gets_through(root, listener, name):
    result = _behavior_with(root, WAYS_OUT[name].format(port=listener.port))
    assert result.ok is False, "the way out was open"
    assert "network is disabled" in result.findings[0].message
    assert listener.accepted == 0


@pytest.mark.parametrize("name", ["create_connection", "plain_socket", "urllib"])
def test_the_control_run_gets_through_so_the_failures_above_mean_something(root, listener, monkeypatch, name):
    monkeypatch.setenv("VISHAP_VALIDATOR_NO_NETWORK", "0")
    _behavior_with(root, WAYS_OUT[name].format(port=listener.port))
    # urllib gets a closed connection back and may raise on the empty reply; the point is the accept.
    assert listener.accepted >= 1


@pytest.mark.skipif(os.name != "posix", reason="on Windows socketpair is TCP on loopback, so the guard refuses it")
def test_a_unix_socket_still_works_for_code_that_needs_one(root):
    result = _behavior_with(root, "import socket\na, b = socket.socketpair()\na.send(b'x')\nassert b.recv(1) == b'x'\n")
    assert result.ok is True, [f.message for f in result.findings]


def test_importing_the_entry_point_cannot_reach_out_either(root, listener):
    write(os.path.join(root, "calc", "__init__.py"),
          f"import socket\nsocket.create_connection(('127.0.0.1', {listener.port}), timeout=3)\n\n\ndef add(a, b):\n    return a + b\n")
    result = contract.run(root, Spec(files=["calc/__init__.py"], entry="calc", exports=["add"]))
    assert result.ok is False
    assert listener.accepted == 0


def test_the_run_says_which_isolation_it_had(root):
    write(os.path.join(root, "test_ok.py"), "def test_ok():\n    assert True\n")
    assert behavior.run(root, Spec(tests=["test_ok.py"])).note == "network: guard"


def test_a_namespace_is_reported_as_a_namespace(monkeypatch):
    monkeypatch.setattr(safe, "_NET_OFF", ["unshare", "-n", "--"])
    assert safe.isolation() == "netns"


# a host that serves other people can refuse to run anything without a namespace -------------

def test_require_netns_refuses_to_run_anything_without_one(root, monkeypatch):
    monkeypatch.setenv("VISHAP_VALIDATOR_REQUIRE_NETNS", "1")
    marker = os.path.join(root, "ran.txt")
    write(os.path.join(root, "test_x.py"), f"open({marker!r}, 'w').write('x')\n\n\ndef test_x():\n    pass\n")
    report = validate(root, Spec(tests=["test_x.py"]))
    assert report.verdict is Verdict.FAIL
    assert "nothing was run" in report.reason
    assert not os.path.exists(marker)


def test_strict_check_refuses_when_only_the_python_guard_is_available(root, monkeypatch):
    """The public endpoint policy must not mistake a Python guard for process isolation."""
    monkeypatch.setattr(safe, "_NET_OFF", [])
    marker = os.path.join(root, "ran.txt")
    write(os.path.join(root, "test_x.py"), f"open({marker!r}, 'w').write('x')\n\n\ndef test_x():\n    pass\n")
    report = validate(root, Spec(tests=["test_x.py"]), require_netns=True)
    assert report.verdict is Verdict.FAIL
    assert "no network namespace" in report.reason
    assert not os.path.exists(marker)


def test_behavior_report_records_network_isolation_level(root):
    write(os.path.join(root, "test_ok.py"), "def test_ok():\n    assert True\n")
    result = behavior.run(root, Spec(tests=["test_ok.py"]))
    assert result.note == "network: guard"


def test_require_netns_lets_a_host_with_a_namespace_run(monkeypatch):
    monkeypatch.setenv("VISHAP_VALIDATOR_REQUIRE_NETNS", "1")
    monkeypatch.setattr(safe, "_NET_OFF", ["unshare", "-n", "--"])
    assert safe.refusal() == ""
