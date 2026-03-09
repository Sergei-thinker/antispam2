# Claude Code Instructions for Антиспамер 2

## Project Description

Антиспамер 2 is an AI-powered Telegram bot that monitors comments in a Telegram channel's discussion group. It uses the OpenRouter API to access language models (Claude, GPT, etc.) for spam detection. When spam is detected with sufficient confidence, the bot automatically deletes the message and bans the user. Admins receive notifications with inline unban buttons for false positive correction.

## Technology Stack

- **Python 3.12+** — Runtime
- **aiogram 3.x** — Async Telegram Bot framework
- **httpx** — Async HTTP client for OpenRouter API calls
- **aiosqlite** — Async SQLite database driver
- **pydantic-settings** — Configuration management via environment variables and `.env`
- **structlog** — Structured logging throughout the application
- **pytest** — Testing framework with pytest-asyncio for async tests
- **ruff** — Linting and code formatting

## Key Files and Their Purposes

| File | Purpose |
|------|---------|
| `main.py` | Application entry point. Initializes all components and starts the bot |
| `src/config.py` | `Settings` class using pydantic-settings `BaseSettings`. Loads all config from `.env` file |
| `src/bot.py` | `AntispamBot` class. Main orchestration: registers handlers, runs the message processing pipeline |
| `src/spam_detector.py` | `SpamDetector` class. Builds AI prompts, calls OpenRouter API, parses responses. Includes rate limiting |
| `src/database.py` | `Database` class. All SQLite operations via aiosqlite: messages, bans, whitelist, spam examples, stats |
| `src/profile_analyzer.py` | `ProfileAnalyzer` class. Fetches Telegram user profiles and photos for additional spam signals |
| `src/admin_commands.py` | `AdminCommands` class. Handlers for /start, /help, /stats, /status, /whitelist, /unban, /recent |
| `src/middleware.py` | `DependencyMiddleware` class. Injects Database, SpamDetector, Settings into aiogram handlers |
| `src/models.py` | Pydantic data models: `SpamVerdict`, `ProfileInfo`, and other internal structures |
| `tests/conftest.py` | Shared pytest fixtures: test settings, in-memory database, mocked detector |

## How to Run

```bash
# Activate virtual environment first
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Run the bot
python main.py
```

Requires a configured `.env` file with at minimum: `BOT_TOKEN`, `OPENROUTER_API_KEY`, `ADMIN_IDS`, `CHANNEL_ID`.

## How to Test

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/test_spam_detector.py -v
```

## How to Lint / Format

```bash
# Check linting
ruff check src/ tests/

# Auto-fix
ruff check src/ tests/ --fix

# Format
ruff format src/ tests/
```

## Environment Configuration

The `.env` file is required. Key variables:

```env
# Required
BOT_TOKEN=...                           # Telegram bot token from @BotFather
OPENROUTER_API_KEY=...                  # API key from openrouter.ai
ADMIN_IDS=123456789,987654321           # Comma-separated admin Telegram IDs
CHANNEL_ID=-1001234567890               # Telegram channel ID

# Optional (with defaults)
AI_MODEL=anthropic/claude-sonnet-4       # OpenRouter model ID
SPAM_CONFIDENCE_THRESHOLD=0.7           # Minimum confidence to classify as spam (0.0-1.0)
MAX_AI_CALLS_PER_MINUTE=20              # Rate limit for AI API calls
OPENROUTER_TIMEOUT=30                   # API timeout in seconds
DATABASE_PATH=data/antispam.db          # SQLite database path
LOG_LEVEL=INFO                          # DEBUG, INFO, WARNING, ERROR
```

## Important Patterns

### Configuration (pydantic-settings)
All settings are loaded via `pydantic-settings` `BaseSettings` class in `src/config.py`. Settings are validated at startup — if a required variable is missing or invalid, the app fails fast with a clear error.

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    BOT_TOKEN: str
    OPENROUTER_API_KEY: str
    ADMIN_IDS: list[int]
    CHANNEL_ID: int
    AI_MODEL: str = "anthropic/claude-sonnet-4"
    # ...

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
```

### Dependency Injection (aiogram middleware)
Dependencies are injected into handlers via `DependencyMiddleware`, not via global state or imports. This makes testing easy — just pass mock objects.

```python
class DependencyMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        data["db"] = self.db
        data["detector"] = self.detector
        data["settings"] = self.settings
        return await handler(event, data)
```

### Structured Logging (structlog)
All logging uses structlog with bound context. Always bind relevant IDs (user_id, message_id) for traceability.

```python
import structlog
log = structlog.get_logger()
log.bind(user_id=123).info("processing_message", text_length=42)
```

### Error Handling (fail-open)
The bot uses a fail-open strategy: if AI is unavailable, messages are ALLOWED through. Never block users when the detection system is down. This applies to: API errors, timeouts, rate limits, JSON parse errors.

### Database
SQLite database at `data/antispam.db` (configurable). Uses aiosqlite for async operations. Tables: `messages`, `banned_users`, `whitelist`, `spam_examples`, `stats`. Schema is auto-created on first run via `Database.initialize()`.

## Project Structure

```
├── main.py
├── src/
│   ├── __init__.py
│   ├── bot.py
│   ├── config.py
│   ├── spam_detector.py
│   ├── database.py
│   ├── profile_analyzer.py
│   ├── admin_commands.py
│   ├── middleware.py
│   └── models.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_spam_detector.py
│   ├── test_database.py
│   ├── test_profile_analyzer.py
│   └── test_admin_commands.py
├── data/
│   └── antispam.db
├── scripts/
│   └── backup_db.sh
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SETUP.md
│   ├── API.md
│   ├── ADMIN_GUIDE.md
│   ├── DEVELOPMENT.md
│   └── DEPLOYMENT.md
├── .env
├── .env.example
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Common Tasks

### Adding a new admin command
1. Add handler method in `src/admin_commands.py`
2. Register in `src/bot.py` `register_handlers()`
3. Update `/help` text
4. Write tests in `tests/test_admin_commands.py`

### Changing the AI model
Update `AI_MODEL` in `.env` and restart. No code changes needed.

### Adjusting spam sensitivity
- Lower `SPAM_CONFIDENCE_THRESHOLD` (e.g., 0.5) to catch more spam (more false positives)
- Raise it (e.g., 0.85) to reduce false positives (may miss some spam)

### Modifying the AI prompt
Edit `build_prompt()` in `src/spam_detector.py`. Test with `scripts/test_prompt.py`.
