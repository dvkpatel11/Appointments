#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# VISA_CTRL — Oracle Cloud Free Tier VM Initialization
#
# Run this ONCE on a fresh Oracle Cloud Ampere A1 instance (Ubuntu 24.04).
# It installs Docker, clones the repo, and starts the container as a
# systemd service so it survives reboots.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/YOUR_USER/UsVisaAppointment/main/scripts/init-oracle-vm.sh | bash
#   # ... or copy the script to the VM and run it:
#   sudo bash init-oracle-vm.sh
#
# Prerequisites:
#   - Oracle Cloud Free Tier VM (Ampere A1, Ubuntu 24.04 recommended)
#   - Port 8080 open in the security list (OCI Console → Networking → Security Lists)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[-]${NC} $*" >&2; }

# ── Check root ───────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  err "Run as root: sudo bash init-oracle-vm.sh"
  exit 1
fi

# ── 1. System packages ───────────────────────────────────────────────────────
log "Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
  ca-certificates curl gnupg lsb-release ufw

# ── 2. Install Docker ────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  log "Installing Docker..."
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
else
  log "Docker already installed"
fi

# ── 3. Firewall (allow 8080) ────────────────────────────────────────────────
log "Configuring firewall..."
ufw allow 22/tcp comment 'SSH'
ufw allow 8080/tcp comment 'VisaCtrl'
ufw --force enable
log "UFW enabled — ports 22 (SSH) and 8080 (VisaCtrl) open"

# ── 4. Clone repo ────────────────────────────────────────────────────────────
REPO_DIR="/opt/visactrl"
if [[ ! -d "$REPO_DIR" ]]; then
  log "Cloning repository to $REPO_DIR..."
  git clone https://github.com/YOUR_USER/UsVisaAppointment.git "$REPO_DIR"
else
  log "Repository already exists at $REPO_DIR — pulling latest..."
  cd "$REPO_DIR" && git pull
fi

cd "$REPO_DIR"

# ── 5. Create data and screenshots directories ────────────────────────────────
mkdir -p /opt/visactrl/data /opt/visactrl/screenshots /opt/visactrl/status /opt/visactrl/logs

# ── 6. Prompt for env vars ──────────────────────────────────────────────────
ENV_FILE="/opt/visactrl/data/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  log "Creating .env file — you'll be prompted for each value."
  echo ""

  read -rp "ADMIN_PASSWORD (admin dashboard login): " ADMIN_PW
  SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

  cat > "$ENV_FILE" <<ENVEOF
# ── Flask ─────────────────────────────────────────────────────────────────────
SECRET_KEY=${SECRET_KEY}
ADMIN_PASSWORD=${ADMIN_PW}
FLASK_DEBUG=false
PORT=8080
DB_PATH=/app/data/visactrl.db

# ── Email Notifications (SMTP) ────────────────────────────────────────────────
# Leave blank to skip email notifications
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
RESEND_API_KEY=

# ── Telegram Notifications ────────────────────────────────────────────────────
# Leave blank to skip Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# ── SMS Notifications (Twilio) ────────────────────────────────────────────────
# Leave blank to skip SMS
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=

# ── Sentry (optional error tracking) ──────────────────────────────────────────
SENTRY_DSN=
ENVEOF

  log ".env created at $ENV_FILE"
  warn "IMPORTANT: Edit the file to add SMTP, Telegram, Twilio, or Sentry credentials."
  warn "  nano $ENV_FILE"
else
  log ".env already exists — using existing configuration"
fi

# ── 7. Build and run container ───────────────────────────────────────────────
log "Building Docker image (this downloads Chromium — may take a few minutes)..."
docker build -t visactrl:latest .

log "Starting container..."
docker stop visactrl 2>/dev/null || true
docker rm visactrl 2>/dev/null || true

docker run -d \
  --name visactrl \
  --restart unless-stopped \
  -p 8080:8080 \
  -v /opt/visactrl/data:/app/data \
  -v /opt/visactrl/data/.env:/app/canada/.env:ro \
  -v /opt/visactrl/screenshots:/app/screenshots \
  -v /opt/visactrl/status:/app/canada/status \
  -v /opt/visactrl/logs:/app/canada/logs \
  visactrl:latest

# ── 8. Create systemd service for Docker auto-start ──────────────────────────
log "Ensuring Docker starts on boot..."
systemctl enable docker

# ── 9. Set up automatic updates with watchtower ─────────────────────────────
log "Setting up watchtower for automatic container updates..."
docker run -d \
  --name watchtower \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower \
  --cleanup --interval 86400 visactrl 2>/dev/null || warn "watchtower already running (or failed)"

# ── 10. Status ──────────────────────────────────────────────────────────────
echo ""
log "============================================"
log "VisaCtrl deployment complete!"
log ""
log "  Container status:"
docker ps --filter name=visactrl --format "  {{.Names}}  {{.Status}}  {{.Ports}}"
log ""
PUBLIC_IP=$(curl -fsSL http://checkip.amazonaws.com 2>/dev/null || echo "YOUR_VM_IP")
log "  Access your dashboard at:"
log "    http://${PUBLIC_IP}:8080"
log ""
log "  Useful commands:"
log "    View logs:           docker logs -f visactrl"
log "    Restart:             docker restart visactrl"
log "    Stop:                docker stop visactrl"
log "    Update:              cd /opt/visactrl && git pull && docker build -t visactrl:latest . && docker restart visactrl"
log ""
warn "  Don't forget to:"
warn "    1. Open port 8080 in Oracle Cloud security list (Networking → Security Lists)"
warn "    2. Edit .env with your SMTP/Telegram/Twilio keys: nano /opt/visactrl/.env"
warn "    3. Restart container after editing .env: docker restart visactrl"
log "============================================"
