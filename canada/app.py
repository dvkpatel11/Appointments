import json
import os
import re
import threading
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask, jsonify, redirect, render_template,
    request, session, url_for,
)
from main import VisaAutomation

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

# In-memory store: user_id -> VisaAutomation instance
automation_instances = {}


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

@app.route("/")
@login_required
def index():
    return render_template("multi_user.html")


@app.route("/client")
def client_form():
    """Public page — no auth required. Clients fill this in."""
    return render_template("client_form.html")


# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------

@app.route("/generate_client_link")
@login_required
def generate_client_link():
    link = url_for("client_form", _external=True)
    return jsonify({"link": link})


@app.route("/start_automation", methods=["POST"])
@login_required
def start_automation():
    user_id = request.form.get("user_id", "default")
    if user_id in automation_instances and automation_instances[user_id].is_running:
        return jsonify({"status": f"ALREADY_RUNNING // {user_id}"})
    try:
        instance = _build_instance_from_form(request.form)
        automation_instances[user_id] = instance
        threading.Thread(target=instance.run, daemon=True).start()
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
            )
            automation_instances[user_id] = instance
            threading.Thread(target=instance.run, daemon=True).start()
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
# Public client submission
# ---------------------------------------------------------------------------

@app.route("/client_submit", methods=["POST"])
def client_submit():
    """Public endpoint — clients submit their details to start monitoring."""
    try:
        appointment_url_full = request.form.get("appointment_url", "").strip()

        # Extract numeric schedule ID from URL
        match = re.search(r"/schedule/(\w+)/", appointment_url_full)
        if not match:
            return jsonify({
                "status": "error",
                "message": "Invalid appointment URL. Expected format: .../schedule/12345678/appointment",
            }), 400

        appointment_id = match.group(1)
        # Build template URL with placeholder
        appointment_url_template = re.sub(
            r"/schedule/\w+/appointment",
            "/schedule/{}/appointment",
            appointment_url_full,
        )

        user_id = f"client_{appointment_id}"

        if user_id in automation_instances and automation_instances[user_id].is_running:
            return jsonify({
                "status": "already_running",
                "message": "Monitoring is already active for this appointment.",
            })

        name = request.form.get("name", "Client")
        email = request.form.get("email", "").strip()

        instance = VisaAutomation(
            username=request.form.get("username", "").strip(),
            password=request.form.get("password", ""),
            appointment_id=appointment_id,
            appointment_url=appointment_url_template,
            notification_email=email,
            browsers=1,
            check=12,
            reschedule=request.form.get("reschedule") == "true",
        )
        automation_instances[user_id] = instance
        threading.Thread(target=instance.run, daemon=True).start()

        return jsonify({
            "status": "success",
            "user_id": user_id,
            "name": name,
            "email": email,
        })

    except Exception as e:
        app.logger.error(f"client_submit error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


# ---------------------------------------------------------------------------
# Public screenshot endpoint — polled by the client form after submission
# ---------------------------------------------------------------------------

@app.route("/client_screenshot/<user_id>")
def client_screenshot(user_id):
    """
    Returns the appointment-page screenshot for a given user_id as base64 JSON.
    The client form polls this after submit to display confirmation to the client.
    No auth required — user_id is an unguessable string (client_{schedule_id}).
    """
    import base64
    inst = automation_instances.get(user_id)
    if inst is None:
        return jsonify({"status": "not_found"}), 404
    path = inst.appointments_page_screenshot
    if not path or not os.path.exists(path):
        return jsonify({"status": "pending"})
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return jsonify({"status": "ready", "image": data})


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
    )


def _serialize(inst):
    return {
        "is_running": inst.is_running,
        "current_action": inst.current_action,
        "action_log": inst.action_log,           # list of {ts, msg}
        "current_appointment": str(inst.current_date) if inst.current_date else None,
        "new_appointment": str(inst.new_date) if inst.new_date else None,
        "last_checked_location": inst.last_checked_location,
    }


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=debug, port=port)
