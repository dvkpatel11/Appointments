import os
import json
import sqlite3
import time
from datetime import datetime
from contextlib import contextmanager

from canada import config


DB_PATH = os.environ.get("DB_PATH", config.DB_PATH)


def get_conn():
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

            CREATE TABLE IF NOT EXISTS client_tokens (
                token TEXT PRIMARY KEY,
                state TEXT NOT NULL DEFAULT 'issued',
                user_id TEXT,
                request_data TEXT,
                reject_reason TEXT,
                notification_email TEXT,
                telegram_chat_id TEXT,
                phone_number TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS automation_state (
                user_id TEXT PRIMARY KEY,
                is_running INTEGER NOT NULL DEFAULT 0,
                current_action TEXT,
                action_log TEXT,
                current_appointment TEXT,
                new_appointment TEXT,
                last_checked_location TEXT,
                appointments_page_screenshot TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS pending_links (
                token TEXT PRIMARY KEY,
                chat_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                linked_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                data TEXT,
                expires_at TIMESTAMP
            );
        """)

    with cursor() as cur:
        try:
            cur.execute("ALTER TABLE client_tokens ADD COLUMN phone_number TEXT")
        except sqlite3.OperationalError:
            pass

    with cursor() as cur:
        if os.path.exists(config.SETTINGS_FILE):
            try:
                with open(config.SETTINGS_FILE) as f:
                    data = json.load(f)
                for key, value in data.items():
                    cur.execute(
                        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                        (key, json.dumps(value) if not isinstance(value, str) else value)
                    )
            except Exception:
                pass

        if os.path.exists(config.CLIENT_TOKENS_FILE):
            try:
                with open(config.CLIENT_TOKENS_FILE) as f:
                    tokens = json.load(f)
                for token, data in tokens.items():
                    cur.execute(
                        """INSERT OR REPLACE INTO client_tokens
                           (token, state, user_id, request_data, reject_reason,
                            notification_email, telegram_chat_id, phone_number)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (token,
                         data.get("state", "issued"),
                         data.get("user_id"),
                         json.dumps(data.get("request")),
                         data.get("reject_reason"),
                         data.get("notification_email"),
                         data.get("telegram_chat_id"),
                         data.get("phone_number"))
                    )
            except Exception:
                pass


SETTINGS_CACHE = {}


def load_settings_into_cache():
    global SETTINGS_CACHE
    SETTINGS_CACHE = dict(config.DEFAULT_SETTINGS)
    with cursor() as cur:
        cur.execute("SELECT key, value FROM settings")
        for row in cur.fetchall():
            SETTINGS_CACHE[row["key"]] = row["value"]


def get_setting(key, default=None):
    val = SETTINGS_CACHE.get(key)
    return val if val is not None else default


def set_setting(key, value):
    SETTINGS_CACHE[key] = value
    with cursor() as cur:
        cur.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )


def get_client_token(token):
    with cursor() as cur:
        cur.execute("SELECT * FROM client_tokens WHERE token = ?", (token,))
        row = cur.fetchone()
    if not row:
        return None
    return _row_to_client_token(row)


def get_all_client_tokens():
    with cursor() as cur:
        cur.execute("SELECT * FROM client_tokens")
        return {row["token"]: _row_to_client_token(row) for row in cur.fetchall()}


def get_client_tokens_by_state(state):
    with cursor() as cur:
        cur.execute("SELECT * FROM client_tokens WHERE state = ?", (state,))
        return {row["token"]: _row_to_client_token(row) for row in cur.fetchall()}


def save_client_token(token, data):
    existing = get_client_token(token) or {}
    merged = dict(existing)
    for key in ("state", "user_id", "reject_reason", "notification_email", "telegram_chat_id", "phone_number"):
        if key in data:
            merged[key] = data[key]
    if "request" in data:
        merged["request"] = data["request"]
    with cursor() as cur:
        cur.execute(
            """INSERT OR REPLACE INTO client_tokens
               (token, state, user_id, request_data, reject_reason,
                notification_email, telegram_chat_id, phone_number, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (token,
             merged.get("state", "issued"),
             merged.get("user_id"),
             json.dumps(merged["request"]) if merged.get("request") else None,
             merged.get("reject_reason"),
             merged.get("notification_email"),
             merged.get("telegram_chat_id"),
             merged.get("phone_number"))
        )


def _row_to_client_token(row):
    result = {
        "state": row["state"],
        "user_id": row["user_id"],
        "reject_reason": row["reject_reason"],
        "notification_email": row["notification_email"],
        "telegram_chat_id": row["telegram_chat_id"],
        "phone_number": row["phone_number"],
    }
    if row["request_data"]:
        try:
            result["request"] = json.loads(row["request_data"])
        except (json.JSONDecodeError, TypeError):
            result["request"] = None
    else:
        result["request"] = None
    return result


def save_automation_state(user_id, state_dict):
    with cursor() as cur:
        cur.execute(
            """INSERT OR REPLACE INTO automation_state
               (user_id, is_running, current_action, action_log,
                current_appointment, new_appointment,
                last_checked_location, appointments_page_screenshot, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (user_id,
             state_dict.get("is_running", False),
             state_dict.get("current_action"),
             json.dumps(state_dict.get("action_log", [])),
             state_dict.get("current_appointment"),
             state_dict.get("new_appointment"),
             state_dict.get("last_checked_location"),
             state_dict.get("appointments_page_screenshot"))
        )


def load_automation_state(user_id):
    with cursor() as cur:
        cur.execute("SELECT * FROM automation_state WHERE user_id = ?", (user_id,))
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


def delete_automation_state(user_id):
    with cursor() as cur:
        cur.execute("DELETE FROM automation_state WHERE user_id = ?", (user_id,))


def save_pending_link(token, data):
    def _ts(val, default=None):
        if val is None:
            return default
        if isinstance(val, (int, float)):
            return datetime.fromtimestamp(val).strftime("%Y-%m-%d %H:%M:%S")
        return str(val)
    with cursor() as cur:
        cur.execute(
            """INSERT OR REPLACE INTO pending_links
               (token, chat_id, created_at, linked_at)
               VALUES (?, ?, ?, ?)""",
            (token,
             data.get("chat_id"),
             _ts(data.get("created")),
             _ts(data.get("linked_at")))
        )


def get_pending_link(token):
    with cursor() as cur:
        cur.execute("SELECT * FROM pending_links WHERE token = ?", (token,))
        row = cur.fetchone()
    if not row:
        return None
    def _parse_ts(val):
        if not val:
            return 0 if val is None else None
        if isinstance(val, (int, float)):
            return int(val)
        try:
            return int(time.mktime(time.strptime(str(val), "%Y-%m-%d %H:%M:%S")))
        except (ValueError, TypeError):
            return 0
    return {
        "chat_id": row["chat_id"],
        "created": _parse_ts(row["created_at"]),
        "linked_at": _parse_ts(row["linked_at"]),
    }


def get_all_pending_links():
    with cursor() as cur:
        cur.execute("SELECT * FROM pending_links")
        result = {}
        for row in cur.fetchall():
            def _parse_ts(val):
                if not val:
                    return 0 if val is None else None
                if isinstance(val, (int, float)):
                    return int(val)
                try:
                    return int(time.mktime(time.strptime(str(val), "%Y-%m-%d %H:%M:%S")))
                except (ValueError, TypeError):
                    return 0
            result[row["token"]] = {
                "chat_id": row["chat_id"],
                "created": _parse_ts(row["created_at"]),
                "linked_at": _parse_ts(row["linked_at"]),
            }
        return result


def delete_pending_link(token):
    with cursor() as cur:
        cur.execute("DELETE FROM pending_links WHERE token = ?", (token,))


def delete_stale_pending_links(ttl):
    cutoff = time.time() - ttl
    with cursor() as cur:
        cur.execute(
            "DELETE FROM pending_links WHERE CAST(strftime('%%s', created_at) AS INTEGER) < ?",
            (int(cutoff),)
        )
        return cur.rowcount
