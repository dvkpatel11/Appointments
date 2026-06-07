"""Initial state snapshot for client hydration.

When the dashboard loads, the browser hits ``GET /snapshot`` to populate
its local store with the current state of all clients, automation states,
pending requests, and global settings. Subsequent updates come via SSE.

This endpoint is the single source of truth for "what does the world look
like right now" — the SSE stream is for deltas, this is for the full picture.
"""

from __future__ import annotations

import time
from pathlib import Path

from flask import Blueprint, jsonify, session

from src.config import settings
from src.infrastructure.database import cursor
from src.infrastructure.repositories import client_repo, state_repo

bp = Blueprint("snapshot", __name__, url_prefix="/snapshot")


def _is_authed() -> bool:
    return bool(session.get("authenticated"))


@bp.route("/")
def snapshot():
    if not _is_authed():
        return jsonify({"error": "unauthorized"}), 401

    clients = client_repo.get_all()
    client_dicts: dict[str, dict] = {}
    state_dicts: dict[str, dict] = {}
    for cid, c in clients.items():
        client_dicts[cid] = {
            "id": c.id,
            "name": c.name or "Client",
            "state": c.state.value,
            "visa_type": c.visa_type.value,
            "reschedule": c.reschedule,
            "preferred_locations": c.preferred_locations or [],
            "appointment_id": c.appointment_id,
            "username": c.username,
            "notification_email": c.notification_email,
            "telegram_chat_id": c.telegram_chat_id,
            "phone_number": c.phone_number,
            "agent_pid": c.agent_pid,
            "updated_at": str(c.updated_at) if c.updated_at else None,
        }
        st = state_repo.load(cid)
        if st:
            state_dicts[cid] = {
                "is_running": bool(st.get("is_running", 0)),
                "current_action": st.get("current_action"),
                "action_log": st.get("action_log") or [],
                "current_appointment": st.get("current_appointment"),
                "new_appointment": st.get("new_appointment"),
                "last_checked_location": st.get("last_checked_location"),
                "screenshot_path": st.get("screenshot_path"),
                "error_count": st.get("error_count", 0) or 0,
                "updated_at": str(st.get("updated_at")) if st.get("updated_at") else None,
            }

    pending = [cid for cid, c in clients.items() if c.state.value == "pending"]
    approved = [cid for cid, c in clients.items() if c.state.value == "approved"]
    running = sum(1 for s in state_dicts.values() if s.get("is_running"))
    error_streak = sum(1 for s in state_dicts.values() if (s.get("error_count") or 0) > 0)

    with cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM clients WHERE updated_at > datetime('now', '-1 day')")
        recent = cur.fetchone()[0]

    # Latest screenshot per client (just one per client, most recent).
    screenshots: dict[str, str] = {}
    shot_root = Path(settings.screenshot_base)
    if shot_root.is_dir():
        for client_dir in shot_root.iterdir():
            if not client_dir.is_dir():
                continue
            files = sorted(client_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
            if files:
                screenshots[client_dir.name] = str(files[0])

    return jsonify(
        {
            "ts": time.time(),
            "clients": client_dicts,
            "states": state_dicts,
            "pending": pending,
            "approved": approved,
            "metrics": {
                "total": len(clients),
                "running": running,
                "pending": len(pending),
                "errors_24h": error_streak,
                "active_24h": recent,
            },
            "screenshots": screenshots,
            "settings": {
                "email_enabled": "true",
                "telegram_enabled": "false",
            },
        }
    )
