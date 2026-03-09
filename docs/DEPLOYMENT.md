# Deployment Guide

This guide covers deploying Антиспамер 2 to production environments using Docker or manual VPS setup.

---

## Table of Contents

- [Docker Deployment (Recommended)](#docker-deployment-recommended)
- [VPS Deployment (Manual)](#vps-deployment-manual)
- [Database Backup](#database-backup)
- [Updating the Bot](#updating-the-bot)
- [Monitoring and Health Checks](#monitoring-and-health-checks)

---

## Docker Deployment (Recommended)

Docker is the recommended deployment method for production use. It provides isolation, reproducibility, and easy management.

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) installed
- [Docker Compose](https://docs.docker.com/compose/install/) installed (v2+)

### Project Files

**`Dockerfile`:**

```dockerfile
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install dependencies first (for Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .
COPY src/ src/

# Create data directory
RUN mkdir -p data

# Run as non-root user for security
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Start the bot
CMD ["python", "main.py"]
```

**`docker-compose.yml`:**

```yaml
version: "3.8"

services:
  antispam-bot:
    build: .
    container_name: antispam-bot
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      # Persist database outside container
      - ./data:/app/data
      # Persist logs (optional)
      - ./logs:/app/logs
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

**`.dockerignore`:**

```
.git
.env.example
.venv
venv
__pycache__
*.pyc
docs/
tests/
scripts/
*.md
.ruff_cache
.mypy_cache
.pytest_cache
```

### Build and Run

```bash
# Build the Docker image
docker-compose build

# Start the bot in detached mode
docker-compose up -d

# Verify it's running
docker-compose ps
```

Expected output:
```
NAME            IMAGE              COMMAND           STATUS          PORTS
antispam-bot    antispamer-2-...   "python main.py"  Up 5 seconds
```

### Managing the Container

```bash
# View real-time logs
docker-compose logs -f

# View last 100 log lines
docker-compose logs --tail=100

# Stop the bot
docker-compose down

# Restart the bot
docker-compose restart

# Rebuild after code changes
docker-compose build && docker-compose up -d
```

### Environment Variables with Docker

You have two options:

**Option 1: `.env` file (recommended)**
```bash
# Create .env in the project root
cp .env.example .env
# Edit with your values
```

**Option 2: Inline in `docker-compose.yml`**
```yaml
services:
  antispam-bot:
    environment:
      - BOT_TOKEN=your-bot-token
      - OPENROUTER_API_KEY=your-api-key
      - ADMIN_IDS=123456789
      - CHANNEL_ID=-1001234567890
```

---

## VPS Deployment (Manual)

For manual deployment on a VPS (Virtual Private Server) running Linux.

### Step 1: Server Setup

Connect to your server via SSH:

```bash
ssh user@your-server-ip
```

### Step 2: Install Python 3.12+

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev
```

**CentOS/RHEL:**
```bash
sudo dnf install -y python3.12 python3.12-devel
```

Verify:
```bash
python3.12 --version
# Python 3.12.x
```

### Step 3: Create Bot User

Run the bot under a dedicated user for security:

```bash
sudo useradd -m -s /bin/bash antispam
sudo su - antispam
```

### Step 4: Deploy the Code

```bash
# As the antispam user
cd ~
git clone https://github.com/your-username/antispamer-2.git
cd antispamer-2

# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create config
cp .env.example .env
nano .env  # Fill in your values

# Create data directory
mkdir -p data

# Test run
python main.py
# Press Ctrl+C to stop after verifying it works
```

### Step 5: Create systemd Service

Create a systemd service file for automatic startup and process management:

```bash
sudo nano /etc/systemd/system/antispam-bot.service
```

Contents:

```ini
[Unit]
Description=Антиспамер 2 Telegram Bot
After=network.target

[Service]
Type=simple
User=antispam
Group=antispam
WorkingDirectory=/home/antispam/antispamer-2
ExecStart=/home/antispam/antispamer-2/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=antispam-bot

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/antispam/antispamer-2/data
PrivateTmp=true

# Environment
EnvironmentFile=/home/antispam/antispamer-2/.env

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable antispam-bot
sudo systemctl start antispam-bot
```

### Step 6: Verify

```bash
# Check service status
sudo systemctl status antispam-bot

# View logs
sudo journalctl -u antispam-bot -f

# Check if running
sudo systemctl is-active antispam-bot
```

### Managing the systemd Service

```bash
# Start
sudo systemctl start antispam-bot

# Stop
sudo systemctl stop antispam-bot

# Restart
sudo systemctl restart antispam-bot

# View logs (last 100 lines)
sudo journalctl -u antispam-bot -n 100

# View logs (real-time)
sudo journalctl -u antispam-bot -f
```

### Alternative: PM2 (Node.js Process Manager)

If you prefer PM2 (works with Python too):

```bash
# Install PM2 globally
sudo npm install -g pm2

# Start the bot
cd /home/antispam/antispamer-2
pm2 start main.py --name antispam-bot --interpreter ./venv/bin/python

# Auto-start on boot
pm2 startup
pm2 save

# View logs
pm2 logs antispam-bot

# Restart
pm2 restart antispam-bot

# Stop
pm2 stop antispam-bot
```

---

## Database Backup

### Backup Script

The project includes a backup script at `scripts/backup_db.sh`:

```bash
#!/bin/bash
# scripts/backup_db.sh
# Backup the antispam database with timestamp

set -euo pipefail

# Configuration
DB_PATH="${DB_PATH:-data/antispam.db}"
BACKUP_DIR="${BACKUP_DIR:-data/backups}"
MAX_BACKUPS="${MAX_BACKUPS:-30}"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Generate timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/antispam_backup_$TIMESTAMP.db"

# Check if database exists
if [ ! -f "$DB_PATH" ]; then
    echo "ERROR: Database not found at $DB_PATH"
    exit 1
fi

# Create backup using SQLite's .backup command (safe for running database)
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

# Compress the backup
gzip "$BACKUP_FILE"

echo "Backup created: ${BACKUP_FILE}.gz ($(du -h "${BACKUP_FILE}.gz" | cut -f1))"

# Rotate old backups (keep last MAX_BACKUPS)
BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/antispam_backup_*.db.gz 2>/dev/null | wc -l)
if [ "$BACKUP_COUNT" -gt "$MAX_BACKUPS" ]; then
    REMOVE_COUNT=$((BACKUP_COUNT - MAX_BACKUPS))
    ls -1t "$BACKUP_DIR"/antispam_backup_*.db.gz | tail -n "$REMOVE_COUNT" | xargs rm -f
    echo "Rotated $REMOVE_COUNT old backup(s). Keeping last $MAX_BACKUPS."
fi

echo "Backup complete. Total backups: $(ls -1 "$BACKUP_DIR"/antispam_backup_*.db.gz | wc -l)"
```

Make it executable:
```bash
chmod +x scripts/backup_db.sh
```

### Running Backups

**Manual backup:**
```bash
./scripts/backup_db.sh
```

**Automated daily backup (cron):**
```bash
# Edit crontab
crontab -e

# Add daily backup at 3:00 AM
0 3 * * * cd /home/antispam/antispamer-2 && ./scripts/backup_db.sh >> data/backups/backup.log 2>&1
```

**Docker backup:**
```bash
# Backup from Docker volume
docker-compose exec antispam-bot bash -c "./scripts/backup_db.sh"

# Or copy the database file directly
docker cp antispam-bot:/app/data/antispam.db ./backup_$(date +%Y%m%d).db
```

### Restoring from Backup

```bash
# Stop the bot first
sudo systemctl stop antispam-bot
# or: docker-compose down

# Decompress backup
gunzip data/backups/antispam_backup_20260309_030000.db.gz

# Replace current database
cp data/antispam.db data/antispam.db.old  # safety copy
cp data/backups/antispam_backup_20260309_030000.db data/antispam.db

# Restart the bot
sudo systemctl start antispam-bot
# or: docker-compose up -d
```

---

## Updating the Bot

### Docker Update

```bash
cd /path/to/antispamer-2

# Pull latest code
git pull origin main

# Rebuild and restart
docker-compose build
docker-compose up -d

# Verify
docker-compose logs --tail=20
```

### Manual (VPS) Update

```bash
# Switch to bot user
sudo su - antispam
cd antispamer-2

# Stop the bot
sudo systemctl stop antispam-bot

# Backup database
./scripts/backup_db.sh

# Pull latest code
git pull origin main

# Activate venv and update dependencies
source venv/bin/activate
pip install -r requirements.txt

# Start the bot
sudo systemctl start antispam-bot

# Verify
sudo systemctl status antispam-bot
sudo journalctl -u antispam-bot --since "1 minute ago"
```

### Zero-Downtime Update (Docker)

For updates with minimal downtime:

```bash
# Build new image without stopping the old container
docker-compose build

# Restart with the new image (brief downtime, typically < 5 seconds)
docker-compose up -d

# The bot reconnects to Telegram automatically
```

---

## Monitoring and Health Checks

### Log Monitoring

**Structured logs** with structlog are output as JSON for easy parsing:

```bash
# View logs in real-time
docker-compose logs -f
# or
sudo journalctl -u antispam-bot -f

# Search for errors
docker-compose logs | grep "error"
# or
sudo journalctl -u antispam-bot --since "1 hour ago" | grep "error"
```

### Key Log Events to Monitor

| Log Event | Level | Meaning |
|-----------|-------|---------|
| `bot_started` | INFO | Bot successfully connected to Telegram |
| `processing_message` | INFO | Message received and being processed |
| `spam_detected` | WARNING | Spam detected, message deleted, user banned |
| `api_timeout` | WARNING | OpenRouter API request timed out |
| `api_error` | ERROR | OpenRouter API returned an error |
| `rate_limit_exceeded` | WARNING | Local rate limit reached, message allowed through |
| `database_error` | ERROR | SQLite operation failed |
| `ban_failed` | ERROR | Failed to ban user (permission issue) |
| `delete_failed` | ERROR | Failed to delete message (permission issue) |

### Health Check Indicators

**The bot is healthy when:**
- Process is running (`systemctl is-active antispam-bot`)
- Recent log entries show `processing_message` events
- `/status` command responds correctly
- Error rate in `/stats` is below 5%

**The bot needs attention when:**
- Process is not running or keeps restarting
- Logs show repeated `api_error` events
- No `processing_message` events for an extended period (channel may be inactive, or bot may not be receiving messages)
- Error rate exceeds 5%

### External Monitoring (Optional)

For production deployments, consider adding external monitoring:

**Uptime monitoring:**
- Use a cron job or external service to periodically send a `/status` command and check for a response
- Or implement a simple HTTP health endpoint

**Alert example with cron:**

```bash
# Check bot status every 5 minutes
*/5 * * * * systemctl is-active --quiet antispam-bot || echo "Antispam bot is down!" | mail -s "ALERT: Bot Down" admin@example.com
```

**Process monitoring with systemd:**

The systemd service is configured with `Restart=always` and `RestartSec=10`, which means:
- If the bot crashes, systemd will automatically restart it after 10 seconds
- This handles transient errors (network issues, temporary API outages) automatically
- Check for restart loops: `sudo systemctl status antispam-bot` shows restart count

### Resource Usage

Антиспамер 2 is lightweight:

| Resource | Typical Usage |
|----------|--------------|
| RAM | 50–100 MB |
| CPU | < 1% (idle), brief spikes during AI calls |
| Disk | Database grows ~1 MB per 1000 messages |
| Network | ~1–5 KB per spam check (API call) |

**Minimum VPS requirements:**
- 1 vCPU
- 512 MB RAM
- 1 GB disk space
- Any Linux distribution with Python 3.12+
