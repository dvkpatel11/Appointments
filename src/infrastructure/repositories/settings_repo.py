from __future__ import annotations

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
