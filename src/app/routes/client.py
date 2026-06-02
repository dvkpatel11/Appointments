import base64
import json
import os
import re

from flask import Blueprint, jsonify, render_template, request

from src.infrastructure.repositories import client_repo
from src.services.automation_service import AutomationService
from src.services.client_service import ClientService

bp = Blueprint("client", __name__)


@bp.route("/client")
def client_form():
    return render_template("client/form.html", token="")


@bp.route("/client/<token>")
def client_view(token):
    client = ClientService.get_by_token(token)
    if not client:
        return render_template("client/form.html", token="", error="Invalid or expired link."), 404
    return render_template("client/form.html", token=token)


@bp.route("/client_submit", methods=["POST"])
def client_submit():
    try:
        token = request.form.get("token", "").strip()
        client = ClientService.get_by_token(token)

        if not token or not client:
            return jsonify({"status": "error", "message": "Invalid or expired link."}), 400

        if client.state.value in ("approved", "pending"):
            return jsonify({"status": "pending_approval", "message": "Your request is already submitted."})
        if client.state.value == "rejected":
            return jsonify({"status": "rejected", "reason": client.reject_reason or "Request was not approved."})

        appointment_id = request.form.get("appointment_id", "").strip()
        if not re.match(r"^\w+$", appointment_id):
            return jsonify({"status": "error", "message": f"Invalid appointment ID: {appointment_id}"}), 400

        appointment_url = "https://ais.usvisa-info.com/en-ca/niv/schedule/{}/appointment"
        raw_locs = request.form.get("preferred_locations", "")
        try:
            preferred_locations = json.loads(raw_locs) if raw_locs else None
        except (json.JSONDecodeError, TypeError):
            preferred_locations = None

        ClientService.submit_request(
            token,
            {
                "name": request.form.get("name", "Client"),
                "username": request.form.get("username", "").strip(),
                "password": request.form.get("password", ""),
                "appointment_id": appointment_id,
                "appointment_url": appointment_url,
                "reschedule": request.form.get("reschedule") == "true",
                "preferred_locations": preferred_locations,
                "preferred_date_from": request.form.get("preferred_date_from", "").strip() or None,
                "preferred_date_to": request.form.get("preferred_date_to", "").strip() or None,
                "telegram_chat_id": request.form.get("telegram_chat_id", "").strip() or None,
            },
        )
        return jsonify({"status": "pending_approval"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/client_status/<token>")
def client_status(token):
    client = ClientService.get_by_token(token)
    if not client:
        return jsonify({"status": "not_found"}), 404

    if client.state.value == "issued":
        return jsonify({"status": "issued"})
    if client.state.value == "pending":
        return jsonify({"status": "pending_approval"})
    if client.state.value == "rejected":
        return jsonify({"status": "rejected", "reason": client.reject_reason})

    try:
        st = AutomationService.get_status(token)
        notif_info = {
            "notification_email": client.notification_email or "",
            "telegram_chat_id": client.telegram_chat_id or "",
            "phone_number": client.phone_number or "",
        }
        return jsonify({"status": "ok", **st, **notif_info})
    except Exception:
        return jsonify(
            {
                "status": "approved",
                "is_running": False,
                "current_action": None,
                "action_log": [],
                "current_appointment": None,
                "new_appointment": None,
                "last_checked_location": None,
            }
        )


@bp.route("/client_stop/<token>", methods=["POST"])
def client_stop(token):
    client = ClientService.get_by_token(token)
    if not client:
        return jsonify({"status": "error", "message": "Token not found"}), 404

    AutomationService.stop(token)
    client_repo.update_field(client.id, state="issued", agent_pid=None)
    return jsonify({"status": "stopped", "message": "Monitoring stopped."})


@bp.route("/client_screenshot/<token>")
def client_screenshot(token):
    client = ClientService.get_by_token(token)
    if not client or client.state.value != "approved":
        return jsonify({"status": "unauthorized"}), 403

    from src.infrastructure.repositories import state_repo

    state = state_repo.load(client.id)
    path = (state or {}).get("screenshot_path")

    if not path or not os.path.exists(path):
        return jsonify({"status": "pending"})

    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return jsonify({"status": "ready", "image_url": f"data:image/png;base64,{b64}"})


@bp.route("/client_link_telegram", methods=["POST"])
def client_link_telegram():
    data = request.get_json() or {}
    user_id = data.get("user_id", "").strip()
    chat_id = data.get("chat_id", "").strip()
    if not user_id or not chat_id:
        return jsonify({"status": "error", "message": "Missing user_id or chat_id"})
    client = ClientService.get_by_id(user_id)
    if not client:
        return jsonify({"status": "error", "message": "Invalid token"}), 401
    client_repo.update_field(user_id, telegram_chat_id=chat_id)
    return jsonify({"status": "ok"})


@bp.route("/client_update_notif", methods=["POST"])
def client_update_notif():
    data = request.get_json() or {}
    user_id = data.get("user_id", "").strip()
    if not user_id:
        return jsonify({"status": "error", "message": "Missing user_id"})
    client = ClientService.get_by_id(user_id)
    if not client:
        return jsonify({"status": "error", "message": "Invalid token"}), 401

    update = {}
    if data.get("notification_email") is not None:
        update["notification_email"] = data["notification_email"]
    if data.get("phone_number") is not None:
        update["phone_number"] = data["phone_number"]
    if update:
        client_repo.update_field(user_id, **update)
    return jsonify({"status": "ok"})
