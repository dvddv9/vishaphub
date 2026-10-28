# SSO (SAML)

Single sign-on via **SAML 2.0** lets an enterprise customer authenticate users
through their own identity provider (Okta, Entra ID / Azure AD, Google
Workspace, OneLogin, JumpCloud, …) instead of Clerk's hosted email/password
flow. After login, users get a Clerk session like any other — Vishap only sees
the resulting tenant (`org_id`) and never handles the credentials.

## Status

**Not implemented yet — the endpoints return `501 Not Implemented`.**

```
GET  /auth/sso/login?tenant=<tenant_id>   -> 501
POST /auth/sso/callback                   -> 501
```

Both responses carry the detail `SSO requires Clerk Enterprise plan`. This is
deliberate: a stub that answers 501 is easier to handle than one that silently
pretends to work. Nothing in the current flow depends on these endpoints.

## Requirements

| Requirement | Notes |
| --- | --- |
| **Clerk Enterprise plan** | SAML and SCIM are Enterprise-tier features. Clerk's published price for the Enterprise tier starts at **$25/month**; check current pricing before committing. |
| IdP admin access | You need permission to create a SAML application in the customer's identity provider. |
| Verified domain | Clerk requires the customer's email domain to be verified before SSO can be enabled for it. |
| Public HTTPS callback | The ACS (assertion consumer service) URL must be reachable over HTTPS — `http://localhost` is not accepted. |

## How to configure (when the plan is active)

1. **Clerk Dashboard → Configure → SSO connections → Add connection → SAML.**
2. Pick the identity provider (or "Custom" for a generic SAML 2.0 app).
3. Copy the two values Clerk generates — **ACS URL** and **Entity ID / Audience
   URI** — into the IdP's SAML application.
4. In the IdP, map the assertion attributes Clerk expects: at minimum `email`,
   plus `first_name` / `last_name` if you want them populated.
5. Upload the IdP metadata (or paste the IdP certificate + SSO URL) back into
   Clerk, then **verify** the connection.
6. Enable the connection for the organisation domain, so members signing in
   with that domain are routed to SSO automatically.

Terraform / API alternative: the same objects are managed through Clerk's
Backend API (`/v1/saml_connections`), which is the recommended path for
reproducible setups.

## How to use

```
GET /auth/sso/login?tenant=<tenant_id>
```

Intended behaviour once implemented: the endpoint resolves the tenant, asks
Clerk for a SAML authorisation URL for that organisation, and redirects the
browser there. On return, the IdP posts the assertion to
`POST /auth/sso/callback`, which hands it to Clerk, receives a session, and
issues the usual session cookie.

Today both calls answer `501`, so a client can probe support cheaply:

```bash
curl -i "https://api.example.com/auth/sso/login?tenant=org_123"
# HTTP/1.1 501 Not Implemented
# {"detail":"SSO requires Clerk Enterprise plan"}
```

## Roadmap

| Step | State |
| --- | --- |
| Stub endpoints + docs | done (v6.3) |
| Redirect to Clerk SAML URL | pending Enterprise plan |
| Assertion verification via Clerk Backend API | pending |
| SCIM user/group provisioning | not planned for v6.x |
| IdP-initiated login | not planned for v6.x |

## See also

- [Privacy Policy](legal/PRIVACY.md) — what identity data Vishap stores.
- [DPA](legal/DPA.md) — Clerk is listed as a sub-processor.
