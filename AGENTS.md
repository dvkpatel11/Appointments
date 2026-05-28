# AGENTS.md — UsVisaAppointment

## Quick start

```bash
make install       # creates .venv, pip install -r requirements.txt, playwright install chromium
make run           # Flask dev server on port 5000
make lint          # ruff check .
make format        # ruff check --fix . && ruff format .
make test          # pytest tests/ -v  (no tests exist yet)
make docker-build  # docker build -t visa-ctrl:latest .
make docker-run    # docker run --rm -p 5000:8080 --env-file .env visa-ctrl
make deploy-gcp    # gcloud builds submit --config cloudbuild.yaml .
make backup        # tar.gz of state files to ./backups/
```

`run.sh` is an alternative entry point that auto-activates `env/` (not `.venv`), sources `.env`, kills port conflicts, and starts Flask.

## Project structure

- `canada/app.py` — Flask app (multi-user admin UI, client portal, Telegram webhook). Entrypoint: `python -m flask --app canada.app run`. Production: `python -m waitress --port=8080 --host=0.0.0.0 canada.app:app`.
- `canada/main.py` — `VisaAutomation` class + `run_in_subprocess()` entrypoint for multiprocessing. Uses Playwright to check/reschedule US visa appointments for Canada.
- `canada/config.py` — Locations, selectors, retry/poll constants.
- `canada/db.py` — SQLite layer (WAL mode, busy timeout 5s). Tables: `settings`, `client_tokens`, `automation_state`, `pending_links`, `sessions`.
- `canada/state.py` — Thin wrapper saving/publishing automation state to DB for the web UI.
- `canada/notifications.py` — Email (SMTP), Telegram, SMS (Twilio).
- `uk/main.py` — Separate UK visa automation (semi-maintained, has **duplicate code and stale bugs** — see CHANGELOG).
- `uk/routes.py` — Simple Flask app for UK module.
- `canada/canada/` — **Both** a Python subpackage **and** a data directory holding legacy JSON state files (`client_tokens.json`, `settings.json`). On startup `db.init_db()` migrates these into SQLite if present.
- `scripts/backup.sh` — State backup. Run from project root.
- `scripts/deploy-gcp.sh` — One-shot GCP setup + deploy.
- `scripts/init-oracle-vm.sh` — Oracle Cloud VM bootstrap.

## Config & secrets

- **.env** — copied from `.env.example`. Loaded by `config.load_environment()` (dotenv from `canada/.env`).
- **Legacy** `canada/creds.py` and `uk/creds.py` — gitignored, hardcoded credentials for standalone CLI runs.

## Ruff (linter + formatter)

- Line length: 120
- Target: Python 3.12
- Quote style: double
- Selected rules: E, F, W, I, N, UP, S (ignore S101)
- `ruff check --fix . && ruff format .` to auto-fix

## Testing

- pytest configured in `pyproject.toml` (`testpaths = ["tests"]`), but **no test files exist yet**.
- CI runs `pytest tests/ -v --cov=canada --cov=uk --cov-report=xml`.
- Any new test files should go in `tests/test_*.py`.

## CI/CD

- GitHub Actions: `lint` → `test` → `docker-build` (push to main or PR).
- Python 3.12 in CI, but `runtime.txt` says 3.11 (Render deployment).
- Docker base: `mcr.microsoft.com/playwright/python:v1.58.0-noble`. Chromium pre-installed.
- Cloud Run deployment via `cloudbuild.yaml`: builds image → pushes to Artifact Registry (`northamerica-northeast1`) → deploys with secrets from Secret Manager. 2Gi memory, 2 CPU, 3600s timeout, concurrency 5.
- Render deployment via `render.yaml` (Docker, `PORT=8080`).

## Architecture quirks

- Each automation user runs in a **separate `multiprocessing.Process`** (not thread). State is persisted via SQLite for the web UI to read.
- Automation instances are resumed on Flask startup via `resume_approved_agents()`.
- The `/health` endpoint triggers a keepalive ping thread (every 5 minutes) to prevent cold starts.
- Telegram webhook handles `/start <token>` to link chat IDs, and `/myid` to return the chat ID.
- `PENDING_LINK_TTL_SECONDS = 600` (10 min). Stale pending links cleaned before every request.
- `canada/canada/` is gitignored (runtime state, contains PII). Don't confuse with the `canada/` app package.

## Gotchas

- **UK module** has known issues: duplicate `except` blocks in `get_appointment_date()`, duplicate `notification_email` parameter in `__init__`, mixed Canada/UK URLs.
- **No tests exist** despite pytest config — CI test step passes vacuously.
- The `canada/canada/` directory serves dual purpose (package + data) — be careful not to delete it thinking it's just `__pycache__`.
- `make install` puts venv in `.venv/`, but `run.sh` expects `env/`. Two different venv paths.
