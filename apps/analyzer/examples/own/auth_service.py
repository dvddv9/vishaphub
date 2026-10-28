# -*- coding: utf-8 -*-
"""User authentication service."""
import hashlib
import sqlite3


def check_password(username: str, password: str) -> bool:
    """Check user password."""
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    # BUG 1: SQL injection via f-string
    query = f"SELECT password_hash FROM users WHERE username = '{username}'"
    cursor.execute(query)
    row = cursor.fetchone()
    conn.close()
    if not row:
        return False
    stored = row[0]
    # BUG 2: timing attack — non-constant-time comparison
    return stored == hashlib.md5(password.encode()).hexdigest()


def reset_password(username: str, new_password: str) -> None:
    """Reset password."""
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    # BUG 3: no validation, no rate limit, MD5
    new_hash = hashlib.md5(new_password.encode()).hexdigest()
    cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?",
                   (new_hash, username))
    conn.commit()
    conn.close()
