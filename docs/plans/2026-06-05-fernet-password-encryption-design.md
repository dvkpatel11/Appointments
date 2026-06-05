# Fernet Password Encryption Design

Date: 2026-06-05
Status: Approved
Parent plan: `2026-05-30-refactor-design.md` + `2026-05-25-prod-gaps-plan.md`

## Problem

`clients.password` is stored as plaintext in SQLite. The AGENTS.md "Security
model" entry already calls this out. Threat surface:

- DB file exfiltration → all visa-portal credentials leaked
- DB snapshot in cloud backups → same
- `/proc/<pid>/cmdline` leak on shared host → in-process only, less serious

The scraper MUST recover plaintext on every run to fill the visa-portal login
form. **bcrypt is the wrong primitive** — it's one-way (verify-only). We need
**reversible symmetric encryption**.

## Goal

At-rest encryption for `clients.password` using Fernet (AES-128-CBC + HMAC-SHA256).
Zero changes to scraper code, zero changes to the `Client` domain object, zero
UX changes. Encrypt at the repository boundary, decrypt on read.

## Non-goals

- HSM / cloud KMS integration (future work)
- Per-user key derivation
- Re-architecting away from at-rest storage of visa credentials (would require
  re-prompt on every run, breaks automation)
- Migration to SQLAlchemy / Alembic (out of scope; project has no migration
  system today and this design follows the existing `CREATE TABLE IF NOT EXISTS`
  + `ALTER TABLE` pattern)

## Threat model

| Asset | Risk | Mitigation |
|-------|------|------------|
| SQLite DB file | Exfiltration of all visa passwords | Fernet at-rest encryption |
| Memory dump | Plaintext password in process memory | Out of scope — required for scraper to function. Mitigated by short scraper process lifetime. |
| `ENCRYPTION_KEY` leak | Decrypts all stored passwords | Loaded from env / secret manager. Standard secret-handling discipline. Documented in deploy docs. |
| `SECRET_KEY` rotation | Currently would invalidate Fernet key if we derived from it | Mitigated by using a **separate** `ENCRYPTION_KEY` env var. |

## Approach

### Encryption layer

New module `src/infrastructure/crypto.py`:

```python
def get_fernet() -> Fernet: ...            # lazy, cached, raises on missing
def encrypt_password(plaintext: str) -> str: ...
def decrypt_password(token: str) -> str: ...
def is_encrypted_token(value: str) -> bool: ...  # "gAAAAA..." sniff
def ensure_encryption_key() -> None: ...   # startup check
```

**Why Fernet**:
- Stdlib-adjacent (`cryptography` is the de-facto Python crypto lib; already a
  transitive dep via PyJWT)
- Authenticated encryption: HMAC detects tampering automatically
- Per-message nonce: same plaintext encrypts to different ciphertexts (prevents
  frequency analysis)
- Single 44-char base64 key, easy to generate and rotate
- Version byte enables future migration to v2 without breaking v1 reads

**Why a separate `ENCRYPTION_KEY` env var, not derived from `SECRET_KEY`**:
- `SECRET_KEY` rotates whenever Flask sessions need invalidating
- Rotation of derived key would invalidate ALL stored passwords
- Independent keys = independent rotation policies

### Repository changes

`src/infrastructure/repositories/client_repo.py`:

- `save(client)`: encrypt `client.password` via `encrypt_password()` before SQL
  write. Stored in `password_ciphertext` column.
- `row_to_client(row)`: read `password_ciphertext`, decrypt via
  `decrypt_password()`, populate `Client.password`. If `password_ciphertext` is
  NULL and legacy `password` column is non-empty (pre-migration row), use the
  legacy value as plaintext and the next `save()` will encrypt it.
- `update_field(client_id, password=...)`: encrypt the value before SQL write
  (recognize the `password` key and route through the crypto helper, not the
  raw setter).

**`ALLOWED_UPDATE_COLUMNS`** in `client_repo.py` already includes `"password"`
— no change there.

### Schema migration

In `init_db()` after the `CREATE TABLE` block:

```python
try:
    cur.execute("ALTER TABLE clients ADD COLUMN password_ciphertext TEXT")
except sqlite3.OperationalError:
    pass  # column already exists
```

`CREATE TABLE IF NOT EXISTS` does NOT add columns to an existing table, so
this is the project's idiomatic approach. The migration is idempotent.

### Migration of existing rows

No backfill script. Strategy:

1. `init_db()` adds the new column (NULL for existing rows).
2. `row_to_client()` returns the legacy plaintext `password` column when
   `password_ciphertext` is NULL. Scraper keeps working.
3. Next `client_repo.save()` call (e.g., when admin edits a client, or when
   `submit_request` is invoked) writes the encrypted version. Migration
   completes organically as clients are touched.

If we want a hard migration: a one-shot script that runs
`UPDATE clients SET password_ciphertext = encrypt(password) WHERE password_ciphertext IS NULL`.
**Out of scope for v1** — the lazy migration is simpler and safer.

### Sniffing heuristic for `is_encrypted_token()`

Fernet tokens always start with byte `\x80` (version) followed by a 64-bit
timestamp. URL-safe base64 of those 9 bytes is `gAAAAA` (6 chars). Plaintext
passwords essentially never start with that literal. No flag column needed.

Verification: `Fernet.generate_key()` + `Fernet(key).encrypt(b"test")` always
produces a token whose first 6 base64 chars are `gAAAAA`. Tested in
`tests/test_crypto.py`.

## Files changed

| File | Change | Lines |
|------|--------|-------|
| `src/infrastructure/crypto.py` (NEW) | Module | +60 |
| `src/config.py` | Add `encryption_key: str = ""` | +1 |
| `src/infrastructure/database.py` | ALTER TABLE in `init_db()` | +5 |
| `src/infrastructure/repositories/client_repo.py` | Encrypt on write, decrypt on read, handle migration | +20 / -5 |
| `src/app/create.py` | Call `ensure_encryption_key()` at boot | +4 |
| `tests/test_crypto.py` (NEW) | Unit tests for crypto module | +80 |
| `tests/test_client_repo.py` (NEW) | Repo encryption roundtrip + migration | +90 |
| `requirements.txt` | Add `cryptography` | +1 |
| `.env.example` | Add `ENCRYPTION_KEY` with generation hint | +3 |
| `cloudbuild.yaml` | Add `ENCRYPTION_KEY` to secrets | +1 |
| `render.yaml` | Add `ENCRYPTION_KEY` to secrets | +1 |

**No changes to**: `Client` dataclass, scraper code, services, routes, templates.

## Key generation & deployment

Generate a key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Output: 44-char base64 string. Store in:

- Local: `.env` (gitignored)
- Render: dashboard secret store
- Cloud Run: Secret Manager via `cloudbuild.yaml`

Rotation strategy: generate new key, re-encrypt all `password_ciphertext`
values with the new key (decrypt with old, encrypt with new), swap key, drop
old key. **Not in v1 scope** — document the procedure, defer implementation.

## Error handling

| Scenario | Behavior |
|----------|----------|
| `ENCRYPTION_KEY` unset | `ensure_encryption_key()` raises `RuntimeError` with setup instructions. `create_app()` propagates → app fails to start (correct — fail loud) |
| Malformed key | `Fernet()` constructor raises `ValueError`. Wrapped in `ensure_encryption_key()` with clear message. |
| Wrong key decrypting existing data | `cryptography.fernet.InvalidToken` → `decrypt_password()` re-raises. `row_to_client()` catches and returns `Client` with `password=None` + logs error. Scraper fails to start via existing `can_start` guard. Visible in admin monitor. |
| Corrupted/tampered token | Same as above — HMAC catches it. |
| Decrypting legacy plaintext row | `is_encrypted_token()` returns False → fallback to `password` column. |

## Testing strategy

### `tests/test_crypto.py` (NEW, ~80 lines)

- `test_roundtrip` — encrypt then decrypt → original
- `test_encrypt_produces_different_tokens` — same plaintext, two encrypts → different tokens (nonce uniqueness)
- `test_is_encrypted_token_true_for_fernet` — generate real token, check sniff
- `test_is_encrypted_token_false_for_plaintext` — typical passwords don't match `gAAAAA*`
- `test_missing_key_raises` — unset env → `ensure_encryption_key()` raises with message
- `test_malformed_key_raises` — `ENCRYPTION_KEY="not-base64"` → raises
- `test_wrong_key_raises_invalid_token` — encrypt with key A, decrypt with key B → `InvalidToken`
- `test_tampered_token_raises` — flip a byte in the token → `InvalidToken`
- `test_get_fernet_caches` — second call returns same instance (not relevant for perf, just for test stability)

### `tests/test_client_repo.py` (NEW, ~90 lines)

- `test_save_encrypts_password` — save client → assert `password_ciphertext` in DB row starts with `gAAAAA` (and `password` column is now NULL or ignored)
- `test_read_decrypts_password` — save then `get_by_id` → `client.password == plaintext`
- `test_update_field_encrypts_password` — `update_field(id, password="new")` → DB has Fernet token
- `test_legacy_plaintext_row_loaded` — seed DB with plaintext `password` column + NULL `password_ciphertext` → `get_by_id` returns plaintext (no crash)
- `test_legacy_row_migrated_on_save` — load legacy row, call `save()` → `password_ciphertext` populated, `password` column still has plaintext (we don't write to the legacy column)

### Boot tests (extend `tests/` later)

- Missing `ENCRYPTION_KEY` → `create_app()` raises clear error (test with `monkeypatch.delenv`)
- Valid `ENCRYPTION_KEY` → `create_app()` succeeds

### Manual smoke

After implementation:

```bash
sqlite3 canada/visactrl.db "SELECT password, password_ciphertext FROM clients LIMIT 3"
# → password column empty/NULL, password_ciphertext starts with gAAAAA...

python -c "from src.app.create import create_app; create_app()"
# → BOOT_OK with ENCRYPTION_KEY set
# → RuntimeError: ENCRYPTION_KEY not set... without it
```

## Open follow-ups (post-v1)

1. **Key rotation script** — `scripts/rotate_encryption_key.py` that re-encrypts
   all `password_ciphertext` values with a new key.
2. **Audit logging** — log every decrypt (low volume; client count is small).
   Helps detect scrapes of the DB.
3. **Argon2id consideration** — Fernet is fine for at-rest reversible
   encryption. If we ever need one-way hashing (e.g., for the admin login
   password), use `argon2-cffi`.
4. **Memory hardening** — `multiprocessing.Process` `args=` serializes the
   plaintext via pickle. Use `ssl` for IPC if we want belt-and-suspenders, or
   move to a Unix socket with a custom protocol. Out of scope for v1.
