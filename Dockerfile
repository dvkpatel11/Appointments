# ─────────────────────────────────────────────────────────────────────────────
# VISA_CTRL — Dockerfile
# Runs the Flask multi-user admin panel + Playwright Chromium automation
# on Google Cloud Run.
#
# Base image: mcr.microsoft.com/playwright/python
#   Microsoft's official image ships with Python, Chromium, and every OS
#   dependency pre-installed and tested. This eliminates the brittle
#   apt-get package lists that differ between Ubuntu and Debian releases
#   (e.g. ttf-unifont vs fonts-unifont, ttf-ubuntu-font-family missing on
#   Debian Bookworm) that cause `playwright install --with-deps` to fail.
#
# Tag format: v{playwright_version}-{ubuntu_codename}
#   jammy  = Ubuntu 22.04 LTS (Python 3.10) — stable, well-tested
#   noble  = Ubuntu 24.04 LTS (Python 3.12) — if you need 3.12 specifically
#
# Keep the tag pinned to the same playwright version as requirements.txt.
# ─────────────────────────────────────────────────────────────────────────────

FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

# ── Python dependencies ───────────────────────────────────────────────────────
# The base image already has: Python 3.12, pip, playwright CLI, Chromium +
# all OS deps. We only need to install our own packages on top.
WORKDIR /app

COPY requirements.txt .

# playwright is already installed in the base image; pip will skip reinstalling
# it but will still pin it. Use --no-cache-dir to keep the layer small.
RUN pip install --no-cache-dir -r requirements.txt

# ── Application code ──────────────────────────────────────────────────────────
COPY . .

# The Flask app + main.py + templates/ all live under /app/canada.
WORKDIR /app/canada

# Screenshot dir (ephemeral on Cloud Run; files live only for the request lifetime).
RUN mkdir -p screenshots

# ── Runtime config ────────────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
ENV FLASK_DEBUG=false
# Cloud Run injects PORT automatically (default 8080).
ENV PORT=8080

EXPOSE 8080

# waitress is a cross-platform production WSGI server (no gunicorn needed).
# Secrets (ADMIN_PASSWORD, SMTP_*, SECRET_KEY) are injected at runtime
# via Cloud Run --set-secrets or plain --set-env-vars.
CMD ["sh", "-c", "waitress-serve --port=${PORT} --host=0.0.0.0 app:app"]
