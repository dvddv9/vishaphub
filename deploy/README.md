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

## Public demo (Render): spec check only

`render.yaml` is a Render blueprint for a public page. With `GENERATOR_CHECK_ONLY=1` the server answers only
`/api/check` (Intake and Design: requirements, planned files, STRIDE table, gaps). `/api/generate` and
`/api/generate/async` return 403, the browser cannot name a model, and no model key is needed. Nothing the
visitor sends is run as code, so the missing isolation of Verify does not apply. A public address is allowed
without a token in this mode only; the Host and Origin check still accepts just this server's own names
(`RENDER_EXTERNAL_HOSTNAME`, which Render sets, and `GENERATOR_PUBLIC_HOSTS` for a custom domain).

Render: New > Blueprint > pick the repository > Apply. The free plan sleeps after 15 minutes without a request
and wakes on the next one (about a minute). The request limit counts the proxy's address, so it is one shared
bucket (`GENERATOR_RATE_LIMIT`, 60 a minute here).

## Not for a public generate service

Generating on a public address would spend your model key for strangers and run code a model wrote from their
text. The server runs one generate run at a time and has no accounts, quotas or billing. Generating is a tool
for you and your team: use the token modes above.
