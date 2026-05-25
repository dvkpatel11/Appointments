#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# VISA_CTRL — Google Cloud Deployment Script
#
# Prerequisites:
#   - gcloud CLI installed and authenticated
#   - PROJECT_ID exported or passed as $1
#
# Usage:
#   ./scripts/deploy-gcp.sh <PROJECT_ID> [--dry-run]
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

PROJECT_ID="${1:?Usage: $0 <PROJECT_ID> [--dry-run]}"
DRY_RUN="${2:-}"
REGION="northamerica-northeast1"
SERVICE_NAME="visa-ctrl"
REPO="visa-ctrl"
LOCATION="${REGION}"

# ── Colors ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[-]${NC} $*" >&2; }

# ── Step 0: Validate ─────────────────────────────────────────────────────────
command -v gcloud >/dev/null 2>&1 || { err "gcloud CLI not found. Install: https://cloud.google.com/sdk"; exit 1; }
gcloud config get-value project >/dev/null 2>&1 || { err "Not authenticated. Run: gcloud auth login"; exit 1; }

# ── Step 1: Enable APIs ──────────────────────────────────────────────────────
log "Enabling required APIs..."
APIS="cloudbuild.googleapis.com run.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com"
for api in $APIS; do
  gcloud services enable "$api" --project="$PROJECT_ID"
done

# ── Step 2: Create Artifact Registry repository ──────────────────────────────
log "Creating Artifact Registry repository..."
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$LOCATION" \
  --description="VisaCtrl container images" \
  --project="$PROJECT_ID" 2>/dev/null || warn "Repository already exists"

# ── Step 3: Create Secrets (skip if exists) ──────────────────────────────────
SECRETS=("SECRET_KEY:visa-ctrl-secret-key" "ADMIN_PASSWORD:visa-ctrl-admin-password" "SMTP_USER:visa-ctrl-smtp-user" "SMTP_PASSWORD:visa-ctrl-smtp-password" "RESEND_API_KEY:visa-ctrl-resend-key" "TELEGRAM_BOT_TOKEN:visa-ctrl-telegram-token" "TELEGRAM_CHAT_ID:visa-ctrl-telegram-chat")

for pair in "${SECRETS[@]}"; do
  IFS=: read -r env_name secret_name <<< "$pair"
  log "Checking secret: $secret_name"
  if ! gcloud secrets describe "$secret_name" --project="$PROJECT_ID" >/dev/null 2>&1; then
    warn "Secret '$secret_name' does not exist. Create it with:"
    warn "  echo -n 'YOUR_VALUE' | gcloud secrets create $secret_name --data-file=- --project=$PROJECT_ID"
  fi
done

# ── Step 4: Grant Cloud Build access to Secret Manager ───────────────────────
log "Granting Cloud Build SA access to Secret Manager..."
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" 2>/dev/null || warn "IAM binding may already exist"

# ── Step 5: Build and Deploy ─────────────────────────────────────────────────
log "Building and deploying to Cloud Run..."
if [[ "$DRY_RUN" == "--dry-run" ]]; then
  warn "DRY RUN — would execute:"
  warn "  gcloud builds submit --config cloudbuild.yaml --project=$PROJECT_ID"
  exit 0
fi

gcloud builds submit \
  --config cloudbuild.yaml \
  --project="$PROJECT_ID" \
  --substitutions=_REGION="$REGION",_SERVICE="$SERVICE_NAME",_REPO="$REPO"

log "Deployed to Cloud Run: https://${SERVICE_NAME}-${PROJECT_NUMBER}.${REGION}.run.app"
