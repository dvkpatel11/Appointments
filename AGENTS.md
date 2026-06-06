# AGENTS.md — UsVisaAppointment

Flask + Playwright app that monitors US visa appointment slots for multiple users
(Canada module is real; UK module is a stub). Each approved client runs in its
own `multiprocessing.Process` so a bad run cannot block the web UI.

## Quick start

```bash
make install       # creates .venv, pip install -r requirements.txt, playwright install chromium
make run           # dev server via run.py on PORT (default 5000)
make test          # pytest tests/ -v  (71 tests, all green)
make lint          # ruff check src/         (note: only src/, CI runs `ruff check .`)
make format        # ruff check --fix src/ && ruff format src/
make docker-build  # docker build -t visa-ctrl:latest .
make docker-run    # docker run --rm -p 5000:8080 --env-file .env visa-ctrl
make deploy-gcp    # gcloud builds submit --config cloudbuild.yaml .
make backup        # ./scripts/backup.sh     (stale script — see Gotchas)
```

`./scripts/setup.sh` is a non-Makefile alternative to `make install` (also
writes a `.env` from `.env.example` if missing, then exits).

`./run.sh` is yet another entry point — it expects the venv in `env/`
(not `.venv/`), sources `.env`, kills anything on `$PORT`, and runs
`python3 run.py`. Use it if you ran setup.sh with the default venv path.

## Entrypoints

- Dev: `run.py` → `src.app.create.create_app()` (Flask debug server)
- Prod (Docker, Render, Cloud Run): `src.app.wsgi:app` served by `waitress`
- Process: `python -m waitress --port=8080 --host=0.0.0.0 src.app.wsgi:app`

## Code layout (src/)

```
src/
├── app/                 # Flask app + blueprints + wsgi
│   ├── create.py        #   create_app(): registers blueprints, starts recovery
│   │                    #   thread, wires rate limiter, security headers,
│   │                    #   Sentry init, /healthz probes, atexit/SIGTERM handlers
│   ├── extensions.py    #   Flask-Limiter singleton (memory:// storage)
│   ├── wsgi.py          #   app = create_app()  (production entry)
│   └── routes/          #   auth, admin, client, telegram blueprints
├── config.py            # pydantic-settings AppSettings (env_file = ".env")
├── domain/              # Client dataclass, enums (ClientState, VisaType), errors
├── infrastructure/
│   ├── database.py      #   sqlite3 (WAL, busy_timeout=5s). Tables: settings, clients,
│   │                    #   automation_state, pending_links, email_confirmations.
│   │                    #   Schema in init_db().
│   ├── logging.py       #   server.log (rotating) + per-client <id>.log
│   └── repositories/    #   client_repo, state_repo, settings_repo (in-memory cache)
├── notifications/       # email (SMTP), telegram, sms (Twilio) — each exposes send()
├── orchestrator/
│   └── manager.py       # start/stop/check_and_recover/resume_approved_agents (multiprocess)
├── scraper/
│   ├── base.py          #   VisaScraper ABC + run loop (login → check 12× → wait 30-60s)
│   ├── canada/          #   CanadaVisaScraper — fully implemented
│   └── uk/              #   UKVisaScraper — login works, check_availability/reschedule are stubs
└── services/            # ClientService, AutomationService, NotificationService
```

Routing: `orchestrator/manager.py` dispatches to `src.scraper.canada.scraper.CanadaVisaScraper`
or `src.scraper.uk.scraper.UKVisaScraper` based on `client.visa_type` (see
`src/domain/enums.py:VisaType`).

## Config & secrets

- `.env` is at project root and loaded by pydantic (`src/config.py`). Copy
  from `.env.example` and edit before first run. Required keys: `SECRET_KEY`,
  `ADMIN_PASSWORD`. Optional: SMTP, Resend, Telegram, Twilio, Sentry.
- `DB_PATH` controls the SQLite file. Default in `src/config.py` is
  `data/visactrl.db`; `.env.example` ships with `canada/visactrl.db`. Pick one
  before first run — the app `mkdir -p`s the parent dir on connect.
- There are NO `creds.py` files anymore. Old `canada/creds.py` / `uk/creds.py`
  in `.gitignore` are leftovers from a pre-refactor single-script era.

## Runtime directories (gitignored)

- `canada/visactrl.db` — current SQLite DB (if you set `DB_PATH=canada/visactrl.db`)
- `data/` — alternative DB location (default in code)
- `logs/server.log` and `logs/<client_id>.log` — server + per-client logs (rotating 5MB × 3)
- `screenshots/<client_id>/NNN_<name>.png` — Playwright screenshots; latest is
  exposed via the client portal as a base64 data URL
- `app.log` — leftover root-level log (gitignored)
- `.env`, `.venv`, `env/`, `.ruff_cache/`, `__pycache__/`

## Telegram integration

- Visit `/set_telegram_webhook` (GET) once after deploy to register the webhook
  URL. Without this, `/telegram_webhook` will be a no-op.
- Commands the bot handles (`src/app/routes/telegram.py`):
  - `/start <token>` — links the chat ID to a client token. Token must already
    exist in `pending_links` (created by `POST /generate_telegram_link`).
  - `/myid` and `/getid` — reply with the user's chat ID.
- `pending_link_ttl_seconds = 1800` (30 min). Stale unlinked rows are
  deleted by `orchestrator.cleanup_stale_pending_links()` which runs on
  every 60s tick of the recovery loop in `create_app()`.

## Lint, format, test

- Ruff config in `pyproject.toml`: line-length 120, py312, select E/F/W/I/N/UP/S
  (ignore S101), double quotes, LF endings.
- **Makefile runs `ruff check src/` (narrow). CI runs `ruff check .` (whole repo).**
  A change in a non-`src/` file can pass `make lint` but fail CI.
- Pytest is configured (`testpaths = ["tests"]`, `addopts = "-v --tb=short"`).
  71 tests across `tests/test_email_magic_link.py`, `tests/test_security_hardening.py`,
  `tests/test_production_hardening.py`, and a few others.
- CI test command is `pytest tests/ -v --cov=canada --cov=uk --cov-report=xml`
  — the `--cov=uk` is a leftover and will fail with "no such file" if coverage
  is ever enforced. CI currently does not enforce coverage.

## CI/CD

- `.github/workflows/ci.yml` jobs: `lint` → `test` → `docker-build` (sequential).
- Python 3.12 in CI, but `runtime.txt` pins **3.11** (Render uses this).
- Docker base: `mcr.microsoft.com/playwright/python:v1.58.0-noble`. Chromium
  pre-installed; `playwright install --with-deps chromium` is also re-run in
  the Dockerfile to keep versions in sync.
- Cloud Run (`cloudbuild.yaml`): 2Gi RAM, 2 CPU, `--timeout=3600`,
  `--concurrency=5`, secrets pulled from Secret Manager, region
  `northamerica-northeast1`. The Cloud Run service is set to
  `--min-instances=0` so cold starts happen — Playwright relogs in on each
  fresh cycle, which is by design.
- Static env vars shipped in `cloudbuild.yaml` and `render.yaml`:
  `SMTP_HOST`, `SMTP_PORT`, `FLASK_DEBUG=false`, `APP_ENV=production`,
  `SENTRY_ENVIRONMENT=production`, `SENTRY_TRACES_SAMPLE_RATE=0.1`,
  `RATELIMIT_ENABLED=true`, `SHUTDOWN_GRACE_SECONDS=25`.
- Render (`render.yaml`): Docker service on port 8080, secrets `sync: false`
  (you enter them in the Render dashboard).

## Architecture quirks

- One `multiprocessing.Process` per approved client, registered in
  `orchestrator/manager.py:_alive_processes`. The parent process never runs
  Playwright — it only orchestrates.
- `create_app()` starts a daemon thread (`_recovery_loop`) that every 60s
  calls `orchestrator.check_and_recover()` to restart crashed scrapers with
  exponential backoff (`crash_backoff_base=30s`, `crash_backoff_max=600s`).
  On the same tick it calls `cleanup_stale_pending_links()` to delete
  unlinked `pending_links` older than `pending_link_ttl_seconds`.
- `orchestrator.resume_approved_agents()` runs on app startup so automations
  survive a web-tier restart. State lives in SQLite, not in the process.
- `/health` returns `{"status": "ok"}`. `/healthz/ready` does a `SELECT 1`
  (503 if the DB is unreachable). `/healthz/live` is a cheap process-up
  probe. Use the latter for Cloud Run livenessProbe to avoid restart
  loops on transient DB issues; use the former for readinessProbe. The
  Dockerfile's HEALTHCHECK polls `/health` every 30s with a 60s start-period.
- `stop(client_id, grace_seconds=None)` and `stop_all(grace_seconds=None)`
  accept a per-call grace budget (default from `settings.shutdown_grace_seconds`,
  default 25s). The budget is divided across running agents so the parent
  process never outlives the platform's termination grace period.
- Security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Permissions-Policy`, `Strict-Transport-Security`) are set on every
  response via an `after_request` hook in `create_app()`. Rate limiting is
  wired via `Flask-Limiter` (`memory://` storage) on `/login`, `/client_submit`,
  email magic link endpoints, and `/telegram_webhook`. Disable with
  `RATELIMIT_ENABLED=false` for tests.
- Per-client state is persisted on every log line via
  `state_repo.save(...)` — `action_log` is a JSON list in the
  `automation_state` table, capped at `max_action_log_entries=100`.
- `BaseSettings` reads `.env` at the project root (NOT `canada/.env` as older
  docs claim). The `extra = "ignore"` config means unknown env vars don't
  crash the app.

## Gotchas

- **UK module is a stub.** `UKVisaScraper.login()` works, but
  `check_availability()` and `reschedule_to()` always return False. Don't
  enable the UK `visa_type` for real users expecting it to do anything.
- **`requirements-lock.txt` is OUT OF DATE.** It lists old versions
  (Flask 3.0.3 not pinned, python-telegram-bot 21.10, etc.). Use
  `requirements.txt` for installs.
- **No tests exist** despite the pytest config. Adding the first
  `tests/test_*.py` will start running the CI test step for real.
- **Stale docs/scripts:** `README.md`, `docs/api.md`, `docs/deployment.md`,
  `scripts/backup.sh`, and `SECURITY.md` all reference the pre-refactor
  single-script layout (paths like `canada.app`, `creds.py`,
  `canada/canada/client_tokens.json`). Do not trust them — read the code
  under `src/` instead. The backup script will find no files and exit 0.
- **Two venv paths exist** because the project was refactored without
  deleting the old setup: `make install` uses `.venv/`, `run.sh` and
  `scripts/setup.sh` use `env/`. Pick one and stick with it.
- **No CSRF protection, no MFA on `/login`.** See `SECURITY.md`. Admin auth
  is a single shared password compared in `src/app/routes/auth.py:login()`.
  Rate limiting IS now in place on `/login` (5/min) and other write endpoints.
- **Client passwords are encrypted at rest** with Fernet
  (`ENCRYPTION_KEY`). The DB is still gitignored and ephemeral in prod.
  Boot fails fast with a clear error if `ENCRYPTION_KEY` is missing.
- **Email notifications require a magic link click.** `notification_email`
  is only persisted after the user clicks the link sent to that address.
  The link is single-use, 24h TTL. Tokens live in `email_confirmations`.
- **No `opencode.json` or `.opencode/`** in this repo — OpenCode picks up
  only this `AGENTS.md`.
- **No pre-commit hooks.** Run `make format` and `make lint` manually
  before pushing (and remember CI lints the whole repo, not just `src/`).
