"""Shared fixtures for the Telegram Anti-Spam Bot v2 test suite."""

from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.database import Database
from src.models import MessageContext, SpamVerdict, UserProfile
from src.config import Settings


@pytest.fixture
def db_path(tmp_path):
    """Return a temporary database file path."""
    return str(tmp_path / "test.db")


@pytest_asyncio.fixture
async def db(db_path):
    """Create, connect and yield a Database; close it after the test."""
    database = Database(db_path)
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
def sample_settings():
    """Create a Settings instance for testing without reading .env file."""
    with patch.dict(
        "os.environ",
        {
            "BOT_TOKEN": "123:ABC",
            "OPENROUTER_API_KEY": "sk-test-key",
            "ADMIN_IDS": "[111,222]",
            "CHANNEL_ID": "-1001234567890",
        },
        clear=False,
    ):
        return Settings(
            bot_token="123:ABC",
            openrouter_api_key="sk-test-key",
            admin_ids=[111, 222],
            channel_id=-1001234567890,
        )


@pytest.fixture
def sample_profile():
    """Return a fully-populated UserProfile for testing."""
    return UserProfile(
        user_id=12345,
        first_name="Test",
        last_name="User",
        username="testuser",
        bio="Just a test user",
        has_profile_photo=True,
    )


@pytest.fixture
def minimal_profile():
    """Return a UserProfile with only required fields."""
    return UserProfile(
        user_id=99999,
        first_name="Minimal",
    )


@pytest.fixture
def spam_verdict():
    """Return a SpamVerdict flagging a message as spam."""
    return SpamVerdict(is_spam=True, confidence=0.95, reason="Crypto spam")


@pytest.fixture
def not_spam_verdict():
    """Return a SpamVerdict allowing a message."""
    return SpamVerdict(is_spam=False, confidence=0.1, reason="Normal comment")


@pytest.fixture
def sample_message_context(sample_profile):
    """Return a MessageContext for testing."""
    return MessageContext(
        message_id=1,
        chat_id=-1001234567890,
        user_id=12345,
        text="Hello world",
        profile=sample_profile,
        is_edited=False,
    )
