"""Tests for the email magic-link verification flow.

Covers the new routes added in Phase 4B Batches 2+4:
  - POST /send_email_magic_link     (wizard Step 3 + monitor panel Email tile)
  - POST /client_request_email_magic_link   (alias for the monitor panel path)
  - GET  /confirm_email/<token>     (callback when user clicks the email link)

The flow:
  1. User submits notification_email via the wizard.
  2. Server inserts an email_confirmations row (token, user_id, email, expires_at).
  3. Server sends an email with a /confirm_email/<token> link.
  4. User clicks; the row is marked confirmed AND notification_email is copied
     onto the client.
  5. /client_status returns notification_email_verified=True iff such a row exists.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta

import pytest


@pytest.fixture
def app(app_modules):
    from src.app import create

    importlib.reload(create)
    flask_app = create.create_app()
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def issued_client(app_modules):
    """Create an 'issued' (not-yet-submitted) client and return its id + token."""
    from src.infrastructure.repositories import client_repo

    token = client_repo.create_token()
    client = client_repo.get_by_token(token)
    return {"id": client.id, "token": token}


# ── Schema ────────────────────────────────────────────────────────────────────


def test_init_db_creates_email_confirmations_table(app_modules, temp_db_path):
    """After init_db the email_confirmations table exists and has the expected columns."""
    from src.infrastructure import database

    with database.cursor() as cur:
        cur.execute("PRAGMA table_info(email_confirmations)")
        cols = {row["name"] for row in cur.fetchall()}
    assert {"token", "user_id", "email", "created_at", "expires_at", "confirmed_at"} <= cols


def test_init_db_creates_email_confirmations_index(app_modules, temp_db_path):
    from src.infrastructure import database

    with database.cursor() as cur:
        cur.execute("PRAGMA index_list(email_confirmations)")
        indexes = {row["name"] for row in cur.fetchall()}
    assert "idx_email_confirmations_user_id" in indexes


def test_init_db_is_idempotent_for_email_confirmations(app_modules, temp_db_path):
    """Calling init_db twice must not raise (re-runs are safe)."""
    from src.infrastructure import database

    database.init_db()
    database.init_db()  # no exception


# ── /send_email_magic_link endpoint ───────────────────────────────────────────


def test_send_magic_link_inserts_pending_row(client, issued_client, monkeypatch):
    """Hitting the endpoint creates a confirmation row in email_confirmations
    with a 24h expiry and no confirmed_at."""
    # Stub the email transport so the test doesn't try to actually send mail.
    from src.app.routes import client as client_routes
    from src.infrastructure import database
    from src.notifications import email as email_notif

    sent: list[dict] = []
    monkeypatch.setattr(email_notif, "send", lambda *a, **kw: sent.append({"a": a, "kw": kw}) or True)
    importlib.reload(client_routes)

    res = client.post(
        "/send_email_magic_link",
        json={"user_id": issued_client["id"], "email": "user@example.com"},
    )
    assert res.status_code == 200
    assert res.get_json()["status"] == "ok"
    assert sent, "stubbed email.send should have been called"

    with database.cursor() as cur:
        cur.execute(
            "SELECT user_id, email, expires_at, confirmed_at FROM email_confirmations WHERE user_id = ?",
            (issued_client["id"],),
        )
        rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0]["user_id"] == issued_client["id"]
    assert rows[0]["email"] == "user@example.com"
    assert rows[0]["confirmed_at"] is None
    expires = datetime.strptime(rows[0]["expires_at"], "%Y-%m-%d %H:%M:%S")
    # Should be ~24h from now. Allow 1 minute slop for test execution time.
    delta = expires - datetime.utcnow()
    assert timedelta(hours=23, minutes=59) < delta < timedelta(hours=24, minutes=1)


def test_send_magic_link_rejects_invalid_email(client, issued_client):
    res = client.post(
        "/send_email_magic_link",
        json={"user_id": issued_client["id"], "email": "not-an-email"},
    )
    # Returns 200 with status=error (the helper's validation surfaces as a
    # status payload, not an HTTP error, so the client can show a friendly
    # message).
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "error"
    assert "Invalid" in data["message"]


def test_send_magic_link_requires_user_id(client):
    res = client.post(
        "/send_email_magic_link",
        json={"email": "user@example.com"},
    )
    assert res.status_code == 400


def test_send_magic_link_rejects_unknown_client(client):
    res = client.post(
        "/send_email_magic_link",
        json={"user_id": "does-not-exist", "email": "user@example.com"},
    )
    assert res.status_code == 401


# ── /confirm_email/<token> endpoint ───────────────────────────────────────────


def test_confirm_email_marks_row_and_copies_to_client(client, issued_client, monkeypatch):
    from src.app.routes import client as client_routes
    from src.infrastructure import database
    from src.infrastructure.repositories import client_repo
    from src.notifications import email as email_notif

    monkeypatch.setattr(email_notif, "send", lambda *a, **kw: True)
    importlib.reload(client_routes)

    # Trigger the magic link first.
    res = client.post(
        "/send_email_magic_link",
        json={"user_id": issued_client["id"], "email": "verify@example.com"},
    )
    assert res.status_code == 200

    with database.cursor() as cur:
        cur.execute(
            "SELECT token FROM email_confirmations WHERE user_id = ?",
            (issued_client["id"],),
        )
        token = cur.fetchone()["token"]

    # Click the link. We expect a 302 redirect to the client view.
    res = client.get(f"/confirm_email/{token}", follow_redirects=False)
    assert res.status_code == 302
    assert "email_confirmed=1" in res.headers["Location"]

    # The client row should now have the verified email.
    refreshed = client_repo.get_by_id(issued_client["id"])
    assert refreshed.notification_email == "verify@example.com"

    # The confirmation row should be marked.
    with database.cursor() as cur:
        cur.execute(
            "SELECT confirmed_at FROM email_confirmations WHERE token = ?",
            (token,),
        )
        confirmed_at = cur.fetchone()["confirmed_at"]
    assert confirmed_at is not None


def test_confirm_email_unknown_token_returns_400(client):
    res = client.get("/confirm_email/this-token-does-not-exist")
    assert res.status_code == 400


def test_confirm_email_expired_token_returns_400(client, app_modules, issued_client):
    """Manually insert a row whose expires_at is in the past."""
    from src.infrastructure import database

    expired = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    with database.cursor() as cur:
        cur.execute(
            "INSERT INTO email_confirmations (token, user_id, email, expires_at) VALUES (?, ?, ?, ?)",
            ("expired-token", issued_client["id"], "old@example.com", expired),
        )

    res = client.get("/confirm_email/expired-token")
    assert res.status_code == 400
    assert "expired" in res.get_data(as_text=True).lower()


def test_confirm_email_idempotent_for_used_link(client, issued_client, monkeypatch):
    """A second click on an already-confirmed link should still redirect
    the user to their monitor page (idempotent), not error."""
    from src.app.routes import client as client_routes
    from src.infrastructure import database
    from src.notifications import email as email_notif

    monkeypatch.setattr(email_notif, "send", lambda *a, **kw: True)
    importlib.reload(client_routes)

    client.post(
        "/send_email_magic_link",
        json={"user_id": issued_client["id"], "email": "x@example.com"},
    )
    with database.cursor() as cur:
        cur.execute(
            "SELECT token FROM email_confirmations WHERE user_id = ?",
            (issued_client["id"],),
        )
        token = cur.fetchone()["token"]

    # First click: 302.
    r1 = client.get(f"/confirm_email/{token}", follow_redirects=False)
    assert r1.status_code == 302
    # Second click: still 302, not 400.
    r2 = client.get(f"/confirm_email/{token}", follow_redirects=False)
    assert r2.status_code == 302


# ── /client_status verified flag ──────────────────────────────────────────────


def test_client_status_reports_verified_flag(client, issued_client, monkeypatch):
    from src.app.routes import client as client_routes
    from src.infrastructure import database
    from src.infrastructure.repositories import client_repo
    from src.notifications import email as email_notif

    monkeypatch.setattr(email_notif, "send", lambda *a, **kw: True)
    importlib.reload(client_routes)

    # Advance the client past 'issued' so /client_status reaches the
    # notification block (issued state short-circuits with no notif fields).
    client_repo.update_field(issued_client["id"], state="approved")

    # Set a notification_email on the client (simulating that the user
    # previously confirmed or admin set it). With no confirmation row,
    # verified must be False.
    client_repo.update_field(issued_client["id"], notification_email="prev@example.com")
    res = client.get(f"/client_status/{issued_client['token']}")
    assert res.status_code == 200
    data = res.get_json()
    assert data["notification_email"] == "prev@example.com"
    assert data["notification_email_verified"] is False

    # Now confirm that email via a magic link.
    client.post(
        "/send_email_magic_link",
        json={"user_id": issued_client["id"], "email": "prev@example.com"},
    )
    with database.cursor() as cur:
        cur.execute(
            "SELECT token FROM email_confirmations WHERE user_id = ?",
            (issued_client["id"],),
        )
        token = cur.fetchone()["token"]
    client.get(f"/confirm_email/{token}")

    res = client.get(f"/client_status/{issued_client['token']}")
    data = res.get_json()
    assert data["notification_email"] == "prev@example.com"
    assert data["notification_email_verified"] is True


def test_client_status_no_notification_email_means_not_verified(client, issued_client):
    """When the client has no notification_email, verified flag is False
    (and the email field is empty string)."""
    from src.infrastructure.repositories import client_repo

    # Advance past 'issued' so the status payload includes notif fields.
    client_repo.update_field(issued_client["id"], state="approved")
    res = client.get(f"/client_status/{issued_client['token']}")
    assert res.status_code == 200
    data = res.get_json()
    assert data["notification_email"] == ""
    assert data["notification_email_verified"] is False


# ── client_request_email_magic_link alias ─────────────────────────────────────


def test_client_request_email_magic_link_works_like_send(client, issued_client, monkeypatch):
    """The monitor-panel alias must behave identically to /send_email_magic_link
    (both go through the same internal helper)."""
    from src.app.routes import client as client_routes
    from src.infrastructure import database
    from src.notifications import email as email_notif

    monkeypatch.setattr(email_notif, "send", lambda *a, **kw: True)
    importlib.reload(client_routes)

    res = client.post(
        "/client_request_email_magic_link",
        json={"user_id": issued_client["id"], "email": "alias@example.com"},
    )
    assert res.status_code == 200
    assert res.get_json()["status"] == "ok"

    with database.cursor() as cur:
        cur.execute(
            "SELECT email FROM email_confirmations WHERE user_id = ?",
            (issued_client["id"],),
        )
        rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0]["email"] == "alias@example.com"
