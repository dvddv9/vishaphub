# syntax=docker/dockerfile:1
# The server in a container. Verify still runs generated code as a child process, but
# inside the container it can reach nothing of the host: this is the isolation that
# README.md asks for before you take specs from other people.

FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt coverage ruff
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps --prefix=/install .

FROM python:3.12-slim
LABEL org.opencontainers.image.title="vishap-generator" \
      org.opencontainers.image.description="Spec-to-code generator that proves its output" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"
RUN useradd -m -u 1000 generator
COPY --from=builder /install /usr/local
USER generator
WORKDIR /home/generator
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8787
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8787/health', timeout=4)" || exit 1

# A non-loopback host needs GENERATOR_API_TOKEN: the server refuses to start without it.
CMD ["vishap-generator", "serve", "--host", "0.0.0.0", "--port", "8787"]
