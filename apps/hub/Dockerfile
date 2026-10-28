FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# core is installed from GitHub until it has a release
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir . "vishap-core @ git+https://github.com/dvddv9/vishap-core.git@main"
# the hub speaks with the same voice as the greeting
RUN pip install --no-cache-dir edge-tts

RUN useradd -m -u 1000 hub
USER hub

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8080')+'/health').read()"

CMD ["python", "-m", "hub.server"]