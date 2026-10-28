FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml README.md ./
COPY src/ ./src/
# pytest is what the behaviour stage runs; without it every deliverable would look broken.\nRUN pip install --no-cache-dir . pytest

RUN useradd -m -u 1000 validator
USER validator

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8080')+'/health').read()"

CMD ["python", "-m", "validator.server"]