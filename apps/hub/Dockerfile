# One image, one URL: the hub, the validator and the analyser's rules live together.
# Build context is the repository root (dockerContext: "." in render.yaml) because all
# three packages are needed in the same process.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY packages/core/ ./packages/core/
COPY apps/validator/ ./apps/validator/
COPY apps/analyzer/ ./apps/analyzer/
COPY apps/hub/ ./apps/hub/

# The analyser's requirements still name vishap-core as a git dependency; in this
# image core is a local package, so that line is dropped before pip runs.
RUN grep -v '^vishap-core' ./apps/analyzer/requirements.txt > /tmp/analyzer-reqs.txt \
    && pip install --no-cache-dir -e ./packages/core -e ./apps/validator \
    && pip install --no-cache-dir -r /tmp/analyzer-reqs.txt \
    && pip install --no-cache-dir -e ./apps/analyzer --no-deps \
    && pip install --no-cache-dir -e "./apps/hub[postgres]" \
    && pip install --no-cache-dir edge-tts pytest

RUN useradd -m -u 1000 hub
USER hub

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8080')+'/health').read()"

CMD ["python", "-m", "hub.server"]
