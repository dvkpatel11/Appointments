import json
import os
import re
import uuid
import multiprocessing
import time

from datetime import datetime
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask, jsonify, redirect, render_template,
    request, session, url_for, send_from_directory,
)
import requests

from canada import config
from canada import notifications
from canada import state
from canada.main import VisaAutomation, run_in_subprocess

config.load_environment()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

# ── Stores ────────────────────────────────────────────────────────────────────

automation_instances = {}
settings_store = state.load_settings()
client_tokens = state.load_client_tokens()
pending_links = {}


# ── Auth helpers ──────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ── Auth routes ───────────────────────────────────────────────────────────────

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


# ── Static pages ──────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})


@app.route("/")
@login_required
def index():
    return render_template("multi_user.html")


@app.route("/client")
def client_form():
    return render_template("client_form.html", token="")


@app.route("/client/<token>")
def client_view(token):
    if token not in client_tokens:
        return render_template("client_form.html", token="", error="Invalid or expired link."), 404
    return render_template("client_form.html", token=token)


# ── Admin API ─────────────────────────────────────────────────────────────────

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
    state.save_client_tokens(client_tokens)
    link = url_for("client_view", token=token, _external=True)
    return jsonify({"link": link})


@app.route("/admin/pending_requests")
@login_required
def pending_requests():
    result = {}
    for token, data in client_tokens.items():
        if data["state"] == "pending":
            req = data["request"] or {}
            result[token] = {
                "name": req.get("name", "—"),
                "email": req.get("email", "—"),
                "appointment_id": req.get("appointment_id", "—"),
                "appointment_url_full": req.get("appointment_url_full", "—"),
                "reschedule": req.get("reschedule", False),
            }
    return jsonify(result)


@app.route("/admin/approve_client/<token>", methods=["POST"])
@login_required
def approve_client(token):
    if token not in client_tokens or client_tokens[token]["state"] != "pending":
        return jsonify({"status": "error", "message": "No pending request for this token"}), 400

    req = client_tokens[token]["request"]
    user_id = token

    if user_id in automation_instances and automation_instances[user_id].is_running:
        client_tokens[token]["state"] = "approved"
        client_tokens[token]["user_id"] = user_id
        state.save_client_tokens(client_tokens)
        return jsonify({"status": "already_running"})

    try:
        instance = VisaAutomation(
            username=req["username"],
            password=req["password"],
            appointment_id=req["appointment_id"],
            appointment_url=req["appointment_url"],
            notification_email=req.get("email"),
            browsers=1,
            check=12,
            reschedule=req.get("reschedule", False),
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
        notif_email = client_tokens[token].get("request", {}).get("notification_email")
        if notif_email:
            client_tokens[token]["notification_email"] = notif_email
        tg_chat = client_tokens[token].get("telegram_chat_id")
        if tg_chat:
            client_tokens[token]["send_telegram"] = True
        state.save_client_tokens(client_tokens)
        return jsonify({"status": "approved", "user_id": user_id})

    except Exception as e:
        app.logger.error(f"approve_client error for {token}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/admin/reject_client/<token>", methods=["POST"])
@login_required
def reject_client(token):
    if token not in client_tokens:
        return jsonify({"status": "error", "message": "Token not found"}), 404
    reason = request.form.get("reason", "Your request was not approved at this time.")
    client_tokens[token]["state"] = "rejected"
    client_tokens[token]["reject_reason"] = reason
    state.save_client_tokens(client_tokens)
    return jsonify({"status": "rejected"})


# ── Automation lifecycle ──────────────────────────────────────────────────────

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
        state.delete_state(user_id)
        return jsonify({"status": f"TERMINATED // {user_id}"})
    return jsonify({"status": f"NOT_RUNNING // {user_id}"})


@app.route("/stop_all_automation", methods=["POST"])
@login_required
def stop_all_automation():
    for uid, inst in list(automation_instances.items()):
        if inst.is_running:
            inst.stop()
            state.delete_state(uid)
    return jsonify({"status": "ALL_TERMINATED"})


@app.route("/get_status")
@login_required
def get_status():
    user_id = request.args.get("user_id", "default")
    if user_id not in automation_instances:
        return jsonify({"status": "NO_INSTANCE"})
    inst = automation_instances[user_id]
    return jsonify(state.serialize_automation(inst))


@app.route("/get_all_status")
@login_required
def get_all_status():
    result = {}
    for uid in list(automation_instances.keys()):
        s = state.load_state(uid)
        if s:
            result[uid] = s
        else:
            inst = automation_instances.get(uid)
            if inst:
                result[uid] = state.serialize_automation(inst)
    return jsonify(result)


# ── Client endpoints ──────────────────────────────────────────────────────────

@app.route("/client_submit", methods=["POST"])
def client_submit():
    try:
        token = request.form.get("token", "").strip()

        if not token or token not in client_tokens:
            return jsonify({"status": "error", "message": "Invalid or expired link."}), 400

        token_data = client_tokens[token]

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

        client_tokens[token] = {
            "state": "pending",
            "user_id": None,
            "request": {
                "name": request.form.get("name", "Client"),
                "email": request.form.get("email", "").strip(),
                "username": request.form.get("username", "").strip(),
                "password": request.form.get("password", ""),
                "appointment_id": appointment_id,
                "appointment_url": appointment_url_template,
                "appointment_url_full": appointment_url_full,
                "reschedule": request.form.get("reschedule") == "true",
            },
            "reject_reason": None,
        }
        state.save_client_tokens(client_tokens)
        return jsonify({"status": "pending_approval"})

    except Exception as e:
        app.logger.error(f"client_submit error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/client_status/<token>")
def client_status(token):
    if token not in client_tokens:
        return jsonify({"status": "not_found"}), 404

    data = client_tokens[token]
    state_val = data["state"]

    if state_val == "issued":
        return jsonify({"status": "issued"})
    if state_val == "pending":
        return jsonify({"status": "pending_approval"})
    if state_val == "rejected":
        return jsonify({
            "status": "rejected",
            "reason": data.get("reject_reason", "Request was not approved."),
        })

    user_id = data["user_id"]
    if not user_id or user_id not in automation_instances:
        return jsonify({"status": "approved"})

    s = state.load_state(user_id)
    if s:
        return jsonify({"status": "ok", **s})
    inst = automation_instances.get(user_id)
    if inst:
        return jsonify({"status": "ok", **state.serialize_automation(inst)})
    return jsonify({"status": "approved"})


@app.route("/client_screenshot/<user_id>")
def client_screenshot(user_id):
    path = None
    inst = automation_instances.get(user_id)
    if inst:
        path = inst.appointments_page_screenshot

    if not path or not os.path.exists(path):
        s = state.load_state(user_id)
        if s:
            path = s.get("appointments_page_screenshot")

    if not path or not os.path.exists(path):
        return jsonify({"status": "pending"})
    if path.startswith("./"):
        path = path[2:]
    return jsonify({"status": "ready", "image_url": f"/{path}"})


@app.route("/screenshots/<path:filename>")
def serve_screenshot(filename):
    return send_from_directory("screenshots", filename)


@app.route("/view_log/<user_id>")
@login_required
def view_log(user_id):
    log_path = "app.log"
    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            lines = f.readlines()
        return jsonify({"status": "ready", "log": "".join(lines[-500:])})
    return jsonify({"status": "not_found", "log": ""}), 404


@app.route("/download_log")
@login_required
def download_log():
    log_path = "app.log"
    if not os.path.exists(log_path):
        return "Log file not found", 404
    from flask import send_file
    return send_file(log_path, as_attachment=True, download_name="visa_automation.log")


# ── Settings API ──────────────────────────────────────────────────────────────

@app.route("/get_settings")
@login_required
def get_settings():
    return jsonify(settings_store)


@app.route("/save_settings", methods=["POST"])
@login_required
def save_settings():
    global settings_store
    settings_store["default_notif_email"] = request.form.get("default_notif_email", "")
    settings_store["default_telegram_chat_id"] = request.form.get("default_telegram_chat_id", "")
    settings_store["email_enabled"] = request.form.get("email_enabled") in ("true", "on")
    settings_store["telegram_enabled"] = request.form.get("telegram_enabled") in ("true", "on")
    state.save_settings(settings_store)
    return jsonify({"status": "ok"})


@app.route("/test_email", methods=["POST"])
def test_email():
    data = request.get_json() or {}
    email = data.get("email", "") or request.form.get("email", "")
    if not email:
        email = settings_store.get("default_notif_email", "")
    if not email:
        return jsonify({"status": "error", "error": "No email address provided"})

    ok = notifications.send_email(
        subject="Test Notification — Visa Automation",
        message="This is a test notification from Visa Automation. If you receive this, your email notifications are working!",
        to_email=email,
    )
    return jsonify({"status": "ok" if ok else "error"})


@app.route("/test_telegram", methods=["POST"])
def test_telegram():
    data = request.get_json() or {}
    chat_id = data.get("chat_id", "") or request.form.get("chat_id", "")
    if not chat_id:
        chat_id = settings_store.get("default_telegram_chat_id", "")
    if not chat_id:
        return jsonify({"status": "error", "error": "No chat ID provided"})

    ok = notifications.send_telegram(
        message="Test message from Visa Automation — Notifications are working!",
        chat_id=chat_id,
        emoji="🇨🇦",
    )
    return jsonify({"status": "ok" if ok else "error"})


# ── Telegram webhook ──────────────────────────────────────────────────────────

@app.route("/set_telegram_webhook", methods=["GET"])
def set_telegram_webhook():
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return "TELEGRAM_BOT_TOKEN not set"
    webhook_url = url_for("telegram_webhook", _external=True)
    r = requests.post(
        f"https://api.telegram.org/bot{bot_token}/setWebhook",
        json={"url": webhook_url},
    )
    return f"Webhook set: {r.json()}"


@app.route("/telegram_webhook", methods=["POST"])
def telegram_webhook():
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
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
            if token and token in pending_links:
                pending_links[token]["chat_id"] = str(chat_id)
                pending_links[token]["linked_at"] = time.time()
                requests.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": "✓ VisaCtrl Notifications linked! You'll receive alerts when earlier visa appointment dates become available.",
                    },
                )
            else:
                requests.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": f"✓ Your Chat ID is: {chat_id}\n\nUse this ID in the VisaCtrl notification settings.",
                    },
                )
        elif text in ("/myid", "/getid"):
            requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": f"Your Chat ID is: {chat_id}"},
            )
    except Exception:
        pass
    return jsonify({"ok": True})


@app.route("/generate_telegram_link", methods=["POST"])
def generate_telegram_link():
    token = str(uuid.uuid4())
    pending_links[token] = {"created": time.time(), "chat_id": None}
    return jsonify({"token": token})


@app.route("/check_telegram_linked", methods=["POST"])
def check_telegram_linked():
    data = request.get_json() or {}
    token = data.get("token")
    if token in pending_links:
        link_data = pending_links[token]
        if link_data.get("chat_id"):
            return jsonify({"linked": True, "chat_id": link_data["chat_id"]})
    return jsonify({"linked": False})


@app.route("/client_link_telegram", methods=["POST"])
def client_link_telegram():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    chat_id = data.get("chat_id")
    if not user_id or not chat_id:
        return jsonify({"status": "error", "message": "Missing user_id or chat_id"})
    user_id = user_id.strip()
    if user_id in client_tokens:
        client_tokens[user_id]["telegram_chat_id"] = chat_id
    inst = automation_instances.get(user_id)
    if inst:
        inst.telegram_chat_id = chat_id
        inst.send_telegram = True
    state.save_client_tokens(client_tokens)
    return jsonify({"status": "ok"})


@app.route("/client_update_notif", methods=["POST"])
def client_update_notif():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    notification_email = data.get("notification_email", "")
    if not user_id:
        return jsonify({"status": "error", "message": "Missing user_id"})
    user_id = user_id.strip()
    if user_id in client_tokens:
        client_tokens[user_id]["notification_email"] = notification_email
    inst = automation_instances.get(user_id)
    if inst:
        inst.notification_email = notification_email
    state.save_client_tokens(client_tokens)
    return jsonify({"status": "ok"})


# ── Periodic cleanup (called before every request) ────────────────────────────

def _cleanup_stale():
    now = time.time()
    stale = [k for k, v in list(pending_links.items())
             if now - v.get("created", 0) > config.PENDING_LINK_TTL_SECONDS]
    for k in stale:
        del pending_links[k]

    stopped = [uid for uid, inst in list(automation_instances.items())
               if not inst.is_running]
    for uid in stopped:
        del automation_instances[uid]


@app.before_request
def _maintenance():
    _cleanup_stale()


# ── Helpers ───────────────────────────────────────────────────────────────────

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


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=debug, port=port)
