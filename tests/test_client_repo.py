"""Tests for client_repo: encryption roundtrip + legacy plaintext migration."""

from __future__ import annotations

from src.domain.client import Client
from src.domain.enums import ClientState, VisaType


def _make_client(**overrides) -> Client:
    base = dict(
        id="c-1",
        token="tok-1",  # noqa: S106
        name="Test",
        state=ClientState.ISSUED,
        reject_reason=None,
        username="u",
        password="hunter2",  # noqa: S106
        appointment_id="a-1",
        appointment_url="https://example.com",
        visa_type=VisaType.CANADA,
        reschedule=False,
        preferred_locations=["Toronto"],
        preferred_date_from=None,
        preferred_date_to=None,
        notification_email=None,
        telegram_chat_id=None,
        phone_number=None,
        agent_pid=None,
    )
    base.update(overrides)
    return Client(**base)


def test_save_encrypts_password_on_disk(temp_db_path, fernet_key, app_modules):
    from src.infrastructure.database import get_conn
    from src.infrastructure.repositories import client_repo

    c = _make_client()
    client_repo.save(c)

    # Read raw from DB to verify what's actually on disk
    conn = get_conn()
    try:
        row = conn.execute("SELECT password, password_ciphertext FROM clients WHERE id = ?", (c.id,)).fetchone()
    finally:
        conn.close()
    assert row["password"] in (None, "")  # legacy column not written for new saves
    assert row["password_ciphertext"] is not None
    assert row["password_ciphertext"].startswith("gAAAAA")  # Fernet token prefix


def test_get_by_id_decrypts_password(temp_db_path, fernet_key, app_modules):
    from src.infrastructure.repositories import client_repo

    c = _make_client(password="MyS3cretP@ss")  # noqa: S106
    client_repo.save(c)

    loaded = client_repo.get_by_id(c.id)
    assert loaded is not None
    assert loaded.password == "MyS3cretP@ss"  # noqa: S105


def test_update_field_encrypts_password(temp_db_path, fernet_key, app_modules):
    from src.infrastructure.database import get_conn
    from src.infrastructure.repositories import client_repo

    c = _make_client(password="old")  # noqa: S106
    client_repo.save(c)

    client_repo.update_field(c.id, password="newP@ss")  # noqa: S106

    # Read raw to verify it's encrypted on disk
    conn = get_conn()
    try:
        row = conn.execute("SELECT password, password_ciphertext FROM clients WHERE id = ?", (c.id,)).fetchone()
    finally:
        conn.close()
    assert row["password_ciphertext"] is not None
    assert row["password_ciphertext"].startswith("gAAAAA")
    assert "newP@ss" not in (row["password"] or "")

    # And it decrypts back correctly
    loaded = client_repo.get_by_id(c.id)
    assert loaded.password == "newP@ss"  # noqa: S105


def test_legacy_plaintext_row_loaded(temp_db_path, fernet_key, app_modules):
    """Pre-migration row: password_ciphertext is NULL, legacy password has plaintext.
    Should load without crashing, returning the legacy plaintext as Client.password."""
    from src.infrastructure.database import get_conn
    from src.infrastructure.repositories import client_repo

    # Seed a legacy row directly via raw SQL
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO clients (id, token, name, state, username, password, visa_type, reschedule) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            ("legacy-1", "legacy-tok", "Legacy", "issued", "u", "OldPlaintext!", "canada"),
        )
        conn.commit()
    finally:
        conn.close()

    loaded = client_repo.get_by_id("legacy-1")
    assert loaded is not None
    assert loaded.password == "OldPlaintext!"  # noqa: S105


def test_legacy_row_migrated_on_save(temp_db_path, fernet_key, app_modules):
    """Load a legacy row, then save() it — password_ciphertext should be populated."""
    from src.infrastructure.database import get_conn
    from src.infrastructure.repositories import client_repo

    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO clients (id, token, name, state, username, password, visa_type, reschedule) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            ("legacy-2", "legacy-tok-2", "Legacy2", "issued", "u", "OldPlaintext2", "canada"),
        )
        conn.commit()
    finally:
        conn.close()

    loaded = client_repo.get_by_id("legacy-2")
    assert loaded.password == "OldPlaintext2"  # noqa: S105
    client_repo.save(loaded)  # triggers migration

    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT password, password_ciphertext FROM clients WHERE id = ?",
            ("legacy-2",),
        ).fetchone()
    finally:
        conn.close()
    assert row["password_ciphertext"] is not None
    assert row["password_ciphertext"].startswith("gAAAAA")
