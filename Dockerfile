# ─────────────────────────────────────────────────────────────────────────────
# VISA_CTRL — Dockerfile
# Runs the Flask multi-user admin panel + Playwright Chromium automation
# on Google Cloud Run.
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# ── Minimal OS prerequisites needed before playwright --with-deps ─────────────
# (curl/wget for the browser download, ca-certs for TLS)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ───────────────────────────────────────────────────────
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Playwright browser + ALL OS deps in one step ─────────────────────────────
# --with-deps is the officially supported Docker method — it runs apt-get
# internally as root (which we are here) to install every Chromium dependency.
# Never split this into "install" + "install-deps": the second command tries
# to sudo and will always fail in a non-interactive container.
RUN playwright install --with-deps chromium

# ── Application code ──────────────────────────────────────────────────────────
COPY . .

# The Flask app lives in /app/canada — all imports (main.py, templates/) are
# relative to this directory.
WORKDIR /app/canada

# Ensure screenshot directory exists (ephemeral on Cloud Run — logs go to stdout)
RUN mkdir -p screenshots

# ── Runtime config ────────────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
ENV FLASK_DEBUG=false
# Cloud Run injects PORT automatically (default 8080)
ENV PORT=8080

EXPOSE 8080

# waitress is a production WSGI server that works on all platforms.
# Secrets (ADMIN_PASSWORD, SMTP_*, SECRET_KEY) are injected at runtime
# via Cloud Run --set-secrets or environment variables.
CMD ["sh", "-c", "waitress-serve --port=${PORT} --host=0.0.0.0 app:app"]
