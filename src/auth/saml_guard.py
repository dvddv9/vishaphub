# src/auth/saml_guard.py
"""SEC-6: SAML assertion gate (CWE-347) -- fail-closed.

Until python3-saml verification (signature, audience, issuer, NotOnOrAfter) is
implemented, EVERY assertion is rejected. Never return True here without a real
cryptographic check: once SSO is enabled this function is the only thing between
a forged assertion and a session.
"""


def validate_saml_assertion(form_data) -> bool:
    """Return True only for a cryptographically verified assertion.

    Not implemented yet, so this denies everything (fail-closed).
    """
    return False
