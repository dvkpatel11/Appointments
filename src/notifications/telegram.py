from __future__ import annotations

import requests

from src.config import settings


def send(message: str, chat_id: str | None = None, emoji: str = "🇨🇦", logger: callable | None = None) -> bool:
    bot_token = settings.telegram_bot_token
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
