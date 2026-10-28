# -*- coding: utf-8 -*-
"""SAML SSO endpoints (v6.3) — placeholder.

SAML (and SCIM provisioning) is a Clerk **Enterprise** feature. Until that plan
is enabled, both endpoints answer ``501 Not Implemented`` so integrators get a
stable, explicit signal instead of a 500 or a silent no-op. The real flow will
delegate to Clerk: mint a SAML redirect URL on login, hand the assertion to
Clerk on callback.

See ``docs/SSO.md`` for the configuration guide.
"""
from fastapi import HTTPException

SSO_UNAVAILABLE_DETAIL = "SSO requires Clerk Enterprise plan"


def sso_enabled() -> bool:
    """Whether a real SAML flow is wired up. Flip only together with a real
    implementation of ``saml_callback`` and ``saml_guard.validate_saml_assertion``.
    """
    return False


def _not_implemented() -> None:
    raise HTTPException(status_code=501, detail=SSO_UNAVAILABLE_DETAIL)


async def saml_login(tenant: str) -> dict:
    """Start a SAML login for ``tenant``.

    Stub: raises 501 until Clerk Enterprise is enabled.
    """
    _not_implemented()


async def saml_callback(payload: dict) -> dict:
    """Consume a SAML assertion posted by the customer's IdP.

    Stub: raises 501 until Clerk Enterprise is enabled. The real implementation
    must verify the assertion signature and audience before trusting any claim.
    """
    _not_implemented()
