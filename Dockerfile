# ─────────────────────────────────────────────────────────────────────────────
# VISA_CTRL — Dockerfile
# Runs the Flask multi-user admin panel + Playwright Chromium automation
# on Google Cloud Run.
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# ── System deps for Playwright / Chromium ────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxkbcommon0 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    lsb-release \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ───────────────────────────────────────────────────────
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Playwright browser ────────────────────────────────────────────────────────
# Downloads Chromium and installs any remaining OS deps
RUN playwright install chromium && playwright install-deps chromium

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
