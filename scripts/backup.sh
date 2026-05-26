#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# VISA_CTRL — State Backup Script
#
# Backs up JSON state files (client tokens, settings, status) to a timestamped
# archive. Designed for cron or manual execution.
#
# Usage:
#   ./scripts/backup.sh [--output-dir /path/to/backups]
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

BACKUP_DIR="${1:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ARCHIVE_NAME="visactrl_state_${TIMESTAMP}.tar.gz"

STATE_FILES=(
  "canada/canada/client_tokens.json"
  "canada/settings.json"
)

STATE_DIRS=(
  "canada/status"
)

# ── Validate ─────────────────────────────────────────────────────────────────
if [ ! -d "canada" ]; then
  echo "Error: Must run from project root (canada/ directory not found)"
  exit 1
fi

mkdir -p "$BACKUP_DIR"

# ── Collect files that exist ─────────────────────────────────────────────────
FILES_TO_BACKUP=()

for f in "${STATE_FILES[@]}"; do
  if [ -f "$f" ]; then
    FILES_TO_BACKUP+=("$f")
  fi
done

for d in "${STATE_DIRS[@]}"; do
  if [ -d "$d" ]; then
    FILES_TO_BACKUP+=("$d")
  fi
done

if [ ${#FILES_TO_BACKUP[@]} -eq 0 ]; then
  echo "No state files found to backup."
  exit 0
fi

# ── Create archive ───────────────────────────────────────────────────────────
tar -czf "${BACKUP_DIR}/${ARCHIVE_NAME}" "${FILES_TO_BACKUP[@]}"
echo "Backup created: ${BACKUP_DIR}/${ARCHIVE_NAME}"

# ── Cleanup old backups (keep last 30 days) ───────────────────────────────────
find "$BACKUP_DIR" -name "visactrl_state_*.tar.gz" -mtime +30 -delete 2>/dev/null || true
echo "Cleaned backups older than 30 days."
