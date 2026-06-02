from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

from src.config import settings


def send(subject: str, message: str, to_email: str, logger: callable | None = None) -> bool:
    if not to_email or not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        if logger:
            logger("SMTP not configured, skipping email", "warning")
        return False
    try:
        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"] = settings.smtp_user
        msg["To"] = to_email
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_user, [to_email], msg.as_string())
        if logger:
            logger(f"Email sent to {to_email}")
        return True
    except Exception as e:
        if logger:
            logger(f"Email send failed: {e}", "error")
        return False
