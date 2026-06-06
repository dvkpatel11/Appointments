from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Profile:
    """A real-world visa portal account that may have one or more
    applications (appointment_ids) under it.

    A Profile owns:
    - Portal credentials (username + encrypted password), shared by all
      applications under the profile. Snapshotted onto each application at
      submit time so the orchestrator and scraper never need to know about
      profiles.
    - Notification contacts (email, telegram, phone). Read at notify time
      with a client-override → profile-fallback chain.

    A Profile is a pure data-layer grouping. It has no state machine and no
    scraper process. The state lives on each application (Client) row.
    """

    id: str
    token: str
    name: str | None = None
    username: str | None = None
    password: str | None = None
    notification_email: str | None = None
    notification_email_verified: bool = False
    telegram_chat_id: str | None = None
    phone_number: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
