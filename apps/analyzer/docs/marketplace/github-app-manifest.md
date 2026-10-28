# GitHub App manifest

The manifest is what GitHub turns into a GitHub App when you register it through
the "create from manifest" flow, and what the Marketplace listing is built on.
The block below is the set of fields Vishap needs; it is an **example**, not a
live registration — `url`, `hook_attributes.url` and `redirect_url` must point at
your own deployment before you submit anything.

## Manifest

```json
{
  "name": "Vishap Security Scanner",
  "url": "https://vishap.dev",
  "hook_attributes": {
    "url": "https://vishap.dev/webhook/github",
    "active": true
  },
  "redirect_url": "https://vishap.dev/auth/github/callback",
  "callback_urls": ["https://vishap.dev/auth/github/callback"],
  "description": "Automated security analysis for engineering materials: findings, STRIDE model and audit trail on every pull request.",
  "public": true,
  "default_permissions": {
    "contents": "read",
    "metadata": "read",
    "pull_requests": "write",
    "checks": "write"
  },
  "default_events": ["pull_request"]
}
```

## Field notes

| Field | Why this value |
| --- | --- |
| `name` | Must match the Marketplace listing name. The `[bot]` suffix is added by GitHub. |
| `url` | Public homepage. GitHub requires a reachable HTTPS page, and the review checks it. |
| `hook_attributes.url` | Vishap already serves `POST /webhook/github`; this must be the public HTTPS URL, not `localhost`. |
| `hook_attributes.active` | `true` so the app starts receiving events as soon as it is installed. |
| `redirect_url` | Where GitHub sends the user after install. Must be HTTPS. |
| `callback_urls` | Used for the OAuth-style user authorisation flow, if you enable one. |
| `description` | Short; truncated in the UI. Keep under ~150 characters. |
| `public` | `true` is required for a Marketplace listing; `false` means install-only. |
| `default_permissions.contents` | `read` — the app reads PR diffs; it never needs to write code. |
| `default_permissions.pull_requests` | `write` — to post the report as a PR comment. |
| `default_permissions.checks` | `write` — to surface pass/fail as a check run. |
| `default_events` | `pull_request` only. Adding `push` multiplies webhook volume for no benefit. |

## Minimal permissions

Ask for nothing you do not use. Vishap needs exactly four scopes:

- `metadata: read` — implicitly granted to every app; lists the repository.
- `contents: read` — fetch the diff and the files under review.
- `pull_requests: write` — post the report as a comment.
- `checks: write` — optional; needed only if you want a check run instead of a
  comment.

Anything broader (`administration`, `secrets`, `actions`) will slow the
Marketplace review and is a poor signal to security-conscious buyers.

## Before submitting

1. Replace the three placeholder URLs with the real deployment.
2. Confirm `POST /webhook/github` verifies the `X-Hub-Signature-256` header —
   reviewers do install the app and watch for a response.
3. Check the install flow end to end on a throwaway repository: install → open a
   PR → comment appears.
4. Keep the manifest in the repository and re-add it whenever permissions change,
   so the requested scopes stay reviewable in git history.

See [`publishing-guide.md`](publishing-guide.md) for the full submission process.
