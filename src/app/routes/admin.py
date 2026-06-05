from functools import wraps

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from src.infrastructure.repositories import settings_repo
from src.services.automation_service import AutomationService
from src.services.client_service import ClientService

bp = Blueprint("admin", __name__, url_prefix="/admin")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        from flask import session

        if not session.get("authenticated"):
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated


@bp.route("/")
@login_required
def index():
    return render_template("admin/dashboard.html")


@bp.route("/pending_requests")
@login_required
def pending_requests():
    result = {}
    for token, client in ClientService.get_pending().items():
        result[token] = {
            "name": client.name or "—",
            "email": client.notification_email or "—",
            "appointment_id": client.appointment_id or "—",
            "reschedule": client.reschedule,
            "locations": client.preferred_locations or [],
        }
    return jsonify(result)


@bp.route("/generate_client_link")
@login_required
def generate_client_link():
    token = ClientService.generate_link()
    base_url = request.host_url.rstrip("/")
    link = f"{base_url}/client/{token}"
    return jsonify({"token": token, "link": link})


@bp.route("/approve/<token>", methods=["POST"])
@bp.route("/approve_client/<token>", methods=["POST"])
@login_required
def approve(token):
    client = ClientService.get_by_token(token)
    if not client or client.state.value != "pending":
        return jsonify({"status": "error", "message": "No pending request"}), 400
    ClientService.approve(token)
    result = AutomationService.start(token)
    return jsonify({"status": "approved" if result["started"] else "error"})


@bp.route("/reject/<token>", methods=["POST"])
@bp.route("/reject_client/<token>", methods=["POST"])
@login_required
def reject(token):
    from src.domain.errors import NotFoundError
    reason = request.form.get("reason", "Request was not approved.")
    try:
        ClientService.reject(token, reason)
        return jsonify({"status": "rejected"})
    except NotFoundError:
        return jsonify({"status": "error", "message": "Client not found"}), 404


@bp.route("/logs/<client_id>")
@login_required
def logs(client_id):
    lines = int(request.args.get("lines", 200))
    log_text = AutomationService.read_logs(client_id, lines)
    return jsonify({"status": "ok", "log": log_text})


@bp.route("/stop/<token>", methods=["POST"])
@login_required
def stop(token):
    from src.domain.errors import NotFoundError
    client = ClientService.get_by_token(token)
    if not client:
        return jsonify({"status": "error", "message": "Client not found"}), 404
    try:
        AutomationService.stop(client.id)
        return jsonify({"status": "stopped"})
    except NotFoundError:
        return jsonify({"status": "error", "message": "Client not found"}), 404


@bp.route("/status")
@login_required
def all_status():
    result = {}
    for cid, client in ClientService.get_approved().items():
        st = AutomationService.get_status(cid)
        result[cid] = st
    return jsonify(result)


@bp.route("/settings")
@login_required
def settings_get():
    return jsonify(
        {
            "default_notif_email": settings_repo.get("default_notif_email", ""),
            "default_telegram_chat_id": settings_repo.get("default_telegram_chat_id", ""),
            "email_enabled": settings_repo.get("email_enabled", "true"),
            "telegram_enabled": settings_repo.get("telegram_enabled", "false"),
            "sms_enabled": settings_repo.get("sms_enabled", "false"),
        }
    )


@bp.route("/settings", methods=["POST"])
@login_required
def save_settings():
    settings_repo.set("default_notif_email", request.form.get("default_notif_email", ""))
    settings_repo.set("default_telegram_chat_id", request.form.get("default_telegram_chat_id", ""))
    settings_repo.set("email_enabled", "true" if request.form.get("email_enabled") in ("true", "on") else "false")
    settings_repo.set("telegram_enabled", "true" if request.form.get("telegram_enabled") in ("true", "on") else "false")
    settings_repo.set("sms_enabled", "true" if request.form.get("sms_enabled") in ("true", "on") else "false")
    return jsonify({"status": "ok"})
