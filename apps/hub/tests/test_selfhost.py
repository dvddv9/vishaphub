"""`vishap-hub init / doctor / serve`: the settings file, and what each command does with it."""
import argparse
import os

import pytest

from hub import cli, selfhost


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("VISHAP_HUB_HOME", str(tmp_path))
    saved = dict(os.environ)                      # load() writes into the environment: put it back afterwards
    for name in selfhost.KEYS:
        os.environ.pop(name, None)
    yield tmp_path
    os.environ.clear()
    os.environ.update(saved)


def args(**kw):
    base = {"provider": None, "url": "", "model": "", "key": None, "offline": None, "isolation": None,
            "worker_image": "", "port": 0, "force": False}
    base.update(kw)
    return argparse.Namespace(**base)


def test_init_writes_a_private_file(home):
    assert selfhost.init(args(), answers=["openai", "http://localhost:11434/v1", "llama3.1", "", "n", "host"]) == 0
    text = (home / "config.env").read_text(encoding="utf-8")
    assert "VISHAP_HUB_LLM_PROVIDER=openai" in text and "VISHAP_HUB_LLM_MODEL=llama3.1" in text
    assert "VISHAP_HUB_ISOLATION=host" in text and "VISHAP_HUB_HOST=127.0.0.1" in text
    assert "VISHAP_HUB_LLM_KEY" not in text            # an empty key is not written
    if os.name == "posix":
        assert (home / "config.env").stat().st_mode & 0o077 == 0


def test_init_does_not_replace_without_force(home):
    selfhost.init(args(provider="none", isolation="host"), answers=[])
    before = (home / "config.env").read_text(encoding="utf-8")
    assert selfhost.init(args(provider="anthropic", key="k", isolation="auto"), answers=[]) == 1
    assert (home / "config.env").read_text(encoding="utf-8") == before


def test_offline_turns_the_voice_off(home):
    selfhost.init(args(provider="none", offline=True, isolation="host"), answers=[])
    values = selfhost.parse((home / "config.env").read_text(encoding="utf-8"))
    assert values["VISHAP_HUB_OFFLINE"] == "1" and values["VISHAP_HUB_VOICE"] == "0"


def test_unknown_choices_are_refused(home):
    with pytest.raises(SystemExit):
        selfhost.wizard(args(provider="none", isolation="dokcer"), answers=[])


def test_environment_wins_over_the_file(home, monkeypatch):
    (home / "config.env").write_text("VISHAP_HUB_LLM_PROVIDER=none\nPORT=9000\nOTHER=1\n", encoding="utf-8")
    monkeypatch.setenv("VISHAP_HUB_LLM_PROVIDER", "anthropic")
    env = dict(os.environ)
    selfhost.load(env)
    assert env["VISHAP_HUB_LLM_PROVIDER"] == "anthropic" and env["PORT"] == "9000" and "OTHER" not in env


def test_doctor_flags_a_broken_setup(home, monkeypatch, capsys):
    (home / "config.env").write_text("VISHAP_HUB_LLM_PROVIDER=openai\nVISHAP_HUB_ISOLATION=docker\n", encoding="utf-8")
    assert selfhost.doctor() == 1
    out = capsys.readouterr().out
    assert "FAIL model settings" in out and "FAIL worker image" in out


def test_doctor_is_quiet_about_a_local_server_without_a_key(home, monkeypatch, capsys):
    (home / "config.env").write_text("VISHAP_HUB_LLM_PROVIDER=openai\nVISHAP_HUB_LLM_URL=http://localhost:11434/v1\n"
                                     "VISHAP_HUB_LLM_MODEL=m\nVISHAP_HUB_ISOLATION=host\n", encoding="utf-8")
    assert selfhost.doctor() == 0
    assert "FAIL" not in capsys.readouterr().out


def test_serve_refuses_a_broken_config(home, monkeypatch, capsys):
    (home / "config.env").write_text("VISHAP_HUB_ISOLATION=dokcer\n", encoding="utf-8")
    assert selfhost.serve() == 2
    assert "dokcer" in capsys.readouterr().err


def test_cli_routes_the_new_commands(home, monkeypatch):
    assert cli.main(["init", "--provider", "none", "--online", "--isolation", "host"]) == 0
    assert cli.main(["doctor"]) in (0, 1)
