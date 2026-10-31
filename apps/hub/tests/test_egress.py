"""Offline mode: nothing leaves for a public address, and the settings say so before anything is tried.

The guard works on outgoing socket connections, so it is checked with real sockets: a connection to a public
address is refused before a packet is sent (the test never reaches the network - the guard raises first), a
connection to loopback works, and an allowed host is let through.
"""
import socket
import threading

import pytest

from hub import chat, egress, llm, proposal, tts

PUBLIC = "93.184.216.34"          # a public address; the guard must refuse it without contacting it


@pytest.fixture(autouse=True)
def guard(monkeypatch):
    for name in ("VISHAP_HUB_OFFLINE", "VISHAP_HUB_ALLOWED_HOSTS", "VISHAP_HUB_VOICE", "VISHAP_HUB_LLM_PROVIDER",
                 "VISHAP_HUB_LLM_URL", "VISHAP_HUB_LLM_MODEL", "VISHAP_HUB_LLM_KEY", "VISHAP_HUB_LLM_KEY_REQUIRED"):
        monkeypatch.delenv(name, raising=False)
    egress.install()
    yield
    egress.uninstall()


@pytest.fixture
def listener():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(5)
    stop = threading.Event()

    def accept():
        server.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = server.accept()
                conn.close()
            except OSError:
                pass

    thread = threading.Thread(target=accept, daemon=True)
    thread.start()
    yield server.getsockname()
    stop.set()
    thread.join(1)
    server.close()


def test_when_not_offline_the_guard_lets_everything_through(listener):
    socket.create_connection(listener, timeout=2).close()
    assert egress.url_allowed("https://api.anthropic.com") is True


def test_offline_refuses_a_public_address_before_anything_is_sent(monkeypatch):
    monkeypatch.setenv("VISHAP_HUB_OFFLINE", "1")
    with pytest.raises(egress.EgressBlocked) as info:
        socket.create_connection((PUBLIC, 80), timeout=1)
    assert PUBLIC in str(info.value) and isinstance(info.value, OSError)
    probe = socket.socket()
    with pytest.raises(egress.EgressBlocked):
        probe.connect_ex((PUBLIC, 80))
    probe.close()


def test_offline_still_reaches_this_machine_and_the_private_network(monkeypatch, listener):
    monkeypatch.setenv("VISHAP_HUB_OFFLINE", "1")
    socket.create_connection(listener, timeout=2).close()
    for inside in ("127.0.0.1", "10.1.2.3", "172.16.0.9", "192.168.1.5", "169.254.1.1", "::1", "fd00::1",
                   "localhost", "host.docker.internal"):
        assert egress.host_allowed(inside), inside
    for outside in (PUBLIC, "8.8.8.8", "2001:4860:4860::8888", "", "no-such-name.invalid"):
        assert not egress.host_allowed(outside), outside


def test_an_allowed_host_is_let_through(monkeypatch):
    monkeypatch.setenv("VISHAP_HUB_OFFLINE", "1")
    monkeypatch.setenv("VISHAP_HUB_ALLOWED_HOSTS", f"{PUBLIC}, 203.0.114.0/24, gateway.corp.invalid")
    assert egress.host_allowed(PUBLIC) and egress.host_allowed("203.0.114.77")
    assert egress.host_allowed("gateway.corp.invalid") and not egress.host_allowed("8.8.8.8")


def test_a_unix_socket_is_not_a_network_connection(monkeypatch, tmp_path):
    if not hasattr(socket, "AF_UNIX"):
        pytest.skip("no unix sockets on this platform")
    monkeypatch.setenv("VISHAP_HUB_OFFLINE", "1")
    path = str(tmp_path / "s")
    server = socket.socket(socket.AF_UNIX)
    server.bind(path)
    server.listen(1)
    client = socket.socket(socket.AF_UNIX)
    client.connect(path)
    client.close()
    server.close()


def test_the_model_settings_refuse_a_public_address_with_the_sentence_that_fixes_it(monkeypatch):
    monkeypatch.setenv("VISHAP_HUB_OFFLINE", "1")
    with pytest.raises(llm.ConfigError) as info:                       # the default is api.anthropic.com
        llm.settings()
    assert "offline mode" in str(info.value) and "VISHAP_HUB_LLM_URL" in str(info.value)
    assert llm.available("a key") is False
    assert "offline mode" in proposal.propose(material="x", api_key="k")["error"]
    assert "offline mode" in chat.reply("hello", [], "k")["error"]

    monkeypatch.setenv("VISHAP_HUB_LLM_PROVIDER", "openai")
    monkeypatch.setenv("VISHAP_HUB_LLM_MODEL", "llama3")
    monkeypatch.setenv("VISHAP_HUB_LLM_URL", "http://127.0.0.1:11434/v1")
    assert llm.settings().base_url == "http://127.0.0.1:11434/v1"
    monkeypatch.setenv("VISHAP_HUB_LLM_URL", f"https://{PUBLIC}/v1")
    with pytest.raises(llm.ConfigError):
        llm.settings()
    monkeypatch.setenv("VISHAP_HUB_ALLOWED_HOSTS", PUBLIC)             # the operator names it: now it is theirs
    assert llm.settings().model == "llama3"


def test_no_model_needs_no_address_even_offline(monkeypatch):
    monkeypatch.setenv("VISHAP_HUB_OFFLINE", "1")
    monkeypatch.setenv("VISHAP_HUB_LLM_PROVIDER", "none")
    assert llm.settings().provider == "none"


def test_the_voice_goes_off_with_offline_mode_and_with_its_own_switch(monkeypatch):
    monkeypatch.setattr(tts, "available", tts.available)               # the real function, whatever is installed
    monkeypatch.setenv("VISHAP_HUB_OFFLINE", "1")
    assert tts.available() is False and "offline" in tts.reason()
    monkeypatch.delenv("VISHAP_HUB_OFFLINE")
    monkeypatch.setenv("VISHAP_HUB_VOICE", "0")
    assert tts.available() is False and "VISHAP_HUB_VOICE" in tts.reason()


def test_the_guard_is_idempotent_and_removable(monkeypatch):
    egress.install()
    egress.install()
    monkeypatch.setenv("VISHAP_HUB_OFFLINE", "1")
    with pytest.raises(egress.EgressBlocked):
        socket.create_connection((PUBLIC, 80), timeout=1)
    egress.uninstall()
    assert not hasattr(socket.socket.connect, "__wrapped__")
