# Setup Guide

Complete step-by-step guide to setting up Антиспамер 2 from scratch.

---

## Prerequisites

Before you begin, ensure you have:

- **Python 3.12 or higher** installed ([python.org/downloads](https://python.org/downloads))
- **A Telegram account** for creating a bot
- **A Telegram channel** with a linked discussion group (comments enabled)
- **An OpenRouter account** for AI-powered spam detection

---

## Step-by-Step Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/your-username/antispamer-2.git
cd antispamer-2
```

Or download and extract the ZIP archive.

### Step 2: Create a Virtual Environment

```bash
python -m venv venv
```

### Step 3: Activate the Virtual Environment

**Linux / macOS:**
```bash
source venv/bin/activate
```

**Windows (Command Prompt):**
```cmd
venv\Scripts\activate
```

**Windows (PowerShell):**
```powershell
venv\Scripts\Activate.ps1
```

You should see `(venv)` in your terminal prompt after activation.

### Step 4: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `aiogram>=3.0` — Telegram Bot framework
- `httpx` — Async HTTP client
- `aiosqlite` — Async SQLite driver
- `pydantic-settings` — Configuration management
- `structlog` — Structured logging

### Step 5: Create Configuration File

```bash
cp .env.example .env
```

Open `.env` in your text editor and fill in the required values (see steps 6–9 below).

### Step 6: Create a Telegram Bot

1. Open Telegram and search for [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Choose a **display name** for your bot (e.g., "Антиспамер 2")
4. Choose a **username** for your bot (must end in `bot`, e.g., `antispamer2_bot`)
5. BotFather will reply with your **bot token** — a string like:
   ```
   7123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
   ```
6. Copy this token and paste it as `BOT_TOKEN` in your `.env` file

**Important bot settings (via BotFather):**
- Send `/mybots` → select your bot → **Bot Settings**
- Enable **Group Privacy** → Turn **OFF** (bot needs to read all messages in the group)
- Optionally set a profile photo and description

### Step 7: Get an OpenRouter API Key

1. Go to [openrouter.ai](https://openrouter.ai) and create an account
2. Navigate to **Keys** section in your dashboard
3. Click **Create Key**
4. Give it a descriptive name (e.g., "Antispamer 2")
5. Copy the API key and paste it as `OPENROUTER_API_KEY` in your `.env` file

**Important:** Add credits to your OpenRouter account. Most models cost between $0.001–$0.01 per spam check. For a channel with ~100 comments/day, expect ~$1–3/month.

### Step 8: Add Bot to Your Channel's Discussion Group

The bot needs to be an **administrator** in your channel's discussion group (the group where comments appear).

1. Open your Telegram channel
2. Go to **Channel Settings** → **Discussion** → ensure a discussion group is linked
3. Open the linked discussion group
4. Go to **Group Settings** → **Administrators** → **Add Administrator**
5. Search for your bot by username and add it
6. Grant these permissions:
   - **Delete Messages** — Required to remove spam
   - **Ban Users** — Required to ban spammers
   - **Read Messages** — Required to monitor comments (should be default)
7. Save the administrator settings

### Step 9: Get Your Channel ID

You need the numeric ID of your Telegram channel.

**Method 1: Using @userinfobot**
1. Forward any message from your channel to [@userinfobot](https://t.me/userinfobot)
2. The bot will reply with the channel ID (a negative number like `-1001234567890`)

**Method 2: Using Telegram Web**
1. Open [web.telegram.org](https://web.telegram.org)
2. Navigate to your channel
3. Look at the URL — it contains the channel ID
4. The full ID is `-100` + the number from the URL (e.g., if URL shows `1234567890`, the ID is `-1001234567890`)

**Method 3: Using the bot itself**
1. Temporarily add this code to your bot and run it:
   ```python
   @dp.channel_post()
   async def get_channel_id(message):
       print(f"Channel ID: {message.chat.id}")
   ```
2. Post a message in your channel
3. The channel ID will be printed to the console

Copy the channel ID (including the `-` sign) and paste it as `CHANNEL_ID` in your `.env` file.

**Getting your Admin ID:**
1. Send any message to [@userinfobot](https://t.me/userinfobot)
2. It will reply with your user ID
3. Paste it as `ADMIN_IDS` in your `.env` file
4. For multiple admins, separate with commas: `ADMIN_IDS=123456789,987654321`

### Step 10: Run the Bot

```bash
python main.py
```

You should see startup logs indicating:
```
INFO     Bot started successfully
INFO     Connected to Telegram API
INFO     Database initialized at data/antispam.db
INFO     Spam detector ready (model: anthropic/claude-sonnet-4)
INFO     Monitoring channel: -1001234567890
```

---

## Complete `.env` Example

```env
# === Required ===
BOT_TOKEN=7123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
OPENROUTER_API_KEY=sk-or-v1-abc123def456...
ADMIN_IDS=123456789
CHANNEL_ID=-1001234567890

# === Optional (with defaults) ===
AI_MODEL=anthropic/claude-sonnet-4
SPAM_CONFIDENCE_THRESHOLD=0.7
MAX_AI_CALLS_PER_MINUTE=20
OPENROUTER_TIMEOUT=30
DATABASE_PATH=data/antispam.db
LOG_LEVEL=INFO
```

---

## Telegram Bot Permissions Summary

| Permission | Required | Purpose |
|-----------|----------|---------|
| Read Messages | Yes | Monitor incoming comments in the discussion group |
| Delete Messages | Yes | Remove messages classified as spam |
| Ban Users | Yes | Ban users who send spam |
| Pin Messages | No | Not used |
| Add Members | No | Not used |
| Manage Topics | No | Not used |
| Manage Video Chats | No | Not used |

**Note:** The bot's **Group Privacy Mode** must be turned OFF in BotFather settings, otherwise the bot will only see commands directed at it (messages starting with `/`), not regular comments.

---

## First Run Verification Checklist

After starting the bot, verify everything works:

- [ ] **Bot starts without errors** — No exceptions in the console output
- [ ] **Database created** — Check that `data/antispam.db` file exists
- [ ] **`/start` command works** — Send `/start` to your bot in a private chat; it should respond
- [ ] **`/status` command works** — Send `/status`; it should show bot status with model name and uptime
- [ ] **Bot sees messages** — Post a comment in your channel; check console logs for message processing
- [ ] **AI classification works** — Post a test message; verify the bot calls OpenRouter (check logs)
- [ ] **Spam detection works** — Post an obvious spam message (e.g., "Buy crypto now! Visit spamsite.com 50% discount!!!"); verify it gets deleted
- [ ] **Admin notification** — After spam detection, check that admins received a notification with an unban button
- [ ] **Unban works** — Click the unban button on the notification; verify the user is unbanned
- [ ] **`/stats` command works** — Send `/stats`; it should show at least 1 message processed

---

## Troubleshooting

### Bot doesn't start

| Error | Solution |
|-------|----------|
| `Invalid bot token` | Double-check your `BOT_TOKEN` in `.env` — it should be the full token from BotFather |
| `Module not found` | Make sure you activated the virtual environment and ran `pip install -r requirements.txt` |
| `.env file not found` | Ensure `.env` exists in the project root (not inside `src/` or another subdirectory) |
| `Permission denied` on database | Ensure the `data/` directory exists and is writable |

### Bot starts but doesn't see messages

| Issue | Solution |
|-------|----------|
| Bot not responding to comments | Turn OFF Group Privacy Mode in BotFather |
| Bot not in the group | Add the bot as admin to the **discussion group** (not the channel itself) |
| Wrong channel ID | Verify `CHANNEL_ID` matches your channel's actual ID |

### AI detection not working

| Issue | Solution |
|-------|----------|
| `401 Unauthorized` from OpenRouter | Check your `OPENROUTER_API_KEY` is correct and has credits |
| `429 Too Many Requests` | Your rate limit may be too high; lower `MAX_AI_CALLS_PER_MINUTE` |
| Timeout errors | Increase `OPENROUTER_TIMEOUT` or check your internet connection |

---

## Next Steps

- Read the [Admin Guide](ADMIN_GUIDE.md) to learn all bot commands
- Review the [Architecture](ARCHITECTURE.md) to understand how the bot works
- Check [Deployment](DEPLOYMENT.md) for production deployment options
