# Deployment Guide

## Overview

VisaCtrl is a Flask + Playwright application deployed as a container. It supports two hosting platforms:

- **Google Cloud Run** (recommended for production)
- **Render.com** (simpler setup, good for personal use)

## Prerequisites

- Python 3.12+
- Docker
- `gcloud` CLI (for GCP deployment)
- Playwright installed (`playwright install --with-deps chromium`)

## Environment Variables

All configuration is via environment variables. Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Flask session signing key. Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_PASSWORD` | Yes | Admin dashboard password |
| `SMTP_HOST` | No | SMTP server hostname (default: `smtp.gmail.com`) |
| `SMTP_PORT` | No | SMTP port (default: `587`) |
| `SMTP_USER` | No | SMTP username for email notifications |
| `SMTP_PASSWORD` | No | SMTP password (use App Password for Gmail) |
| `RESEND_API_KEY` | No | Resend API key for alternative email delivery |
| `TELEGRAM_BOT_TOKEN` | No | Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | No | Telegram chat ID for notifications |
| `FLASK_DEBUG` | No | Set to `true` for local development only |
| `PORT` | No | Port to listen on (default: `8080` for cloud, `5000` local) |

## Local Development

```bash
make install
make playwright
make run
```

Or manually:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install --with-deps chromium
cd canada && FLASK_DEBUG=true python -m flask --app app run --port 5000
```

## Docker

```bash
make docker-build
make docker-run
```

## Deploy to Google Cloud Run

### One-time Setup

```bash
# Authenticate
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Run the deployment script (creates APIs, secrets, and deploys)
./scripts/deploy-gcp.sh YOUR_PROJECT_ID
```

### Manual Secret Creation

```bash
echo -n "your-secret-key"     | gcloud secrets create visa-ctrl-secret-key     --data-file=-
echo -n "your-admin-password" | gcloud secrets create visa-ctrl-admin-password  --data-file=-
echo -n "you@gmail.com"       | gcloud secrets create visa-ctrl-smtp-user       --data-file=-
echo -n "your-app-password"   | gcloud secrets create visa-ctrl-smtp-password   --data-file=-
```

### Trigger Deploy

```bash
make deploy-gcp
# Or manually:
gcloud builds submit --config cloudbuild.yaml
```

### After Deploy

1. Set the Telegram webhook: visit `https://YOUR_SERVICE_URL/set_telegram_webhook`
2. Visit the service URL and log in with `ADMIN_PASSWORD`
3. Generate client links from the admin dashboard

## Deploy to Render

1. Connect your GitHub repo to Render
2. Create a new **Web Service**
3. Use the included `render.yaml` blueprint
4. Fill in environment variables in the Render dashboard
5. Deploy

## Health Checks

- Cloud Run: Docker `HEALTHCHECK` instruction + `/health` endpoint
- Render: Built-in health monitoring from the web service config
- External: Point UptimeRobot or similar at `https://YOUR_URL/health`

## Backup

State files (client tokens, settings, status) are stored on the ephemeral filesystem. Back them up regularly:

```bash
make backup
```

Or add to crontab:

```bash
0 */6 * * * cd /path/to/UsVisaAppointment && ./scripts/backup.sh /path/to/backups
```

## Scaling Notes

- Cloud Run: `--memory=2Gi` required for Chromium. `--min-instances=0` to save costs.
- Playwright browser state is lost on cold start — login happens fresh each cycle.
- Each user runs in a separate subprocess. `--max-instances` limits concurrent users.
