#!/usr/bin/env bash
# =============================================================================
# deploy.sh - Deploy script for Telegram Anti-Spam Bot v2
# Usage: bash scripts/deploy.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== Telegram Anti-Spam Bot v2 - Deploy ==="
echo "Project directory: $PROJECT_DIR"
echo ""

# Step 1: Pull latest code
echo "[1/3] Pulling latest code..."
git pull origin main
echo ""

# Step 2: Install/update dependencies
echo "[2/3] Installing dependencies..."
if [ -f "docker-compose.yml" ]; then
    echo "Docker detected, rebuilding image..."
    docker compose build --no-cache
else
    echo "Installing Python dependencies..."
    pip install -r requirements.txt
fi
echo ""

# Step 3: Restart the bot
echo "[3/3] Restarting the bot..."
if [ -f "docker-compose.yml" ] && command -v docker &> /dev/null; then
    docker compose down
    docker compose up -d
    echo "Bot restarted via docker-compose."
elif command -v pm2 &> /dev/null; then
    pm2 restart antispam-bot 2>/dev/null || pm2 start main.py --name antispam-bot --interpreter python3
    echo "Bot restarted via PM2."
else
    echo "WARNING: No process manager found (docker/pm2)."
    echo "Start manually: python main.py"
    exit 1
fi

echo ""
echo "=== Deploy complete ==="
