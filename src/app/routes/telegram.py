import time
import uuid

import requests
from flask import Blueprint, jsonify, request, url_for

from src.app.extensions import limiter
from src.config import settings
from src.infrastructure.logging import setup_server_logger

logger = setup_server_logger()

bp = Blueprint("telegram", __name__)


@bp.route("/set_telegram_webhook", methods=["GET"])
def set_webhook():
    bot_token = settings.telegram_bot_token
    if not bot_token:
        return "TELEGRAM_BOT_TOKEN not set"
    webhook_url = url_for("telegram.telegram_webhook", _external=True)
    r = requests.post(
        f"https://api.telegram.org/bot{bot_token}/setWebhook",
        json={"url": webhook_url},
        timeout=10,
    )
    return f"Webhook set: {r.json()}"


@bp.route("/telegram_webhook", methods=["POST"])
@limiter.limit("120 per minute")
def telegram_webhook():
    bot_token = settings.telegram_bot_token
    if not bot_token:
        return jsonify({"ok": True})

    try:
        data = request.get_json() or {}
        message = data.get("message", {})
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = message.get("text", "")

        if text.startswith("/start"):
            token = text.replace("/start", "").strip()
            link_data = _get_pending_link(token)
            if token and link_data:
                _save_pending_link(token, {"chat_id": str(chat_id), "linked_at": time.time()})
                requests.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": (
                            "✓ VisaCtrl Notifications linked!"
                            " You'll receive alerts when earlier dates become available."
                        ),
                    },
                    timeout=10,
                )
            else:
                requests.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": f"✓ Your Chat ID is: {chat_id}\n\nUse this ID in the VisaCtrl notification settings.",
                    },
                    timeout=10,
                )
        elif text in ("/myid", "/getid"):
            requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": f"Your Chat ID is: {chat_id}"},
                timeout=10,
            )
    except Exception as e:
        logger.warning("Telegram send chat_id failed: %s", e)
    return jsonify({"ok": True})


@bp.route("/bot_info")
def bot_info():
    return jsonify(
        {
            "username": settings.telegram_bot_username,
        }
    )


@bp.route("/generate_telegram_link", methods=["POST"])
def generate_telegram_link():
    token = str(uuid.uuid4())
    _save_pending_link(token, {"created": time.time(), "chat_id": None})
    return jsonify({"token": token})


@bp.route("/check_telegram_linked", methods=["POST"])
def check_telegram_linked():
    data = request.get_json() or {}
    token = data.get("token")
    link_data = _get_pending_link(token)
    if link_data and link_data.get("chat_id"):
        return jsonify({"linked": True, "chat_id": link_data["chat_id"]})
    return jsonify({"linked": False})


def _get_pending_link(token: str) -> dict | None:
    from src.infrastructure.database import cursor

    with cursor() as cur:
        cur.execute("SELECT * FROM pending_links WHERE token = ?", (token,))
        row = cur.fetchone()
    if not row:
        return None
    return {
        "chat_id": row["chat_id"],
        "created": row["created_at"],
        "linked_at": row["linked_at"],
    }


def _save_pending_link(token: str, data: dict) -> None:
    from datetime import datetime

    from src.infrastructure.database import cursor

    with cursor() as cur:
        cur.execute(
            "INSERT OR REPLACE INTO pending_links (token, chat_id, linked_at) VALUES (?, ?, ?)",
            (token, data.get("chat_id"), datetime.fromtimestamp(data["linked_at"]) if data.get("linked_at") else None),
        )
