#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
VENV="${VENV:-env}"
PORT="${PORT:-5000}"

echo "==> Creating virtual environment..."
"$PYTHON" -m venv "$VENV"

echo "==> Installing dependencies..."
"$VENV"/bin/pip install --upgrade pip -q
"$VENV"/bin/pip install -r requirements.txt -q

echo "==> Installing Playwright browsers..."
"$VENV"/bin/playwright install --with-deps chromium

if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    echo "==> Created .env from .env.example — edit it with your secrets!"
  else
    echo "==> WARNING: No .env or .env.example found"
  fi
fi

echo ""
echo "  Setup complete!"
echo ""
echo "  Run:  make run"
echo "  Or:   $VENV/bin/python run.py"
echo "  Or:   ./scripts/setup.sh && $VENV/bin/python -m flask --app src.app.wsgi run --port $PORT --host 0.0.0.0"
echo ""
