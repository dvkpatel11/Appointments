"""Tests for the Fernet password encryption module."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet, InvalidToken


def test_roundtrip(fernet_key: str):
    from src.infrastructure.crypto import encrypt_password, decrypt_password

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
    from src.infrastructure.crypto import encrypt_password, decrypt_password

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
    from src.infrastructure.crypto import encrypt_password, decrypt_password

    token = encrypt_password("secret")
    # Flip a character in the middle
    bad = token[:50] + ("A" if token[50] != "A" else "B") + token[51:]
    with pytest.raises(InvalidToken):
        decrypt_password(bad)
