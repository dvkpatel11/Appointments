from __future__ import annotations

import json
import uuid
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
            (
                client.id,
                client.token,
                client.name,
                client.state.value,
                client.reject_reason,
                client.username,
                client.password,
                client.appointment_id,
                client.appointment_url,
                client.visa_type.value,
                1 if client.reschedule else 0,
                json.dumps(client.preferred_locations) if client.preferred_locations else None,
                client.preferred_date_from,
                client.preferred_date_to,
                client.notification_email,
                client.telegram_chat_id,
                client.phone_number,
                client.agent_pid,
            ),
        )


def update_field(client_id: str, **kwargs: Any) -> None:
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
    token = uuid.uuid4().hex
    with cursor() as cur:
        cur.execute(
            "INSERT INTO clients (id, token, state) VALUES (?, ?, 'issued')",
            (token, token),
        )
    return token
