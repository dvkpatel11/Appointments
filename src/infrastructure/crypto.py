"""Fernet symmetric encryption for at-rest client passwords.

The visa-portal scraper needs plaintext on every run to fill the login form, so
plaintext is held in memory by design. The DB column is encrypted at rest.

Encryption layer: cryptography.fernet.Fernet (AES-128-CBC + HMAC-SHA256,
authenticated, per-message nonce).

Key: a 44-char URL-safe base64 string in the ENCRYPTION_KEY env var. Generate
with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from src.config import settings

_FERNET: Fernet | None = None

# Fernet token prefix: version byte 0x80 base64-url-encoded = 'gAAAAA...'
_FERNET_PREFIX = "gAAAAA"


def _load_fernet() -> Fernet:
    key = settings.encryption_key
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set. Generate one with: "
            "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"` "
            "and add it to your .env (or secret manager)."
        )
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as e:
        raise RuntimeError(f"ENCRYPTION_KEY is malformed: {e}") from e


def get_fernet() -> Fernet:
    """Return a cached Fernet instance, loading the key from settings on first call."""
    global _FERNET
    if _FERNET is None:
        _FERNET = _load_fernet()
    return _FERNET


def reset_fernet_cache() -> None:
    """Drop the cached Fernet. Used by tests that swap ENCRYPTION_KEY."""
    global _FERNET
    _FERNET = None


def encrypt_password(plaintext: str) -> str:
    """Encrypt a plaintext password. Returns a URL-safe base64 Fernet token."""
    if plaintext is None:
        return None  # type: ignore[return-value]
    return get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_password(token: str) -> str:
    """Decrypt a Fernet token. Raises InvalidToken on tampering or wrong key."""
    return get_fernet().decrypt(token.encode()).decode()


def is_encrypted_token(value: str) -> bool:
    """Cheap sniff: Fernet tokens always start with 'gAAAAA' (version byte + timestamp)."""
    return bool(value) and value.startswith(_FERNET_PREFIX)


def ensure_encryption_key() -> None:
    """Boot-time check. Raises RuntimeError if the key is missing or malformed."""
    get_fernet()
