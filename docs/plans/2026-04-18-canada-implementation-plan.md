# Canada Production Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use godmode:task-runner to implement this plan task-by-task.

**Goal:** Make canada/ project production-ready with Resend email notifications, Telegram bot, and Render deployment config.

**Architecture:** Flask app runs as web service on Render. Automation runs in daemon threads per client. Notifications triggered on date-found events.

**Tech Stack:** Flask, Playwright, Resend (email), python-telegram-bot, Waitress, Render.com

---

## Pre-requisite: Create branch

```bash
git checkout -b production/canada-ready
```

---

## Task 1: Update requirements.txt with Resend

**Files:**
- Modify: `requirements.txt`

**Step 1: Add Resend to requirements**

Add to end of `requirements.txt`:
```
resend>=0.1.0
python-telegram-bot>=20.0
```

**Step 2: Verify install**

```bash
pip install resend python-telegram-bot
```

**Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add resend and telegram-bot dependencies"
```

---

## Task 2: Implement Resend email notifications

**Files:**
- Modify: `canada/main.py` (add send_email_notification implementation)

**Step 1: Add imports at top of canada/main.py**

After existing imports, add:

```python
import resend
```

**Step 2: Replace send_email_notification method**

Find the existing stub method (~line 456) and replace:

```python
def send_email_notification(self, message):
    if not self.notification_email:
        return
    
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        self._log("RESEND_API_KEY not set, skipping email", "warning")
        return
    
    try:
        resend.api_key = api_key
        response = resend.Emails.send({
            "from": "Visa Alerts <onboarding@resend.dev>",
            "to": [self.notification_email],
            "subject": f"VISA UPDATE: {message[:50]}...",
            "text": message,
        })
        self._log(f"Email sent to {self.notification_email}")
    except Exception as e:
        self._log(f"Email send failed: {e}", "error")
```

**Step 3: Test import**

```bash
python -c "from main import VisaAutomation; print('OK')"
```

**Step 4: Commit**

```bash
git add canada/main.py
git commit -m "feat: add Resend email notifications"
```

---

## Task 3: Implement Telegram notifications

**Files:**
- Modify: `canada/main.py` (add Telegram bot support)

**Step 1: Add Telegram import and config**

After `import resend`, add:

```python
import requests
```

**Step 2: Add Telegram method**

After `send_email_notification`, add:

```python
def send_telegram_notification(self, message):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        self._log("Telegram not configured, skipping", "debug")
        return
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {"chat_id": chat_id, "text": f"🇨🇦 {message}"}
    
    try:
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200:
            self._log("Telegram notification sent")
        else:
            self._log(f"Telegram failed: {response.status_code}", "warning")
    except Exception as e:
        self._log(f"Telegram error: {e}", "error")
```

**Step 3: Update run_check to call Telegram**

Find the section in `run_check` around line 380 where it checks `new_date < current_date`. Replace that block:

```python
if self.new_date and self.current_date and self.new_date < self.current_date:
    msg = f"Earlier date found at {location}: {self.new_date.strftime('%Y-%m-%d')}"
    if self.notification_email:
        self.send_email_notification(msg)
    self.send_telegram_notification(msg)
```

**Step 4: Verify syntax**

```bash
python -m py_compile canada/main.py
```

**Step 5: Commit**

```bash
git add canada/main.py
git commit -m "feat: add Telegram bot notifications"
```

---

## Task 4: Create Render deployment config

**Files:**
- Create: `render.yaml`

**Step 1: Create render.yaml in project root**

```yaml
services:
  - type: web
    name: visa-ctrl-canada
    region: Toronto
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: cd canada && waitress-serve --port=$PORT --host=0.0.0.0 app:app
    envVars:
      - key: FLASK_DEBUG
        value: "false"
      - key: PORT
        value: "8080"
      - key: SECRET_KEY
        sync: false
      - key: ADMIN_PASSWORD
        sync: false
      - key: RESEND_API_KEY
        sync: false
      - key: TELEGRAM_BOT_TOKEN
        sync: false
      - key: TELEGRAM_CHAT_ID
        sync: false
```

**Step 2: Commit**

```bash
git add render.yaml
git commit -m "feat: add Render deployment config"
```

---

## Task 5: Update .env.example

**Files:**
- Create: `canada/.env.example`

**Step 1: Create canada/.env.example**

```
# Required
SECRET_KEY=your-secret-key-here
ADMIN_PASSWORD=your-admin-password-here

# Optional - Email notifications via Resend
RESEND_API_KEY=re_123456789

# Optional - Telegram bot notifications
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
```

**Step 2: Commit**

```bash
git add canada/.env.example
git commit -m "docs: add env example for canada"
```

---

## Task 6: Fix Dockerfile for canada/ folder

**Files:**
- Modify: `Dockerfile`

**Step 1: Update WORKDIR**

The Dockerfile already sets `WORKDIR /app/canada` at line 37. Verify it matches.

**Step 2: Add requirements install for Resend**

Since we added to requirements.txt, the existing Dockerfile should work. Verify line 27-31 installs all deps.

**Step 3: Commit**

```bash
git add Dockerfile
git commit -m "chore: verify Dockerfile ready for canada deployment"
```

---

## Task 7: Final verification

**Step 1: Test app imports**

```bash
cd canada
python -c "from app import app; print('app.py OK')"
python -c "from main import VisaAutomation; print('main.py OK')"
```

**Step 2: Verify all env vars documented**

```bash
grep -r "os.environ.get" canada/
# Should show: SECRET_KEY, ADMIN_PASSWORD, RESEND_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
```

**Step 3: Run flake8/lint if available**

```bash
pip install flake8
flake8 canada/app.py canada/main.py --max-line-length=120
```

**Step 4: Commit final**

```bash
git add -A
git commit -m "chore: production-ready verification"
```

---

## Execution Options

**Plan complete. Two execution options:**

1. **Delegated Execution (this session)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

2. **Separate Session** - Open a new session with task-runner, batch execution with checkpoints

Which approach?