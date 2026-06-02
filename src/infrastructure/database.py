from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager

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
