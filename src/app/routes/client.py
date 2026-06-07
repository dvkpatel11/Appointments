import base64
import json
import os
import re
import secrets
from datetime import datetime, timedelta
from email.utils import parseaddr

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from src.app.extensions import limiter
from src.infrastructure.database import cursor
from src.infrastructure.repositories import client_repo
from src.notifications import email as email_notif
from src.services.automation_service import AutomationService
from src.services.client_service import ClientService

bp = Blueprint("client", __name__)

EMAIL_CONFIRM_TTL_HOURS = 24


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
@limiter.limit("10 per minute")
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

        # If the wizard's Step 3 included a notification email, fire the
        # magic link. We do not block submit on email transport — the user
        # can re-trigger from the monitor panel's Email tile after approval.
        notification_email = request.form.get("notification_email", "").strip()
        magic_link_msg = None
        if notification_email:
            ok, msg = _send_magic_link_internal(client.id, notification_email)
            magic_link_msg = msg if not ok else "sent"

        response = {"status": "pending_approval"}
        if magic_link_msg is not None:
            response["magic_link"] = magic_link_msg
        return jsonify(response)

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
        # Email verification flag: True only when the client has a notification_email
        # AND at least one email_confirmations row for them is confirmed.
        email_verified = False
        if client.notification_email:
            with cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM email_confirmations "
                    "WHERE user_id = ? AND email = ? AND confirmed_at IS NOT NULL "
                    "LIMIT 1",
                    (client.id, client.notification_email),
                )
                email_verified = cur.fetchone() is not None
        return jsonify(
            {
                "status": "ok",
                **st,
                **notif_info,
                "notification_email_verified": email_verified,
            }
        )
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
        return jsonify({"status": "error", "message": "Missing user_id"}), 400
    client = ClientService.get_by_id(user_id)
    if not client:
        return jsonify({"status": "error", "message": "Invalid token"}), 401

    update = {}
    if data.get("phone_number") is not None:
        update["phone_number"] = data["phone_number"]
    if update:
        client_repo.update_field(user_id, **update)
    return jsonify({"status": "ok"})


@bp.route("/client_request_email_magic_link", methods=["POST"])
@limiter.limit("5 per minute")
def client_request_email_magic_link():
    """Re-trigger a magic link from the monitor panel's Email tile.

    The wizard's submit path uses /send_email_magic_link. This endpoint is
    for the post-approval flow where the user has already submitted and
    wants to add or change their notification email.
    """
    data = request.get_json() or {}
    user_id = data.get("user_id", "").strip()
    email = data.get("email", "").strip()
    if not user_id or not email:
        return jsonify({"status": "error", "message": "Missing user_id or email."}), 400
    client = ClientService.get_by_id(user_id)
    if not client:
        return jsonify({"status": "error", "message": "Invalid token."}), 401

    ok, message = _send_magic_link_internal(user_id, email)
    return jsonify({"status": "ok" if ok else "error", "message": message})


def _is_valid_email(value: str) -> bool:
    if not value or len(value) > 254:
        return False
    parsed = parseaddr(value)
    if not parsed[1] or "@" not in parsed[1]:
        return False
    local, _, domain = parsed[1].partition("@")
    if not local or not domain or "." not in domain:
        return False
    return True


def _send_magic_link_internal(client_id: str, email: str) -> tuple[bool, str]:
    """Generate a token, store the pending confirmation, and email the link.

    Returns (sent, message). `sent=False` means the email transport failed
    (e.g. SMTP not configured); the token row is still created so the user
    can retry by re-submitting. Does NOT write to `clients.notification_email`
    — that only happens after the link is clicked.
    """
    if not _is_valid_email(email):
        return False, "Invalid email address."

    token = secrets.token_urlsafe(32)
    expires_at = (datetime.utcnow() + timedelta(hours=EMAIL_CONFIRM_TTL_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    with cursor() as cur:
        cur.execute(
            "INSERT INTO email_confirmations (token, user_id, email, expires_at) VALUES (?, ?, ?, ?)",
            (token, client_id, email, expires_at),
        )

    confirm_url = url_for("client.confirm_email", token=token, _external=True)
    body = (
        "Click the link below to verify your email for VisaCtrl "
        "appointment monitoring:\n\n"
        f"{confirm_url}\n\n"
        f"This link expires in {EMAIL_CONFIRM_TTL_HOURS} hours. "
        "If you did not request this, you can safely ignore the email."
    )
    sent = email_notif.send("Verify your VisaCtrl email", body, email)
    if sent:
        return True, "Verification email sent."
    return False, "SMTP not configured or send failed. Token stored; try again later."


@bp.route("/send_email_magic_link", methods=["POST"])
@limiter.limit("5 per minute")
def send_email_magic_link():
    data = request.get_json() or {}
    user_id = data.get("user_id", "").strip()
    email = data.get("email", "").strip()
    if not user_id or not email:
        return jsonify({"status": "error", "message": "Missing user_id or email."}), 400
    client = ClientService.get_by_id(user_id)
    if not client:
        return jsonify({"status": "error", "message": "Invalid token."}), 401

    ok, message = _send_magic_link_internal(user_id, email)
    return jsonify({"status": "ok" if ok else "error", "message": message})


@bp.route("/confirm_email/<token>", methods=["GET"])
def confirm_email(token):
    """Magic-link callback. Validates the token, copies the verified email
    onto the client, and redirects to the user's monitor page so they see
    the verified state without a manual login."""
    with cursor() as cur:
        cur.execute(
            "SELECT user_id, email, expires_at, confirmed_at FROM email_confirmations WHERE token = ?",
            (token,),
        )
        row = cur.fetchone()

    if not row:
        return render_template("client/email_confirm_result.html", ok=False, reason="Invalid link."), 400

    if row["confirmed_at"]:
        # Idempotent: link already used. Look up client token for the redirect.
        client = ClientService.get_by_id(row["user_id"])
        if not client:
            return render_template("client/email_confirm_result.html", ok=False, reason="Account not found."), 404
        return redirect(url_for("client.client_view", token=client.token, email_confirmed="1"))

    if row["expires_at"]:
        try:
            expires = datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S")
            if datetime.utcnow() > expires:
                return render_template("client/email_confirm_result.html", ok=False, reason="Link expired."), 400
        except ValueError:
            return render_template("client/email_confirm_result.html", ok=False, reason="Link invalid."), 400

    # All checks passed: mark confirmed and copy email to the client row.
    with cursor() as cur:
        cur.execute(
            "UPDATE email_confirmations SET confirmed_at = CURRENT_TIMESTAMP WHERE token = ?",
            (token,),
        )
    client_repo.update_field(row["user_id"], notification_email=row["email"])

    client = ClientService.get_by_id(row["user_id"])
    if not client:
        return render_template("client/email_confirm_result.html", ok=False, reason="Account not found."), 404
    return redirect(url_for("client.client_view", token=client.token, email_confirmed="1"))
