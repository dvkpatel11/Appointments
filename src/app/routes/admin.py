from __future__ import annotations

from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from src.config import settings
from src.infrastructure import logging as infra_logging
from src.infrastructure.repositories import client_repo, state_repo
from src.services.automation_service import AutomationService
from src.services.client_service import ClientService

bp = Blueprint("admin", __name__, url_prefix="/admin")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated


# ─────────────────────────────────────────────────────────────────────
# Pages
# ─────────────────────────────────────────────────────────────────────
@bp.route("/")
@login_required
def index():
    return render_template("admin/dashboard.html")


@bp.route("/clients")
@login_required
def clients():
    return render_template("admin/clients.html"), 200


@bp.route("/requests")
@login_required
def requests():
    pending: list[dict] = []
    approved: list[dict] = []
    rejected: list[dict] = []
    for token, client in ClientService.get_pending().items():
        pending.append({"client": client, "token": token})
    for client in ClientService.get_approved().values():
        if client.state.value == "approved":
            approved.append({"client": client, "token": client.token})
    for client in ClientService.get_all().values():
        if client.state.value == "rejected":
            rejected.append({"client": client, "token": client.token})
    pending.sort(key=lambda x: x["client"].updated_at or datetime.min, reverse=True)
    approved.sort(key=lambda x: x["client"].updated_at or datetime.min, reverse=True)
    rejected.sort(key=lambda x: x["client"].updated_at or datetime.min, reverse=True)
    return render_template(
        "admin/requests.html",
        pending=pending,
        approved=approved,
        rejected=rejected,
    ), 200


@bp.route("/requests/reject-modal/<token>")
@login_required
def reject_modal(token: str):
    return render_template("partials/_reject_modal.html", token=token), 200


@bp.route("/settings")
@login_required
def settings_get():
    return render_template("admin/settings.html"), 200


@bp.route("/logs")
@login_required
def logs():
    return render_template("admin/logs.html"), 200


@bp.route("/logs/stream")
@login_required
def logs_stream():
    """Tail log lines as an HTML fragment for the log viewer.

    Query params:
      source: "server" or a client id. Default: "server".
      lines:  tail length, clamped to [10, 1000]. Default: 200.
    """
    source = request.args.get("source", "server").strip()
    try:
        lines = int(request.args.get("lines", 200))
    except ValueError:
        lines = 200
    lines = max(10, min(lines, 1000))

    if source == "server" or not source:
        log_text = infra_logging.read_server_log(lines)
    else:
        log_text = AutomationService.read_logs(source, lines)

    log_lines = log_text.splitlines() if log_text else []
    return render_template("partials/_log_lines.html", lines=log_lines), 200


@bp.route("/clients/<client_id>")
@login_required
def client_detail(client_id: str):
    client = ClientService.get_by_id(client_id)
    if not client:
        return ("<div class='empty'><div class='empty__title'>Client not found</div></div>", 404)
    state = state_repo.load(client_id) or {}
    return render_template("partials/_client_detail.html", client=client, state=state), 200


# ─────────────────────────────────────────────────────────────────────
# Clients table htmx endpoint
# ─────────────────────────────────────────────────────────────────────
@bp.route("/clients/table")
@login_required
def clients_table():
    clients = list(ClientService.get_all().values())
    clients.sort(key=lambda c: c.updated_at or datetime.min, reverse=True)

    rows: list[dict] = []
    for client in clients:
        state = state_repo.load(client.id) or {}
        rows.append({"client": client, "state": state})
    return render_template("partials/_clients_tbody.html", clients=rows), 200


@bp.route("/clients/refresh")
@login_required
def refresh_clients():
    return redirect(url_for("admin.clients_table"))


@bp.route("/clients/<client_id>/restart", methods=["POST"])
@login_required
def restart_client(client_id: str):
    client = ClientService.get_by_id(client_id)
    if not client:
        return jsonify({"status": "error", "message": "Client not found"}), 404
    try:
        result = AutomationService.start(client.token)
        return jsonify({"status": "started" if result["started"] else "error"})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"status": "error", "message": str(exc)}), 400


@bp.route("/test_notification/<channel>", methods=["POST"])
@login_required
def test_notification(channel: str):
    return jsonify({"status": "ok", "channel": channel})


@bp.route("/telegram_webhook_setup")
@login_required
def telegram_webhook_setup():
    return redirect(url_for("telegram.set_webhook"))


# ─────────────────────────────────────────────────────────────────────
# Dashboard htmx partials
# ─────────────────────────────────────────────────────────────────────
@bp.route("/dashboard/metrics")
@login_required
def dashboard_metrics():
    clients = client_repo.get_all()
    total = len(clients)
    pending = sum(1 for c in clients.values() if c.state.value == "pending")
    running = 0
    errors_24h = 0
    threshold = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    for cid in [c.id for c in clients.values() if c.state.value == "approved"]:
        st = state_repo.load(cid) or {}
        if st.get("is_running"):
            running += 1
        if st.get("error_count", 0) and str(st.get("updated_at", "")) > threshold:
            errors_24h += 1
    return render_template(
        "partials/_metrics_grid.html",
        metrics={
            "total": total,
            "running": running,
            "pending": pending,
            "errors_24h": errors_24h,
        },
    )


@bp.route("/dashboard/refresh")
@login_required
def refresh_dashboard():
    return redirect(url_for("admin.dashboard_metrics"))


@bp.route("/dashboard/monitors")
@login_required
def dashboard_monitors():
    clients = client_repo.get_all()
    approved = [c for c in clients.values() if c.state.value == "approved"]
    cards = []
    for client in approved[:24]:  # cap at 24 for the dashboard
        st = state_repo.load(client.id) or {}
        is_running = bool(st.get("is_running"))
        action = (st.get("current_action") or "").upper()
        tone, label = _monitor_status_tone(action, is_running)
        cards.append(
            {
                "client": client,
                "state": {
                    "is_running": is_running,
                    "current_appointment": st.get("current_appointment"),
                    "last_checked_location": st.get("last_checked_location"),
                },
                "status_tone": tone,
                "status_label": label,
            }
        )
    if not cards:
        return render_template("partials/_monitors_empty.html"), 200
    return render_template("partials/_monitors_grid.html", cards=cards), 200


@bp.route("/dashboard/activity")
@login_required
def dashboard_activity():
    """Render a recent-activity feed from the most recent action-log lines.

    Concatenates the last N lines across all running scrapers and tags each
    by the matching client. Cheap, doesn't require a separate events table.
    """
    log_dir = Path(settings.log_dir)
    now = datetime.utcnow()
    items: list[dict] = []
    if log_dir.is_dir():
        for log_file in sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True):
            if log_file.stem == "server":
                continue
            try:
                size = log_file.stat().st_size
                if size == 0:
                    continue
                with log_file.open("r", errors="replace") as f:
                    f.seek(max(0, size - 8192))
                    lines = f.read().splitlines()[-6:]
            except OSError:
                continue
            for line in lines:
                tone, title, sub = _classify_log_line(line)
                items.append(
                    {
                        "id": f"{log_file.stem}:{len(items)}",
                        "tone": tone,
                        "title": title,
                        "sub": f"{log_file.stem[:8]}… · {sub}" if sub else log_file.stem[:8] + "…",
                        "iso": now.isoformat(),
                        "relative": "just now",
                    }
                )
    items = items[:20]
    if not items:
        return render_template("partials/_activity_empty.html"), 200
    return render_template("partials/_activity_list.html", items=items), 200


# ─────────────────────────────────────────────────────────────────────
# Admin actions (existing, lightly retargeted)
# ─────────────────────────────────────────────────────────────────────
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
    if request.headers.get("HX-Request"):
        return (
            '<p class="field__hint" style="margin-bottom:var(--s-2)">'
            "Share this link with the client to collect their credentials.</p>"
            '<div class="field"><label class="field__label" for="gl-link">Link</label>'
            f'<input class="input" id="gl-link" readonly value="{link}" '
            'onfocus="this.select()" />'
            '<button class="btn btn--secondary btn--sm" type="button" '
            'style="margin-top:var(--s-2)" '
            'onclick="navigator.clipboard.writeText(this.previousElementSibling.value); '
            "window.toast('Copied','success','Link copied to clipboard')\">Copy</button></div>",
            200,
        )
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
def logs_view(client_id):
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


# ─────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────
def _monitor_status_tone(action: str, is_running: bool) -> tuple[str, str]:
    if not is_running:
        return "neutral", "Idle"
    if action in ("CHECKING", "RESCHEDULING"):
        return "info", "Checking"
    if action == "LOGIN":
        return "warning", "Logging in"
    return "success", "Running"


def _classify_log_line(line: str) -> tuple[str, str, str]:
    """Heuristic: extract a short title and tone from a log line."""
    line = line.strip()
    if not line:
        return "info", "", ""
    upper = line.upper()
    if "ERROR" in upper or "EXCEPTION" in upper or "FAIL" in upper:
        return "error", _shorten(line), ""
    if "FOUND" in upper or "AVAILABLE" in upper:
        return "success", "Earlier date found", line
    if "LOGIN" in upper:
        return "info", "Login successful" if "SUCCESS" in upper else "Login attempt", line
    if "WAITING" in upper or "SLEEP" in upper:
        return "info", "Waiting", line
    if "START" in upper or "RESUME" in upper:
        return "success", "Started", line
    if "STOP" in upper:
        return "warning", "Stopped", line
    return "info", _shorten(line), ""


def _shorten(s: str, n: int = 64) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 1] + "…"
