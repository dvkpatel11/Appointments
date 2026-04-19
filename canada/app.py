import base64
import json
import os
import re
import threading
import uuid
import multiprocessing
from datetime import datetime
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask, jsonify, redirect, render_template,
    request, session, url_for,
)
from main import VisaAutomation, run_in_subprocess

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

# In-memory store: user_id -> VisaAutomation instance
automation_instances = {}

# Client token store.
# token -> {
#   "state":         "issued" | "pending" | "approved" | "rejected",
#   "user_id":       str | None,          # set after approval
#   "request":       dict | None,         # client-submitted data
#   "reject_reason": str | None,
# }
client_tokens = {}


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        submitted = request.form.get("password", "")
        if ADMIN_PASSWORD and submitted == ADMIN_PASSWORD:
            session["authenticated"] = True
            return redirect(url_for("index"))
        error = "ACCESS_DENIED // INVALID_CREDENTIALS"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Main pages
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    """Public health check for uptime monitors."""
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})


@app.route("/")
@login_required
def index():
    return render_template("multi_user.html")


@app.route("/client")
def client_form():
    """Legacy public page — generic client form (no token)."""
    return render_template("client_form.html", token="")


@app.route("/client/<token>")
def client_view(token):
    """Unique per-client link."""
    if token not in client_tokens:
        return render_template("client_form.html", token="", error="Invalid or expired link."), 404
    return render_template("client_form.html", token=token)


# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------

@app.route("/generate_client_link")
@login_required
def generate_client_link():
    token = uuid.uuid4().hex
    client_tokens[token] = {
        "state": "issued",
        "user_id": None,
        "request": None,
        "reject_reason": None,
    }
    link = url_for("client_view", token=token, _external=True)
    return jsonify({"link": link})


@app.route("/admin/pending_requests")
@login_required
def pending_requests():
    """Returns all client requests waiting for admin approval."""
    result = {}
    for token, data in client_tokens.items():
        if data["state"] == "pending":
            req = data["request"] or {}
            result[token] = {
                "name":           req.get("name", "—"),
                "email":          req.get("email", "—"),
                "appointment_id": req.get("appointment_id", "—"),
                "appointment_url_full": req.get("appointment_url_full", "—"),
                "reschedule":     req.get("reschedule", False),
            }
    return jsonify(result)


@app.route("/admin/approve_client/<token>", methods=["POST"])
@login_required
def approve_client(token):
    """Start monitoring for an approved client request."""
    if token not in client_tokens or client_tokens[token]["state"] != "pending":
        return jsonify({"status": "error", "message": "No pending request for this token"}), 400

    req = client_tokens[token]["request"]
    user_id = token   # token is the stable user_id so /client/<token> stays valid

    if user_id in automation_instances and automation_instances[user_id].is_running:
        client_tokens[token]["state"] = "approved"
        client_tokens[token]["user_id"] = user_id
        return jsonify({"status": "already_running"})

    try:
        instance = VisaAutomation(
            username=req["username"],
            password=req["password"],
            appointment_id=req["appointment_id"],
            appointment_url=req["appointment_url"],
            notification_email=req["email"],
            browsers=1,
            check=12,
            reschedule=req["reschedule"],
        )
        automation_instances[user_id] = instance
        process = multiprocessing.Process(
            target=run_in_subprocess,
            args=(user_id, instance.username, instance.password, instance.appointment_id,
                  instance.appointment_url, instance.notification_email, instance.browsers,
                  instance.check, instance.reschedule, instance.telegram_chat_id, instance.send_telegram)
        )
        process.start()

        client_tokens[token]["state"] = "approved"
        client_tokens[token]["user_id"] = user_id
        return jsonify({"status": "approved", "user_id": user_id})

    except Exception as e:
        app.logger.error(f"approve_client error for {token}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/admin/reject_client/<token>", methods=["POST"])
@login_required
def reject_client(token):
    """Reject a pending client request."""
    if token not in client_tokens:
        return jsonify({"status": "error", "message": "Token not found"}), 404
    reason = request.form.get("reason", "Your request was not approved at this time.")
    client_tokens[token]["state"] = "rejected"
    client_tokens[token]["reject_reason"] = reason
    return jsonify({"status": "rejected"})


@app.route("/start_automation", methods=["POST"])
@login_required
def start_automation():
    user_id = request.form.get("user_id", "default")
    if user_id in automation_instances and automation_instances[user_id].is_running:
        return jsonify({"status": f"ALREADY_RUNNING // {user_id}"})
    try:
        instance = _build_instance_from_form(request.form)
        automation_instances[user_id] = instance
        process = multiprocessing.Process(
            target=run_in_subprocess,
            args=(user_id, instance.username, instance.password, instance.appointment_id,
                  instance.appointment_url, instance.notification_email, instance.browsers,
                  instance.check, instance.reschedule, instance.telegram_chat_id, instance.send_telegram)
        )
        process.start()
        return jsonify({"status": f"ONLINE // {user_id}"})
    except (ValueError, TypeError) as e:
        return jsonify({"status": f"ERROR // {e}"}), 400


@app.route("/start_multi_automation", methods=["POST"])
@login_required
def start_multi_automation():
    try:
        users_data = json.loads(request.form.get("users_data", "{}"))
    except json.JSONDecodeError:
        return jsonify({"status": "ERROR // Invalid JSON in users_data"}), 400

    started = []
    for user_id, data in users_data.items():
        if user_id in automation_instances and automation_instances[user_id].is_running:
            continue
        try:
            instance = VisaAutomation(
                username=data.get("username"),
                password=data.get("password"),
                appointment_id=data.get("appointment_id"),
                appointment_url=data.get("appointment_url"),
                notification_email=data.get("notification_email"),
                browsers=int(data.get("browsers", 1)),
                check=int(data.get("check", 12)),
                reschedule=bool(data.get("reschedule", False)),
                telegram_chat_id=data.get("telegram_chat_id"),
                send_telegram=bool(data.get("send_telegram", False)),
            )
            automation_instances[user_id] = instance
            process = multiprocessing.Process(
                target=run_in_subprocess,
                args=(user_id, instance.username, instance.password, instance.appointment_id,
                      instance.appointment_url, instance.notification_email, instance.browsers,
                      instance.check, instance.reschedule, instance.telegram_chat_id, instance.send_telegram)
            )
            process.start()
            started.append(user_id)
        except Exception as e:
            app.logger.error(f"Failed to start {user_id}: {e}")

    return jsonify({"status": f"ONLINE // {', '.join(started) or 'none started'}"})


@app.route("/stop_automation", methods=["POST"])
@login_required
def stop_automation():
    user_id = request.form.get("user_id", "default")
    if user_id in automation_instances and automation_instances[user_id].is_running:
        automation_instances[user_id].stop()
        return jsonify({"status": f"TERMINATED // {user_id}"})
    return jsonify({"status": f"NOT_RUNNING // {user_id}"})


@app.route("/stop_all_automation", methods=["POST"])
@login_required
def stop_all_automation():
    for instance in automation_instances.values():
        if instance.is_running:
            instance.stop()
    return jsonify({"status": "ALL_TERMINATED"})


@app.route("/get_status")
@login_required
def get_status():
    user_id = request.args.get("user_id", "default")
    if user_id not in automation_instances:
        return jsonify({"status": "NO_INSTANCE"})
    return jsonify(_serialize(automation_instances[user_id]))


@app.route("/get_all_status")
@login_required
def get_all_status():
    return jsonify({uid: _serialize(inst) for uid, inst in automation_instances.items()})


# ---------------------------------------------------------------------------
# Public client endpoints
# ---------------------------------------------------------------------------

@app.route("/client_submit", methods=["POST"])
def client_submit():
    """
    Queue a client request for admin approval instead of starting immediately.
    """
    try:
        token = request.form.get("token", "").strip()

        # Validate token
        if not token or token not in client_tokens:
            return jsonify({"status": "error", "message": "Invalid or expired link."}), 400

        token_data = client_tokens[token]

        # Idempotency: already approved or pending
        if token_data["state"] == "approved":
            return jsonify({"status": "pending_approval",
                            "message": "Your request is already approved and running."})
        if token_data["state"] == "pending":
            return jsonify({"status": "pending_approval",
                            "message": "Your request is already submitted and awaiting approval."})
        if token_data["state"] == "rejected":
            return jsonify({"status": "rejected",
                            "reason": token_data.get("reject_reason", "Request was not approved.")})

        appointment_url_full = request.form.get("appointment_url", "").strip()
        match = re.search(r"/schedule/(\w+)/", appointment_url_full)
        if not match:
            return jsonify({
                "status": "error",
                "message": "Invalid appointment URL. Expected: .../schedule/12345678/appointment",
            }), 400

        appointment_id = match.group(1)
        appointment_url_template = re.sub(
            r"/schedule/\w+/appointment",
            "/schedule/{}/appointment",
            appointment_url_full,
        )

        # Store request data — automation will be started only after admin approves
        client_tokens[token] = {
            "state": "pending",
            "user_id": None,
            "request": {
                "name":                 request.form.get("name", "Client"),
                "email":                request.form.get("email", "").strip(),
                "username":             request.form.get("username", "").strip(),
                "password":             request.form.get("password", ""),
                "appointment_id":       appointment_id,
                "appointment_url":      appointment_url_template,
                "appointment_url_full": appointment_url_full,
                "reschedule":           request.form.get("reschedule") == "true",
            },
            "reject_reason": None,
        }

        return jsonify({"status": "pending_approval"})

    except Exception as e:
        app.logger.error(f"client_submit error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/client_status/<token>")
def client_status(token):
    """
    Live status for a client's token. States:
      issued           — link not yet submitted
      pending_approval — submitted, waiting for admin
      approved         — admin approved, automation starting/running
      rejected         — admin rejected
      ok + data        — approved and automation is active
    """
    if token not in client_tokens:
        return jsonify({"status": "not_found"}), 404

    data = client_tokens[token]
    state = data["state"]

    if state == "issued":
        return jsonify({"status": "issued"})

    if state == "pending":
        return jsonify({"status": "pending_approval"})

    if state == "rejected":
        return jsonify({
            "status": "rejected",
            "reason": data.get("reject_reason", "Request was not approved."),
        })

    # state == "approved"
    user_id = data["user_id"]
    if not user_id or user_id not in automation_instances:
        return jsonify({"status": "approved"})   # approved but automation not started yet

    return jsonify({"status": "ok", **_serialize(automation_instances[user_id])})


@app.route("/client_screenshot/<user_id>")
def client_screenshot(user_id):
    """Screenshot of the appointment page, served as base64."""
    inst = automation_instances.get(user_id)
    if inst is None:
        return jsonify({"status": "not_found"}), 404
    path = inst.appointments_page_screenshot
    if not path or not os.path.exists(path):
        return jsonify({"status": "pending"})
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return jsonify({"status": "ready", "image": data})


@app.route("/view_log/<user_id>")
@login_required
def view_log(user_id):
    """View log file for a specific user."""
    log_path = f"canada/app.log"
    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            lines = f.readlines()
        return jsonify({"status": "ready", "log": "".join(lines[-500:])})
    return jsonify({"status": "not_found", "log": ""}), 404


@app.route("/download_log")
@login_required
def download_log():
    """Download the log file."""
    log_path = "canada/app.log"
    if not os.path.exists(log_path):
        return "Log file not found", 404
    from flask import send_file
    return send_file(log_path, as_attachment=True, download_name="visa_automation.log")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_instance_from_form(form):
    return VisaAutomation(
        username=form.get("username"),
        password=form.get("password"),
        appointment_id=form.get("appointment_id"),
        appointment_url=form.get("appointment_url"),
        notification_email=form.get("notification_email"),
        browsers=int(form.get("browsers", 1)),
        check=int(form.get("check", 12)),
        reschedule=form.get("reschedule") == "true",
        telegram_chat_id=form.get("telegram_chat_id"),
        send_telegram=form.get("send_telegram") == "true",
    )


def _serialize(inst):
    return {
        "is_running":           inst.is_running,
        "current_action":       inst.current_action,
        "action_log":           inst.action_log,
        "current_appointment":  str(inst.current_date) if inst.current_date else None,
        "new_appointment":      str(inst.new_date) if inst.new_date else None,
        "last_checked_location": inst.last_checked_location,
    }


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=debug, port=port)
