# -*- coding: utf-8 -*-
"""Tests for GitHub App JWT (v6.1)."""
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.github_app.auth import generate_jwt

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PEM = _KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode("utf-8")


def test_jwt_generated(monkeypatch):
    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    token = generate_jwt(private_key=_PEM)
    assert isinstance(token, str)
    assert token.count(".") == 2


def test_jwt_issuer(monkeypatch):
    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    token = generate_jwt(private_key=_PEM)
    payload = jwt.decode(token, options={"verify_signature": False})
    assert payload["iss"] == "12345"


def test_jwt_expires_10min(monkeypatch):
    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    token = generate_jwt(private_key=_PEM)
    payload = jwt.decode(token, options={"verify_signature": False})
    assert payload["exp"] - payload["iat"] == 600
