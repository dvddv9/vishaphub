# syntax=docker/dockerfile:1

# ---------- builder: dependencies first, so the layer caches ----------
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Dependency layer: only rebuilt when requirements.txt changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Application layer.
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
COPY vishap/ ./vishap/
RUN pip install --no-cache-dir --no-deps --prefix=/install .

# ---------- runtime ----------
FROM python:3.12-slim

LABEL org.opencontainers.image.title="vishap-analyzer" \
      org.opencontainers.image.description="Vishap — multi-material IT analyst" \
      org.opencontainers.image.source="https://github.com/dvddv9/vishap" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"

# curl is required by the HEALTHCHECK below; it is the only runtime dependency.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 vishap

COPY --from=builder /install /usr/local

USER root
RUN ln -s /usr/local/lib/python3.12/site-packages/src /home/vishap/src
USER vishap
WORKDIR /home/vishap
COPY alembic.ini ./
COPY alembic/ ./alembic/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    VISHAP_DATA_DIR=/home/vishap/.vishap/data

RUN mkdir -p /home/vishap/.vishap/data

EXPOSE 5001

# Graceful shutdown: uvicorn handles SIGTERM.
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://0.0.0.0:${PORT:-10000}/health || exit 1

# NB: without CONVEYOR_API_KEY the app binds 127.0.0.1 (see src/main.py) and is
# therefore unreachable from outside the container. Set it in production — the
# healthcheck above still passes either way, which is exactly why this is
# documented rather than detected.
#
# The LLM is **not** in this image: analysis goes through a DSH harness
# (`HARNESS_URL`, `HARNESS_TOKEN`). Running the harness on the host and pointing
# the container at `host.docker.internal:3080` is the supported setup — see
# docker-compose.yml.
CMD ["sh", "-c", "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-10000}"]