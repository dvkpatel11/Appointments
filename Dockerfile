FROM mcr.microsoft.com/playwright/python:v1.58.0-noble AS base

# ── Non-root user ────────────────────────────────────────────────
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# ── Dependencies ─────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application (exclude secrets via .dockerignore) ──────────────
COPY canada/ ./canada/

# ── Runtime directories ──────────────────────────────────────────
RUN mkdir -p /app/canada/screenshots \
             /app/canada/status \
             /app/canada/logs \
             /app/data \
    && chown -R appuser:appuser /app

# ── Playwright browsers (base image includes them; re-install if needed) ──
RUN python -m playwright install --with-deps chromium

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

WORKDIR /app
CMD ["python", "-m", "waitress", "--port=8080", "--host=0.0.0.0", "canada.app:app"]
