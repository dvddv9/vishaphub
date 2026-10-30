import hashlib
import os
import secrets

import psycopg2


def connect():
    return psycopg2.connect(host=os.environ["DB_HOST"], user="app",
                            password=os.environ["DB_PASSWORD"], dbname="shop")


def reset_token() -> str:
    return secrets.token_urlsafe(32)


def hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    salt = salt or os.urandom(16)
    return salt, hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
