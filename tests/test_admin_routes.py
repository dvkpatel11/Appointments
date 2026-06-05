"""Tests for the new admin endpoints: /version, /clients/bulk-start, /clients/bulk-stop.

These are auth-gated (session["authenticated"]), so each test logs in
via the legacy login route before exercising the API.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def app(app_modules):
    """Build a Flask test app + test client from the shared fixtures."""
    from src.app import create

    importlib.reload(create)
    flask_app = create.create_app()
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client) -> None:
    """Set the session flag directly (faster than going through the login form)."""
    with client.session_transaction() as sess:
        sess["authenticated"] = True


def test_version_returns_app_and_commit(client):
    _login(client)
    res = client.get("/admin/version")
    assert res.status_code == 200
    data = res.get_json()
    assert "version" in data
    assert "commit" in data
    assert isinstance(data["version"], str) and data["version"]
    assert isinstance(data["commit"], str) and data["commit"]


def test_version_requires_auth(client):
    res = client.get("/admin/version")
    assert res.status_code == 302  # redirect to login


def test_bulk_start_unknown_id_reports_not_found(client):
    _login(client)
    res = client.post(
        "/admin/clients/bulk-start",
        json={"ids": ["does-not-exist"]},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ok"
    assert data["results"]["does-not-exist"] == "not_found"


def test_bulk_stop_unknown_id_reports_not_found(client):
    _login(client)
    res = client.post(
        "/admin/clients/bulk-stop",
        json={"ids": ["nope"]},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ok"
    assert data["results"]["nope"] == "not_found"


def test_bulk_start_rejects_non_list_ids(client):
    _login(client)
    res = client.post("/admin/clients/bulk-start", json={"ids": "not-a-list"})
    assert res.status_code == 400
    assert res.get_json()["status"] == "error"


def test_bulk_stop_rejects_non_list_ids(client):
    _login(client)
    res = client.post("/admin/clients/bulk-stop", json={"ids": "not-a-list"})
    assert res.status_code == 400
    assert res.get_json()["status"] == "error"


def test_bulk_start_requires_auth(client):
    res = client.post("/admin/clients/bulk-start", json={"ids": []})
    assert res.status_code == 302


def test_bulk_stop_requires_auth(client):
    res = client.post("/admin/clients/bulk-stop", json={"ids": []})
    assert res.status_code == 302


def test_dashboard_activity_route_removed(client):
    """The legacy /admin/dashboard/activity endpoint must 404 (route deleted)."""
    _login(client)
    res = client.get("/admin/dashboard/activity")
    assert res.status_code == 404
