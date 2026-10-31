# One image, one URL: the hub, the validator and the analyser's rules live together.
# Build context is the repository root (dockerContext: "." in render.yaml) because all
# three packages are needed in the same process.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VISHAP_VALIDATOR_REQUIRE_NETNS=1

COPY packages/core/ ./packages/core/
COPY apps/validator/ ./apps/validator/
COPY apps/analyzer/ ./apps/analyzer/
COPY apps/hub/ ./apps/hub/

# What the service imports is small. The hub calls the analyser's static rules, which need
# nothing outside the standard library (checked by loading them over all 104 labelled
# examples in 11 languages: no third-party module is imported), so the analyser's own
# requirements.txt (fastapi, celery, stripe, opentelemetry, ...) is NOT installed here and
# the analyser goes in with --no-deps. No compiler either: every package below ships a wheel.
#   pytest      - the validator's `behavior` check runs the deliverable's tests with it
#   edge-tts    - the product voice (/api/speak)
#   psycopg     - team mode (Postgres)
# Direct dependencies are pinned so a rebuild cannot change what runs.
RUN pip install -e ./packages/core -e ./apps/validator \
    && pip install -e ./apps/analyzer --no-deps \
    && pip install -e ./apps/hub \
    && pip install "psycopg[binary]==3.3.6" "pytest==9.1.1" "edge-tts==7.3.1"

# Non-root on purpose: the code under test is somebody else's code.
RUN useradd -m -u 1000 hub
USER hub

# The image is meant to run read-only: nothing is written outside /tmp (runs live in memory
# unless VISHAP_HUB_RUNS_FILE says otherwise; the voice cache is in memory). Run it as
#   docker run --read-only --tmpfs /tmp:size=128m --pids-limit 256 --memory 1g ...
# so a submission cannot rewrite the code that judges it.

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8080')+'/health').read()"

CMD ["python", "-m", "hub.server"]
