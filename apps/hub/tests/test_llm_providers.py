"""The hub talks to the model the operator chose: Anthropic, an OpenAI-compatible server (local or not) or none.

Every test here runs against a throwaway server on 127.0.0.1 or against no network at all. The things that
matter, and are checked: the request goes to the configured address and nowhere else, a key is sent only when
there is one, what the client typed is still redacted before it leaves for a local model, a missing or broken
setting says what to change, and "no model" really sends nothing.
"""
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

import pytest

from hub import chat, llm, meter, proposal

PROPOSAL = {"verdict": "SAFE", "summary": "fine", "findings": [], "patch": {}, "questions": [], "proof": []}
CARD = "4111 1111 1111 1111"          # the standard test number, passes the Luhn check


def openai_answer(content, finish="stop", usage=None):
    return {"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish}],
            "usage": usage if usage is not None else {"prompt_tokens": 11, "completion_tokens": 7}}


def anthropic_answer(text, stop="end_turn"):
    return {"content": [{"type": "text", "text": text}], "stop_reason": stop,
            "usage": {"input_tokens": 5, "output_tokens": 3}}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        self.server.seen.append({"path": self.path, "body": body,
                                 "headers": {k.lower(): v for k, v in self.headers.items()}})
        status, payload = self.server.respond(self.path, body)
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):
        pass


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("VISHAP_HUB_LLM_PROVIDER", "VISHAP_HUB_LLM_URL", "VISHAP_HUB_LLM_MODEL", "VISHAP_HUB_LLM_KEY",
                 "VISHAP_HUB_LLM_KEY_REQUIRED", "VISHAP_HUB_LLM_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def fake_model():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    server.seen = []
    server.respond = lambda path, body: (500, {"error": "not set up"})
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server.url = f"http://127.0.0.1:{server.server_port}"
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def hosts(monkeypatch):
    """Every host a model call was made to, recorded while the real call still happens."""
    seen = []
    real = urllib.request.urlopen

    def spy(request, *args, **kwargs):
        seen.append(urlparse(request.full_url).hostname)
        return real(request, *args, **kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", spy)
    return seen


def use_openai(monkeypatch, server, model="llama3"):
    monkeypatch.setenv("VISHAP_HUB_LLM_PROVIDER", "openai")
    monkeypatch.setenv("VISHAP_HUB_LLM_URL", server.url + "/v1")
    monkeypatch.setenv("VISHAP_HUB_LLM_MODEL", model)


# an OpenAI-compatible server -----------------------------------------------------------------------------------

def test_a_local_openai_compatible_server_answers_without_a_key_and_nothing_goes_elsewhere(monkeypatch, fake_model, hosts):
    use_openai(monkeypatch, fake_model)
    fake_model.respond = lambda path, body: (200, openai_answer(json.dumps(PROPOSAL)))
    result = proposal.propose(material="x = 1")
    assert result["ok"] is True and result["verdict"] == "SAFE" and result["model"] == "llama3"
    call = fake_model.seen[0]
    assert call["path"] == "/v1/chat/completions"
    assert "authorization" not in call["headers"]                     # a local model asks for no key
    assert call["body"]["messages"][0]["role"] == "system"
    assert call["body"]["max_tokens"] == 4000 and "system" not in call["body"]
    assert set(hosts) == {"127.0.0.1"}                                 # the only address that was contacted


def test_a_key_is_sent_as_a_bearer_token_when_there_is_one(monkeypatch, fake_model):
    use_openai(monkeypatch, fake_model)
    fake_model.respond = lambda path, body: (200, openai_answer(json.dumps(PROPOSAL)))
    proposal.propose(material="x = 1", api_key="sekret")
    assert fake_model.seen[0]["headers"]["authorization"] == "Bearer sekret"


def test_what_the_client_typed_is_redacted_before_it_reaches_a_local_model_too(monkeypatch, fake_model):
    use_openai(monkeypatch, fake_model)
    fake_model.respond = lambda path, body: (200, openai_answer(json.dumps(PROPOSAL)))
    proposal.propose(material=f"card = '{CARD}'", spec=f"pay with {CARD}", question=f"is {CARD} stored?")
    sent = json.dumps(fake_model.seen[0]["body"])
    assert CARD not in sent and "4111111111111111" not in sent


def test_the_chat_speaks_to_the_same_server(monkeypatch, fake_model, hosts):
    use_openai(monkeypatch, fake_model)
    fake_model.respond = lambda path, body: (200, openai_answer("Hello from the local model."))
    result = chat.reply("hello", [], "")
    assert result["ok"] is True and result["text"] == "Hello from the local model."
    body = fake_model.seen[0]["body"]
    assert body["messages"][0]["role"] == "system" and body["messages"][-1] == {"role": "user", "content": "hello"}
    assert set(hosts) == {"127.0.0.1"}


def test_the_providers_token_counts_reach_the_meter(monkeypatch, fake_model):
    use_openai(monkeypatch, fake_model)
    fake_model.respond = lambda path, body: (200, openai_answer(json.dumps(PROPOSAL)))
    with meter.metering() as m:
        proposal.propose(material="x = 1")
    assert m.measured()["input"] == 11 and m.measured()["output"] == 7


def test_an_answer_cut_by_the_limit_is_named_as_such(monkeypatch, fake_model):
    use_openai(monkeypatch, fake_model)
    fake_model.respond = lambda path, body: (200, openai_answer('{"verdict": "SA', finish="length"))
    result = proposal._call("", "", "material", "", "")
    assert result["ok"] is False and "token limit" in result["error"]
    fake_model.respond = lambda path, body: (200, openai_answer("half a sent", finish="length"))
    reply = chat.reply("hello", [], "")
    assert reply["ok"] is True and reply["truncated"] is True


def test_a_refusal_from_the_server_is_reported_not_raised(monkeypatch, fake_model):
    use_openai(monkeypatch, fake_model)
    fake_model.respond = lambda path, body: (401, {"error": "bad key"})
    result = proposal.propose(material="x = 1")
    assert result["ok"] is False and "HTTP 401" in result["error"]


# the Anthropic dialect, at an address the operator chose --------------------------------------------------------

def test_the_anthropic_dialect_goes_to_the_configured_gateway(monkeypatch, fake_model, hosts):
    monkeypatch.setenv("VISHAP_HUB_LLM_URL", fake_model.url)
    fake_model.respond = lambda path, body: (200, anthropic_answer(json.dumps(PROPOSAL)))
    result = proposal.propose(material="x = 1", api_key="k")
    assert result["ok"] is True
    call = fake_model.seen[0]
    assert call["path"] == "/v1/messages"
    assert call["headers"]["x-api-key"] == "k" and call["headers"]["anthropic-version"] == "2023-06-01"
    assert call["body"]["model"] == llm.DEFAULT_ANTHROPIC_MODEL and call["body"]["system"]
    assert set(hosts) == {"127.0.0.1"}                                 # api.anthropic.com was not contacted


def test_the_default_is_still_anthropic_and_still_needs_a_key():
    current = llm.settings()
    assert (current.provider, current.base_url) == ("anthropic", "https://api.anthropic.com")
    assert current.key_required is True
    assert proposal.propose(material="x = 1")["key_required"] is True
    assert chat.reply("hello", [], "")["key_required"] is True


# no model -------------------------------------------------------------------------------------------------------

def test_no_model_sends_nothing_anywhere(monkeypatch, hosts):
    monkeypatch.setenv("VISHAP_HUB_LLM_PROVIDER", "none")
    monkeypatch.setenv("VISHAP_HUB_LLM_KEY", "a key that must not be used")
    result = proposal.propose(material="x = 1")
    assert result["ok"] is False and result["model_disabled"] is True
    talk = chat.reply("hello", [], "")
    assert talk["ok"] is True and talk["model"] == "local" and "without a language model" in talk["text"]
    assert hosts == []
    assert llm.available("a key") is False                             # a request does not spend a model budget


# settings that cannot work say what to change ---------------------------------------------------------------------

def test_the_openai_provider_has_no_default_model(monkeypatch, hosts):
    monkeypatch.setenv("VISHAP_HUB_LLM_PROVIDER", "openai")
    monkeypatch.setenv("VISHAP_HUB_LLM_URL", "http://127.0.0.1:1/v1")
    result = proposal.propose(material="x = 1")
    assert result["ok"] is False and "VISHAP_HUB_LLM_MODEL" in result["error"]
    assert chat.reply("hello", [], "")["ok"] is False
    assert hosts == []


def test_an_unknown_provider_or_a_bad_address_is_refused(monkeypatch, hosts):
    monkeypatch.setenv("VISHAP_HUB_LLM_PROVIDER", "gemini")
    assert "VISHAP_HUB_LLM_PROVIDER" in proposal.propose(material="x")["error"]
    monkeypatch.setenv("VISHAP_HUB_LLM_PROVIDER", "openai")
    monkeypatch.setenv("VISHAP_HUB_LLM_MODEL", "m")
    monkeypatch.setenv("VISHAP_HUB_LLM_URL", "file:///etc/passwd")
    assert "VISHAP_HUB_LLM_URL" in proposal.propose(material="x")["error"]
    assert hosts == []


def test_a_remote_server_needs_a_key_a_local_one_does_not(monkeypatch):
    monkeypatch.setenv("VISHAP_HUB_LLM_PROVIDER", "openai")
    monkeypatch.setenv("VISHAP_HUB_LLM_MODEL", "m")
    monkeypatch.setenv("VISHAP_HUB_LLM_URL", "https://llm.example.invalid/v1")
    assert llm.available("") is False and llm.available("k") is True
    for local in ("http://localhost:11434/v1", "http://127.0.0.1:8000/v1", "http://[::1]:8000/v1",
                  "http://host.docker.internal:11434/v1"):
        monkeypatch.setenv("VISHAP_HUB_LLM_URL", local)
        assert llm.available("") is True, local
    monkeypatch.setenv("VISHAP_HUB_LLM_KEY_REQUIRED", "1")             # the operator can insist
    assert llm.available("") is False
    monkeypatch.setenv("VISHAP_HUB_LLM_URL", "https://gateway.corp.invalid/v1")
    monkeypatch.setenv("VISHAP_HUB_LLM_KEY_REQUIRED", "0")             # or waive it for a gateway that authenticates itself
    assert llm.available("") is True


def test_the_address_is_the_operators_not_the_clients(monkeypatch, fake_model, hosts):
    """A request body can carry a key and a model name; it cannot carry an address."""
    monkeypatch.setenv("VISHAP_HUB_LLM_URL", fake_model.url)
    fake_model.respond = lambda path, body: (200, anthropic_answer("hi"))
    chat.reply("hello", [], "k", model="some-model")
    assert set(hosts) == {"127.0.0.1"} and fake_model.seen[0]["body"]["model"] == "some-model"


# the request each dialect builds --------------------------------------------------------------------------------

def test_request_shapes():
    anthropic = llm.Settings("anthropic", "https://gateway.invalid/v1", "m", True)
    assert llm.endpoint(anthropic) == "https://gateway.invalid/v1/messages"
    _url, headers, payload = llm.request_parts(anthropic, "", "sys", [{"role": "user", "content": "q"}], 10)
    assert "x-api-key" not in headers and payload["system"] == "sys" and payload["max_tokens"] == 10

    hosted = llm.Settings("openai", "https://api.openai.com/v1", "gpt", True)
    _, _, payload = llm.request_parts(hosted, "k", "sys", [], 10)
    assert payload["max_completion_tokens"] == 10 and "max_tokens" not in payload

    other = llm.Settings("openai", "http://127.0.0.1:11434/v1", "llama", False)
    _, _, payload = llm.request_parts(other, "", "sys", [], 10)
    assert payload["max_tokens"] == 10 and payload["messages"][0] == {"role": "system", "content": "sys"}


def test_a_reply_in_either_dialect_is_read_whatever_its_shape():
    anthropic = llm.Settings("anthropic", "u", "m", True)
    openai = llm.Settings("openai", "u", "m", False)
    assert llm.read_reply(anthropic, anthropic_answer("a")).text == "a"
    assert llm.read_reply(openai, openai_answer([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}])).text == "a\nb"
    for odd in (None, [], {}, {"choices": []}, {"choices": [None]}, {"choices": [{"message": {"content": None}}]}):
        assert llm.read_reply(openai, odd).text == ""
        assert llm.read_reply(anthropic, odd).text == ""


def test_deepseek_is_a_preset_with_a_fixed_address_and_its_own_default_model(monkeypatch):
    from hub import llm
    monkeypatch.setenv("VISHAP_HUB_LLM_PROVIDER", "deepseek")
    for name in ("VISHAP_HUB_LLM_URL", "VISHAP_HUB_LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    s = llm.settings()
    assert (s.provider, s.base_url, s.model) == ("openai", "https://api.deepseek.com", "deepseek-flash")
    assert llm.endpoint(s) == "https://api.deepseek.com/chat/completions"


def test_a_visitor_can_pick_deepseek_by_name_but_never_by_address(monkeypatch):
    from hub import llm
    monkeypatch.setenv("VISHAP_HUB_LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("VISHAP_HUB_LLM_URL", raising=False)
    s = llm.settings(preset="deepseek")
    assert s.base_url == "https://api.deepseek.com" and s.provider == "openai"
    assert llm.settings(preset="http://evil.example/v1").base_url == "https://api.anthropic.com"
    # an operator who set their own address is not overridden by the page
    monkeypatch.setenv("VISHAP_HUB_LLM_URL", "https://gateway.example/v1")
    assert llm.settings(preset="deepseek").base_url == "https://gateway.example/v1"


def test_the_operators_key_is_never_sent_to_a_provider_the_operator_did_not_choose(monkeypatch):
    from hub import llm
    monkeypatch.setenv("VISHAP_HUB_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("VISHAP_HUB_LLM_KEY", "operator-secret")
    assert llm.key_for("", "deepseek") == ""
    assert llm.key_for("their-own", "deepseek") == "their-own"
    assert llm.key_for("", "") == "operator-secret"
    assert llm.key_for("", "anthropic") == "operator-secret"
    assert llm.available("", "deepseek") is False
    assert llm.available("their-own", "deepseek") is True


def test_chatgpt_and_ollama_are_presets_with_fixed_addresses(monkeypatch):
    from hub import llm
    monkeypatch.setenv("VISHAP_HUB_LLM_PROVIDER", "anthropic")
    for name in ("VISHAP_HUB_LLM_URL", "VISHAP_HUB_LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VISHAP_HUB_HOST", "127.0.0.1")
    gpt = llm.settings(preset="openai")
    assert gpt.base_url == "https://api.openai.com/v1" and gpt.key_required and gpt.model == llm.DEFAULT_OPENAI_MODEL
    ollama = llm.settings(preset="ollama")
    assert ollama.base_url == "http://localhost:11434/v1" and not ollama.key_required
    assert llm.settings("my-model", "ollama").model == "my-model"
    assert llm.available("", "ollama") is True


def test_the_ollama_pick_is_ignored_when_the_hub_is_not_bound_to_this_machine(monkeypatch):
    from hub import llm
    monkeypatch.setenv("VISHAP_HUB_LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("VISHAP_HUB_LLM_URL", raising=False)
    monkeypatch.setenv("VISHAP_HUB_HOST", "0.0.0.0")
    assert llm.settings(preset="ollama").base_url == "https://api.anthropic.com"
