from __future__ import annotations

from src.config import settings


def send(message: str, to_phone: str | None = None, logger: callable | None = None) -> bool:
    account_sid = settings.twilio_account_sid
    auth_token = settings.twilio_auth_token
    from_phone = settings.twilio_from_number
    if not account_sid or not auth_token or not from_phone or not to_phone:
        if logger:
            logger("Twilio not configured, skipping SMS", "warning")
        return False
    try:
        from twilio.rest import Client

        client = Client(account_sid, auth_token)
        client.messages.create(body=message, from_=from_phone, to=to_phone)
        if logger:
            logger(f"SMS sent to {to_phone}")
        return True
    except Exception as e:
        if logger:
            logger(f"SMS send failed: {e}", "error")
        return False
