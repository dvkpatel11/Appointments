import json
import os
import re
import secrets
import uuid
import threading
import multiprocessing
import time

from datetime import datetime
from functools import wraps

from flask import (
    Flask, jsonify, redirect, render_template,
    request, session, url_for, send_from_directory,
    request, session, url_for, send_from_directory,
)
import requests

from canada import config
from canada import db
from canada import notifications
from canada import state
from canada.main import VisaAutomation, run_in_subprocess

config.load_environment()
db.init_db()
db.migrate_from_json()
db.load_settings_into_cache()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[FlaskIntegration()],
        traces_sample_rate=0.1,
    )

# ── Stores ────────────────────────────────────────────────────────────────────

automation_instances = {}
automation_processes = {}


def sanitize_user_id(uid):
    if not uid or not re.match(r"^[a-zA-Z0-9_-]+$", uid):
        return None
    return uid


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


def _ping_self():
    import urllib.request
    port = os.environ.get("PORT", 8080)
    while True:
        time.sleep(300)
        try:
            urllib.request.urlopen(f"http://localhost:{port}/health", timeout=10)
        except Exception:
            pass


threading.Thread(target=_ping_self, daemon=True).start()


@app.route("/")
@login_required
def index():
    return render_template("multi_user.html")


@app.route("/client")
def client_form():
    return render_template("client_form.html", token="")


@app.route("/client/<token>")
def client_view(token):
    if not db.get_client_token(token):
        return render_template("client_form.html", token="", error="Invalid or expired link."), 404
    return render_template("client_form.html", token=token)


# ── Admin API ─────────────────────────────────────────────────────────────────

@app.route("/generate_client_link")
@login_required
def generate_client_link():
    token = uuid.uuid4().hex
    db.save_client_token(token, {
        "state": "issued",
        "user_id": None,
        "request": None,
        "reject_reason": None,
    })
    link = url_for("client_view", token=token, _external=True)
    return jsonify({"link": link})


@app.route("/admin/pending_requests")
@login_required
def pending_requests():
    result = {}
    for token, data in db.get_client_tokens_by_state("pending").items():
        req = data.get("request") or {}
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
    token_data = db.get_client_token(token)
    if not token_data or token_data["state"] != "pending":
        return jsonify({"status": "error", "message": "No pending request for this token"}), 400

    req = token_data.get("request", {})
    user_id = token

    if user_id in automation_instances and automation_instances[user_id].is_running:
        db.save_client_token(token, {"state": "approved", "user_id": user_id})
        return jsonify({"status": "already_running"})

    try:
        instance = VisaAutomation(
            username=req.get("username"),
            password=req.get("password"),
            appointment_id=req.get("appointment_id"),
            appointment_url=req.get("appointment_url"),
            notification_email=req.get("email"),
            browsers=1,
            check=12,
            reschedule=req.get("reschedule", False),
            phone_number=token_data.get("phone_number"),
            send_sms=bool(token_data.get("phone_number")),
        )
        automation_instances[user_id] = instance
        process = multiprocessing.Process(
            target=run_in_subprocess,
            args=(user_id, instance.username, instance.password, instance.appointment_id,
                  instance.appointment_url, instance.notification_email, instance.browsers,
                  instance.check, instance.reschedule, instance.telegram_chat_id, instance.send_telegram,
                  instance.phone_number, instance.send_sms)
        )
        process.start()
        automation_processes[user_id] = process

        update = {"state": "approved", "user_id": user_id}
        notif_email = req.get("notification_email")
        if notif_email:
            update["notification_email"] = notif_email
        db.save_client_token(token, update)
        return jsonify({"status": "approved", "user_id": user_id})

    except Exception as e:
        app.logger.error(f"approve_client error for {token}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/admin/reject_client/<token>", methods=["POST"])
@login_required
def reject_client(token):
    token_data = db.get_client_token(token)
    if not token_data:
        return jsonify({"status": "error", "message": "Token not found"}), 404
    reason = request.form.get("reason", "Your request was not approved at this time.")
    db.save_client_token(token, {"state": "rejected", "reject_reason": reason})
    return jsonify({"status": "rejected"})


# ── Automation lifecycle ──────────────────────────────────────────────────────

@app.route("/start_automation", methods=["POST"])
@login_required
def start_automation():
    user_id = request.form.get("user_id", "default")
    if not sanitize_user_id(user_id):
        return jsonify({"status": "ERROR // invalid user_id"}), 400
    if user_id in automation_instances and automation_instances[user_id].is_running:
        return jsonify({"status": f"ALREADY_RUNNING // {user_id}"})
    try:
        instance = _build_instance_from_form(request.form)
        automation_instances[user_id] = instance
        process = multiprocessing.Process(
            target=run_in_subprocess,
            args=(user_id, instance.username, instance.password, instance.appointment_id,
                  instance.appointment_url, instance.notification_email, instance.browsers,
                  instance.check, instance.reschedule, instance.telegram_chat_id, instance.send_telegram,
                  instance.phone_number, instance.send_sms)
        )
        process.start()
        automation_processes[user_id] = process
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
        if not sanitize_user_id(user_id):
            continue
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
                phone_number=data.get("phone_number"),
                send_sms=bool(data.get("send_sms", False)),
            )
            automation_instances[user_id] = instance
            process = multiprocessing.Process(
                target=run_in_subprocess,
                args=(user_id, instance.username, instance.password, instance.appointment_id,
                      instance.appointment_url, instance.notification_email, instance.browsers,
                      instance.check, instance.reschedule, instance.telegram_chat_id, instance.send_telegram,
                      instance.phone_number, instance.send_sms)
            )
            process.start()
            automation_processes[user_id] = process
            started.append(user_id)
        except Exception as e:
            app.logger.error(f"Failed to start {user_id}: {e}")

    return jsonify({"status": f"ONLINE // {', '.join(started) or 'none started'}"})


@app.route("/stop_automation", methods=["POST"])
@login_required
def stop_automation():
    user_id = request.form.get("user_id", "default")
    if not sanitize_user_id(user_id):
        return jsonify({"status": "ERROR // invalid user_id"}), 400
    if user_id in automation_instances and automation_instances[user_id].is_running:
        automation_instances[user_id].stop()
        proc = automation_processes.get(user_id)
        if proc and proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
        automation_processes.pop(user_id, None)
        state.delete_state(user_id)
        return jsonify({"status": f"TERMINATED // {user_id}"})
    return jsonify({"status": f"NOT_RUNNING // {user_id}"})


@app.route("/stop_all_automation", methods=["POST"])
@login_required
def stop_all_automation():
    for uid, inst in list(automation_instances.items()):
        if inst.is_running:
            inst.stop()
            proc = automation_processes.get(uid)
            if proc and proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)
            automation_processes.pop(uid, None)
            state.delete_state(uid)
    return jsonify({"status": "ALL_TERMINATED"})


@app.route("/get_status")
@login_required
def get_status():
    user_id = request.args.get("user_id", "default")
    if not sanitize_user_id(user_id):
        return jsonify({"status": "ERROR // invalid user_id"}), 400
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
        token_data = db.get_client_token(token)

        if not token or not token_data:
            return jsonify({"status": "error", "message": "Invalid or expired link."}), 400

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

        db.save_client_token(token, {
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
        })
        return jsonify({"status": "pending_approval"})

    except Exception as e:
        app.logger.error(f"client_submit error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/client_status/<token>")
def client_status(token):
    data = db.get_client_token(token)
    if not data:
        return jsonify({"status": "not_found"}), 404
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
    notif_info = {
        "notification_email": data.get("notification_email") or "",
        "telegram_chat_id": data.get("telegram_chat_id") or "",
        "phone_number": data.get("phone_number") or "",
    }
    if not user_id or user_id not in automation_instances:
        return jsonify({"status": "approved", **notif_info})

    s = state.load_state(user_id)
    if s:
        return jsonify({"status": "ok", **s, **notif_info})
    inst = automation_instances.get(user_id)
    if inst:
        return jsonify({"status": "ok", **state.serialize_automation(inst), **notif_info})
    return jsonify({"status": "approved", **notif_info})


@app.route("/client_screenshot/<user_id>")
def client_screenshot(user_id):
    token_data = db.get_client_token(user_id)
    if not token_data or token_data["state"] not in ("approved",):
        return jsonify({"status": "unauthorized"}), 403
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
    path = os.path.normpath(path)
    if path.startswith(".."):
        return jsonify({"status": "error"}), 400
    import base64
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return jsonify({"status": "ready", "image_url": f"data:image/png;base64,{b64}"})


@app.route("/screenshots/<path:filename>")
@login_required
def serve_screenshot(filename):
    safe = os.path.normpath(filename)
    if safe.startswith("..") or safe.startswith("/"):
        return jsonify({"error": "invalid path"}), 400
    return send_from_directory("screenshots", safe)


@app.route("/view_log/<user_id>")
@login_required
def view_log(user_id):
    if not sanitize_user_id(user_id):
        return jsonify({"status": "ERROR // invalid user_id"}), 400
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
    return jsonify({
        "default_notif_email": db.get_setting("default_notif_email", ""),
        "default_telegram_chat_id": db.get_setting("default_telegram_chat_id", ""),
        "email_enabled": db.get_setting("email_enabled", "true") == "true",
        "telegram_enabled": db.get_setting("telegram_enabled", "false") == "true",
        "sms_enabled": db.get_setting("sms_enabled", "false") == "true",
    })


@app.route("/save_settings", methods=["POST"])
@login_required
def save_settings():
    db.set_setting("default_notif_email", request.form.get("default_notif_email", ""))
    db.set_setting("default_telegram_chat_id", request.form.get("default_telegram_chat_id", ""))
    db.set_setting("email_enabled", "true" if request.form.get("email_enabled") in ("true", "on") else "false")
    db.set_setting("telegram_enabled", "true" if request.form.get("telegram_enabled") in ("true", "on") else "false")
    db.set_setting("sms_enabled", "true" if request.form.get("sms_enabled") in ("true", "on") else "false")
    return jsonify({"status": "ok"})


@app.route("/test_email", methods=["POST"])
def test_email():
    data = request.get_json() or {}
    email = data.get("email", "") or request.form.get("email", "")
    if not email:
        email = db.get_setting("default_notif_email", "")
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
        chat_id = db.get_setting("default_telegram_chat_id", "")
    if not chat_id:
        return jsonify({"status": "error", "error": "No chat ID provided"})

    ok = notifications.send_telegram(
        message="Test message from Visa Automation — Notifications are working!",
        chat_id=chat_id,
        emoji="🇨🇦",
    )
    return jsonify({"status": "ok" if ok else "error"})


@app.route("/test_sms", methods=["POST"])
def test_sms():
    data = request.get_json() or {}
    phone = data.get("phone", "") or request.form.get("phone", "")
    if not phone:
        return jsonify({"status": "error", "error": "No phone number provided"})

    ok = notifications.send_sms(
        message="Test message from Visa Automation — SMS notifications are working!",
        to_phone=phone,
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
            link_data = db.get_pending_link(token)
            if token and link_data:
                db.save_pending_link(token, {"chat_id": str(chat_id), "linked_at": time.time()})
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
    db.save_pending_link(token, {"created": time.time(), "chat_id": None})
    return jsonify({"token": token})


@app.route("/check_telegram_linked", methods=["POST"])
def check_telegram_linked():
    data = request.get_json() or {}
    token = data.get("token")
    link_data = db.get_pending_link(token)
    if link_data and link_data.get("chat_id"):
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
    token_data = db.get_client_token(user_id)
    if not token_data:
        return jsonify({"status": "error", "message": "Invalid token"}), 401
    db.save_client_token(user_id, {"telegram_chat_id": chat_id})
    inst = automation_instances.get(user_id)
    if inst:
        inst.telegram_chat_id = chat_id
        inst.send_telegram = True
    return jsonify({"status": "ok"})


@app.route("/client_update_notif", methods=["POST"])
def client_update_notif():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "message": "Missing user_id"})
    user_id = user_id.strip()
    token_data = db.get_client_token(user_id)
    if not token_data:
        return jsonify({"status": "error", "message": "Invalid token"}), 401
    notification_email = data.get("notification_email")
    phone_number = data.get("phone_number")
    update = {}
    if notification_email is not None:
        update["notification_email"] = notification_email
    if phone_number is not None:
        update["phone_number"] = phone_number
    if update:
        db.save_client_token(user_id, update)
    inst = automation_instances.get(user_id)
    if inst:
        if notification_email is not None:
            inst.notification_email = notification_email
        if phone_number is not None:
            inst.phone_number = phone_number
            inst.send_sms = True
    return jsonify({"status": "ok"})


# ── Periodic cleanup (called before every request) ────────────────────────────

def _cleanup_stale():
    db.delete_stale_pending_links(config.PENDING_LINK_TTL_SECONDS)

    stopped = [uid for uid, inst in list(automation_instances.items())
               if not inst.is_running]
    for uid in stopped:
        del automation_instances[uid]
        automation_processes.pop(uid, None)
        state.delete_state(uid)

    dead = [uid for uid, p in list(automation_processes.items())
            if not p.is_alive()]
    for uid in dead:
        automation_processes.pop(uid, None)
        automation_instances.pop(uid, None)
        state.delete_state(uid)


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
        phone_number=form.get("phone_number"),
        send_sms=form.get("send_sms") == "true",
    )


def _load_state(user_id):
    """Load state from JSON file written by subprocess."""
    state_file = f"canada/status/{user_id}.json"
    if os.path.exists(state_file):
        try:
            with open(state_file, "r") as f:
                return json.load(f)
        except:
            pass
    return None


pending_links = {}
import time

def _cleanup_pending_links():
    """Remove stale pending links older than 10 minutes."""
    global pending_links
    now = time.time()
    stale = [k for k, v in pending_links.items() if now - v["created"] > 600]
    for k in stale:
        del pending_links[k]

@app.route("/set_telegram_webhook", methods=["GET"])
def set_telegram_webhook():
    """Helper to configure the Telegram bot webhook - visit this to set it up."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return "TELEGRAM_BOT_TOKEN not set"
    webhook_url = url_for("telegram_webhook", _external=True)
    r = requests.post(f"https://api.telegram.org/bot{bot_token}/setWebhook", json={"url": webhook_url})
    return f"Webhook set: {r.json()}"

@app.route("/telegram_webhook", methods=["POST"])
def telegram_webhook():
    """Handle incoming Telegram updates - register chat_id when user starts bot."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return jsonify({"ok": True})

    try:
        data = request.get_json() or {}
        message = data.get("message", {})
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = message.get("text", "")

        if text.startswith("/start ") or text.startswith("/start"):
            token = text.replace("/start ", "").strip()
            if token and token in pending_links:
                pending_links[token]["chat_id"] = str(chat_id)
                pending_links[token]["linked_at"] = time.time()
                requests.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": "✓ VisaCtrl Notifications linked! You'll receive alerts when earlier visa appointment dates become available."}
                )
    except:
        pass
    return jsonify({"ok": True})

@app.route("/generate_telegram_link", methods=["POST"])
def generate_telegram_link():
    """Generate a unique token for linking Telegram."""
    token = str(uuid.uuid4())
    pending_links[token] = {"created": time.time(), "chat_id": None}
    return jsonify({"token": token})

@app.route("/check_telegram_linked", methods=["POST"])
def check_telegram_linked():
    """Check if a Telegram token has been linked."""
    data = request.get_json() or {}
    token = data.get("token")
    if token in pending_links:
        link_data = pending_links[token]
        if link_data["chat_id"]:
            return jsonify({"linked": True, "chat_id": link_data["chat_id"]})
    return jsonify({"linked": False})

@app.route("/client_link_telegram", methods=["POST"])
def client_link_telegram():
    """Link Telegram chat_id to an existing client."""
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
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=debug, port=port)
