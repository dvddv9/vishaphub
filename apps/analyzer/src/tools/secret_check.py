# -*- coding: utf-8 -*-
"""Offline checks on a secret the scan has already matched.

A match on ``ghp_...`` or ``AKIA...`` says "this looks like a key". It does not say the key is real:
examples, placeholders and typos match the same pattern. These checks look at the value itself
(structure, alphabet, checksum, placeholder words) and never touch the network, so the value is
never sent anywhere. Whether a key is *live* can only be learned by using it; this module does not
and will not do that.

Policy (fail closed): a check may only annotate a finding or lower a placeholder to "low". It never
removes a finding, and a failed structural check never lowers severity - it adds a note and marks
the confidence "low", so a person decides. SAFE still needs a scan with no findings at all.

Known limit: the GitHub checksum below follows GitHub's published token format (base62 CRC32 of the
30-character entropy part, padded to 6). It has not been compared against a live token here, which
is why a mismatch is worded as "verify before dismissing".
"""
from __future__ import annotations

import re
import json
import os
import urllib.error
import urllib.request
import zlib

_B62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_AWS_ALPHABET = re.compile(r"^AKIA[A-Z2-7]{16}$")
_GH_TOKEN = re.compile(r"^gh[pousr]_([A-Za-z0-9]{36})$")
_SLACK_TOKEN = re.compile(r"^xox[baprs]-[A-Za-z0-9-]{10,}$")
_STRIPE_SECRET = re.compile(r"^sk_live_[A-Za-z0-9]{20,}$")

_PLACEHOLDER_WORDS = (
    "example", "sample", "dummy", "placeholder", "changeme", "change_me", "change-me", "your_", "your-",
    "yourkey", "yourtoken", "xxxx", "redacted", "fakekey", "fake_", "foobar", "insert_", "replace_me",
    "replaceme", "todo", "notreal", "not_real",
)
_REPEAT = re.compile(r"(.)\1{7,}")


def _b62(number: int) -> str:
    out = ""
    while number:
        number, rem = divmod(number, 62)
        out = _B62[rem] + out
    return out or "0"


def github_checksum_ok(token: str) -> bool | None:
    """True/False for a 36-character GitHub token body; None when the format cannot be checked."""
    m = _GH_TOKEN.match(token or "")
    if not m:
        return None
    body = m.group(1)
    entropy, tail = body[:30], body[30:]
    return _b62(zlib.crc32(entropy.encode("ascii"))).rjust(6, "0") == tail


def github_token_with_checksum(entropy: str) -> str:
    """Build the 6-character tail for a 30-character entropy part (used by tests)."""
    return entropy + _b62(zlib.crc32(entropy.encode("ascii"))).rjust(6, "0")


def is_placeholder(value: str) -> bool:
    low = (value or "").lower()
    return any(w in low for w in _PLACEHOLDER_WORDS) or bool(_REPEAT.search(low))


def live_check_enabled() -> bool:
    """Sending detected credentials to their providers is opt-in and off by default."""
    return os.environ.get("VISHAP_SECRET_LIVE_CHECK", "").strip().lower() in ("1", "true", "yes", "on")


def _provider(token: str) -> str | None:
    if _GH_TOKEN.match(token or ""):
        return "github"
    if _SLACK_TOKEN.match(token or ""):
        return "slack"
    if _STRIPE_SECRET.match(token or ""):
        return "stripe"
    return None


def _request(url: str, token: str, provider: str) -> tuple[int, object]:
    headers = {"Accept": "application/json", "User-Agent": "vishap-secret-check"}
    data = None
    if provider == "github":
        headers.update({"Authorization": f"Bearer {token}", "X-GitHub-Api-Version": "2022-11-28"})
    elif provider == "slack":
        headers["Authorization"] = f"Bearer {token}"
        data = b""
    elif provider == "stripe":
        import base64
        headers["Authorization"] = "Basic " + base64.b64encode((token + ":").encode()).decode("ascii")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    try:
        opener = urllib.request.build_opener(NoRedirect)
        with opener.open(req, timeout=5) as response:
            body = response.read(32_000).decode("utf-8", "replace")
            try:
                return response.status, json.loads(body)
            except ValueError:
                return response.status, None
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read(32_000).decode("utf-8", "replace"))
        except Exception:
            body = None
        return exc.code, body
    except Exception:
        return 0, None


def validate_live(rule_id: str, matched: str, request_fn=None) -> dict | None:
    """Check supported credentials with a read-only provider endpoint; never returns or logs the token."""
    token = (matched or "").strip().strip("\"'")
    provider = _provider(token)
    if not live_check_enabled() or not provider or is_placeholder(token):
        return None
    endpoints = {
        "github": "https://api.github.com/user",
        "slack": "https://slack.com/api/auth.test",
        "stripe": "https://api.stripe.com/v1/account",
    }
    status, body = (request_fn or _request)(endpoints[provider], token, provider)
    active = False if status == 401 else None
    if provider == "github" and status == 200 and isinstance(body, dict) and body.get("login"):
        active = True
    elif provider == "slack" and status == 200 and isinstance(body, dict):
        if body.get("ok") is True:
            active = True
        elif body.get("error") in ("invalid_auth", "token_expired", "token_revoked"):
            active = False
        else:
            active = None
    elif provider == "stripe" and status == 200 and isinstance(body, dict) and body.get("object") == "account":
        active = True
    return {"provider": provider, "status": "active" if active is True else
            "inactive" if active is False else "unknown"}


def assess(rule_id: str, matched: str, live_result: dict | None = None) -> dict | None:
    """Return {"confidence": "high"|"low", "note": str, "placeholder": bool} or None when nothing to add."""
    value = (matched or "").strip().strip("\"'")
    if not value:
        return None
    if live_result:
        status = live_result.get("status")
        provider = live_result.get("provider", "provider")
        labels = {"active": "provider confirmed this credential is active",
                  "inactive": "provider rejected this credential",
                  "unknown": "provider could not determine credential validity"}
        return {"confidence": "high" if status in ("active", "inactive") else "low",
                "placeholder": False, "credential_status": status,
                "note": f"{provider}: {labels.get(status, labels['unknown'])}"}
    if is_placeholder(value):
        return {"confidence": "low", "placeholder": True,
                "note": "looks like an example or placeholder value; confirm it is not a real credential"}
    if rule_id == "secret-aws":
        if not _AWS_ALPHABET.match(value):
            return {"confidence": "low", "placeholder": False,
                    "note": "key id uses characters outside the alphabet AWS key ids use (A-Z, 2-7); "
                            "verify before dismissing"}
        return {"confidence": "high", "placeholder": False, "note": "key id has the shape of a real AWS key id"}
    if rule_id == "secret-token":
        ok = github_checksum_ok(value)
        if ok is False:
            return {"confidence": "low", "placeholder": False,
                    "note": "GitHub token checksum does not match the published format; "
                            "verify before dismissing"}
        if ok is True:
            return {"confidence": "high", "placeholder": False,
                    "note": "GitHub token checksum matches: the value is well-formed, not a made-up example"}
    return None
