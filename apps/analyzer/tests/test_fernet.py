# -*- coding: utf-8 -*-
"""Tests for Fernet secret encryption (v6.1 Block 4)."""
import pytest
from cryptography.fernet import Fernet, InvalidToken

from src.security import fernet


@pytest.fixture(autouse=True)
def _set_key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())
    fernet._fernet = None
    yield
    fernet._fernet = None


def test_encrypt_returns_bytes():
    assert isinstance(fernet.encrypt("secret"), bytes)


def test_decrypt_returns_original():
    pt = "hello world"
    assert fernet.decrypt(fernet.encrypt(pt)) == pt


def test_encrypt_is_non_deterministic():
    c1 = fernet.encrypt("same")
    c2 = fernet.encrypt("same")
    assert c1 != c2


def test_decrypt_wrong_key_fails():
    ct = fernet.encrypt("secret")
    other = Fernet(Fernet.generate_key())
    with pytest.raises(InvalidToken):
        other.decrypt(ct)


def test_decrypt_corrupted_fails():
    ct = fernet.encrypt("secret")
    corrupted = ct[:-1] + bytes([ct[-1] ^ 0xFF])
    with pytest.raises(InvalidToken):
        fernet.decrypt(corrupted)


def test_generate_key_format():
    key = fernet.generate_key()
    assert isinstance(key, str)
    assert len(key) == 44
    Fernet(key)  # must not raise


def test_encrypt_empty_string():
    assert fernet.decrypt(fernet.encrypt("")) == ""


def test_encrypt_unicode():
    pt = "ключ 中国"
    assert fernet.decrypt(fernet.encrypt(pt)) == pt
