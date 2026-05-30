from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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
