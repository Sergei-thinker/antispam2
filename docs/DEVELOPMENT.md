# Development Guide

Guide for developers contributing to or extending Антиспамер 2.

---

## Table of Contents

- [Development Environment Setup](#development-environment-setup)
- [Running Tests](#running-tests)
- [Code Style](#code-style)
- [Module Responsibility Guide](#module-responsibility-guide)
- [Adding New Admin Commands](#adding-new-admin-commands)
- [Modifying the Spam Detection Prompt](#modifying-the-spam-detection-prompt)
- [Database Migrations](#database-migrations)

---

## Development Environment Setup

### Prerequisites

- Python 3.12 or higher
- Git
- A code editor (VS Code recommended with the Python extension)

### Initial Setup

```bash
# Clone the repository
git clone https://github.com/your-username/antispamer-2.git
cd antispamer-2

# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies (including dev dependencies)
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Copy environment config
cp .env.example .env
# Fill in .env with your test credentials
```

### Dev Dependencies

The `requirements-dev.txt` file includes:

```
pytest>=8.0
pytest-asyncio>=0.23
pytest-cov>=5.0
ruff>=0.3.0
mypy>=1.8
aioresponses>=0.7
```

### IDE Configuration

**VS Code** — recommended `settings.json`:

```json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.analysis.typeCheckingMode": "basic",
    "[python]": {
        "editor.defaultFormatter": "charliermarsh.ruff",
        "editor.formatOnSave": true,
        "editor.codeActionsOnSave": {
            "source.fixAll.ruff": "explicit",
            "source.organizeImports.ruff": "explicit"
        }
    },
    "python.testing.pytestArgs": ["tests/"],
    "python.testing.pytestEnabled": true
}
```

---

## Running Tests

### Full Test Suite

```bash
pytest tests/ -v
```

### Specific Test Files

```bash
# Test spam detector
pytest tests/test_spam_detector.py -v

# Test database operations
pytest tests/test_database.py -v

# Test profile analyzer
pytest tests/test_profile_analyzer.py -v

# Test admin commands
pytest tests/test_admin_commands.py -v
```

### With Coverage Report

```bash
pytest tests/ -v --cov=src --cov-report=term-missing
```

This shows which lines of code are not covered by tests.

### Running a Single Test

```bash
pytest tests/test_spam_detector.py::test_detect_obvious_spam -v
```

### Test Configuration

Tests use `pytest-asyncio` for async test support. The `conftest.py` file provides shared fixtures:

```python
# tests/conftest.py

import pytest
import aiosqlite
from src.config import Settings
from src.database import Database
from src.spam_detector import SpamDetector

@pytest.fixture
def settings():
    """Test settings with safe defaults."""
    return Settings(
        BOT_TOKEN="test:token",
        OPENROUTER_API_KEY="test-key",
        ADMIN_IDS=[123456789],
        CHANNEL_ID=-1001234567890,
        DATABASE_PATH=":memory:",
        LOG_LEVEL="DEBUG",
    )

@pytest.fixture
async def db(settings):
    """In-memory database for testing."""
    database = Database(settings.DATABASE_PATH)
    await database.initialize()
    yield database
    await database.close()

@pytest.fixture
def mock_detector(settings):
    """SpamDetector with mocked HTTP client."""
    return SpamDetector(settings)
```

### Writing Tests

Follow these conventions:

1. **File naming:** `test_<module_name>.py`
2. **Function naming:** `test_<what_it_tests>`
3. **Use async tests** for any code that uses `await`
4. **Mock external services** (Telegram API, OpenRouter) — never make real API calls in tests
5. **Use in-memory database** (`:memory:`) for database tests

Example test:

```python
# tests/test_spam_detector.py

import pytest
from unittest.mock import AsyncMock, patch
from src.spam_detector import SpamDetector

@pytest.mark.asyncio
async def test_detect_obvious_spam(mock_detector):
    """Test that obvious spam is detected with high confidence."""
    mock_response = {
        "choices": [{
            "message": {
                "content": '{"is_spam": true, "confidence": 0.95, "reason": "Promotional spam"}'
            }
        }]
    }

    with patch.object(mock_detector, "call_api", return_value=mock_response):
        verdict = await mock_detector.check_message(
            text="Buy cheap followers! Visit spam-site.com",
            profile_info=None
        )

    assert verdict.is_spam is True
    assert verdict.confidence >= 0.9


@pytest.mark.asyncio
async def test_allow_normal_message(mock_detector):
    """Test that a normal comment is not flagged as spam."""
    mock_response = {
        "choices": [{
            "message": {
                "content": '{"is_spam": false, "confidence": 0.1, "reason": "Normal comment"}'
            }
        }]
    }

    with patch.object(mock_detector, "call_api", return_value=mock_response):
        verdict = await mock_detector.check_message(
            text="Great video, thanks for sharing!",
            profile_info=None
        )

    assert verdict.is_spam is False


@pytest.mark.asyncio
async def test_fail_open_on_api_error(mock_detector):
    """Test that API errors result in allowing the message (fail-open)."""
    with patch.object(mock_detector, "call_api", side_effect=Exception("API Error")):
        verdict = await mock_detector.check_message(
            text="Some message",
            profile_info=None
        )

    assert verdict.is_spam is False  # fail-open
```

---

## Code Style

### Linter and Formatter: Ruff

The project uses [Ruff](https://docs.astral.sh/ruff/) for both linting and formatting.

```bash
# Check for linting issues
ruff check src/ tests/

# Auto-fix linting issues
ruff check src/ tests/ --fix

# Format code
ruff format src/ tests/

# Check formatting without modifying files
ruff format src/ tests/ --check
```

### Ruff Configuration

Configuration in `pyproject.toml`:

```toml
[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort (import sorting)
    "N",    # pep8-naming
    "UP",   # pyupgrade
    "B",    # flake8-bugbear
    "SIM",  # flake8-simplify
    "ASYNC",# flake8-async
]

[tool.ruff.lint.isort]
known-first-party = ["src"]
```

### Code Style Conventions

1. **Type hints** — Use type hints for all function signatures
   ```python
   async def check_message(self, text: str, profile_info: ProfileInfo | None) -> SpamVerdict:
   ```

2. **Docstrings** — Use Google-style docstrings for public methods
   ```python
   async def ban_user(self, user_id: int, reason: str) -> None:
       """Ban a user and record the action in the database.

       Args:
           user_id: Telegram user ID to ban.
           reason: AI-generated reason for the ban.

       Raises:
           TelegramAPIError: If the ban API call fails.
       """
   ```

3. **Logging** — Use structlog with bound context
   ```python
   log = structlog.get_logger()

   async def handle_message(self, message):
       log_ctx = log.bind(user_id=message.from_user.id, message_id=message.message_id)
       log_ctx.info("processing_message")
   ```

4. **Error handling** — Use specific exceptions, log all errors
   ```python
   try:
       result = await self.call_api(messages)
   except httpx.TimeoutException:
       log.warning("api_timeout", timeout=self.settings.OPENROUTER_TIMEOUT)
       return SpamVerdict(is_spam=False, confidence=0.0, reason="API timeout")
   except httpx.HTTPStatusError as e:
       log.error("api_error", status_code=e.response.status_code)
       return SpamVerdict(is_spam=False, confidence=0.0, reason="API error")
   ```

5. **Constants** — Use UPPER_CASE for module-level constants
   ```python
   DEFAULT_TIMEOUT = 30
   MAX_RETRIES = 3
   BACKOFF_MULTIPLIER = 2
   ```

---

## Module Responsibility Guide

Each module has a clearly defined responsibility. Follow the Single Responsibility Principle.

| Module | Responsibility | Dependencies |
|--------|---------------|-------------|
| `main.py` | Entry point, initialize and start the bot | All `src/` modules |
| `src/config.py` | Load and validate configuration from `.env` | pydantic-settings |
| `src/bot.py` | Orchestrate the spam detection pipeline | SpamDetector, Database, ProfileAnalyzer |
| `src/spam_detector.py` | AI-based spam classification via OpenRouter | httpx, Database (for examples) |
| `src/database.py` | All SQLite database operations | aiosqlite |
| `src/profile_analyzer.py` | Fetch and analyze Telegram user profiles | aiogram Bot instance |
| `src/admin_commands.py` | Handle admin bot commands | Database, aiogram |
| `src/middleware.py` | Dependency injection via aiogram middleware | All injected services |
| `src/models.py` | Pydantic data models (SpamVerdict, ProfileInfo, etc.) | pydantic |

### Dependency Rules

- `config.py` depends on nothing (except pydantic-settings)
- `models.py` depends on nothing (except pydantic)
- `database.py` depends on `models.py`
- `spam_detector.py` depends on `config.py`, `models.py`, `database.py`
- `profile_analyzer.py` depends on `models.py`
- `admin_commands.py` depends on `database.py`, `models.py`
- `bot.py` depends on everything
- `middleware.py` depends on the service instances
- `main.py` wires everything together

---

## Adding New Admin Commands

### Step 1: Define the Handler

Add a new method to `AdminCommands` in `src/admin_commands.py`:

```python
async def cmd_mycommand(self, message: types.Message, db: Database) -> None:
    """Handle the /mycommand command.

    Usage: /mycommand [args]
    """
    # Verify admin access
    if message.from_user.id not in self.settings.ADMIN_IDS:
        return

    # Parse arguments
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Usage: /mycommand <argument>")
        return

    argument = args[1]

    # Do something
    result = await db.some_operation(argument)

    # Reply
    await message.reply(f"Result: {result}")
```

### Step 2: Register the Handler

In `src/bot.py`, register the new command in the `register_handlers` method:

```python
def register_handlers(self):
    # ... existing handlers ...
    self.dp.message.register(
        self.admin_commands.cmd_mycommand,
        Command("mycommand")
    )
```

### Step 3: Update Help Text

Add the new command to the `/help` output in `cmd_help`:

```python
help_text = """
...
/mycommand <arg> — Description of what mycommand does
...
"""
```

### Step 4: Write Tests

```python
# tests/test_admin_commands.py

@pytest.mark.asyncio
async def test_cmd_mycommand(admin_commands, mock_message, db):
    mock_message.text = "/mycommand test_arg"
    mock_message.from_user.id = 123456789  # admin ID

    await admin_commands.cmd_mycommand(mock_message, db)

    mock_message.reply.assert_called_once()
    assert "Result:" in mock_message.reply.call_args[0][0]
```

---

## Modifying the Spam Detection Prompt

The AI prompt is constructed in `src/spam_detector.py` in the `build_prompt` method.

### Prompt Structure

```python
def build_prompt(self, text: str, profile_info: ProfileInfo | None, examples: list) -> list[dict]:
    messages = [
        {
            "role": "system",
            "content": self.system_prompt
        }
    ]

    # Add few-shot examples
    for example in examples:
        messages.append({"role": "user", "content": f"Classify: {example.text}"})
        messages.append({"role": "assistant", "content": json.dumps({
            "is_spam": True,
            "confidence": 0.95,
            "reason": example.reason
        })})

    # Add the actual message to classify
    user_content = self._format_classification_request(text, profile_info)
    messages.append({"role": "user", "content": user_content})

    return messages
```

### Guidelines for Prompt Changes

1. **Always test with both spam and legitimate messages** after changing the prompt
2. **Keep the output format consistent** — `is_spam`, `confidence`, `reason` as JSON
3. **Be explicit about edge cases** — what counts as spam vs legitimate promotion
4. **Include context about Telegram channel comments** — the model needs to understand the domain
5. **Maintain the conservative bias** — prefer false negatives over false positives
6. **Document your changes** in `DEVELOPMENT_LOG.md` with before/after examples

### Testing Prompt Changes

Create a test script for quick iteration:

```python
# scripts/test_prompt.py

import asyncio
from src.config import Settings
from src.spam_detector import SpamDetector

TEST_MESSAGES = [
    # (text, expected_is_spam)
    ("Great video, thanks!", False),
    ("Buy followers cheap at spam.com", True),
    ("I disagree with your point about...", False),
    ("🔥🔥 SALE 90% OFF CLICK HERE 🔥🔥", True),
    ("Has anyone tried this technique?", False),
    ("DM me for investment opportunity 300% ROI", True),
]

async def main():
    settings = Settings()
    detector = SpamDetector(settings)

    for text, expected in TEST_MESSAGES:
        verdict = await detector.check_message(text, profile_info=None)
        status = "PASS" if verdict.is_spam == expected else "FAIL"
        print(f"[{status}] '{text[:50]}...' -> spam={verdict.is_spam} ({verdict.confidence:.2f})")

asyncio.run(main())
```

Run it:
```bash
python scripts/test_prompt.py
```

---

## Database Migrations

Антиспамер 2 uses SQLite, which has limited ALTER TABLE support. For schema changes, follow this approach:

### Simple Changes (Adding Columns)

SQLite supports `ALTER TABLE ... ADD COLUMN`. Add the migration to the `initialize()` method in `src/database.py`:

```python
async def initialize(self):
    async with aiosqlite.connect(self.db_path) as db:
        # Create tables (existing code)
        await self._create_tables(db)

        # Migrations
        await self._migrate_v2(db)

async def _migrate_v2(self, db):
    """Add new_column to messages table (v2 migration)."""
    try:
        await db.execute("ALTER TABLE messages ADD COLUMN new_column TEXT")
        await db.commit()
    except aiosqlite.OperationalError:
        # Column already exists, migration already applied
        pass
```

### Complex Changes (Renaming Columns, Changing Types)

For complex schema changes, use the SQLite migration pattern:

```python
async def _migrate_v3(self, db):
    """Rename column old_name to new_name in messages table."""
    try:
        # Check if migration is needed
        cursor = await db.execute("PRAGMA table_info(messages)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "new_name" in columns:
            return  # Already migrated

        # Create new table with correct schema
        await db.execute("""
            CREATE TABLE messages_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                new_name TEXT,
                -- ... all other columns ...
            )
        """)

        # Copy data
        await db.execute("""
            INSERT INTO messages_new (id, new_name, ...)
            SELECT id, old_name, ...
            FROM messages
        """)

        # Swap tables
        await db.execute("DROP TABLE messages")
        await db.execute("ALTER TABLE messages_new RENAME TO messages")

        # Recreate indexes
        await db.execute("CREATE INDEX idx_messages_... ON messages(...)")

        await db.commit()
    except Exception as e:
        log.error("migration_v3_failed", error=str(e))
        raise
```

### Migration Best Practices

1. **Always wrap in try/except** — migrations should be idempotent (safe to run multiple times)
2. **Check if migration is needed** before executing
3. **Back up the database** before running migrations in production
4. **Test migrations** with a copy of production data
5. **Log all migrations** — use structlog to record migration success/failure
6. **Never delete data** without a backup strategy

### Backup Before Migration

```bash
# Manual backup
cp data/antispam.db data/antispam.db.backup.$(date +%Y%m%d)

# Or use the backup script
bash scripts/backup_db.sh
```
