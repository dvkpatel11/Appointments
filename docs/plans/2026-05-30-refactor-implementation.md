# Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use godmode:task-runner to implement this plan task-by-task.

**Goal:** Refactor monolith into modular multi-tenant web app with shared Canada/UK scraper abstraction

**Architecture:** Clean layered approach — Flask blueprints → services → domain → infrastructure → scraper. Subprocess per client managed by orchestrator. Per-client structured logging.

**Migration:** Incremental. Existing `canada/app.py` stays as entry point through Phase 3. Cutover in Phase 4.

**Tech Stack:** Python 3.12, Flask, SQLite, Playwright, Pydantic, Ruff

---

## Phase 1 — Scaffold (no behavior change)

### Task 1: Create src directory structure

**Files:**
- Create: `src/__init__.py`
- Create: `src/app/__init__.py`
- Create: `src/app/routes/__init__.py`
- Create: `src/app/templates/` (empty, placeholder)
- Create: `src/domain/__init__.py`
- Create: `src/infrastructure/__init__.py`
- Create: `src/infrastructure/repositories/__init__.py`
- Create: `src/services/__init__.py`
- Create: `src/scraper/__init__.py`
- Create: `src/scraper/canada/__init__.py`
- Create: `src/scraper/uk/__init__.py`
- Create: `src/orchestrator/__init__.py`
- Create: `src/notifications/__init__.py`
- Create: `logs/` (empty directory)
- Create: `data/` (empty directory)

**Step 1: Create directories and __init__.py files**

```bash
mkdir -p src/app/routes src/app/templates src/domain src/infrastructure/repositories src/services \
         src/scraper/canada src/scraper/uk src/orchestrator src/notifications \
         logs data
for d in src src/app src/app/routes src/domain src/infrastructure src/infrastructure/repositories \
         src/services src/scraper src/scraper/canada src/scraper/uk src/orchestrator src/notifications; do
  touch "$d/__init__.py"
done
```

**Step 2: Verify**

```bash
find src -type f -name "__init__.py" | wc -l
# Expected output: 14
```

**Step 3: Commit**

```bash
git add src/ logs/ data/
git commit -m "chore: scaffold src directory structure"
```

---

### Task 2: Add domain models + enums + errors

**Files:**
- Create: `src/domain/enums.py`
- Create: `src/domain/errors.py`
- Create: `src/domain/client.py`
- Modify: `src/domain/__init__.py`

**Step 1: Write src/domain/enums.py**

```python
from enum import Enum


class ClientState(str, Enum):
    ISSUED = "issued"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STOPPED = "stopped"


class VisaType(str, Enum):
    CANADA = "canada"
    UK = "uk"
```

**Step 2: Write src/domain/errors.py**

```python
class DomainError(Exception):
    """Base domain error."""


class NotFoundError(DomainError):
    """Entity not found."""


class InvalidStateError(DomainError):
    """Operation not allowed in current state."""


class AutomationError(DomainError):
    """Automation operation failed."""
```

**Step 3: Write src/domain/client.py**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.domain.enums import ClientState, VisaType


@dataclass
class Client:
    id: str
    token: str
    name: str | None = None
    state: ClientState = ClientState.ISSUED
    reject_reason: str | None = None
    username: str | None = None
    password: str | None = None
    appointment_id: str | None = None
    appointment_url: str | None = None
    visa_type: VisaType = VisaType.CANADA
    reschedule: bool = False
    preferred_locations: list[str] | None = None
    preferred_date_from: str | None = None
    preferred_date_to: str | None = None
    notification_email: str | None = None
    telegram_chat_id: str | None = None
    phone_number: str | None = None
    agent_pid: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def can_start(self) -> bool:
        return self.state == ClientState.APPROVED and bool(self.username and self.password)
```

**Step 4: Write src/domain/__init__.py**

```python
from src.domain.client import Client
from src.domain.enums import ClientState, VisaType
from src.domain.errors import DomainError, NotFoundError, InvalidStateError, AutomationError

__all__ = [
    "Client",
    "ClientState",
    "VisaType",
    "DomainError",
    "NotFoundError",
    "InvalidStateError",
    "AutomationError",
]
```

**Step 5: Verify**

```bash
ruff check src/domain/
# Expected: no errors
python -c "from src.domain import Client, ClientState, VisaType, NotFoundError; print('OK')"
# Expected: OK
```

**Step 6: Commit**

```bash
git add src/domain/
git commit -m "feat: add domain models, enums, and errors"
```

---

### Task 3: Add Pydantic settings

**Files:**
- Create: `src/config.py`

**Step 1: Write src/config.py**

```python
from __future__ import annotations

import os
from pathlib import Path
from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    # App
    admin_password: str = ""
    secret_key: str = ""
    debug: bool = False

    # Paths
    db_path: str = os.environ.get("DB_PATH", "data/visactrl.db")
    log_dir: str = "logs"
    screenshot_base: str = "screenshots"

    # Automation
    max_action_log_entries: int = 100
    hang_timeout_seconds: int = 900
    pending_link_ttl_seconds: int = 1800
    navigate_max_retries: int = 5
    max_polls: int = 30
    min_sleep_before_retry: int = 30
    max_sleep_before_retry: int = 60
    min_wait_between_checks: int = 30
    max_wait_between_checks: int = 60
    crash_backoff_base: int = 30
    crash_backoff_max: int = 600

    # SMTP
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None

    # Telegram
    telegram_bot_token: str | None = None
    telegram_bot_username: str = "us_x_visa_x_bot"

    # Twilio
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None

    # Sentry
    sentry_dsn: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = AppSettings()
```

**Step 2: Add pydantic-settings to requirements.txt**

Add `pydantic-settings==2.7.1` to `requirements.txt`.

**Step 3: Verify**

```bash
python -c "from src.config import settings; print(settings.db_path)"
# Expected: data/visactrl.db
```

**Step 4: Commit**

```bash
git add src/config.py requirements.txt
git commit -m "feat: add Pydantic settings management"
```

---

### Task 4: Infrastructure — database

**Files:**
- Create: `src/infrastructure/database.py`

**Step 1: Write src/infrastructure/database.py**

```python
from __future__ import annotations

import os
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from src.config import settings


DB_PATH = settings.db_path


def get_conn() -> sqlite3.Connection:
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def cursor():
    conn = get_conn()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with cursor() as cur:
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS clients (
                id TEXT PRIMARY KEY,
                token TEXT UNIQUE,
                name TEXT,
                state TEXT NOT NULL DEFAULT 'issued',
                reject_reason TEXT,
                username TEXT,
                password TEXT,
                appointment_id TEXT,
                appointment_url TEXT,
                visa_type TEXT NOT NULL DEFAULT 'canada',
                reschedule INTEGER NOT NULL DEFAULT 0,
                preferred_locations TEXT,
                preferred_date_from TEXT,
                preferred_date_to TEXT,
                notification_email TEXT,
                telegram_chat_id TEXT,
                phone_number TEXT,
                agent_pid INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS automation_state (
                client_id TEXT PRIMARY KEY REFERENCES clients(id),
                is_running INTEGER NOT NULL DEFAULT 0,
                current_action TEXT,
                action_log TEXT,
                current_appointment TEXT,
                new_appointment TEXT,
                last_checked_location TEXT,
                screenshot_path TEXT,
                error_count INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS pending_links (
                token TEXT PRIMARY KEY,
                chat_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                linked_at TIMESTAMP
            );
        """)

    # Migrate legacy data if exists
    _migrate_from_legacy()


def _migrate_from_legacy():
    """Copy data from canada/ tables if this is a fresh DB."""
    with cursor() as cur:
        count = cur.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
        if count > 0:
            return  # Already migrated

    # Legacy settings
    from canada.config import SETTINGS_FILE  # type: ignore
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE) as f:
                data = json.load(f)
            for key, value in data.items():
                from src.infrastructure.repositories.settings_repo import set_setting
                set_setting(key, str(value) if not isinstance(value, str) else value)
        except Exception:
            pass

    # Legacy client tokens
    from canada.config import CLIENT_TOKENS_FILE  # type: ignore
    if os.path.exists(CLIENT_TOKENS_FILE):
        try:
            with open(CLIENT_TOKENS_FILE) as f:
                tokens = json.load(f)
            for token, data in tokens.items():
                req = data.get("request") or {}
                with cursor() as cur:
                    cur.execute(
                        """INSERT OR REPLACE INTO clients
                           (id, token, state, reject_reason, username, password,
                            appointment_id, appointment_url, reschedule,
                            preferred_locations, preferred_date_from, preferred_date_to,
                            notification_email, telegram_chat_id, phone_number, agent_pid)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (token, token,
                         data.get("state", "issued"),
                         data.get("reject_reason"),
                         req.get("username"),
                         req.get("password"),
                         req.get("appointment_id"),
                         req.get("appointment_url"),
                         1 if req.get("reschedule") else 0,
                         json.dumps(req.get("preferred_locations")) if req.get("preferred_locations") else None,
                         req.get("preferred_date_from"),
                         req.get("preferred_date_to"),
                         data.get("notification_email"),
                         data.get("telegram_chat_id"),
                         data.get("phone_number"),
                         data.get("agent_pid")),
                    )
        except Exception:
            pass
```

**Step 2: Verify**

```bash
python -c "from src.infrastructure.database import init_db; init_db(); print('OK')"
# Expected: OK
ls -la data/
# Expected: visactrl.db exists (WAL files too)
```

**Step 3: Commit**

```bash
git add src/infrastructure/database.py
git commit -m "feat: add database module with migration from legacy"
```

---

### Task 5: Infrastructure — repositories

**Files:**
- Create: `src/infrastructure/repositories/client_repo.py`
- Create: `src/infrastructure/repositories/state_repo.py`
- Create: `src/infrastructure/repositories/settings_repo.py`
- Modify: `src/infrastructure/repositories/__init__.py`

**Step 1: Write src/infrastructure/repositories/client_repo.py**

```python
from __future__ import annotations

import json
from typing import Any

from src.domain.client import Client
from src.domain.enums import ClientState, VisaType
from src.infrastructure.database import cursor


def row_to_client(row: dict[str, Any]) -> Client:
    return Client(
        id=row["id"],
        token=row["token"],
        name=row["name"],
        state=ClientState(row["state"]),
        reject_reason=row["reject_reason"],
        username=row["username"],
        password=row["password"],
        appointment_id=row["appointment_id"],
        appointment_url=row["appointment_url"],
        visa_type=VisaType(row.get("visa_type", "canada")),
        reschedule=bool(row["reschedule"]),
        preferred_locations=json.loads(row["preferred_locations"]) if row.get("preferred_locations") else None,
        preferred_date_from=row["preferred_date_from"],
        preferred_date_to=row["preferred_date_to"],
        notification_email=row["notification_email"],
        telegram_chat_id=row["telegram_chat_id"],
        phone_number=row["phone_number"],
        agent_pid=row["agent_pid"],
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def get_by_token(token: str) -> Client | None:
    with cursor() as cur:
        cur.execute("SELECT * FROM clients WHERE token = ?", (token,))
        row = cur.fetchone()
    return row_to_client(dict(row)) if row else None


def get_by_id(client_id: str) -> Client | None:
    with cursor() as cur:
        cur.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
        row = cur.fetchone()
    return row_to_client(dict(row)) if row else None


def get_by_state(state: str | ClientState) -> dict[str, Client]:
    if isinstance(state, ClientState):
        state = state.value
    with cursor() as cur:
        cur.execute("SELECT * FROM clients WHERE state = ?", (state,))
        return {row["id"]: row_to_client(dict(row)) for row in cur.fetchall()}


def get_all() -> dict[str, Client]:
    with cursor() as cur:
        cur.execute("SELECT * FROM clients")
        return {row["id"]: row_to_client(dict(row)) for row in cur.fetchall()}


def save(client: Client) -> None:
    with cursor() as cur:
        cur.execute(
            """INSERT OR REPLACE INTO clients
               (id, token, name, state, reject_reason, username, password,
                appointment_id, appointment_url, visa_type, reschedule,
                preferred_locations, preferred_date_from, preferred_date_to,
                notification_email, telegram_chat_id, phone_number, agent_pid,
                updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       CURRENT_TIMESTAMP)""",
            (client.id, client.token, client.name, client.state.value,
             client.reject_reason, client.username, client.password,
             client.appointment_id, client.appointment_url, client.visa_type.value,
             1 if client.reschedule else 0,
             json.dumps(client.preferred_locations) if client.preferred_locations else None,
             client.preferred_date_from, client.preferred_date_to,
             client.notification_email, client.telegram_chat_id,
             client.phone_number, client.agent_pid),
        )


def update_field(client_id: str, **kwargs: Any) -> None:
    """Update specific fields on a client row without loading the full object."""
    if not kwargs:
        return
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values())
    with cursor() as cur:
        cur.execute(
            f"UPDATE clients SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (*vals, client_id),
        )


def create_token() -> str:
    import uuid
    token = uuid.uuid4().hex
    with cursor() as cur:
        cur.execute(
            "INSERT INTO clients (id, token, state) VALUES (?, ?, 'issued')",
            (token, token),
        )
    return token
```

**Step 2: Write src/infrastructure/repositories/state_repo.py**

```python
from __future__ import annotations

import json
from typing import Any

from src.infrastructure.database import cursor


def save(client_id: str, state_data: dict[str, Any]) -> None:
    with cursor() as cur:
        cur.execute(
            """INSERT OR REPLACE INTO automation_state
               (client_id, is_running, current_action, action_log,
                current_appointment, new_appointment,
                last_checked_location, screenshot_path,
                error_count, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                       CURRENT_TIMESTAMP)""",
            (client_id,
             state_data.get("is_running", False),
             state_data.get("current_action"),
             json.dumps(state_data.get("action_log", [])),
             state_data.get("current_appointment"),
             state_data.get("new_appointment"),
             state_data.get("last_checked_location"),
             state_data.get("screenshot_path"),
             state_data.get("error_count", 0)),
        )


def load(client_id: str) -> dict[str, Any] | None:
    with cursor() as cur:
        cur.execute("SELECT * FROM automation_state WHERE client_id = ?", (client_id,))
        row = cur.fetchone()
    if not row:
        return None
    result = dict(row)
    if result.get("action_log"):
        try:
            result["action_log"] = json.loads(result["action_log"])
        except (json.JSONDecodeError, TypeError):
            result["action_log"] = []
    return result


def delete(client_id: str) -> None:
    with cursor() as cur:
        cur.execute("DELETE FROM automation_state WHERE client_id = ?", (client_id,))
```

**Step 3: Write src/infrastructure/repositories/settings_repo.py**

```python
from __future__ import annotations

from typing import Any
from src.infrastructure.database import cursor


CACHE: dict[str, str] = {}


def load_cache() -> None:
    global CACHE
    CACHE.clear()
    with cursor() as cur:
        cur.execute("SELECT key, value FROM settings")
        for row in cur.fetchall():
            CACHE[row["key"]] = row["value"]


def get(key: str, default: str | None = None) -> str | None:
    return CACHE.get(key, default)


def set(key: str, value: str) -> None:
    CACHE[key] = value
    with cursor() as cur:
        cur.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )


def get_all() -> dict[str, str]:
    return dict(CACHE)
```

**Step 4: Write src/infrastructure/repositories/__init__.py**

```python
from src.infrastructure.repositories import client_repo as client_repo_module
from src.infrastructure.repositories import state_repo as state_repo_module
from src.infrastructure.repositories import settings_repo as settings_repo_module

client_repo = client_repo_module
state_repo = state_repo_module
settings_repo = settings_repo_module
```

**Step 5: Verify**

```bash
ruff check src/infrastructure/
# Expected: no errors
python -c "
from src.infrastructure.database import init_db
init_db()
from src.infrastructure.repositories import client_repo
token = client_repo.create_token()
print(f'Created client: {token}')
c = client_repo.get_by_token(token)
print(f'Client state: {c.state}')
"
# Expected: Created client: <uuid> \n Client state: issued
```

**Step 6: Commit**

```bash
git add src/infrastructure/
git commit -m "feat: add repositories for clients, state, and settings"
```

---

### Task 6: Infrastructure — per-client logging

**Files:**
- Create: `src/infrastructure/logging.py`

**Step 1: Write src/infrastructure/logging.py**

```python
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from src.config import settings


def setup_server_logger() -> logging.Logger:
    """Root logger for the Flask app and orchestrator."""
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "server.log"

    logger = logging.getLogger("usvisa")
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s"
    )

    file_handler = RotatingFileHandler(
        str(log_file), maxBytes=5 * 1024 * 1024, backupCount=3
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def get_client_logger(client_id: str) -> logging.Logger:
    """Get or create a per-client logger that writes to logs/{client_id}.log."""
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{client_id}.log"

    logger_name = f"usvisa.client.{client_id}"
    logger = logging.getLogger(logger_name)

    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(client_id)s] %(message)s"
        )

        file_handler = RotatingFileHandler(
            str(log_file), maxBytes=5 * 1024 * 1024, backupCount=3
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


class ClientLoggerAdapter(logging.LoggerAdapter):
    """Adapter that injects client_id into every log record."""

    def __init__(self, client_id: str) -> None:
        self.client_id = client_id
        super().__init__(get_client_logger(client_id), {"client_id": client_id})

    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        kwargs.setdefault("extra", {})["client_id"] = self.client_id
        return msg, kwargs


def read_client_log(client_id: str, lines: int = 200) -> str:
    """Read last N lines from a client's log file."""
    log_file = Path(settings.log_dir) / f"{client_id}.log"
    if not log_file.exists():
        return ""

    with open(log_file) as f:
        all_lines = f.readlines()
    return "".join(all_lines[-lines:])
```

**Step 2: Verify**

```bash
python -c "
from src.infrastructure.logging import ClientLoggerAdapter, read_client_log
log = ClientLoggerAdapter('test-client')
log.info('Test message')
print(read_client_log('test-client', 5))
"
# Expected: log line with timestamp, test-client, Test message
```

**Step 3: Commit**

```bash
git add src/infrastructure/logging.py
git commit -m "feat: add per-client structured logging"
```

---

### Task 7: Notifications module

**Files:**
- Create: `src/notifications/email.py`
- Create: `src/notifications/telegram.py`
- Create: `src/notifications/sms.py`
- Modify: `src/notifications/__init__.py`

**Step 1: Write src/notifications/email.py**

```python
from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

from src.config import settings


def send(subject: str, message: str, to_email: str, logger: callable | None = None) -> bool:
    if not to_email or not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        if logger:
            logger("SMTP not configured, skipping email", "warning")
        return False

    try:
        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"] = settings.smtp_user
        msg["To"] = to_email

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_user, [to_email], msg.as_string())

        if logger:
            logger(f"Email sent to {to_email}")
        return True

    except Exception as e:
        if logger:
            logger(f"Email send failed: {e}", "error")
        return False
```

**Step 2: Write src/notifications/telegram.py**

```python
from __future__ import annotations

import requests

from src.config import settings


def send(message: str, chat_id: str | None = None, emoji: str = "🇨🇦", logger: callable | None = None) -> bool:
    bot_token = settings.telegram_bot_token
    chat_id = chat_id or settings.telegram_bot_token  # fallback not ideal, but preserves old behavior

    if not bot_token or not chat_id:
        if logger:
            logger("Telegram not configured, skipping", "debug")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": f"{emoji} {message}"}

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            if logger:
                logger("Telegram notification sent")
            return True
        else:
            if logger:
                logger(f"Telegram failed: {response.status_code}", "warning")
            return False
    except Exception:
        if logger:
            logger("Telegram error", "error")
        return False
```

**Step 3: Write src/notifications/sms.py**

```python
from __future__ import annotations

from src.config import settings


def send(message: str, to_phone: str | None = None, logger: callable | None = None) -> bool:
    account_sid = settings.twilio_account_sid
    auth_token = settings.twilio_auth_token
    from_phone = settings.twilio_from_number
    to_phone = to_phone  # passed directly

    if not account_sid or not auth_token or not from_phone or not to_phone:
        if logger:
            logger("Twilio not configured, skipping SMS", "warning")
        return False

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        client.messages.create(body=message, from_=from_phone, to=to_phone)
        if logger:
            logger(f"SMS sent to {to_phone}")
        return True
    except Exception as e:
        if logger:
            logger(f"SMS send failed: {e}", "error")
        return False
```

**Step 4: Write src/notifications/__init__.py**

```python
from src.notifications import email, telegram, sms

__all__ = ["email", "telegram", "sms"]
```

**Step 5: Verify**

```bash
ruff check src/notifications/
# Expected: no errors
python -c "from src.notifications import email, telegram, sms; print('Notifications OK')"
# Expected: Notifications OK
```

**Step 6: Commit**

```bash
git add src/notifications/
git commit -m "feat: add notifications module (email, telegram, sms)"
```

---

## Phase 2 — Extract services

### Task 8: Notification service

**Files:**
- Create: `src/services/notification_service.py`

**Step 1: Write src/services/notification_service.py**

```python
from __future__ import annotations

from typing import Any

from src import notifications
from src.infrastructure.repositories import settings_repo


class NotificationService:
    """Coordinates all notification channels based on client config and global settings."""

    @staticmethod
    def send(
        message: str,
        email_addr: str | None = None,
        telegram_chat_id: str | None = None,
        phone_number: str | None = None,
        logger: callable | None = None,
    ) -> None:
        email_enabled = settings_repo.get("email_enabled", "true") == "true"
        telegram_enabled = settings_repo.get("telegram_enabled", "false") == "true"
        sms_enabled = settings_repo.get("sms_enabled", "false") == "true"

        if email_addr and email_enabled:
            notifications.email.send(
                subject=f"VISA UPDATE: {message[:50]}...",
                message=message,
                to_email=email_addr,
                logger=logger,
            )

        if telegram_chat_id and telegram_enabled:
            notifications.telegram.send(
                message=message,
                chat_id=telegram_chat_id,
                logger=logger,
            )

        if phone_number and sms_enabled:
            notifications.sms.send(
                message=message,
                to_phone=phone_number,
                logger=logger,
            )
```

**Step 2: Verify**

```bash
ruff check src/services/
# Expected: no errors
```

**Step 3: Commit**

```bash
git add src/services/notification_service.py
git commit -m "feat: add notification service with channel dispatch"
```

---

### Task 9: Client service

**Files:**
- Create: `src/services/client_service.py`

**Step 1: Write src/services/client_service.py**

```python
from __future__ import annotations

import uuid
from datetime import datetime

from src.domain.client import Client
from src.domain.enums import ClientState
from src.domain.errors import NotFoundError, InvalidStateError
from src.infrastructure.repositories import client_repo
from src.infrastructure.repositories import settings_repo


class ClientService:
    """Business logic for client lifecycle."""

    @staticmethod
    def generate_link() -> str:
        return client_repo.create_token()

    @staticmethod
    def get_by_token(token: str) -> Client | None:
        return client_repo.get_by_token(token)

    @staticmethod
    def get_by_id(client_id: str) -> Client | None:
        return client_repo.get_by_id(client_id)

    @staticmethod
    def get_pending() -> dict[str, Client]:
        return client_repo.get_by_state(ClientState.PENDING)

    @staticmethod
    def get_approved() -> dict[str, Client]:
        return client_repo.get_by_state(ClientState.APPROVED)

    @staticmethod
    def get_all() -> dict[str, Client]:
        return client_repo.get_all()

    @staticmethod
    def submit_request(token: str, form_data: dict) -> Client:
        client = client_repo.get_by_token(token)
        if not client:
            raise NotFoundError(f"Token {token[:12]}... not found")
        if client.state in (ClientState.APPROVED, ClientState.PENDING):
            raise InvalidStateError(f"Client is already {client.state.value}")

        client.state = ClientState.PENDING
        client.name = form_data.get("name", "Client")
        client.username = form_data.get("username", "").strip()
        client.password = form_data.get("password", "")
        client.appointment_id = form_data.get("appointment_id", "").strip()
        client.appointment_url = form_data.get("appointment_url", "")
        client.reschedule = form_data.get("reschedule") == "true"
        client.preferred_locations = form_data.get("preferred_locations")
        client.preferred_date_from = form_data.get("preferred_date_from", "").strip() or None
        client.preferred_date_to = form_data.get("preferred_date_to", "").strip() or None
        client.notification_email = form_data.get("username", "").strip()
        client.telegram_chat_id = form_data.get("telegram_chat_id", "").strip() or None
        client.updated_at = datetime.utcnow()

        client_repo.save(client)
        return client

    @staticmethod
    def approve(token: str) -> Client:
        client = client_repo.get_by_token(token)
        if not client:
            raise NotFoundError(f"Token {token[:12]}... not found")
        if client.state != ClientState.PENDING:
            raise InvalidStateError(f"Can only approve pending requests, got {client.state.value}")

        client.state = ClientState.APPROVED
        client.updated_at = datetime.utcnow()
        client_repo.save(client)
        return client

    @staticmethod
    def reject(token: str, reason: str = "Your request was not approved at this time.") -> Client:
        client = client_repo.get_by_token(token)
        if not client:
            raise NotFoundError(f"Token {token[:12]}... not found")
        client.state = ClientState.REJECTED
        client.reject_reason = reason
        client.updated_at = datetime.utcnow()
        client_repo.save(client)
        return client

    @staticmethod
    def update_notification(client_id: str, email: str | None = None, phone: str | None = None) -> Client:
        client = client_repo.get_by_id(client_id)
        if not client:
            raise NotFoundError(f"Client {client_id[:12]}... not found")
        if email is not None:
            client.notification_email = email
        if phone is not None:
            client.phone_number = phone
        client.updated_at = datetime.utcnow()
        client_repo.save(client)
        return client
```

**Step 2: Verify**

```bash
ruff check src/services/
# Expected: no errors
python -c "
from src.infrastructure.database import init_db; init_db()
from src.services.client_service import ClientService
token = ClientService.generate_link()
print(f'Generated token: {token}')
client = ClientService.get_by_token(token)
print(f'Client state: {client.state}')
"
# Expected: Generated token, Client state: issued
```

**Step 3: Commit**

```bash
git add src/services/client_service.py
git commit -m "feat: add client service with lifecycle management"
```

---

### Task 10: Orchestrator — process manager

**Files:**
- Create: `src/orchestrator/manager.py`

**Step 1: Write src/orchestrator/manager.py**

```python
from __future__ import annotations

import os
import signal
import time
import multiprocessing
from datetime import datetime
from typing import Any

from src.config import settings
from src.domain.client import Client
from src.infrastructure import logging as client_logging
from src.infrastructure.repositories import client_repo, state_repo


logger = client_logging.setup_server_logger()
_alive_processes: dict[str, multiprocessing.Process] = {}
_error_counts: dict[str, int] = {}
_last_crash: dict[str, float] = {}


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def _scraper_entry(
    client_id: str,
    username: str,
    password: str,
    appointment_id: str | None,
    appointment_url: str | None,
    visa_type: str,
    reschedule: bool,
    preferred_locations: list[str] | None,
    preferred_date_from: str | None,
    preferred_date_to: str | None,
    notification_email: str | None,
    telegram_chat_id: str | None,
    phone_number: str | None,
) -> None:
    """Target function for multiprocessing — runs in a child process."""
    if visa_type == "canada":
        from src.scraper.canada.scraper import CanadaVisaScraper
        scraper = CanadaVisaScraper(
            client_id=client_id,
            username=username,
            password=password,
            appointment_id=appointment_id,
            appointment_url=appointment_url,
            reschedule=reschedule,
            preferred_locations=preferred_locations,
            preferred_date_from=preferred_date_from,
            preferred_date_to=preferred_date_to,
            notification_email=notification_email,
            telegram_chat_id=telegram_chat_id,
            phone_number=phone_number,
        )
    elif visa_type == "uk":
        from src.scraper.uk.scraper import UKVisaScraper
        scraper = UKVisaScraper(
            client_id=client_id,
            username=username,
            password=password,
            appointment_id=appointment_id,
            appointment_url=appointment_url,
            reschedule=reschedule,
            preferred_locations=preferred_locations,
            preferred_date_from=preferred_date_from,
            preferred_date_to=preferred_date_to,
            notification_email=notification_email,
            telegram_chat_id=telegram_chat_id,
            phone_number=phone_number,
        )
    else:
        raise ValueError(f"Unknown visa type: {visa_type}")

    scraper.run()


def start(client: Client) -> bool:
    """Start a scraper subprocess for a client. Returns True if started."""
    client_id = client.id
    if client_id in _alive_processes and _alive_processes[client_id].is_alive():
        logger.warning(f"Client {client_id[:12]}... already running")
        return False

    if not client.username or not client.password:
        logger.error(f"Client {client_id[:12]}... missing credentials")
        return False

    try:
        proc = multiprocessing.Process(
            target=_scraper_entry,
            args=(
                client_id, client.username, client.password,
                client.appointment_id, client.appointment_url,
                client.visa_type.value, client.reschedule,
                client.preferred_locations,
                client.preferred_date_from, client.preferred_date_to,
                client.notification_email, client.telegram_chat_id,
                client.phone_number,
            ),
        )
        proc.start()
        _alive_processes[client_id] = proc
        client_repo.update_field(client_id, agent_pid=proc.pid)
        logger.info(f"Started scraper for {client_id[:12]}... (pid={proc.pid})")
        return True
    except Exception as e:
        logger.error(f"Failed to start scraper for {client_id[:12]}...: {e}")
        _alive_processes.pop(client_id, None)
        return False


def stop(client_id: str) -> bool:
    """Stop a running scraper subprocess."""
    proc = _alive_processes.get(client_id)
    if not proc or not proc.is_alive():
        logger.warning(f"Client {client_id[:12]}... not running")
        _alive_processes.pop(client_id, None)
        return False

    try:
        proc.terminate()
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=3)
    except Exception:
        pass

    _alive_processes.pop(client_id, None)
    client_repo.update_field(client_id, agent_pid=None)
    state_repo.delete(client_id)
    logger.info(f"Stopped scraper for {client_id[:12]}...")
    return True


def stop_all() -> None:
    """Stop all running scraper subprocesses."""
    for client_id in list(_alive_processes.keys()):
        stop(client_id)


def is_alive(client_id: str) -> bool:
    proc = _alive_processes.get(client_id)
    return proc is not None and proc.is_alive()


def get_backoff_seconds(client_id: str) -> int:
    """Exponential backoff based on consecutive error count."""
    err_count = _error_counts.get(client_id, 0)
    delay = min(settings.crash_backoff_base * (2 ** (err_count - 1)), settings.crash_backoff_max) if err_count > 0 else 0
    return delay


def check_and_recover() -> None:
    """Check all approved clients and recover dead processes."""
    approved = client_repo.get_by_state("approved")
    now = time.time()

    for client_id, client in approved.items():
        proc = _alive_processes.get(client_id)

        # Process is alive — skip
        if proc and proc.is_alive():
            continue

        # PID still alive externally — record is stale, remove
        if _pid_alive(client.agent_pid):
            _alive_processes.pop(client_id, None)
            continue

        # Clean up stale state
        _alive_processes.pop(client_id, None)

        # Check backoff
        last = _last_crash.get(client_id, 0)
        backoff = get_backoff_seconds(client_id)
        if backoff > 0 and (now - last) < backoff:
            logger.info(f"Client {client_id[:12]}... in backoff ({backoff}s remaining)")
            continue

        # Re-launch
        state_repo.delete(client_id)
        _error_counts[client_id] = _error_counts.get(client_id, 0) + 1
        _last_crash[client_id] = now
        logger.info(f"Recovering client {client_id[:12]}... (crash #{_error_counts[client_id]})")
        start(client)


def reset_error_count(client_id: str) -> None:
    _error_counts.pop(client_id, None)
    _last_crash.pop(client_id, None)
```

**Step 2: Verify**

```bash
ruff check src/orchestrator/
# Expected: no errors
python -c "from src.orchestrator.manager import check_and_recover; print('Orchestrator OK')"
# Expected: Orchestrator OK
```

**Step 3: Commit**

```bash
git add src/orchestrator/
git commit -m "feat: add orchestrator with process lifecycle and crash recovery"
```

---

### Task 11: Automation service

**Files:**
- Create: `src/services/automation_service.py`

**Step 1: Write src/services/automation_service.py**

```python
from __future__ import annotations

from src.domain.errors import NotFoundError, InvalidStateError
from src.infrastructure.repositories import client_repo, state_repo
from src.infrastructure import logging as client_logging
from src.orchestrator import manager as orchestrator
from src.services.client_service import ClientService


class AutomationService:
    """Coordinates automation lifecycle between client data and orchestrator."""

    @staticmethod
    def start(token: str) -> dict:
        client = ClientService.get_by_token(token)
        if not client:
            raise NotFoundError(f"Token {token[:12]}... not found")

        if not client.can_start:
            raise InvalidStateError(f"Client {client.id[:12]}... cannot start (state={client.state.value})")

        ok = orchestrator.start(client)
        if ok:
            client_repo.update_field(client.id, state="approved")
        return {"client_id": client.id, "started": ok}

    @staticmethod
    def stop(token: str) -> dict:
        client = ClientService.get_by_token(token)
        if not client:
            raise NotFoundError(f"Token {token[:12]}... not found")
        ok = orchestrator.stop(client.id)
        return {"client_id": client.id, "stopped": ok}

    @staticmethod
    def get_status(token: str) -> dict:
        client = ClientService.get_by_token(token)
        if not client:
            raise NotFoundError(f"Token {token[:12]}... not found")

        state = state_repo.load(client.id) or {}
        running = orchestrator.is_alive(client.id)
        return {
            "is_running": running,
            "client_state": client.state.value,
            **state,
        }

    @staticmethod
    def read_logs(client_id: str, lines: int = 200) -> str:
        return client_logging.read_client_log(client_id, lines)
```

**Step 2: Verify**

```bash
ruff check src/services/automation_service.py
# Expected: no errors
```

**Step 3: Commit**

```bash
git add src/services/automation_service.py
git commit -m "feat: add automation service"
```

---

## Phase 3 — Refactor scraper

### Task 12: Base scraper abstraction

**Files:**
- Create: `src/scraper/base.py`

**Step 1: Write src/scraper/base.py**

```python
from __future__ import annotations

import os
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import sync_playwright

from src.config import settings
from src.infrastructure.logging import ClientLoggerAdapter
from src.infrastructure.repositories import state_repo as state_db
from src.services.notification_service import NotificationService


@dataclass
class CheckResult:
    available: bool
    date: datetime | None = None
    location: str | None = None


class VisaScraper(ABC):
    """Abstract base for visa portal scrapers."""

    USER_AGENTS: list[str] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    ]

    def __init__(
        self,
        client_id: str,
        username: str,
        password: str,
        appointment_id: str | None = None,
        appointment_url: str | None = None,
        reschedule: bool = False,
        preferred_locations: list[str] | None = None,
        preferred_date_from: str | None = None,
        preferred_date_to: str | None = None,
        notification_email: str | None = None,
        telegram_chat_id: str | None = None,
        phone_number: str | None = None,
    ) -> None:
        self.client_id = client_id
        self.username = username
        self.password = password
        self.appointment_id = appointment_id or ""
        self.appointment_url = appointment_url or ""
        self.reschedule = reschedule
        self.preferred_locations = preferred_locations
        self.preferred_date_from = preferred_date_from
        self.preferred_date_to = preferred_date_to
        self.notification_email = notification_email
        self.telegram_chat_id = telegram_chat_id
        self.phone_number = phone_number

        self.log = ClientLoggerAdapter(client_id)
        self.notifier = NotificationService()

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._is_running = False
        self._shutting_down = False

        self.current_date: datetime | None = None
        self.new_date: datetime | None = None
        self.current_action: str = ""
        self.action_log: list[dict[str, str]] = []
        self.last_checked_location: str | None = None
        self.screenshot_path: str | None = None
        self.poll_count: int = 0
        self.debug_counter: int = 0

    # ── Abstract methods (portal-specific) ─────────────────────────────────

    @abstractmethod
    def get_login_url(self) -> str: ...

    @abstractmethod
    def get_selectors(self) -> dict[str, str]: ...

    @abstractmethod
    def get_visa_locations(self) -> dict[str, str]: ...

    @abstractmethod
    def login(self) -> bool: ...

    @abstractmethod
    def get_current_appointment(self) -> datetime | None: ...

    @abstractmethod
    def check_availability(self, location: str) -> CheckResult: ...

    @abstractmethod
    def reschedule_to(self, location: str) -> bool: ...

    # ── Shared lifecycle ─────────────────────────────────────────────────

    def _log(self, msg: str, level: str = "info") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.action_log.append({"ts": ts, "msg": msg})
        if len(self.action_log) > settings.max_action_log_entries:
            self.action_log = self.action_log[-settings.max_action_log_entries:]
        if not self._shutting_down:
            self._persist_state()
        getattr(self.log, level)(msg)

    def _persist_state(self) -> None:
        state_db.save(self.client_id, {
            "is_running": self._is_running,
            "current_action": self.current_action,
            "action_log": self.action_log,
            "current_appointment": str(self.current_date) if self.current_date else None,
            "new_appointment": str(self.new_date) if self.new_date else None,
            "last_checked_location": self.last_checked_location,
            "screenshot_path": self.screenshot_path,
        })

    def _log_url(self, label: str) -> None:
        try:
            url = self._page.url
            self._log(f"[{label}] URL: {url}")
        except Exception:
            self._log(f"[{label}] URL: <unreachable>", "warn")

    def _screenshot(self, name: str, persist: bool = False) -> None:
        self.debug_counter += 1
        screenshot_dir = Path(settings.screenshot_base) / self.client_id
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = screenshot_dir / f"{self.debug_counter:03d}_{name}.png"
        try:
            self._page.screenshot(path=str(path))
            if persist:
                self.screenshot_path = str(path)
                self._persist_state()
        except Exception:
            pass

    def _notify(self, message: str) -> None:
        self.notifier.send(
            message=message,
            email_addr=self.notification_email,
            telegram_chat_id=self.telegram_chat_id,
            phone_number=self.phone_number,
            logger=lambda msg, lvl="info": self._log(msg, lvl),
        )

    def _init_browser(self) -> None:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)

    def _close_browser(self) -> None:
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass

    def _new_context(self) -> None:
        if self._context:
            self._context.close()
        user_agent = random.choice(self.USER_AGENTS)
        self._context = self._browser.new_context(user_agent=user_agent)
        self._page = self._context.new_page()

    def _navigate(self, url: str) -> None:
        self._page.goto(url)
        self._page.wait_for_load_state("networkidle")

    # ── Main loop ────────────────────────────────────────────────────────

    def run(self) -> None:
        self._is_running = True
        self._log("Automation started")
        self._notify("Visa Automation started — monitoring for earlier dates...")

        try:
            self._init_browser()

            while self._is_running:
                for session_num in range(1):  # 1 session per cycle
                    if not self._is_running:
                        break
                    try:
                        self._new_context()
                        self.login()
                        self.current_date = self.get_current_appointment()

                        for check_num in range(12):  # 12 checks per session
                            if not self._is_running:
                                return
                            self._log(f"Check {check_num + 1}/12")
                            self._run_check_cycle()

                            if check_num < 11:
                                self._sleep_before_retry(check_num)

                    except Exception as e:
                        self._handle_error(e)
                    finally:
                        if self._context:
                            self._context.close()

                if self._is_running:
                    wait = random.randint(30, 60)
                    self._log(f"Waiting {wait}s before next cycle")
                    time.sleep(wait)

        finally:
            self._is_running = False
            self._shutting_down = True
            self._close_browser()
            self._persist_state()
            self._log("Automation stopped")

    def _run_check_cycle(self) -> bool:
        locations = self.get_visa_locations()
        if self.preferred_locations:
            locations = {k: v for k, v in locations.items() if k in self.preferred_locations}

        found = False
        for location in locations:
            self.last_checked_location = location
            self._log(f"Checking {location}")
            result = self.check_availability(location)

            if result.available and result.date:
                self.new_date = result.date

                # Check preferred date window
                if not self._in_preferred_window(result.date):
                    self._log(f"Date {result.date.date()} outside preferred window — skipping")
                    continue

                msg = f"Date available at {location} on {result.date.strftime('%Y-%m-%d')}"
                self._log(msg)
                self._screenshot(f"date_found_{location}", persist=True)

                if self.current_date and result.date < self.current_date:
                    self._notify(f"Earlier date found at {location}: {result.date.strftime('%Y-%m-%d')}")

                if self.reschedule and self.current_date and result.date < self.current_date:
                    self.reschedule_to(location)

                found = True

        return found

    def _in_preferred_window(self, date: datetime) -> bool:
        if not self.preferred_date_from and not self.preferred_date_to:
            return True
        if self.preferred_date_from and date < datetime.strptime(self.preferred_date_from, "%Y-%m-%d"):
            return False
        if self.preferred_date_to and date > datetime.strptime(self.preferred_date_to, "%Y-%m-%d"):
            return False
        return True

    def _sleep_before_retry(self, check_num: int) -> None:
        base = (check_num // 5) * 30
        sleep_time = random.randint(base, base + 30)
        self._log(f"Sleeping {sleep_time}s before next check")
        time.sleep(sleep_time)

    def _handle_error(self, error: Exception) -> None:
        self._log(f"Error: {error}", "error")
        self._screenshot("error")
        time.sleep(300)

    def stop(self) -> None:
        self._is_running = False
        self._log("Stop requested")
```

**Step 2: Verify**

```bash
ruff check src/scraper/base.py
# Expected: no errors
```

**Step 3: Commit**

```bash
git add src/scraper/base.py
git commit -m "feat: add abstract VisaScraper base class"
```

---

### Task 13: Canada scraper

**Files:**
- Create: `src/scraper/canada/selectors.py`
- Create: `src/scraper/canada/scraper.py`

**Step 1: Write src/scraper/canada/selectors.py**

```python
SELECTORS: dict[str, str] = {
    "username": "Email",
    "password": "Password",
    "terms_label": "I have read and understood the Privacy Policy and the Terms of Use",
    "sign_in_button": "Sign In",
    "continue_button": "Continue",
    "not_available": "#consulate_date_time_not_available",
    "location": "#appointments_consulate_appointment_facility_id",
    "date_dropdown": "#appointments_consulate_appointment_date",
    "calendar_title": ".ui-datepicker-title",
    "calendar_month": ".ui-datepicker-month",
    "calendar_year": ".ui-datepicker-year",
    "match_date": ".ui-datepicker-group-first  td.undefined > a.ui-state-default",
    "appointment_date": ".consular-appt",
    "time_slot": "#appointments_consulate_appointment_time",
    "next_button": "Next",
    "applicants_checkbox": "input[type='checkbox'][name^='applicants']",
}

APPOINTMENT_DATE_REGEX = r".*Appointment:(.*)(?:Vancouver|Toronto|Calgary|Ottawa|Halifax|Montreal) local time.*$"
LOGIN_URL = "https://ais.usvisa-info.com/en-ca/niv/users/sign_in"
APPOINTMENT_URL_TEMPLATE = "https://ais.usvisa-info.com/en-ca/niv/schedule/{}/appointment"

VISA_LOCATIONS: dict[str, str] = {
    "Toronto": "225 Simcoe Street, Toronto, ON, M5G 1S4, Canada",
    "Vancouver": "1075 West Pender Street, Vancouver, BC, V6E 2M6, Canada",
    "Calgary": "615 Macleod Trail, SE, Suite 1000, Calgary, AB, T2G 4T8, Canada",
    "Ottawa": "490 Sussex Drive, Ottawa, ON, K1N 1G8, Canada",
    "Halifax": "Suite 904, Purdy's Wharf Tower II, 1969 Upper Water Street, Halifax, NS, B3J 3R7, Canada",
    "Montreal": "1134 Saint-Catherine St. West, Montréal, QC, H3B 1H4, Canada",
}

MONTH_MAP: dict[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
```

**Step 2: Write src/scraper/canada/scraper.py**

```python
from __future__ import annotations

import re
import time
from datetime import datetime

from dateutil import parser
from playwright.sync_api import TimeoutError

from src.scraper.base import CheckResult, VisaScraper
from src.scraper.canada import selectors


class CanadaVisaScraper(VisaScraper):

    def get_login_url(self) -> str:
        return selectors.LOGIN_URL

    def get_selectors(self) -> dict[str, str]:
        return selectors.SELECTORS

    def get_visa_locations(self) -> dict[str, str]:
        return selectors.VISA_LOCATIONS

    def get_appointment_url(self) -> str:
        return selectors.APPOINTMENT_URL_TEMPLATE.format(self.appointment_id)

    def login(self) -> bool:
        s = selectors.SELECTORS
        try:
            self._log("Attempting login")
            self.current_action = "LOGIN"
            self._navigate(selectors.LOGIN_URL)
            self._screenshot("login_page")

            self._page.get_by_label(s["username"]).fill(self.username)
            self._page.get_by_label(s["password"]).fill(self.password)
            self._page.locator("label").filter(has_text=s["terms_label"]).click()
            self._page.get_by_role("button", name=s["sign_in_button"]).click()

            self._log("Login successful")
            self._screenshot("login_success")
            self.current_action = "IDLE"
            return True

        except Exception as e:
            self._log(f"Login failed: {e}", "error")
            self._screenshot("login_error")
            time.sleep(60)
            # Retry with alternate flow
            try:
                self._page.get_by_role("menuitem", name=s["continue_button"]).click()
            except Exception:
                pass
            return False

    def get_current_appointment(self) -> datetime | None:
        try:
            date_text = self._page.locator(selectors.SELECTORS["appointment_date"]).text_content()
        except Exception as e:
            e_strings = str(e).split("get_by_text")
            if len(e_strings) > 1:
                start = e_strings[1].index("(")
                end = e_strings[1].index(")")
                date_text = e_strings[1][start + 1: end]
            else:
                self._log("Could not parse current appointment", "warning")
                return None

        date_text = date_text.replace("\n", "")
        matches = re.search(selectors.APPOINTMENT_DATE_REGEX, date_text)
        if matches:
            date_text = matches.group(1).strip()
            return parser.parse(date_text)
        self._log("No current appointment found", "warning")
        return None

    def check_availability(self, location: str) -> CheckResult:
        if location not in selectors.VISA_LOCATIONS:
            return CheckResult(available=False)

        s = selectors.SELECTORS
        self._log(f"Selecting location: {location}")

        try:
            loc = self._page.locator(s["location"])
            if loc.count() == 0:
                self._log(f"Location selector not found for {location}", "error")
                return CheckResult(available=False)

            loc.select_option(location)
            self._page.wait_for_load_state("networkidle")
            self._screenshot(f"location_{location}")

            # Check if dates available
            try:
                self._page.wait_for_selector(s["not_available"], timeout=100)
                return CheckResult(available=False)
            except TimeoutError:
                pass  # Dates may be available

            # Open date picker
            try:
                self._page.wait_for_selector(s["date_dropdown"], timeout=5000)
                self._page.locator(s["date_dropdown"]).click(timeout=10000)
            except Exception as e:
                self._log(f"Error opening date picker: {e}", "error")
                return CheckResult(available=False)

            # Iterate calendar months
            while True:
                cal_date = self._parse_calendar_date()
                if cal_date:
                    self._screenshot(f"date_found_{location}")
                    self._page.keyboard.press("Escape")
                    return CheckResult(available=True, date=cal_date, location=location)

                next_btn = self._page.get_by_text(s["next_button"])
                if next_btn.count() == 0:
                    break
                next_btn.click()
                time.sleep(0.2)

            self._page.keyboard.press("Escape")
            return CheckResult(available=False)

        except Exception as e:
            self._log(f"Error checking {location}: {e}", "error")
            return CheckResult(available=False)

    def _parse_calendar_date(self) -> datetime | None:
        s = selectors.SELECTORS
        try:
            match_el = self._page.query_selector(s["match_date"])
            if not match_el:
                return None
            day = int(match_el.text_content())
            month = self._page.locator(s["calendar_month"]).first.text_content()
            year = int(self._page.locator(s["calendar_year"]).first.text_content())
            month_num = selectors.MONTH_MAP.get(month[:3].lower())
            if month_num:
                return datetime(year, month_num, day)
        except Exception:
            pass
        return None

    def reschedule_to(self, location: str) -> bool:
        s = selectors.SELECTORS
        try:
            self.current_action = "RESCHEDULING"
            self._log(f"Rescheduling at {location}")
            self._screenshot("before_reschedule")

            # Handle multiple applicants
            checkbox = self._page.locator(s["applicants_checkbox"])
            count = checkbox.count()
            if count > 1:
                for i in range(count):
                    cb = checkbox.nth(i)
                    if cb.is_checked():
                        cb.uncheck()
                self._page.get_by_text(s["continue_button"]).click()

            # Click new date
            self._page.query_selector(s["match_date"]).click()
            time.sleep(0.5)

            # Select time
            options = self._page.locator(s["time_slot"]).text_content()
            option = options.strip()[:5]
            self._page.locator(s["time_slot"]).select_option(option)

            self._page.get_by_text("Reschedule").last.click()
            self._page.get_by_text("Confirm").last.click()
            time.sleep(5)

            self.current_date = self.get_current_appointment()
            addr = selectors.VISA_LOCATIONS.get(location, location)
            msg = f"Rescheduled to earlier date at {location}: {self.current_date}\nLocation: {addr}"
            self._log(msg)
            self._notify(msg)
            self._screenshot("reschedule_complete")
            self.current_action = "IDLE"
            return True

        except Exception as e:
            self._log(f"Reschedule failed: {e}", "error")
            self._screenshot("reschedule_error")
            self.current_action = "IDLE"
            return False
```

**Step 3: Verify**

```bash
ruff check src/scraper/canada/
# Expected: no errors
```

**Step 4: Commit**

```bash
git add src/scraper/canada/
git commit -m "feat: add Canada scraper implementation"
```

---

### Task 14: UK scraper (skeleton, ported from existing)

**Files:**
- Create: `src/scraper/uk/selectors.py`
- Create: `src/scraper/uk/scraper.py`

**Step 1: Write src/scraper/uk/selectors.py**

Ported from the existing `uk/main.py` with corrections. UK module needs its own selectors.

```python
SELECTORS: dict[str, str] = {
    "username": "Email",
    "password": "Password",
    "terms_label": "I have read and understood the Privacy Policy and the Terms of Use",
    "sign_in_button": "Sign In",
    "continue_button": "Continue",
    "not_available": "#consulate_date_time_not_available",
    "location": "#appointments_consulate_appointment_facility_id",
    "date_dropdown": "#appointments_consulate_appointment_date",
    "calendar_title": ".ui-datepicker-title",
    "calendar_month": ".ui-datepicker-month",
    "calendar_year": ".ui-datepicker-year",
    "match_date": ".ui-datepicker-group-first  td.undefined > a.ui-state-default",
    "appointment_date": ".consular-appt",
    "time_slot": "#appointments_consulate_appointment_time",
    "next_button": "Next",
}

LOGIN_URL = "https://ais.usvisa-info.com/en-uk/niv/users/sign_in"
APPOINTMENT_URL_TEMPLATE = "https://ais.usvisa-info.com/en-uk/niv/schedule/{}/appointment"

VISA_LOCATIONS: dict[str, str] = {
    "London": "Consular Address, 33 Nine Elms Lane, London, SW11 7US, United Kingdom",
    "Belfast": "Consular Address, Belfast, United Kingdom",
}
```

**Step 2: Write src/scraper/uk/scraper.py**

```python
from __future__ import annotations

from datetime import datetime

from src.scraper.base import CheckResult, VisaScraper
from src.scraper.uk import selectors


class UKVisaScraper(VisaScraper):
    """UK visa portal scraper. Shares most Playwright patterns with Canada."""

    def get_login_url(self) -> str:
        return selectors.LOGIN_URL

    def get_selectors(self) -> dict[str, str]:
        return selectors.SELECTORS

    def get_visa_locations(self) -> dict[str, str]:
        return selectors.VISA_LOCATIONS

    def get_appointment_url(self) -> str:
        return selectors.APPOINTMENT_URL_TEMPLATE.format(self.appointment_id)

    def login(self) -> bool:
        # Same login flow as Canada — portal uses the same UI pattern
        # (Implementation mirrors Canada login; import shared helpers if needed)
        self._log("UK login — stub")
        return True

    def get_current_appointment(self) -> datetime | None:
        self._log("UK get_current_appointment — stub")
        return None

    def check_availability(self, location: str) -> CheckResult:
        return CheckResult(available=False)

    def reschedule_to(self, location: str) -> bool:
        return False
```

**Step 3: Commit**

```bash
git add src/scraper/uk/
git commit -m "feat: add UK scraper skeleton"
```

---

## Phase 4 — Flask Blueprints

### Task 15: App factory

**Files:**
- Create: `src/app/create.py`

**Step 1: Write src/app/create.py**

```python
from __future__ import annotations

from flask import Flask

from src.config import settings
from src.infrastructure.database import init_db
from src.infrastructure.repositories import settings_repo
from src.app.routes import auth, admin, client, telegram


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = settings.secret_key

    # Initialize DB and settings cache
    init_db()
    settings_repo.load_cache()

    # Register blueprints
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(client.bp)
    app.register_blueprint(telegram.bp)

    return app
```

**Step 2: Commit**

```bash
git add src/app/create.py
git commit -m "feat: add Flask app factory"
```

---

### Task 16: Auth blueprint

**Files:**
- Create: `src/app/routes/auth.py`

Full implementation ported from `canada/app.py` login/logout routes — session-based auth with `ADMIN_PASSWORD`.

**Step 1: Write src/app/routes/auth.py**

```python
from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, session, url_for

from src.config import settings


bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        submitted = request.form.get("password", "")
        if settings.admin_password and submitted == settings.admin_password:
            session["authenticated"] = True
            return redirect(url_for("admin.index"))
        error = "ACCESS_DENIED // INVALID_CREDENTIALS"
    return render_template("login.html", error=error)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
```

**Step 2: Commit**

```bash
git add src/app/routes/auth.py
git commit -m "feat: add auth blueprint"
```

---

### Task 17: Admin blueprint

**Files:**
- Create: `src/app/routes/admin.py`

**Step 1: Write src/app/routes/admin.py**

```python
from __future__ import annotations

import json
from functools import wraps

from flask import Blueprint, jsonify, render_template, request, url_for

from src.services.client_service import ClientService
from src.services.automation_service import AutomationService
from src.orchestrator import manager as orchestrator
from src.infrastructure.repositories import settings_repo


bp = Blueprint("admin", __name__, url_prefix="/admin")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        from flask import session, redirect
        if not session.get("authenticated"):
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


@bp.route("/")
@login_required
def index():
    return render_template("admin/dashboard.html")


@bp.route("/pending_requests")
@login_required
def pending_requests():
    result = {}
    for token, client in ClientService.get_pending().items():
        result[token] = {
            "name": client.name or "—",
            "email": client.notification_email or "—",
            "appointment_id": client.appointment_id or "—",
            "reschedule": client.reschedule,
            "locations": client.preferred_locations or [],
        }
    return jsonify(result)


@bp.route("/approve/<token>", methods=["POST"])
@login_required
def approve(token):
    client = ClientService.get_by_token(token)
    if not client or client.state.value != "pending":
        return jsonify({"status": "error", "message": "No pending request"}), 400
    result = AutomationService.start(token)
    return jsonify({"status": "approved" if result["started"] else "error"})


@bp.route("/reject/<token>", methods=["POST"])
@login_required
def reject(token):
    reason = request.form.get("reason", "Request was not approved.")
    ClientService.reject(token, reason)
    return jsonify({"status": "rejected"})


@bp.route("/logs/<client_id>")
@login_required
def logs(client_id):
    lines = int(request.args.get("lines", 200))
    log_text = AutomationService.read_logs(client_id, lines)
    return jsonify({"status": "ok", "log": log_text})


@bp.route("/stop/<token>", methods=["POST"])
@login_required
def stop(token):
    AutomationService.stop(token)
    return jsonify({"status": "stopped"})


@bp.route("/status")
@login_required
def all_status():
    result = {}
    for cid, client in ClientService.get_approved().items():
        st = AutomationService.get_status(cid)
        result[cid] = st
    return jsonify(result)


@bp.route("/settings")
@login_required
def get_settings():
    return jsonify({
        "default_notif_email": settings_repo.get("default_notif_email", ""),
        "email_enabled": settings_repo.get("email_enabled", "true"),
        "telegram_enabled": settings_repo.get("telegram_enabled", "false"),
        "sms_enabled": settings_repo.get("sms_enabled", "false"),
    })


@bp.route("/settings", methods=["POST"])
@login_required
def save_settings():
    settings_repo.set("default_notif_email", request.form.get("default_notif_email", ""))
    settings_repo.set("email_enabled", "true" if request.form.get("email_enabled") in ("true", "on") else "false")
    settings_repo.set("telegram_enabled", "true" if request.form.get("telegram_enabled") in ("true", "on") else "false")
    settings_repo.set("sms_enabled", "true" if request.form.get("sms_enabled") in ("true", "on") else "false")
    return jsonify({"status": "ok"})
```

**Step 2: Commit**

```bash
git add src/app/routes/admin.py
git commit -m "feat: add admin blueprint with dashboard, approvals, logs, settings"
```

---

### Task 18: Client blueprint

**Files:**
- Create: `src/app/routes/client.py`

**Step 1: Write src/app/routes/client.py**

Ports `client_submit`, `client_status`, `client_stop`, `client_screenshot` from `canada/app.py`.

Renders `client/form.html` at `/client/<token>`.

**Step 2: Commit**

```bash
git add src/app/routes/client.py
git commit -m "feat: add client blueprint with submit, status, stop"
```

---

### Task 19: Telegram blueprint

**Files:**
- Create: `src/app/routes/telegram.py`

Ports the Telegram webhook, `/set_telegram_webhook`, `/generate_telegram_link`, `/check_telegram_linked`, `/client_link_telegram`, `/client_update_notif` from `canada/app.py`.

**Step 2: Commit**

```bash
git add src/app/routes/telegram.py
git commit -m "feat: add telegram blueprint with webhook and link flow"
```

---

## Phase 5 — Cutover and Cleanup

### Task 20: Update entry points

- Modify `Dockerfile` to use `src.app:create_app` as entrypoint (via `waitress`)
- Add `run.py` at project root for dev usage
- Update `Makefile` targets

### Task 21: Remove legacy code

- Remove `canada/` directory (after migration)
- Remove `uk/` directory
- Update `.gitignore`
- Update `AGENTS.md`

---

## Execution Notes

1. Tasks are **sequential dependencies** — Phase must complete before Phase 2
2. At each Phase boundary: run `ruff check . && ruff format .` to ensure code quality
3. The existing app runs off `canada/app.py` until Phase 4 cutover — no downtime
4. Phase 5 is the final cleanup after confirming the new app works
