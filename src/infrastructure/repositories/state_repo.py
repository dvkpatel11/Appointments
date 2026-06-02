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
            (
                client_id,
                state_data.get("is_running", False),
                state_data.get("current_action"),
                json.dumps(state_data.get("action_log", [])),
                state_data.get("current_appointment"),
                state_data.get("new_appointment"),
                state_data.get("last_checked_location"),
                state_data.get("screenshot_path"),
                state_data.get("error_count", 0),
            ),
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
