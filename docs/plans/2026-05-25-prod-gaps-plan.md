# Production Gap Closure Plan

> **For Claude:** Use task-runner to implement
> **User constraint:** No test files, no credential rotation (user handles rotation)

**Goal:** Close all remaining production-readiness gaps in UsVisaAppointment

**Architecture:** Incremental fixes to existing Python/Flask/Playwright codebase. No structural refactors — targeted patches for security, robustness, and deployment hygiene.

**Tech Stack:** Python 3.12, Flask 3, Playwright, waitress

---

## Gap Status Summary

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| #1 | Live credentials on disk | CRITICAL | SECURITY.md guide added; user rotates |
| #2 | Predictable secret key fallback | CRITICAL | **TODO** |
| #3 | No CSRF protection | CRITICAL | **TODO** |
| #4 | Unauthenticated screenshot + path traversal | CRITICAL | **TODO** |
| #5 | .gitignore state files | CRITICAL | Already covered by `canada/canada/` + `canada/status/` patterns |
| #6 | Duplicate except block | CRITICAL | Already fixed (no duplicate exists) |
| #7 | Dockerfile broken | HIGH | Already fixed |
| #8 | Cloud Build deprecated GCR | HIGH | Already fixed |
| #9 | Render.yaml missing SMTP | HIGH | Already fixed |
| #10 | No rate limiting on login | HIGH | **TODO** |
| #11 | No input validation (path traversal) | HIGH | **TODO** |
| #12 | Multiprocess PID not tracked | HIGH | **TODO** |
| #13 | Unbounded in-memory state | HIGH | Already fixed (before_request cleanup) |
| #14 | .env.example divergence | HIGH | Already fixed |
| #15-24 | Missing skeleton files | MEDIUM | All created (CI, Makefile, scripts, docs, etc.) |
| #25 | Missing requirements-lock.txt | MEDIUM | **TODO** |
| #26 | Missing Sentry integration | MEDIUM | **TODO** |

**5 remaining items** across 6 files.

---

## Task 1: Secure secret key fallback (#2)

**Files:**
- Modify: `canada/app.py:26`

**Step 1: Change empty-string fallback to generated key**

```python
# Before:
app.secret_key = os.environ.get("SECRET_KEY", "")

# After (add import at top, change line):
import secrets
# ...
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
```

**Verification:** When `SECRET_KEY` is unset, a random 64-char hex key is generated. Sessions remain signed (no warning from Flask).

---

## Task 2: CSRF protection (#3)

**Files:**
- Add: none (use existing `secrets` / `uuid` from stdlib)
- Modify: `canada/app.py`

**Approach:** Manual CSRF token pattern (no Flask-WTF dependency). Generate per-session token, validate on POST.

### Step 1: Add `csrf_token` to session on login

In `login()` after successful auth:
```python
session["csrf_token"] = secrets.token_hex(16)
```

### Step 2: Add template helper for CSRF token

New helper function:
```python
def csrf_token():
    return session.get("csrf_token", "")
```

Pass to template context or add as context processor.

### Step 3: Add `@csrf_protect` decorator

```python
from functools import wraps

def csrf_protect(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = session.get("csrf_token")
        submitted = request.form.get("csrf_token") or (
            request.get_json(silent=True) or {}
        ).get("csrf_token")
        if not token or not submitted or not secrets.compare_digest(token, submitted):
            return jsonify({"status": "CSRF_FAILED"}), 403
        return f(*args, **kwargs)
    return decorated
```

### Step 4: Apply decorator to all POST routes

Add `@csrf_protect` below `@login_required` on:
- `start_automation`
- `start_multi_automation`
- `stop_automation`
- `stop_all_automation`
- `save_settings`
- `approve_client`
- `reject_client`
- `generate_telegram_link`
- `check_telegram_linked`
- `client_link_telegram`
- `client_update_notif`
- `test_email`
- `test_telegram`

Do NOT apply to `login` (POST) — CSRF token is generated after login succeeds; the login form itself uses admin password as implicit CSRF.

### Step 5: Update templates to include CSRF token

Insert hidden input in every POST form:
```html
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
```

And in fetch-based POST calls:
```javascript
fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ csrf_token: csrf_token, ...data })
})
```

**Verification:** A POST without valid CSRF token returns 403. Login is exempt.

---

## Task 3: Authenticate screenshot endpoints + path traversal fix (#4, #11)

**Files:**
- Modify: `canada/app.py:391-412`

### Step 1: Add `@login_required` to screenshot endpoints

```python
@app.route("/client_screenshot/<user_id>")
@login_required
def client_screenshot(user_id):
    # ...

@app.route("/screenshots/<path:filename>")
@login_required
def serve_screenshot(filename):
    return send_from_directory("screenshots", filename)
```

### Step 2: Sanitize user_id (path traversal protection)

```python
import re

def sanitize_user_id(user_id):
    if not re.match(r"^[a-zA-Z0-9_-]+$", user_id):
        return None
    return user_id
```

Apply to all endpoints accepting `user_id` from URL or form:
- `client_screenshot` — validate `user_id` from URL
- `view_log` — validate `user_id` from URL  
- `get_status` — validate `user_id` from query arg
- `stop_automation` — validate `user_id` from form
- `start_automation` — validate `user_id` from form

### Step 3: Sanitize screenshot paths

In `serve_screenshot`, prevent path traversal via `os.path.normpath`:
```python
@app.route("/screenshots/<path:filename>")
@login_required
def serve_screenshot(filename):
    safe = os.path.normpath(filename)
    if safe.startswith("..") or safe.startswith("/"):
        return jsonify({"error": "invalid path"}), 400
    return send_from_directory("screenshots", safe)
```

**Verification:** Unauthenticated requests to `/screenshots/` or `/client_screenshot/` redirect to login. Requests with `../../etc/passwd` in path return 400.

---

## Task 4: Rate limiting on login (#10)

**Files:**
- Modify: `canada/app.py`

**Approach:** Manual rate limiting using in-memory dict + timestamps (no Flask-Limiter dependency). Track attempts per IP.

### Step 1: Add rate limit state

```python
from collections import defaultdict
import time

login_attempts = defaultdict(list)
LOGIN_RATE_LIMIT = 10       # max attempts
LOGIN_RATE_WINDOW = 300     # per 5 minutes
```

### Step 2: Add decorator

```python
def rate_limit(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        ip = request.remote_addr or "unknown"
        now = time.time()
        attempts = login_attempts[ip]
        attempts[:] = [t for t in attempts if now - t < LOGIN_RATE_WINDOW]
        if len(attempts) >= LOGIN_RATE_LIMIT:
            return jsonify({"status": "RATE_LIMITED"}), 429
        attempts.append(now)
        return f(*args, **kwargs)
    return decorated
```

### Step 3: Apply to login route

```python
@app.route("/login", methods=["GET", "POST"])
@rate_limit
def login():
    # ...
```

**Verification:** 11+ POST requests to `/login` within 5 minutes from same IP returns 429.

---

## Task 5: Multiprocess PID tracking (#12)

**Files:**
- Modify: `canada/app.py`

**Approach:** Track subprocess health alongside automation instances. Periodically clean dead processes.

### Step 1: Add process tracking dict

```python
automation_processes = {}  # user_id -> multiprocessing.Process
```

### Step 2: Store process when starting

In `start_automation`, `start_multi_automation`, `approve_client` — after `process.start()`:
```python
automation_processes[user_id] = process
```

### Step 3: Check process health + cleanup

```python
def _cleanup_stale():
    now = time.time()
    # ... existing cleanup ...

    dead = [uid for uid, p in list(automation_processes.items())
            if not p.is_alive()]
    for uid in dead:
        del automation_processes[uid]
        automation_instances.pop(uid, None)
        state.delete_state(uid)
```

### Step 4: Stop kills process too

In `stop_automation`:
```python
inst = automation_instances.get(user_id)
if inst:
    inst.stop()
    proc = automation_processes.get(user_id)
    if proc and proc.is_alive():
        proc.terminate()
        proc.join(timeout=5)
    # ... cleanup ...
```

**Verification:** Starting automation creates entry in `automation_processes`. Dead processes auto-cleaned via stale cleanup.

---

## Task 6: requirements-lock.txt (#25)

**Files:**
- Create: `requirements-lock.txt`

**Step 1: Generate lock file**

```bash
pip freeze > requirements-lock.txt
```

Since we can't run pip in this env, create manually from current `requirements.txt` with pinned transitive deps.

**Verification:** `pip install -r requirements-lock.txt` produces identical environment.

---

## Task 7: Sentry integration (#26)

**Files:**
- Modify: `requirements.txt`
- Modify: `canada/app.py`
- Add to: `.env.example`

**Approach:** Add Sentry Python SDK for error tracking.

### Step 1: Add to requirements

```
sentry-sdk>=2.0
```

### Step 2: Initialize in app.py

```python
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[FlaskIntegration()],
        traces_sample_rate=0.1,
    )
```

### Step 3: Add to .env.example

```
SENTRY_DSN=https://key@oXXX.ingest.sentry.io/project
```

**Verification:** Unhandled exceptions appear in Sentry dashboard when `SENTRY_DSN` is set. No crash if unset.

---

## Execution Order

```
Task 1 (secret key)     → 1 file, 2 lines, safe
Task 3 (screenshot)     → unauthenticated endpoint is active risk
Task 4 (rate limit)     → brute-force protection
Task 5 (PID tracking)   → resource leak fix
Task 2 (CSRF)           → broader change, touches templates + JS
Task 6 (lock file)      → mechanical, no risk
Task 7 (Sentry)         → additive, no risk
```

Recommended: Tasks 1, 3, 4, 5, 2 in that order (risk-based). Tasks 6, 7 whenever.
