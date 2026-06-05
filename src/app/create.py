from __future__ import annotations

import atexit
import json
import logging
import signal
import threading

from flask import Flask, jsonify, redirect, request, session

try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None  # type: ignore[assignment]

from src.app.routes import admin, auth, client, events, snapshot, telegram
from src.config import settings
from src.infrastructure import logging as server_logging
from src.infrastructure.database import init_db
from src.infrastructure.repositories import client_repo, settings_repo
from src.orchestrator import manager as orchestrator
from src.services.automation_service import AutomationService
from src.services.client_service import ClientService


def _generate_secret_key() -> str:
    import secrets

    return secrets.token_hex(32)


def _stop_all_on_exit() -> None:
    orchestrator.stop_all()


def _handle_signal(signum: int, frame) -> None:
    orchestrator.stop_all()


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = settings.secret_key or _generate_secret_key()

    if sentry_sdk and settings.sentry_dsn:
        try:
            sentry_sdk.init(dsn=settings.sentry_dsn)
        except Exception as exc:
            app.logger.warning("Sentry init failed: %s", exc)

    server_logging.setup_server_logger()

    init_db()
    settings_repo.load_cache()

    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(client.bp)
    app.register_blueprint(telegram.bp)
    app.register_blueprint(events.bp)
    app.register_blueprint(snapshot.bp)

    @app.context_processor
    def _inject_ui_config():
        from flask import session

        return {
            "current_user_is_admin": bool(session.get("authenticated")),
            "app_config": {
                "streamUrl": "/events/stream",
                "snapshotUrl": "/snapshot/",
                "logsStreamUrl": "/admin/logs/stream",
            },
        }

    @app.route("/")
    def index():
        from flask import redirect

        return redirect("/login")

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    def _login_required():
        if not session.get("authenticated"):
            return redirect("/login")

    @app.route("/get_all_status")
    def legacy_all_status():
        resp = _login_required()
        if resp:
            return resp
        return admin.all_status()

    @app.route("/stop_automation", methods=["POST"])
    def legacy_stop():
        resp = _login_required()
        if resp:
            return resp
        user_id = request.form.get("user_id", "")
        try:
            AutomationService.stop(user_id)
            return jsonify({"status": "stopped"})
        except Exception:
            return jsonify({"status": "error", "message": "Client not found"}), 404

    @app.route("/stop_all_automation", methods=["POST"])
    def legacy_stop_all():
        resp = _login_required()
        if resp:
            return resp
        orchestrator.stop_all()
        return jsonify({"status": "all_stopped"})

    @app.route("/view_log/<client_id>")
    def legacy_view_log(client_id):
        resp = _login_required()
        if resp:
            return resp
        return admin.logs(client_id)

    @app.route("/get_settings")
    def legacy_get_settings():
        resp = _login_required()
        if resp:
            return resp
        return admin.settings_get()

    @app.route("/save_settings", methods=["POST"])
    def legacy_save_settings():
        resp = _login_required()
        if resp:
            return resp
        return admin.save_settings()

    @app.route("/generate_client_link")
    def legacy_generate_client_link():
        resp = _login_required()
        if resp:
            return resp
        return admin.generate_client_link()

    # ── Missing legacy routes ─────────────────────────────────────────────

    @app.route("/download_log")
    def legacy_download_log():
        resp = _login_required()
        if resp:
            return resp
        client_id = request.args.get("client_id", "server")
        log_text = AutomationService.read_logs(client_id, 5000)
        from flask import Response

        return Response(
            log_text,
            mimetype="text/plain",
            headers={"Content-Disposition": f"attachment; filename={client_id}.log"},
        )

    @app.route("/test_email", methods=["POST"])
    def legacy_test_email():
        from src.notifications.email import send as send_email

        recipient = request.form.get("email") or (request.get_json(silent=True) or {}).get("email", "")
        if not recipient:
            return jsonify({"status": "error", "error": "No email address provided"}), 400
        ok = send_email("VisaCtrl Test", "This is a test email from VisaCtrl.", recipient)
        return jsonify({"status": "ok" if ok else "error", "error": None if ok else "Email sending failed"})

    @app.route("/test_telegram", methods=["POST"])
    def legacy_test_telegram():
        from src.notifications.telegram import send as send_telegram

        chat_id = request.form.get("chat_id") or (request.get_json(silent=True) or {}).get("chat_id", "")
        if not chat_id:
            return jsonify({"status": "error", "error": "No chat_id provided"}), 400
        ok = send_telegram("This is a test message from VisaCtrl.", chat_id)
        return jsonify({"status": "ok" if ok else "error", "error": None if ok else "Telegram sending failed"})

    @app.route("/test_sms", methods=["POST"])
    def legacy_test_sms():
        from src.notifications.sms import send as send_sms

        phone = request.form.get("phone") or (request.get_json(silent=True) or {}).get("phone", "")
        if not phone:
            return jsonify({"status": "error", "error": "No phone number provided"}), 400
        ok = send_sms("This is a test SMS from VisaCtrl.", phone)
        return jsonify({"status": "ok" if ok else "error", "error": None if ok else "SMS sending failed"})

    @app.route("/start_multi_automation", methods=["POST"])
    def legacy_start_multi():
        resp = _login_required()
        if resp:
            return resp
        raw = request.form.get("users_data", "{}")
        try:
            users_data = json.loads(raw)
        except json.JSONDecodeError:
            return jsonify({"status": "error", "message": "Invalid JSON"}), 400
        if not isinstance(users_data, dict):
            return jsonify({"status": "error", "message": "Expected object"}), 400
        results = {}
        for uid, data in users_data.items():
            username = (data.get("username") or "").strip()
            password = data.get("password") or ""
            if not username or not password:
                results[uid] = {"status": "skipped", "reason": "missing credentials"}
                continue
            appointment_id = (data.get("appointment_id") or "").strip()
            appointment_url = (
                data.get("appointment_url") or ""
            ).strip() or "https://ais.usvisa-info.com/en-ca/niv/schedule/{}/appointment"
            token = client_repo.create_token()
            ClientService.submit_request(
                token,
                {
                    "name": uid,
                    "username": username,
                    "password": password,
                    "appointment_id": appointment_id,
                    "appointment_url": appointment_url,
                    "reschedule": data.get("reschedule", False),
                },
            )
            ClientService.approve(token)
            result = AutomationService.start(token)
            started = result.get("started")
            results[uid] = {"status": "started" if started else "error", "client_id": result.get("client_id")}
        return jsonify({"status": "ok", "results": results})

    # ── Crash recovery background thread ──────────────────────────────────

    def _recovery_loop() -> None:
        while True:
            threading.Event().wait(60)
            try:
                orchestrator.check_and_recover()
            except Exception as e:
                logging.getLogger("usvisa").warning("Recovery loop error: %s", e)

    _recovery_thread = threading.Thread(target=_recovery_loop, daemon=True)
    _recovery_thread.start()

    events.start_poller_once()

    # ── Shutdown hooks ────────────────────────────────────────────────────

    atexit.register(_stop_all_on_exit)
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    orchestrator.resume_approved_agents()

    return app
