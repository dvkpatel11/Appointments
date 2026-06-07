"""Flask extensions, registered by the app factory.

Kept in a separate module so blueprints and route modules can import these
without triggering create_app() side effects (init_db, recovery thread, etc).
"""

from __future__ import annotations

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    # Default: no global rate limit. Endpoints opt in via @limiter.limit(...).
    default_limits=[],
    # Memory backend — works for single-process Waitress (which Cloud Run uses).
    # Switch to "redis://..." by setting RATELIMIT_STORAGE_URI for multi-process.
    storage_uri="memory://",
    # Trust the first hop in X-Forwarded-For so per-IP limits work behind
    # Cloud Run's reverse proxy. Behind one trusted proxy (the default),
    # X-Forwarded-For contains "<client>, <proxy>"; we want the client.
    headers_enabled=True,
    strategy="fixed-window",
)
