# Fernet Password Encryption — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use godmode:task-runner to implement this plan task-by-task.

**Goal:** Add Fernet at-rest encryption for `clients.password` at the repository boundary. Migrate existing plaintext rows lazily. No changes to `Client` dataclass, scrapers, services, or routes.

**Architecture:** New `src/infrastructure/crypto.py` module with a lazy `get_fernet()` keyed on a new `ENCRYPTION_KEY` env var. `client_repo.save()` encrypts before SQL write; `row_to_client()` decrypts on read. Schema migration via `ALTER TABLE ... ADD COLUMN` in `init_db()`. Boot-time check in `create_app()` fails loud if the key is missing.

**Tech Stack:** Python 3.12, `cryptography` (new dep), pydantic-settings, sqlite3, pytest, monkeypatch fixtures.

**Design:** `docs/plans/2026-06-05-fernet-password-encryption-design.md` (commit f537583).

---

## Task 1: Test infrastructure — `conftest.py` with isolated DB + crypto key

**Files:**
- Create: `tests/conftest.py`

**Why first:** All subsequent tests need a fresh DB and a valid Fernet key. Centralizing these fixtures here means each test file is hermetic.

**Step 1: Create `tests/conftest.py`**

```python
"""Shared test fixtures.

Each test gets:
  - A temporary SQLite DB (DB_PATH monkey-patched BEFORE src.infrastructure.database is imported)
  - A valid Fernet key (ENCRYPTION_KEY monkey-patched BEFORE src.config is imported)
  - A clean src.config.settings (reloaded so pydantic-settings sees the new env)
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet


@pytest.fixture
def temp_db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the app at a fresh temp DB. Set BEFORE importing app modules."""
    db = tmp_path / "test_visactrl.db"
    monkeypatch.setenv("DB_PATH", str(db))
    return db


@pytest.fixture
def fernet_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """Generate a fresh Fernet key and expose it via ENCRYPTION_KEY."""
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    return key


@pytest.fixture
def app_modules(temp_db_path: Path, fernet_key: str):
    """Reload config + db modules so pydantic-settings sees the new env vars.
    Returns a namespace with the most commonly used handles."""
    import importlib

    from src import config
    from src.infrastructure import database

    importlib.reload(config)
    importlib.reload(database)
    database.init_db()

    return {"settings": config.settings, "db": database}
```

**Step 2: Verify it loads**

Run: `cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment && .venv/bin/python -c "from tests.conftest import *; print('ok')"`
Expected: prints `ok`, exits 0. (Bare import only — fixtures activate on pytest run.)

**Step 3: Run existing test to confirm fixture setup doesn't break it**

Run: `cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment && .venv/bin/pytest tests/test_event_bus.py -v`
Expected: 8 tests pass (existing test_event_bus.py is hermetic; doesn't use the fixtures).

**Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "test: shared fixtures (temp DB, Fernet key)"
```

---

## Task 2: `cryptography` dependency + `encryption_key` config field

**Files:**
- Modify: `requirements.txt` (add line)
- Modify: `src/config.py` (add field)

**Step 1: Add `cryptography` to requirements**

Edit `requirements.txt`, add this line at the end:

```
cryptography==46.0.4
```

(Note: 46.0.4 is the current stable as of 2026-06. If pip resolution fails, accept whatever pip picks — `cryptography>=42` is the floor we need for modern Fernet APIs.)

**Step 2: Install the dep and verify**

Run: `cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment && .venv/bin/pip install -r requirements.txt 2>&1 | tail -5`
Expected: installs `cryptography`, no errors.

Run: `cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment && .venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
Expected: prints a 44-char base64 string.

**Step 3: Add `encryption_key` field to `AppSettings`**

In `src/config.py`, add `encryption_key: str = ""` after `secret_key: str = ""` (line 10):

```python
    secret_key: str = ""
    encryption_key: str = ""
    debug: bool = False
```

**Step 4: Verify the field loads from env**

Run: `cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment && ENCRYPTION_KEY=test123 .venv/bin/python -c "from src.config import AppSettings; s = AppSettings(); print(repr(s.encryption_key))"`
Expected: prints `'test123'`.

**Step 5: Commit**

```bash
git add requirements.txt src/config.py
git commit -m "feat: add cryptography dep and ENCRYPTION_KEY config"
```

---

## Task 3: `src/infrastructure/crypto.py` module (TDD)

**Files:**
- Create: `src/infrastructure/crypto.py`
- Create: `tests/test_crypto.py`

**Step 1: Write the failing tests**

Create `tests/test_crypto.py`:

```python
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
```

**Step 2: Run tests, confirm they fail**

Run: `cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment && .venv/bin/pytest tests/test_crypto.py -v`
Expected: ALL FAIL with `ModuleNotFoundError: No module named 'src.infrastructure.crypto'`.

**Step 3: Implement `src/infrastructure/crypto.py`**

```python
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
```

**Step 4: Run tests, confirm they pass**

Run: `cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment && .venv/bin/pytest tests/test_crypto.py -v`
Expected: 8 tests pass.

**Step 5: Commit**

```bash
git add src/infrastructure/crypto.py tests/test_crypto.py
git commit -m "feat: Fernet password crypto module (encrypt/decrypt/sniff/boot check)"
```

---

## Task 4: Schema migration in `init_db()` (add `password_ciphertext` column)

**Files:**
- Modify: `src/infrastructure/database.py` (`init_db()`)

**Step 1: Write a test that asserts the column exists after `init_db()`**

Append to `tests/test_crypto.py` (or create `tests/test_database.py` — keep with crypto tests for now):

```python
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
```

**Step 2: Run, confirm failure**

Run: `cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment && .venv/bin/pytest tests/test_crypto.py::test_init_db_adds_password_ciphertext_column -v`
Expected: FAIL — column does not exist yet.

**Step 3: Modify `init_db()` to add the column**

In `src/infrastructure/database.py`, after the `executescript` block (after line 87), add:

```python
        # Idempotent migration: add password_ciphertext if missing.
        # Existing rows keep their plaintext in `password` until next save().
        try:
            cur.execute("ALTER TABLE clients ADD COLUMN password_ciphertext TEXT")
        except sqlite3.OperationalError:
            pass
```

Make sure the indentation matches the existing `with cursor() as cur:` block (8 spaces for the body, since `cur` is the loop variable of the `with`).

**Step 4: Run, confirm pass**

Run: `cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment && .venv/bin/pytest tests/test_crypto.py::test_init_db_adds_password_ciphertext_column tests/test_crypto.py::test_init_db_is_idempotent -v`
Expected: both pass.

**Step 5: Commit**

```bash
git add src/infrastructure/database.py tests/test_crypto.py
git commit -m "feat: schema migration - add password_ciphertext column (idempotent)"
```

---

## Task 5: Encrypt on write / decrypt on read in `client_repo.py`

**Files:**
- Modify: `src/infrastructure/repositories/client_repo.py`
- Create: `tests/test_client_repo.py`

**Step 1: Write the failing tests**

Create `tests/test_client_repo.py`:

```python
"""Tests for client_repo: encryption roundtrip + legacy plaintext migration."""
from __future__ import annotations

import sqlite3

import pytest

from src.domain.client import Client
from src.domain.enums import ClientState, VisaType


def _make_client(**overrides) -> Client:
    base = dict(
        id="c-1",
        token="tok-1",
        name="Test",
        state=ClientState.ISSUED,
        reject_reason=None,
        username="u",
        password="hunter2",
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
    from src.infrastructure.repositories import client_repo

    c = _make_client()
    client_repo.save(c)

    # Read raw from DB to verify what's actually on disk
    from src.infrastructure.database import get_conn
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

    c = _make_client(password="MyS3cretP@ss")
    client_repo.save(c)

    loaded = client_repo.get_by_id(c.id)
    assert loaded is not None
    assert loaded.password == "MyS3cretP@ss"


def test_update_field_encrypts_password(temp_db_path, fernet_key, app_modules):
    from src.infrastructure.repositories import client_repo
    from src.infrastructure.database import get_conn

    c = _make_client(password="old")
    client_repo.save(c)

    client_repo.update_field(c.id, password="newP@ss")

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
    assert loaded.password == "newP@ss"


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
    assert loaded.password == "OldPlaintext!"


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
    assert loaded.password == "OldPlaintext2"
    client_repo.save(loaded)  # triggers migration

    conn = get_conn()
    try:
        row = conn.execute("SELECT password, password_ciphertext FROM clients WHERE id = ?", ("legacy-2",)).fetchone()
    finally:
        conn.close()
    assert row["password_ciphertext"] is not None
    assert row["password_ciphertext"].startswith("gAAAAA")
```

**Step 2: Run, confirm failure**

Run: `cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment && .venv/bin/pytest tests/test_client_repo.py -v`
Expected: ALL FAIL (the schema column doesn't exist yet, so writes crash; even if they didn't, no encryption would happen).

**Step 3: Modify `client_repo.py`**

In `src/infrastructure/repositories/client_repo.py`:

**(a)** Update imports (top of file):

```python
from src.infrastructure.crypto import decrypt_password, encrypt_password, is_encrypted_token
```

**(b)** Update `row_to_client` (currently line 33-55). Replace the `password=row["password"]` line with logic that prefers `password_ciphertext`:

```python
    # Prefer the encrypted column; fall back to legacy plaintext for
    # pre-migration rows (migrated on next save()).
    token = row.get("password_ciphertext")
    if token and is_encrypted_token(token):
        decrypted = decrypt_password(token)
    else:
        decrypted = row["password"]
```

And in the `Client(...)` constructor call, change `password=row["password"]` to `password=decrypted`.

**(c)** Update `save` (currently line 86-117). Replace the `password` value in the SQL params tuple with the encrypted form, and the SQL column list must include `password_ciphertext` (drop `password` for the write). The new SQL:

```python
        cur.execute(
            """INSERT OR REPLACE INTO clients
               (id, token, name, state, reject_reason, username,
                password_ciphertext, appointment_id, appointment_url,
                visa_type, reschedule, preferred_locations,
                preferred_date_from, preferred_date_to, notification_email,
                telegram_chat_id, phone_number, agent_pid, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       CURRENT_TIMESTAMP)""",
            (
                client.id,
                client.token,
                client.name,
                client.state.value,
                client.reject_reason,
                client.username,
                encrypt_password(client.password) if client.password else None,
                client.appointment_id,
                client.appointment_url,
                client.visa_type.value,
                1 if client.reschedule else 0,
                json.dumps(client.preferred_locations) if client.preferred_locations else None,
                client.preferred_date_from,
                client.preferred_date_to,
                client.notification_email,
                client.telegram_chat_id,
                client.phone_number,
                client.agent_pid,
            ),
        )
```

**(d)** Update `update_field` (currently line 120-135). If the `password` key is in `kwargs`, encrypt the value before SQL write:

```python
def update_field(client_id: str, **kwargs: Any) -> None:
    if not kwargs:
        return
    invalid = set(kwargs) - ALLOWED_UPDATE_COLUMNS
    if invalid:
        raise ValueError(f"Invalid update columns: {sorted(invalid)}")
    # If updating password, encrypt the value AND write to the ciphertext column.
    if "password" in kwargs:
        kwargs["password_ciphertext"] = encrypt_password(kwargs.pop("password")) if kwargs["password"] is not None else None
        # Re-validate the swapped column
        invalid = set(kwargs) - ALLOWED_UPDATE_COLUMNS
        if invalid:
            raise ValueError(f"Invalid update columns: {sorted(invalid)}")
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values())
    with cursor() as cur:
        # Column names are validated against ALLOWED_UPDATE_COLUMNS above; values
        # are parameterized. The f-string only interpolates whitelisted column
        # names, not user data.
        cur.execute(
            f"UPDATE clients SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",  # noqa: S608
            (*vals, client_id),
        )
```

**Step 4: Run, confirm pass**

Run: `cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment && .venv/bin/pytest tests/test_client_repo.py -v`
Expected: 5 tests pass.

**Step 5: Commit**

```bash
git add src/infrastructure/repositories/client_repo.py tests/test_client_repo.py
git commit -m "feat: encrypt password on save/update, decrypt on read; lazy migrate legacy rows"
```

---

## Task 6: Boot-time check in `create_app()`

**Files:**
- Modify: `src/app/create.py`

**Step 1: Add a test for the boot check**

Add to `tests/test_crypto.py` (or create `tests/test_create_app.py` — keep adjacent):

```python
def test_create_app_fails_without_encryption_key(temp_db_path, monkeypatch):
    """Without ENCRYPTION_KEY, the app factory must raise a clear error."""
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    import importlib
    from src import config
    importlib.reload(config)

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
```

**Step 2: Run, confirm failure**

Run: `cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment && .venv/bin/pytest tests/test_crypto.py::test_create_app_fails_without_encryption_key -v`
Expected: FAIL — `create_app()` doesn't check the key yet.

**Step 3: Add the check in `create_app()`**

In `src/app/create.py`, add this import near the top (after the existing `from src.app.routes import ...` block):

```python
from src.infrastructure.crypto import ensure_encryption_key
```

In the `create_app()` function (find the line `app = Flask(__name__)`), insert immediately BEFORE it:

```python
    ensure_encryption_key()
```

**Step 4: Run, confirm pass**

Run: `cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment && .venv/bin/pytest tests/test_crypto.py::test_create_app_fails_without_encryption_key tests/test_crypto.py::test_create_app_succeeds_with_encryption_key -v`
Expected: both pass.

**Step 5: Manual boot check**

Run: `cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment && unset ENCRYPTION_KEY && .venv/bin/python -c "from src.app.create import create_app; create_app()"`
Expected: `RuntimeError: ENCRYPTION_KEY is not set...`

Run: `cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment && ENCRYPTION_KEY=$(.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") .venv/bin/python -c "from src.app.create import create_app; create_app(); print('OK')"`
Expected: prints `OK`.

**Step 6: Commit**

```bash
git add src/app/create.py tests/test_crypto.py
git commit -m "feat: boot-time ENCRYPTION_KEY check in create_app"
```

---

## Task 7: Update `.env.example`, `cloudbuild.yaml`, `render.yaml`

**Files:**
- Modify: `.env.example`
- Modify: `cloudbuild.yaml`
- Modify: `render.yaml`

**Step 1: Add to `.env.example`**

Append (preserving the existing format):

```
# Encryption key for at-rest client passwords (Fernet).
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=
```

**Step 2: Add to `cloudbuild.yaml`**

In the `--update-secrets` (or `secrets:`) section, add `ENCRYPTION_KEY=projects/$PROJECT_ID/secrets/encryption-key:latest` next to the other `SECRET_KEY=...` reference. Preserve existing indentation.

If the file uses inline `--set-env-vars`, add `,ENCRYPTION_KEY=$$ENCRYPTION_KEY` (with appropriate escaping per file conventions). Read the file first to match style.

**Step 3: Add to `render.yaml`**

In the `envVars:` section (or `secretFiles:` / `secrets:` block), add an entry for `ENCRYPTION_KEY` with `sync: false` (operator must enter in Render dashboard). Preserve style.

**Step 4: Verify all 3 files are valid YAML / dotenv**

Run: `cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment && .venv/bin/python -c "import yaml; yaml.safe_load(open('cloudbuild.yaml')); yaml.safe_load(open('render.yaml')); print('YAML OK')"`
Expected: `YAML OK`.

Run: `cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment && grep -E "ENCRYPTION_KEY|SECRET_KEY" .env.example cloudbuild.yaml render.yaml`
Expected: all 3 files mention `ENCRYPTION_KEY`; `SECRET_KEY` still present.

**Step 5: Commit**

```bash
git add .env.example cloudbuild.yaml render.yaml
git commit -m "docs: add ENCRYPTION_KEY to .env.example, cloudbuild, render"
```

---

## Task 8: Final integration verification

**Step 1: Full test suite**

Run: `cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment && .venv/bin/pytest tests/ -v`
Expected: all tests pass (existing `test_event_bus.py` + new `test_crypto.py` + `test_client_repo.py`).

**Step 2: Lint**

Run: `cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment && ruff check .`
Expected: `All checks passed!`

**Step 3: Format check (don't auto-format, just verify)**

Run: `cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment && ruff format --check src/ tests/`
Expected: `0 files would be changed, X files already formatted` (or similar — if not formatted, run `ruff format src/ tests/`).

**Step 4: Boot test with real key**

```bash
cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment
KEY=$(.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
ENCRYPTION_KEY=$KEY .venv/bin/python -c "from src.app.create import create_app; app = create_app(); print(f'BOOT_OK routes={len(list(app.url_map.iter_rules()))}')"
```
Expected: `BOOT_OK routes=58` (same route count as before).

**Step 5: End-to-end smoke — submit a client, verify DB has ciphertext, decrypts back**

```bash
cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment
KEY=$(.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
ENCRYPTION_KEY=$KEY DB_PATH=/tmp/fernet_smoke.db .venv/bin/python -c "
from src.infrastructure import database
database.init_db()
from src.infrastructure.repositories import client_repo
from src.domain.client import Client
from src.domain.enums import ClientState, VisaType
c = Client(id='smoke', token='smoke', name='Smoke', state=ClientState.ISSUED,
          username='u', password='VisaPortalP@ss2024', visa_type=VisaType.CANADA, reschedule=False)
client_repo.save(c)
loaded = client_repo.get_by_id('smoke')
print(f'LOADED_PASSWORD: {loaded.password!r}')
import sqlite3
conn = sqlite3.connect('/tmp/fernet_smoke.db')
row = conn.execute('SELECT password, password_ciphertext FROM clients WHERE id=?', ('smoke',)).fetchone()
print(f'ON_DISK_PASSWORD: {row[0]!r}')
print(f'ON_DISK_CIPHERTEXT: {row[1][:30]!r}...')
assert row[0] is None or row[0] == ''
assert row[1].startswith('gAAAAA')
assert loaded.password == 'VisaPortalP@ss2024'
print('SMOKE_OK')
"
```
Expected:
```
LOADED_PASSWORD: 'VisaPortalP@ss2024'
ON_DISK_PASSWORD: None
ON_DISK_CIPHERTEXT: 'gAAAAA...'...
SMOKE_OK
```

**Step 6: Clean up the smoke DB and commit any remaining format fixes**

```bash
rm -f /tmp/fernet_smoke.db
cd /mnt/c/Users/deepv/Desktop/Projects/UsVisaAppointment
ruff format src/ tests/   # only if step 3 showed drift
git status
```

If there are any uncommitted formatting changes: `git add -u && git commit -m "style: ruff format"`.

---

## Acceptance criteria

- [ ] `ENCRYPTION_KEY` missing → `create_app()` raises clear `RuntimeError`
- [ ] `ENCRYPTION_KEY` set → `create_app()` boots, all 58 routes registered
- [ ] `pytest tests/ -v` → all green
- [ ] `ruff check .` → clean
- [ ] Saving a client → DB row has `password_ciphertext` starting with `gAAAAA`, `password` column empty
- [ ] Loading a client → `Client.password` is the original plaintext
- [ ] Pre-migration rows (legacy `password` plaintext, `password_ciphertext` NULL) load correctly
- [ ] `update_field(id, password="x")` → DB row has encrypted ciphertext, `Client.password` decrypts back
- [ ] Tampered token → `InvalidToken` raised
- [ ] Wrong key → `InvalidToken` raised
- [ ] No plaintext password ever appears in DB row, log line, or JSON response
