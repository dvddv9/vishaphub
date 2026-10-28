# -*- coding: utf-8 -*-
"""GitHub App JWT auth (v6.1)."""
import os
import time
from pathlib import Path

import jwt


def generate_jwt(private_key: str | None = None) -> str:
    """Generate a GitHub App JWT (RS256).

    ``private_key`` is an optional PEM string (used by tests). If omitted, the
    key path is read from ``GITHUB_PRIVATE_KEY``.
    """
    app_id = os.getenv("GITHUB_APP_ID", "")
    if not app_id:
        raise RuntimeError("GITHUB_APP_ID not set")
    if private_key is None:
        key_path = os.getenv("GITHUB_PRIVATE_KEY", "")
        if not key_path:
            raise RuntimeError("GITHUB_PRIVATE_KEY not set")
        private_key = Path(key_path).read_text(encoding="utf-8")
    now = int(time.time())
    payload = {"iat": now, "exp": now + 600, "iss": app_id}
    return jwt.encode(payload, private_key, algorithm="RS256")
