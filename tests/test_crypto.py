"""Tests for the Fernet password encryption module."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet, InvalidToken


def test_roundtrip(fernet_key: str):
    from src.infrastructure.crypto import decrypt_password, encrypt_password

    plain = "MyS3cretP@ss"
    token = encrypt_password(plain)
    assert decrypt_password(token) == plain


def test_encrypt_produces_different_tokens(fernet_key: str):
    from src.infrastructure.crypto import encrypt_password

    plain = "same-password"
    a = encrypt_password(plain)
    b = encrypt_password(plain)
    assert a != b  # nonce uniqueness


def test_is_encrypted_token_true_for_fernet(fernet_key: str):
    from src.infrastructure.crypto import is_encrypted_token

    token = Fernet(fernet_key.encode()).encrypt(b"x").decode()
    assert is_encrypted_token(token) is True


def test_is_encrypted_token_false_for_plaintext(fernet_key: str):
    from src.infrastructure.crypto import is_encrypted_token

    assert is_encrypted_token("hunter2") is False
    assert is_encrypted_token("") is False
    assert is_encrypted_token("Visa@2024!") is False


def test_missing_key_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    # Reload config so the empty default is read
    import importlib

    from src import config

    importlib.reload(config)

    from src.infrastructure import crypto

    importlib.reload(crypto)

    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        crypto.encrypt_password("x")


def test_malformed_key_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "not-a-valid-base64-key!!")
    import importlib

    from src import config

    importlib.reload(config)

    from src.infrastructure import crypto

    importlib.reload(crypto)

    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        crypto.encrypt_password("x")


def test_wrong_key_raises_invalid_token(fernet_key: str):
    from src.infrastructure.crypto import encrypt_password

    token = encrypt_password("secret")
    # Swap the key underneath — decrypt should fail
    import importlib

    from src import config

    monkeypatch_key = Fernet.generate_key().decode()
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setenv("ENCRYPTION_KEY", monkeypatch_key)
        importlib.reload(config)
        importlib.reload(__import__("src.infrastructure.crypto", fromlist=["*"]))
        from src.infrastructure.crypto import decrypt_password as decrypt2

        with pytest.raises(InvalidToken):
            decrypt2(token)
    finally:
        monkeypatch.undo()


def test_tampered_token_raises(fernet_key: str):
    from src.infrastructure.crypto import decrypt_password, encrypt_password

    token = encrypt_password("secret")
    # Flip a character in the middle
    bad = token[:50] + ("A" if token[50] != "A" else "B") + token[51:]
    with pytest.raises(InvalidToken):
        decrypt_password(bad)


def test_init_db_adds_password_ciphertext_column(temp_db_path, fernet_key, app_modules):
    from src.infrastructure.database import cursor

    with cursor() as cur:
        cur.execute("PRAGMA table_info(clients)")
        cols = {row["name"] for row in cur.fetchall()}
    assert "password_ciphertext" in cols
    assert "password" in cols  # legacy column preserved for migration window


def test_init_db_is_idempotent(temp_db_path, fernet_key, app_modules):
    """Running init_db() twice must not crash (ALTER TABLE ADD COLUMN errors
    are caught and treated as 'column already exists')."""
    from src.infrastructure import database

    database.init_db()  # second run
    # If we get here without exception, the test passes.


def test_create_app_fails_without_encryption_key(temp_db_path, monkeypatch):
    """Without ENCRYPTION_KEY, the app factory must raise a clear error."""
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    import importlib

    from src import config
    from src.infrastructure import crypto

    importlib.reload(config)
    importlib.reload(crypto)  # crypto holds a stale settings ref from earlier tests
    # Sanity check: settings is now empty
    assert config.settings.encryption_key == ""

    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        from src.app.create import create_app

        create_app()


def test_create_app_succeeds_with_encryption_key(temp_db_path, fernet_key, app_modules):
    """With ENCRYPTION_KEY set, the app factory must boot successfully."""
    # The fernet_key fixture already sets ENCRYPTION_KEY and reloaded config.
    # app_modules reloaded config + db. Now reload create.
    import importlib

    from src.app import create

    importlib.reload(create)

    app = create.create_app()
    assert app is not None
