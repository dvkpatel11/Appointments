# Refactor Design — Lean Architectural Upgrade

Date: 2026-05-30
Status: Approved

## Scope

Lean architectural upgrade of the UsVisaAppointment monolith into a modular,
production-ready multi-tenant web app. No queues, no microservices. Shared
scraper abstraction for Canada and UK visa portals.

## Project Structure

```
usvisa-appointment/
├── src/
│   ├── app/                         # Flask application
│   │   ├── __init__.py
│   │   ├── create.py                # Application factory
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py              # /login, /logout
│   │   │   ├── admin.py             # /admin/*, /start, /stop
│   │   │   ├── client.py            # /client/*, /client_submit
│   │   │   └── telegram.py          # /telegram_webhook
│   │   ├── templates/
│   │   │   ├── login.html
│   │   │   ├── admin/
│   │   │   │   └── dashboard.html
│   │   │   └── client/
│   │   │       └── form.html
│   │   └── static/
│   ├── domain/                      # Pure models, no I/O
│   │   ├── __init__.py
│   │   ├── client.py                # Client entity dataclass
│   │   ├── enums.py                 # ClientState, NotificationType
│   │   └── errors.py                # DomainError, NotFound, etc.
│   ├── infrastructure/              # Framework concerns
│   │   ├── __init__.py
│   │   ├── database.py              # Connection + migration
│   │   ├── repositories/
│   │   │   ├── __init__.py
│   │   │   ├── client_repo.py
│   │   │   ├── state_repo.py
│   │   │   └── settings_repo.py
│   │   └── logging.py               # Per-client logger
│   ├── services/                    # Business logic
│   │   ├── __init__.py
│   │   ├── client_service.py
│   │   ├── automation_service.py
│   │   └── notification_service.py
│   ├── scraper/                     # Playwright
│   │   ├── __init__.py
│   │   ├── base.py                  # Abstract VisaScraper
│   │   ├── canada/
│   │   │   ├── __init__.py
│   │   │   ├── scraper.py           # CanadaVisaScraper
│   │   │   └── selectors.py         # Canada DOM selectors
│   │   └── uk/
│   │       ├── __init__.py
│   │       ├── scraper.py           # UKVisaScraper
│   │       └── selectors.py         # UK DOM selectors
│   ├── orchestrator/                # Subprocess manager
│   │   ├── __init__.py
│   │   └── manager.py               # Process lifecycle
│   ├── notifications/               # Pure dispatch
│   │   ├── __init__.py
│   │   ├── email.py
│   │   ├── telegram.py
│   │   └── sms.py
│   └── config.py                    # Pydantic BaseSettings
├── logs/                            # Per-client log files
├── data/                            # SQLite DB
├── pyproject.toml
├── Makefile
├── Dockerfile
└── .env.example
```

## Data Model

### clients
| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK (UUID) | |
| token | TEXT UNIQUE | Client link token |
| name | TEXT | |
| state | TEXT | issued\|pending\|approved\|rejected\|stopped |
| reject_reason | TEXT | |
| username | TEXT NOT NULL | Visa portal username |
| password | TEXT NOT NULL | Encrypted at rest |
| appointment_id | TEXT | |
| appointment_url | TEXT | |
| visa_type | TEXT DEFAULT 'canada' | Routes to correct scraper |
| reschedule | INTEGER DEFAULT 0 | |
| preferred_locations | TEXT | JSON array |
| preferred_date_from | TEXT | |
| preferred_date_to | TEXT | |
| notification_email | TEXT | |
| telegram_chat_id | TEXT | |
| phone_number | TEXT | |
| agent_pid | INTEGER | |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### automation_state
| Column | Type | Notes |
|--------|------|-------|
| client_id | TEXT PK → clients.id | |
| is_running | INTEGER | |
| current_action | TEXT | |
| action_log | TEXT | JSON array |
| current_appointment | TEXT | |
| new_appointment | TEXT | |
| last_checked_location | TEXT | |
| screenshot_path | TEXT | |
| error_count | INTEGER DEFAULT 0 | Consecutive errors for crash detection |
| updated_at | TIMESTAMP | |

### settings
| Column | Type |
|--------|------|
| key | TEXT PK |
| value | TEXT |

### pending_links
| Column | Type |
|--------|------|
| token | TEXT PK |
| chat_id | TEXT |
| created_at | TIMESTAMP |
| linked_at | TIMESTAMP |

## Scraper Abstraction

```
scraper/base.py: VisaScraper(ABC)
  ├── abstract login() -> bool
  ├── abstract get_current_appointment() -> datetime | None
  ├── abstract check_availability(location) -> CheckResult
  ├── abstract reschedule(location) -> bool
  ├── concrete run_check_cycle() -> bool    # iterate locations, notify, reschedule
  └── concrete run() -> None                # main loop

scraper/canada/scraper.py: CanadaVisaScraper(VisaScraper)
scraper/uk/scraper.py:     UKVisaScraper(VisaScraper)
```

## Orchestrator

- `orchestrator/manager.py` owns all subprocess lifecycle
- start, stop, health check, crash recovery (with exponential backoff)
- On restart detected: re-launch client (30s → 60s → 120s → capped at 600s)
- Flask routes call orchestrator methods (not directly VisaAutomation)

## Per-Client Logging

- Each subprocess writes to `logs/{client_id}.log` via RotatingFileHandler
- Admin endpoint: `GET /admin/logs/<client_id>` returns last N lines
- Structured log format: `[timestamp] [level] [client_id] message`

## Admin Configurability

`src/config.py` uses Pydantic BaseSettings for typed, validated config with .env override:

- Global app settings (db path, log dir, timeouts)
- SMTP, Telegram, Twilio credentials
- DB-level settings table for runtime toggles (email/telegram/sms enabled)
- Admin UI to read/write settings

## Crash Recovery Flow

1. Subprocess dies → PID gone, state not updated
2. `_cleanup_stale()` detects hung state (no update in HANG_TIMEOUT)
3. Increments `error_count` in automation_state
4. Backoff: `min(30 * 2^(error_count-1), 600)` seconds delay
5. Re-launches subprocess with same client config
6. Admin UI shows error_count + "Restart" override button

## Migration Plan

### Phase 1 — Scaffold (no behavior change)
- Create new directory structure
- Add src/config.py (Pydantic settings)
- Add src/infrastructure/database.py (wrapper around current db.py)
- Add domain models + enums
- Keep canada/app.py as the entry point, importing from new modules

### Phase 2 — Extract services
- Move client CRUD → src/services/client_service.py
- Move notification dispatch → src/services/notification_service.py
- Move process lifecycle → src/orchestrator/manager.py
- app.py becomes thin: just routes calling services

### Phase 3 — Refactor scraper
- Extract src/scraper/base.py (abstract VisaScraper)
- Move Canada logic → src/scraper/canada/
- Move UK logic → src/scraper/uk/
- Subprocess runner uses visa_type param

### Phase 4 — Flask blueprints + UI
- Split app.py routes into src/app/routes/*.py
- Application factory in src/app/create.py
- Add per-client log viewer
- Admin config UI (read/write settings from Pydantic)
- Deprecate canada/app.py → new entry point: src/app/create.py

### Phase 5 — Cleanup
- Remove canada/ directory (old code)
- Remove uk/ directory (old code)
- Update Dockerfile, Makefile, deploy scripts
- Update AGENTS.md
