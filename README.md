# Антиспамер 2

**AI-powered Telegram anti-spam bot for channel comments**

Антиспамер 2 is a Telegram bot that monitors comments in your Telegram channel's discussion group and uses AI (via OpenRouter) to intelligently detect and remove spam. When spam is detected, the bot automatically deletes the message and bans the offending user, keeping your community clean without manual moderation.

---

## Features

- **AI-Powered Spam Detection** — Uses OpenRouter API to access state-of-the-art language models (Claude, GPT, etc.) for highly accurate spam classification
- **Auto-Delete + Ban** — Automatically removes detected spam messages and bans the sender from the discussion group
- **Admin Commands** — Full set of admin commands for bot management, statistics, and moderation
- **Whitelist System** — Protect trusted users from false positive detections
- **Statistics Dashboard** — Track spam detection rates, false positives, and bot performance
- **Few-Shot Learning** — Maintains a database of confirmed spam examples to improve AI accuracy over time
- **Profile Analysis** — Analyzes user profiles (account age, photo, bio) as additional spam signals
- **Rate Limiting** — Built-in rate limiter to stay within API quotas and control costs
- **Fail-Open Strategy** — If AI is unavailable, messages are allowed through (no false bans during outages)
- **Structured Logging** — Full audit trail with structlog for debugging and monitoring

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/your-username/antispamer-2.git
cd antispamer-2
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your values (see Configuration below)
```

### 3. Run the bot

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows
pip install -r requirements.txt
python main.py
```

---

## Configuration

All configuration is done via environment variables (`.env` file).

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BOT_TOKEN` | **Yes** | — | Telegram Bot API token from [@BotFather](https://t.me/BotFather) |
| `OPENROUTER_API_KEY` | **Yes** | — | API key from [openrouter.ai](https://openrouter.ai) |
| `ADMIN_IDS` | **Yes** | — | Comma-separated list of Telegram user IDs with admin access (e.g., `123456789,987654321`) |
| `CHANNEL_ID` | **Yes** | — | Telegram channel ID (e.g., `-1001234567890`) |
| `AI_MODEL` | No | `anthropic/claude-sonnet-4` | OpenRouter model identifier for spam classification |
| `SPAM_CONFIDENCE_THRESHOLD` | No | `0.7` | Minimum confidence score (0.0–1.0) to classify a message as spam |
| `MAX_AI_CALLS_PER_MINUTE` | No | `20` | Maximum number of AI API calls per minute (rate limiting) |
| `OPENROUTER_TIMEOUT` | No | `30` | Timeout in seconds for OpenRouter API requests |
| `DATABASE_PATH` | No | `data/antispam.db` | Path to the SQLite database file |
| `LOG_LEVEL` | No | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## Bot Commands

All commands are restricted to admin users (configured via `ADMIN_IDS`).

| Command | Description |
|---------|-------------|
| `/start` | Start the bot and display welcome message |
| `/help` | Show all available commands with descriptions |
| `/stats` | Display spam detection statistics (total messages, spam caught, false positives, ban count) |
| `/status` | Show bot operational status (uptime, AI model, rate limit usage, database size) |
| `/whitelist <user_id>` | Add a user to the whitelist (their messages will never be checked for spam) |
| `/unban <user_id>` | Unban a previously banned user and remove them from the ban list |
| `/recent` | Show the most recent spam detections with message previews and confidence scores |

---

## Project Structure

```
antispamer-2/
├── main.py                     # Application entry point
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variables template
├── .env                        # Local environment config (not in git)
├── src/
│   ├── __init__.py
│   ├── bot.py                  # AntispamBot — main bot orchestration
│   ├── config.py               # Settings via pydantic-settings
│   ├── spam_detector.py        # SpamDetector — OpenRouter AI integration
│   ├── database.py             # Database — SQLite operations via aiosqlite
│   ├── profile_analyzer.py     # ProfileAnalyzer — user profile fetching & analysis
│   ├── admin_commands.py       # AdminCommands — admin command handlers
│   ├── middleware.py           # DependencyMiddleware — DI via aiogram middleware
│   └── models.py               # Pydantic models for internal data structures
├── data/
│   └── antispam.db             # SQLite database (auto-created)
├── scripts/
│   └── backup_db.sh            # Database backup script
├── tests/
│   ├── __init__.py
│   ├── test_spam_detector.py   # SpamDetector unit tests
│   ├── test_database.py        # Database operation tests
│   ├── test_profile_analyzer.py# ProfileAnalyzer tests
│   ├── test_admin_commands.py  # Admin command handler tests
│   └── conftest.py             # Shared pytest fixtures
├── docs/
│   ├── ARCHITECTURE.md         # System architecture and design
│   ├── SETUP.md                # Detailed setup guide
│   ├── API.md                  # OpenRouter API documentation
│   ├── ADMIN_GUIDE.md          # Admin usage guide (Russian)
│   ├── DEVELOPMENT.md          # Developer guide
│   └── DEPLOYMENT.md           # Deployment guide
├── CLAUDE.md                   # Instructions for Claude Code
├── DEVELOPMENT_LOG.md          # Development changelog
└── README.md                   # This file
```

---

## Technology Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| [Python](https://python.org) | 3.12+ | Runtime |
| [aiogram](https://aiogram.dev) | 3.x | Async Telegram Bot framework |
| [httpx](https://www.python-httpx.org) | Latest | Async HTTP client for OpenRouter API |
| [aiosqlite](https://github.com/omnilib/aiosqlite) | Latest | Async SQLite database driver |
| [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | Latest | Configuration management via environment variables |
| [structlog](https://www.structlog.org) | Latest | Structured logging |
| [pytest](https://pytest.org) | Latest | Testing framework |
| [ruff](https://docs.astral.sh/ruff/) | Latest | Linting and formatting |

---

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | System design, component diagrams, database schema |
| [Setup Guide](docs/SETUP.md) | Step-by-step installation and configuration |
| [API Reference](docs/API.md) | OpenRouter API integration details |
| [Admin Guide](docs/ADMIN_GUIDE.md) | Bot commands and moderation guide (Russian) |
| [Development](docs/DEVELOPMENT.md) | Developer guide, testing, code style |
| [Deployment](docs/DEPLOYMENT.md) | Docker, VPS, and production deployment |

---

## License

This project is proprietary software. All rights reserved.

---

## Support

For issues and questions, contact the project administrator or open an issue in the repository.
