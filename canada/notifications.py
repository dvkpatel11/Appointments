import os
import smtplib
import logging
from email.mime.text import MIMEText


# ── SMTP Email ─────────────────────────────────────────────────────────────────

def send_email(subject, message, to_email, logger=None):
    if not to_email:
        return False

    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")

    if not smtp_host or not smtp_user or not smtp_password:
        if logger:
            logger("SMTP not configured, skipping email", "warning")
        return False

    try:
        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = to_email

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, [to_email], msg.as_string())

        if logger:
            logger(f"Email sent to {to_email}")
        return True

    except Exception as e:
        if logger:
            logger(f"Email send failed: {e}", "error")
        return False


# ── Telegram ───────────────────────────────────────────────────────────────────

import requests


def send_telegram(message, chat_id=None, bot_token=None, emoji="🇨🇦", logger=None):
    bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        if logger:
            logger("Telegram not configured, skipping", "debug")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": f"{emoji} {message}"}

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            if logger:
                logger("Telegram notification sent")
            return True
        else:
            if logger:
                logger(f"Telegram failed: {response.status_code}", "warning")
            return False
    except Exception:
        if logger:
            logger("Telegram error", "error")
        return False


# ── SMS (Twilio) ────────────────────────────────────────────────────────────────


def send_sms(message, to_phone=None, logger=None):
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_phone = os.environ.get("TWILIO_FROM_NUMBER")
    to_phone = to_phone or os.environ.get("TWILIO_TO_NUMBER")

    if not account_sid or not auth_token or not from_phone or not to_phone:
        if logger:
            logger("Twilio not configured, skipping SMS", "warning")
        return False

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        client.messages.create(
            body=message,
            from_=from_phone,
            to=to_phone,
        )
        if logger:
            logger(f"SMS sent to {to_phone}")
        return True
    except Exception as e:
        if logger:
            logger(f"SMS send failed: {e}", "error")
        return False
