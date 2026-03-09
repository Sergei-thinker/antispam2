# Architecture

This document describes the system architecture of Антиспамер 2, including component design, message processing flow, database schema, and error handling strategies.

---

## System Overview

Антиспамер 2 is built as an asynchronous Python application using the aiogram 3.x framework. The bot connects to Telegram via long polling, receives messages from a channel's discussion group, and uses an external AI service (OpenRouter) to classify messages as spam or legitimate.

### High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Антиспамер 2                                 │
│                                                                     │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │              │    │                  │    │                  │  │
│  │  AntispamBot │───▶│  SpamDetector    │───▶│  OpenRouter API  │  │
│  │  (bot.py)    │    │ (spam_detector)  │    │  (external)      │  │
│  │              │    │                  │    │                  │  │
│  └──────┬───────┘    └──────────────────┘    └──────────────────┘  │
│         │                                                           │
│         │            ┌──────────────────┐    ┌──────────────────┐  │
│         ├───────────▶│ ProfileAnalyzer  │───▶│  Telegram API    │  │
│         │            │ (profile_analyzer│    │  (user profiles) │  │
│         │            │                  │    │                  │  │
│         │            └──────────────────┘    └──────────────────┘  │
│         │                                                           │
│         │            ┌──────────────────┐                           │
│         ├───────────▶│    Database      │                           │
│         │            │   (database.py)  │                           │
│         │            │   [SQLite]       │                           │
│         │            └──────────────────┘                           │
│         │                                                           │
│         │            ┌──────────────────┐                           │
│         └───────────▶│  AdminCommands   │                           │
│                      │ (admin_commands) │                           │
│                      └──────────────────┘                           │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              DependencyMiddleware (middleware.py)             │  │
│  │         Injects dependencies into aiogram handlers           │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                   Settings (config.py)                        │  │
│  │           pydantic-settings BaseSettings from .env            │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Message Processing Flow

Every message that arrives in the channel's discussion group goes through the following pipeline:

```
┌─────────────────────────┐
│   New comment arrives    │
│   in discussion group    │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Is sender a bot?       │──── Yes ──▶ SKIP (allow message)
└────────────┬────────────┘
             │ No
             ▼
┌─────────────────────────┐
│  Is sender an admin?    │──── Yes ──▶ SKIP (allow message)
│  (in ADMIN_IDS)         │
└────────────┬────────────┘
             │ No
             ▼
┌─────────────────────────┐
│  Is sender whitelisted? │──── Yes ──▶ SKIP (allow message)
│  (in whitelist table)   │
└────────────┬────────────┘
             │ No
             ▼
┌─────────────────────────┐
│  ProfileAnalyzer        │
│  ┌────────────────────┐ │
│  │ Fetch user profile │ │
│  │ • Display name     │ │
│  │ • Username         │ │
│  │ • Bio/description  │ │
│  │ • Profile photo    │ │
│  │ • Account features │ │
│  └────────────────────┘ │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  SpamDetector           │
│  ┌────────────────────┐ │
│  │ Rate limit check   │─┤──── Over limit ──▶ ALLOW (fail-open)
│  └────────┬───────────┘ │
│           │ OK          │
│  ┌────────▼───────────┐ │
│  │ Build AI prompt    │ │
│  │ • System prompt    │ │
│  │ • Few-shot examples│ │
│  │ • User profile     │ │
│  │ • Message content  │ │
│  └────────┬───────────┘ │
│           │             │
│  ┌────────▼───────────┐ │
│  │ Call OpenRouter API │─┤──── Error ──▶ ALLOW (fail-open)
│  └────────┬───────────┘ │
│           │             │
│  ┌────────▼───────────┐ │
│  │ Parse AI response  │ │
│  │ Extract:           │ │
│  │ • is_spam (bool)   │ │
│  │ • confidence (0-1) │ │
│  │ • reason (text)    │ │
│  └────────┬───────────┘ │
│           │             │
│  ┌────────▼───────────┐ │
│  │ confidence >=       │ │
│  │ threshold?         │─┤──── No ──▶ ALLOW
│  └────────┬───────────┘ │
│           │ Yes         │
└───────────┤─────────────┘
            │
            ▼
┌─────────────────────────┐
│  SPAM DETECTED          │
│                         │
│  1. Delete message      │
│  2. Ban user from group │
│  3. Log to database     │
│  4. Send admin notif.   │
│     (with unban button) │
│  5. Save as spam example│
└─────────────────────────┘
```

---

## Component Descriptions

### AntispamBot (`src/bot.py`)

The main orchestration component that ties everything together.

**Responsibilities:**
- Initialize the aiogram `Bot` and `Dispatcher` instances
- Register message handlers and middleware
- Coordinate the spam detection pipeline
- Handle message deletion and user banning
- Send spam notifications to admins
- Manage the bot lifecycle (startup, shutdown, graceful cleanup)

**Key Methods:**
- `start()` — Initialize components, register handlers, start polling
- `handle_message(message)` — Main message processing pipeline
- `delete_and_ban(message, verdict)` — Execute spam response actions
- `notify_admins(message, verdict)` — Send detection notifications with inline unban button

### SpamDetector (`src/spam_detector.py`)

Handles all interaction with the OpenRouter AI API for spam classification.

**Responsibilities:**
- Build structured prompts for the AI model
- Manage few-shot examples from the database
- Enforce rate limiting (token bucket algorithm)
- Make async HTTP requests to OpenRouter
- Parse and validate AI responses
- Handle API errors with retry and backoff

**Key Methods:**
- `check_message(text, profile_info) -> SpamVerdict` — Main classification method
- `build_prompt(text, profile_info, examples) -> list[dict]` — Construct the chat messages
- `call_api(messages) -> dict` — Make the OpenRouter API call with rate limiting
- `parse_response(raw) -> SpamVerdict` — Extract structured verdict from AI response

**Rate Limiting:**
Uses a sliding window counter to enforce `MAX_AI_CALLS_PER_MINUTE`. When the limit is reached, the detector returns a non-spam verdict (fail-open strategy) to avoid blocking legitimate messages.

### Database (`src/database.py`)

Manages all persistent data storage using SQLite via aiosqlite.

**Responsibilities:**
- Initialize database schema on first run
- Store processed messages and their verdicts
- Maintain banned users list
- Manage whitelist entries
- Store confirmed spam examples for few-shot learning
- Track statistics (messages processed, spam detected, false positives)

**Key Methods:**
- `initialize()` — Create tables and indexes if they don't exist
- `log_message(message_data) -> int` — Record a processed message
- `ban_user(user_id, reason)` — Add user to banned list
- `unban_user(user_id)` — Remove user from banned list
- `add_to_whitelist(user_id)` — Add user to whitelist
- `remove_from_whitelist(user_id)` — Remove user from whitelist
- `is_whitelisted(user_id) -> bool` — Check whitelist membership
- `get_spam_examples(limit) -> list` — Retrieve recent spam examples for few-shot
- `add_spam_example(text, reason)` — Store a confirmed spam example
- `get_stats() -> dict` — Aggregate statistics
- `get_recent_spam(limit) -> list` — Get recent spam detections

### ProfileAnalyzer (`src/profile_analyzer.py`)

Fetches and analyzes Telegram user profiles to provide additional context to the AI model.

**Responsibilities:**
- Fetch user profile information via Telegram Bot API
- Retrieve user profile photos (if available)
- Compile profile signals (name patterns, bio content, photo presence)
- Format profile data for inclusion in the AI prompt

**Key Methods:**
- `analyze(user) -> ProfileInfo` — Full profile analysis for a user
- `get_profile_photo(user_id) -> bool` — Check if user has a profile photo
- `format_for_prompt(profile_info) -> str` — Format profile data as prompt context

**Profile Signals:**
- Has profile photo (legitimate users usually do)
- Display name patterns (spammers often use promotional names)
- Username presence and format
- Bio/description content (if accessible)

### AdminCommands (`src/admin_commands.py`)

Handles all admin-facing bot commands.

**Responsibilities:**
- Validate admin authorization for all commands
- Implement command handlers for bot management
- Format and display statistics
- Handle whitelist and unban operations
- Process inline keyboard callbacks (unban buttons)

**Key Methods:**
- `cmd_start(message)` — Welcome message handler
- `cmd_help(message)` — Command list display
- `cmd_stats(message)` — Statistics display
- `cmd_status(message)` — Bot operational status
- `cmd_whitelist(message)` — Add user to whitelist
- `cmd_unban(message)` — Unban a user
- `cmd_recent(message)` — Recent spam detections
- `callback_unban(callback_query)` — Handle inline unban button press

### DependencyMiddleware (`src/middleware.py`)

Implements aiogram's middleware pattern for dependency injection.

**Responsibilities:**
- Inject shared instances (Database, SpamDetector, Settings) into handler context
- Ensure all handlers have access to required dependencies without global state
- Manage per-request context

**Implementation:**
```python
class DependencyMiddleware(BaseMiddleware):
    def __init__(self, db: Database, detector: SpamDetector, settings: Settings):
        self.db = db
        self.detector = detector
        self.settings = settings

    async def __call__(self, handler, event, data):
        data["db"] = self.db
        data["detector"] = self.detector
        data["settings"] = self.settings
        return await handler(event, data)
```

### Settings (`src/config.py`)

Configuration management using pydantic-settings.

**Responsibilities:**
- Load configuration from `.env` file and environment variables
- Validate all settings at startup (fail fast on misconfiguration)
- Provide typed access to configuration values
- Set sensible defaults for optional settings

---

## Database Schema

The SQLite database contains 5 tables:

### `messages`

Stores every processed message and its classification result.

```sql
CREATE TABLE messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id      INTEGER NOT NULL,          -- Telegram message ID
    chat_id         INTEGER NOT NULL,          -- Telegram chat ID
    user_id         INTEGER NOT NULL,          -- Sender's Telegram user ID
    username        TEXT,                       -- Sender's username (nullable)
    display_name    TEXT,                       -- Sender's display name
    text            TEXT NOT NULL,              -- Message content
    is_spam         BOOLEAN NOT NULL DEFAULT 0, -- AI classification result
    confidence      REAL,                       -- AI confidence score (0.0-1.0)
    reason          TEXT,                       -- AI explanation for classification
    action_taken    TEXT,                       -- Action taken: 'deleted_banned', 'allowed', 'skipped'
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_messages_user_id ON messages(user_id);
CREATE INDEX idx_messages_is_spam ON messages(is_spam);
CREATE INDEX idx_messages_created_at ON messages(created_at);
```

### `banned_users`

Tracks all users banned by the bot.

```sql
CREATE TABLE banned_users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL UNIQUE,    -- Telegram user ID
    username        TEXT,                        -- Username at time of ban
    display_name    TEXT,                        -- Display name at time of ban
    reason          TEXT,                        -- AI-provided reason for ban
    spam_message    TEXT,                        -- The message that triggered the ban
    confidence      REAL,                        -- AI confidence score
    banned_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    unbanned_at     TIMESTAMP                   -- NULL if still banned
);

CREATE INDEX idx_banned_users_user_id ON banned_users(user_id);
```

### `whitelist`

Users who are exempt from spam checking.

```sql
CREATE TABLE whitelist (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL UNIQUE,    -- Telegram user ID
    added_by        INTEGER NOT NULL,           -- Admin who added them
    added_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_whitelist_user_id ON whitelist(user_id);
```

### `spam_examples`

Confirmed spam messages used for few-shot learning in AI prompts.

```sql
CREATE TABLE spam_examples (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    text            TEXT NOT NULL,               -- Spam message content
    reason          TEXT,                        -- Why it's spam
    source          TEXT DEFAULT 'auto',         -- 'auto' (from detections) or 'manual'
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_spam_examples_created_at ON spam_examples(created_at);
```

### `stats`

Aggregated daily statistics for performance tracking.

```sql
CREATE TABLE stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            DATE NOT NULL UNIQUE,        -- Statistics date
    messages_total  INTEGER DEFAULT 0,           -- Total messages processed
    spam_detected   INTEGER DEFAULT 0,           -- Messages classified as spam
    spam_deleted    INTEGER DEFAULT 0,           -- Messages actually deleted
    users_banned    INTEGER DEFAULT 0,           -- Users banned
    false_positives INTEGER DEFAULT 0,           -- Reported false positives
    ai_calls        INTEGER DEFAULT 0,           -- Total AI API calls
    ai_errors       INTEGER DEFAULT 0,           -- AI API errors
    avg_confidence  REAL DEFAULT 0,              -- Average confidence score
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_stats_date ON stats(date);
```

---

## Error Handling

### Fail-Open Strategy

The bot implements a **fail-open** error handling strategy: when any component in the spam detection pipeline fails, the message is **allowed through** rather than blocked. This prevents false bans during service outages.

Fail-open applies to:
- OpenRouter API timeouts or errors
- Rate limit exceeded (too many API calls)
- JSON parsing failures in AI responses
- Database write errors (for logging, not for whitelist/ban checks)
- Profile analysis failures

### Retry with Exponential Backoff

API calls to OpenRouter use a retry strategy:
- **Max retries:** 3
- **Initial delay:** 1 second
- **Backoff multiplier:** 2x (1s, 2s, 4s)
- **Retry on:** HTTP 429 (rate limited), HTTP 500+ (server errors), connection errors
- **Do not retry on:** HTTP 400 (bad request), HTTP 401 (auth error), HTTP 403 (forbidden)

### Error Logging

All errors are logged with full context using structlog:
- Error type and message
- User ID and message ID that triggered the error
- Component that raised the error
- Stack trace for unexpected exceptions

---

## AI Prompt Design Philosophy

The spam detection prompt is designed with these principles:

1. **Structured Output** — The AI is instructed to return JSON with `is_spam`, `confidence`, and `reason` fields for reliable parsing.

2. **Context-Rich** — The prompt includes:
   - Clear definition of what constitutes spam in this context (Telegram channel comments)
   - The user's profile information for holistic analysis
   - Few-shot examples from the database for calibration
   - The actual message text to classify

3. **Conservative Classification** — The prompt explicitly instructs the AI to err on the side of caution: if uncertain, classify as not spam. Combined with the confidence threshold, this minimizes false positives.

4. **Evolving Examples** — The few-shot examples are drawn from the database of confirmed spam, so the model improves over time as more spam is caught and verified.

5. **Reason Transparency** — Every classification includes a human-readable reason, enabling admin review and helping identify potential false positives.
