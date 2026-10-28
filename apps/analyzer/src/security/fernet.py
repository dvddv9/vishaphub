# -*- coding: utf-8 -*-
"""Fernet secret encryption (v6.1 Block 4).

Encrypts secret values (API keys) before persisting them; decrypts on read.
Requires FERNET_KEY env var. Raises RuntimeError at call time (not import)
when the key is missing, so the app can import safely without a key.
"""
import os

from cryptography.fernet import Fernet

_fernet: Fernet | None = None


def generate_key() -> str:
    """Return a new URL-safe base64 Fernet key (44 characters)."""
    return Fernet.generate_key().decode("utf-8")


def is_configured() -> bool:
    """True if FERNET_KEY is present."""
    return bool(os.getenv("FERNET_KEY", ""))


def get_fernet() -> Fernet:
    """Return a lazy singleton Fernet instance (reads FERNET_KEY from env)."""
    global _fernet
    if _fernet is None:
        key = os.getenv("FERNET_KEY", "")
        if not key:
            raise RuntimeError("FERNET_KEY not set")
        _fernet = Fernet(key.encode("utf-8"))
    return _fernet


def encrypt(plaintext: str) -> bytes:
    """Encrypt a string, returning bytes."""
    return get_fernet().encrypt(plaintext.encode("utf-8"))


def decrypt(ciphertext: bytes) -> str:
    """Decrypt bytes, returning the original string."""
    return get_fernet().decrypt(ciphertext).decode("utf-8")
