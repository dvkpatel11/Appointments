from __future__ import annotations

import atexit
import signal

from flask import Flask, jsonify, redirect, request, session

try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None  # type: ignore[assignment]

from src.app.routes import admin, auth, client, telegram
from src.config import settings
from src.infrastructure import logging as server_logging
from src.infrastructure.database import init_db
from src.infrastructure.repositories import settings_repo
from src.orchestrator import manager as orchestrator


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
        from src.services.automation_service import AutomationService
        AutomationService.stop(user_id)
        return jsonify({"status": "stopped"})

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
        return admin.get_settings()

    @app.route("/save_settings", methods=["POST"])
    def legacy_save_settings():
        resp = _login_required()
        if resp:
            return resp
        return admin.save_settings()

    atexit.register(_stop_all_on_exit)
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    orchestrator.resume_approved_agents()

    return app
