# ─────────────────────────────────────────────────────────────────────────────
# VISA_CTRL — Dockerfile
# Runs the Flask multi-user admin panel + Playwright Chromium automation
#
# We use mcr.microsoft.com/playwright/python which already has everything
# needed - Python, Chromium, and OS dependencies pre-installed.
# ─────────────────────────────────────────────────────────────────────────────

FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

WORKDIR /app

COPY requirements.txt .
# Base image already has playwright, greenlet, pyee, chromium
# Just install app dependencies
RUN echo "=== USING PRE-INSTALLED PLAYWRIGHT ===" && \
    python -c "import playwright; print(f'Playwright: {playwright.__version__}')" && \
    echo "=== INSTALLING APP DEPENDENCIES ===" && \
    pip install --no-deps -r requirements.txt && \
    echo "=== DONE ==="

COPY . .

WORKDIR /app/canada

RUN mkdir -p screenshots

ENV PYTHONUNBUFFERED=1
ENV FLASK_DEBUG=false
ENV PORT=8080

EXPOSE 8080

CMD ["sh", "-c", "waitress-serve --port=${PORT} --host=0.0.0.0 app:app"]