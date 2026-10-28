# Deploy

Two ways, both with a token: a server that is not on loopback refuses to start without `GENERATOR_API_TOKEN`.

## Docker (recommended: the container is the isolation Verify lacks)

    $env:GENERATOR_API_TOKEN = "<long random string>"
    $env:CUSTOM_LLM_KEY = "<model key>"
    docker compose up -d --build

The port is published on 127.0.0.1 only; put a reverse proxy with HTTPS in front to go further.
The container is read-only, drops all capabilities and runs as an ordinary user.

Not checked in this repository's tests: the Dockerfile and compose file were written, not run.

## systemd

`systemd/vishap-generator.service`: a virtualenv in `/opt/vishap-generator`, an `.env` next to it
(mode 600), and the hardening switches of the unit. Verify runs generated code with the service user's
rights, so give that user nothing else.

## Render, one service for two uses (GENERATOR_PUBLIC_CHECK=1)

This is what `render.yaml` sets up now. Everyone can open the page and run the spec check; generating code
needs your token.

- `GENERATOR_API_TOKEN` (long random string) and `CUSTOM_LLM_KEY` are `sync: false`: after the Blueprint sync
  Render asks for them in the dashboard. Without the token the server refuses to start and the previous deploy
  keeps serving.
- `CUSTOM_LLM_URL`, `CUSTOM_LLM_MODEL`, `CUSTOM_LLM_THINKING` are the project's defaults (`.env.example`).
- On the page open "Access token and model settings" and paste the token (it stays in that browser tab);
  the model key is on the server, the browser does not send one.
- `/api/check` is open; `/api/generate`, `/api/generate/async` and `/api/jobs/<id>` answer 401 without the token.
  `/api/status` shows `public_check: true` and `token_required: true`.
- Verify runs the code the model wrote from *your* specs on the service itself, as a child process: no
  isolation (see `docs/LIMITATIONS.md`). That is acceptable for one owner; it is the reason the run is behind a
  token. Jobs live in memory, so a restart or the free plan's sleep loses a running job.
- The image installs Flask, so `target: python/flask` is verified as Flask. Anthropic's compatibility layer ignores `seed`, so `--repro` is not exactly repeatable there.
- The cost is shown only when `GENERATOR_PRICE_IN` and `GENERATOR_PRICE_OUT` (USD per 1M tokens) are set in Render; the project does not carry model prices.
- The Vishap analyzer is not in the image, so the report says the verdict does not include it; set `require_analyzer: true` in the gate to block such runs.
- A visitor who is not you cannot spend your model key and cannot make the server run code.

To go back to the check-only demo: remove `GENERATOR_PUBLIC_CHECK`, set `GENERATOR_CHECK_ONLY` to `"1"`.

## Render, check-only demo (GENERATOR_CHECK_ONLY=1)

`render.yaml` is a Render blueprint for a public page. With `GENERATOR_CHECK_ONLY=1` the server answers only
`/api/check` (Intake and Design: requirements, planned files, STRIDE table, gaps). `/api/generate` and
`/api/generate/async` return 403, the browser cannot name a model, and no model key is needed. Nothing the
visitor sends is run as code, so the missing isolation of Verify does not apply. A public address is allowed
without a token in this mode only; the Host and Origin check still accepts just this server's own names
(`RENDER_EXTERNAL_HOSTNAME`, which Render sets, and `GENERATOR_PUBLIC_HOSTS` for a custom domain).

Live: https://vishap-generator.onrender.com/

Render: New > Blueprint > pick the repository > Apply. The free plan sleeps after 15 minutes without a request
and wakes on the next one (about a minute). The request limit counts the proxy's address, so it is one shared
bucket (`GENERATOR_RATE_LIMIT`, 60 a minute here).

## Not for open public generating

Generating open to everyone would spend your model key for strangers and run code a model wrote from their
text. The server runs one generate run at a time and has no accounts, quotas or billing. Keep generating behind
the token.
