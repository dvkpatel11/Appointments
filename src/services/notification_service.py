from __future__ import annotations

from src import notifications
from src.infrastructure.repositories import settings_repo


class NotificationService:
    @staticmethod
    def send(
        message: str,
        email_addr: str | None = None,
        telegram_chat_id: str | None = None,
        phone_number: str | None = None,
        logger: callable | None = None,
    ) -> None:
        email_enabled = settings_repo.get("email_enabled", "true") == "true"
        telegram_enabled = settings_repo.get("telegram_enabled", "false") == "true"
        sms_enabled = settings_repo.get("sms_enabled", "false") == "true"

        if email_addr and email_enabled:
            notifications.email.send(
                subject=f"VISA UPDATE: {message[:50]}...",
                message=message,
                to_email=email_addr,
                logger=logger,
            )

        if telegram_chat_id and telegram_enabled:
            notifications.telegram.send(
                message=message,
                chat_id=telegram_chat_id,
                logger=logger,
            )

        if phone_number and sms_enabled:
            notifications.sms.send(
                message=message,
                to_phone=phone_number,
                logger=logger,
            )
