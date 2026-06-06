from __future__ import annotations

import uuid
from typing import Any

from src.domain.profile import Profile
from src.infrastructure.crypto import decrypt_password, encrypt_password, is_encrypted_token
from src.infrastructure.database import cursor

ALLOWED_UPDATE_COLUMNS = frozenset(
    {
        "name",
        "username",
        "password",
        "notification_email",
        "notification_email_verified",
        "telegram_chat_id",
        "phone_number",
    }
)


def row_to_profile(row: dict[str, Any]) -> Profile:
    # Profiles are a brand-new table — every row's password is encrypted.
    # We accept a legacy plaintext row only if the column is empty/None.
    token = row.get("password_ciphertext")
    if token and is_encrypted_token(token):
        password = decrypt_password(token)
    else:
        password = None
    return Profile(
        id=row["id"],
        token=row["token"],
        name=row["name"],
        username=row["username"],
        password=password,
        notification_email=row["notification_email"],
        notification_email_verified=bool(row["notification_email_verified"]),
        telegram_chat_id=row["telegram_chat_id"],
        phone_number=row["phone_number"],
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def get_by_token(token: str) -> Profile | None:
    with cursor() as cur:
        cur.execute("SELECT * FROM profiles WHERE token = ?", (token,))
        row = cur.fetchone()
    return row_to_profile(dict(row)) if row else None


def get_by_id(profile_id: str) -> Profile | None:
    with cursor() as cur:
        cur.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
        row = cur.fetchone()
    return row_to_profile(dict(row)) if row else None


def get_all() -> dict[str, Profile]:
    with cursor() as cur:
        cur.execute("SELECT * FROM profiles")
        return {row["id"]: row_to_profile(dict(row)) for row in cur.fetchall()}


def save(profile: Profile) -> None:
    encrypted_pw = encrypt_password(profile.password) if profile.password else None
    with cursor() as cur:
        cur.execute(
            """INSERT OR REPLACE INTO profiles
               (id, token, name, username, password_ciphertext,
                notification_email, notification_email_verified,
                telegram_chat_id, phone_number, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (
                profile.id,
                profile.token,
                profile.name,
                profile.username,
                encrypted_pw,
                profile.notification_email,
                1 if profile.notification_email_verified else 0,
                profile.telegram_chat_id,
                profile.phone_number,
            ),
        )


def update_field(profile_id: str, **kwargs: Any) -> None:
    if not kwargs:
        return
    invalid = set(kwargs) - ALLOWED_UPDATE_COLUMNS
    if invalid:
        raise ValueError(f"Invalid update columns: {sorted(invalid)}")
    if "password" in kwargs:
        plaintext = kwargs.pop("password")
        kwargs["password_ciphertext"] = encrypt_password(plaintext) if plaintext else None
    if "notification_email_verified" in kwargs:
        kwargs["notification_email_verified"] = (
            1 if kwargs["notification_email_verified"] else 0
        )
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values())
    with cursor() as cur:
        # Column names are validated against ALLOWED_UPDATE_COLUMNS above; values
        # are parameterized. The f-string only interpolates whitelisted column
        # names, not user data.
        cur.execute(
            f"UPDATE profiles SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",  # noqa: S608
            (*vals, profile_id),
        )


def create_token() -> str:
    token = uuid.uuid4().hex
    with cursor() as cur:
        cur.execute(
            "INSERT INTO profiles (id, token) VALUES (?, ?)",
            (token, token),
        )
    return token
