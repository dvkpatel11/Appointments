FROM mcr.microsoft.com/playwright/python:v1.58.0-noble AS base

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY run.py .

RUN mkdir -p /app/data /app/logs /app/screenshots \
    && chown -R appuser:appuser /app

RUN python -m playwright install --with-deps chromium

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

WORKDIR /app
CMD ["python", "-m", "waitress", "--port=8080", "--host=0.0.0.0", "src.app.wsgi:app"]
