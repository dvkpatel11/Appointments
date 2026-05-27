#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# ── 1. Environment ────────────────────────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  echo "[!] Created .env from .env.example — edit it with your secrets first!"
  exit 1
fi
set -a; source <(tr -d '\r' < .env); set +a

# ── 2. Virtualenv ─────────────────────────────────────────────────────────
env="${VIRTUAL_ENV:-}"
if [ -z "$env" ]; then
  if [ ! -d env ]; then
    echo "[+] Creating virtual environment..."
    python3 -m venv env
  fi
  source env/bin/activate
fi

# ── 3. Dependencies ────────────────────────────────────────────────────────

if ! python3 -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
  echo "[+] Installing Playwright browsers..."
  python3 -m playwright install --with-deps chromium
fi

# ── 4. Kill anything on the target port ─────────────────────────────────────
port="${PORT:-5000}"
if lsof -ti :"$port" &>/dev/null; then
  echo "[+] Killing process on port $port ..."
  kill -9 $(lsof -ti :"$port") 2>/dev/null || true
  sleep 0.5
fi

# ── 5. Run ─────────────────────────────────────────────────────────────────
echo "[+] Starting VisaCtrl on http://localhost:${port}"
FLASK_DEBUG="${FLASK_DEBUG:-true}" \
python3 -m flask --app canada.app run --port "$port" --host 0.0.0.0
