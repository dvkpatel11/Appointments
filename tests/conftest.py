"""Shared test fixtures.

Each test gets:
  - A temporary SQLite DB (DB_PATH monkey-patched BEFORE src.infrastructure.database is imported)
  - A valid Fernet key (ENCRYPTION_KEY monkey-patched BEFORE src.config is imported)
  - A clean src.config.settings (reloaded so pydantic-settings sees the new env)
"""
from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet


@pytest.fixture
def temp_db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the app at a fresh temp DB. Set BEFORE importing app modules."""
    db = tmp_path / "test_visactrl.db"
    monkeypatch.setenv("DB_PATH", str(db))
    return db


@pytest.fixture
def fernet_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """Generate a fresh Fernet key and expose it via ENCRYPTION_KEY."""
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    return key


@pytest.fixture
def app_modules(temp_db_path: Path, fernet_key: str):
    """Reload config + db modules so pydantic-settings sees the new env vars.
    Returns a namespace with the most commonly used handles."""
    import importlib

    from src import config
    from src.infrastructure import database

    importlib.reload(config)
    importlib.reload(database)
    database.init_db()

    return {"settings": config.settings, "db": database}
