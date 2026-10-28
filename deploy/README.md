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

## Not for a public site

The server runs one generate run at a time and has no accounts, quotas or billing. It is a tool for you
and your team, not a public service.
