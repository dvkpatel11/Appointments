"""Shared test fixtures.

Each test gets:
  - A temporary SQLite DB (DB_PATH monkey-patched BEFORE src.infrastructure.database is imported)
  - A valid Fernet key (ENCRYPTION_KEY monkey-patched BEFORE src.config is imported)
  - A clean src.config.settings (reloaded so pydantic-settings sees the new env)

Fixtures defensively reload cached module state on entry, so tests are isolated
from each other regardless of order or what previous tests did to the env.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def temp_db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the app at a fresh temp DB and refresh src.infrastructure.database."""
    import importlib

    db = tmp_path / "test_visactrl.db"
    monkeypatch.setenv("DB_PATH", str(db))
    # Reload so the module-level DB_PATH constant rebinds to the new value.
    from src.infrastructure import database

    importlib.reload(database)
    return db


@pytest.fixture
def fernet_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """Generate a fresh Fernet key and refresh src.config + src.infrastructure.crypto.

    Reloading is required because prior tests may have set bad ENCRYPTION_KEY
    values and reloaded src.config — monkeypatch.undo() restores env vars but
    does not roll back module-level singletons.
    """
    import importlib

    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    from src import config
    from src.infrastructure import crypto

    importlib.reload(config)
    importlib.reload(crypto)
    return key


@pytest.fixture
def app_modules(temp_db_path: Path, fernet_key: str) -> dict[str, Any]:
    """Reload config + db + crypto modules and initialize the temp DB.

    Returns a dict with the most commonly used handles.
    """
    from src.infrastructure import database

    database.init_db()

    # Re-import after reloads so callers get the fresh module references.
    from src import config
    from src.infrastructure import crypto

    return {"settings": config.settings, "db": database, "crypto": crypto}
