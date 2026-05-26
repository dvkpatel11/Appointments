# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| `main` branch | Yes |

## Reporting a Vulnerability

If you discover a security vulnerability in VisaCtrl, please report it privately:

1. **Do NOT** open a public GitHub issue
2. Email the maintainer directly with details
3. Include steps to reproduce, impact assessment, and suggested fix if possible
4. Allow 72 hours for initial response

## Known Risk Areas

### Credential Storage

- Client credentials (username/password for visa portal) are stored in plaintext in `client_tokens.json` during active sessions. This is a known limitation of the current architecture.
- **Mitigation:** `.gitignore` excludes state files. In production, the ephemeral filesystem limits exposure window.

### Authentication

- Admin authentication is a single shared password with session-based auth.
- No MFA, no password reset, no brute-force protection currently implemented.
- **Mitigation:** Use a strong, unique `ADMIN_PASSWORD`. Consider placing behind Cloud IAP or a reverse proxy with rate limiting.

### Input Validation

- `user_id` values are used in file paths. Insufficient sanitization could allow path traversal.
- **Mitigation:** Admin-only access limits attack surface. Input validation is planned.

### Browser Automation

- Playwright runs headless Chromium with real user credentials. The application logs into a third-party service on behalf of users.
- **Mitigation:** Credentials are only stored in memory and JSON state files (excluded from git). Browser contexts are isolated per session.

### CSRF

- POST endpoints do not currently include CSRF tokens.
- **Mitigation:** Session-based auth provides some protection. Full CSRF tokens planned.

## Credential Rotation Procedure

The following credentials exist on disk and should be rotated before production use.

### 1. SMTP / Gmail App Password

Stored in `.env` as `SMTP_PASSWORD`.

1. Go to https://myaccount.google.com/apppasswords
2. Generate a new App Password for "Mail"
3. Update `SMTP_PASSWORD` in `.env`

### 2. Admin Password

Stored in `.env` as `ADMIN_PASSWORD`.

1. Generate a new password: `python -c "import secrets; print(secrets.token_urlsafe(16))"`
2. Update `ADMIN_PASSWORD` in `.env`

### 3. Telegram Bot Token

Stored in `canada/creds.py` as `TOKEN` and `uk/creds.py` as `TOKEN`.

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Use `/mybots` → select your bot → **API Token** → Revoke current token
3. Copy the new token
4. Set `TELEGRAM_BOT_TOKEN` in `.env`
5. Delete the `TOKEN` line from `canada/creds.py` and `uk/creds.py`

### 4. Visa Portal Passwords

Stored in `canada/creds.py` and `uk/creds.py`:

- **Email:** `ashleykasombo@gmail.com`
- **Portal password:** Change at https://ais.usvisa-info.com (Sign In → Settings)
- **Jiggar's password** (`JiggarUSvisa@2529`): Ask Jiggar to change theirs

After rotation, remove the credential fields from `creds.py` files and read them exclusively from environment variables (set in `.env` or deployment secrets).

### 5. Migrating from creds.py to .env

Once credentials are rotated:

1. Add to your `.env`:
   ```
   VISA_USERNAME=your_email@example.com
   VISA_PASSWORD=your_new_password
   VISA_APPOINTMENT_ID=AA00XXXXXX
   VISA_APPOINTMENT_URL=https://ais.usvisa-info.com/en-ca/niv/schedule/{}/appointment
   TELEGRAM_BOT_TOKEN=your_new_bot_token
   TELEGRAM_CHAT_ID=your_chat_id
   ```
2. Delete the hardcoded values from `canada/creds.py` and `uk/creds.py`
3. Update the code to read from `os.environ.get("VISA_USERNAME")` etc.
4. Delete `client_tokens.json` session data (it will be recreated)

## Best Practices for Operators

1. Rotate `ADMIN_PASSWORD` periodically
2. Use SMTP App Passwords (not primary account passwords) for Gmail
3. Set `FLASK_DEBUG=false` in production
4. Never commit `.env` files
5. Regularly back up state files (`make backup`)
6. Monitor the `/health` endpoint with an external uptime monitor
7. Keep dependencies updated (`pip install --upgrade -r requirements.txt`)
