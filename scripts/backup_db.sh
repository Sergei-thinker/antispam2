#!/usr/bin/env bash
# =============================================================================
# backup_db.sh - Database backup script for Telegram Anti-Spam Bot v2
# Usage: bash scripts/backup_db.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

DB_PATH="$PROJECT_DIR/data/antispam.db"
BACKUP_DIR="$PROJECT_DIR/backups"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="$BACKUP_DIR/antispam_${TIMESTAMP}.db"

echo "=== Database Backup ==="

# Check if database exists
if [ ! -f "$DB_PATH" ]; then
    echo "ERROR: Database not found at $DB_PATH"
    exit 1
fi

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Copy database with timestamp
cp "$DB_PATH" "$BACKUP_FILE"

echo "Backup created: $BACKUP_FILE"
echo "Size: $(du -h "$BACKUP_FILE" | cut -f1)"

# Clean up old backups (keep last 10)
BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/antispam_*.db 2>/dev/null | wc -l)
if [ "$BACKUP_COUNT" -gt 10 ]; then
    echo ""
    echo "Cleaning old backups (keeping last 10)..."
    ls -1t "$BACKUP_DIR"/antispam_*.db | tail -n +11 | xargs rm -f
    echo "Removed $((BACKUP_COUNT - 10)) old backup(s)."
fi

echo ""
echo "=== Backup complete ==="
