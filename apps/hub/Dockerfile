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

# The analyzer's static rules use the standard library, so its large web/worker dependency
# set (FastAPI, Celery, Stripe, OpenTelemetry, ...) is NOT installed in the hub image.
# The GitHub App route is the exception: the hub's optional github extra adds only HTTPX
# and PyJWT/cryptography. No compiler either: the packages below ship wheels.
#   pytest      - the validator's `behavior` check runs the deliverable's tests with it
#   edge-tts    - the product voice (/api/speak)
#   psycopg     - team mode (Postgres)
# Direct dependencies are pinned so a rebuild cannot change what runs.
RUN pip install -e ./packages/core -e ./apps/validator \
    && pip install -e ./apps/analyzer --no-deps \
    && pip install "tree-sitter==0.26.0" "tree-sitter-javascript==0.25.0" "tree-sitter-typescript==0.23.2" "tree-sitter-java==0.23.5" "tree-sitter-go==0.25.0" "tree-sitter-rust==0.24.2" \
    && pip install -e "./apps/hub[github]" \
    && pip install "psycopg[binary]==3.3.6" "pytest==9.1.1" "edge-tts==7.3.1"

# Non-root on purpose: the code under test is somebody else's code.
RUN useradd -m -u 1000 hub && mkdir /data && chown hub /data
USER hub

# The image is meant to run read-only: nothing is written outside /tmp (runs live in memory
# unless VISHAP_HUB_RUNS_FILE says otherwise; the voice cache is in memory). Run it as
#   docker run --read-only --tmpfs /tmp:size=128m --pids-limit 256 --memory 1g ...
# so a submission cannot rewrite the code that judges it.

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8080')+'/health').read()"

CMD ["python", "-m", "hub.server"]
