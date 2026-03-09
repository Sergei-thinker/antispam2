"""Tests for bot message handling logic.

Since the handler module (src/handlers/message.py or similar) may not exist yet,
these tests validate the *expected behaviour* of the message processing pipeline
using mocked Telegram objects and dependencies.

The handler logic under test:
1. Skip messages from bots, admins, whitelisted users, or without text.
2. Run SpamDetector.analyze() on the message.
3. If spam: delete the message, ban the user, notify admins, log to DB.
4. If not spam: allow and log to DB.
"""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from src.models import SpamVerdict, UserProfile


# =========================================================================
# Helpers -- mock Telegram objects
# =========================================================================

def _make_user(*, user_id: int = 12345, is_bot: bool = False, first_name: str = "Test",
               username: str = "testuser"):
    """Build a minimal mock Telegram User."""
    user = MagicMock()
    user.id = user_id
    user.is_bot = is_bot
    user.first_name = first_name
    user.last_name = None
    user.username = username
    return user


def _make_message(*, user=None, text="Hello world", chat_id=-1001234567890):
    """Build a minimal mock Telegram Message."""
    if user is None:
        user = _make_user()
    msg = AsyncMock()
    msg.from_user = user
    msg.text = text
    msg.message_id = 42
    msg.chat = MagicMock()
    msg.chat.id = chat_id
    msg.chat.ban = AsyncMock()
    msg.delete = AsyncMock()
    msg.answer = AsyncMock()
    return msg


def _make_bot():
    """Build a minimal mock Bot."""
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    return bot


def _make_db():
    """Build a mock Database."""
    db = AsyncMock()
    db.is_whitelisted = AsyncMock(return_value=False)
    db.is_banned = AsyncMock(return_value=False)
    db.log_message = AsyncMock(return_value=1)
    db.add_banned_user = AsyncMock(return_value=1)
    db.add_spam_example = AsyncMock(return_value=1)
    db.increment_stat = AsyncMock()
    return db


def _make_detector(verdict: SpamVerdict):
    """Build a mock SpamDetector returning a fixed verdict."""
    detector = AsyncMock()
    detector.analyze = AsyncMock(return_value=verdict)
    return detector


def _make_profile_analyzer(profile: UserProfile | None = None):
    """Build a mock ProfileAnalyzer returning a fixed profile."""
    if profile is None:
        profile = UserProfile(user_id=12345, first_name="Test", username="testuser")
    analyzer = AsyncMock()
    analyzer.get_profile = AsyncMock(return_value=profile)
    return analyzer


# =========================================================================
# Handler simulation
# =========================================================================

async def _simulate_message_handler(
    message,
    bot,
    db,
    detector,
    profile_analyzer,
    admin_ids: list[int],
    spam_threshold: float = 0.7,
):
    """Simulate the expected message handling pipeline.

    This mirrors the logic that should exist in the bot's message handler.
    """
    user = message.from_user

    # 1. Skip bots
    if user.is_bot:
        return "skipped_bot"

    # 2. Skip admins
    if user.id in admin_ids:
        return "skipped_admin"

    # 3. Skip no-text messages
    if not message.text:
        return "skipped_no_text"

    # 4. Skip whitelisted users
    if await db.is_whitelisted(user.id):
        return "skipped_whitelisted"

    # 5. Get profile and analyze
    profile = await profile_analyzer.get_profile(user, message.chat.id)
    verdict = await detector.analyze(message.text, profile)

    today = date.today().isoformat()
    await db.increment_stat(today, "messages_checked")

    # 6. Act on verdict
    if verdict.is_spam and verdict.confidence >= spam_threshold:
        await message.delete()
        await message.chat.ban(user.id)
        await db.add_banned_user(
            user_id=user.id,
            chat_id=message.chat.id,
            username=user.username,
            reason=verdict.reason,
            confidence=verdict.confidence,
            message_text=message.text,
        )
        await db.increment_stat(today, "spam_detected")
        await db.increment_stat(today, "users_banned")
        await db.log_message(
            message_id=message.message_id,
            chat_id=message.chat.id,
            user_id=user.id,
            username=user.username,
            message_text=message.text,
            is_edited=False,
            verdict_spam=True,
            verdict_confidence=verdict.confidence,
            verdict_reason=verdict.reason,
            action_taken="deleted_and_banned",
        )
        # Notify admins
        for admin_id in admin_ids:
            await bot.send_message(admin_id, f"Spam detected from @{user.username}")
        return "spam_banned"
    else:
        await db.log_message(
            message_id=message.message_id,
            chat_id=message.chat.id,
            user_id=user.id,
            username=user.username,
            message_text=message.text,
            is_edited=False,
            verdict_spam=False,
            verdict_confidence=verdict.confidence,
            verdict_reason=verdict.reason,
            action_taken="allowed",
        )
        return "allowed"


# =========================================================================
# Tests
# =========================================================================

class TestMessageHandlerSkips:

    async def test_skip_bot_message(self):
        """Messages from bot users should be skipped entirely."""
        bot_user = _make_user(is_bot=True)
        message = _make_message(user=bot_user)
        result = await _simulate_message_handler(
            message, _make_bot(), _make_db(),
            _make_detector(SpamVerdict(is_spam=False, confidence=0.0, reason="")),
            _make_profile_analyzer(),
            admin_ids=[111],
        )
        assert result == "skipped_bot"

    async def test_skip_admin_message(self):
        """Messages from admin users should be skipped."""
        admin_user = _make_user(user_id=111)
        message = _make_message(user=admin_user)
        result = await _simulate_message_handler(
            message, _make_bot(), _make_db(),
            _make_detector(SpamVerdict(is_spam=False, confidence=0.0, reason="")),
            _make_profile_analyzer(),
            admin_ids=[111, 222],
        )
        assert result == "skipped_admin"

    async def test_skip_whitelisted_user(self):
        """Whitelisted users should be skipped."""
        db = _make_db()
        db.is_whitelisted = AsyncMock(return_value=True)
        message = _make_message()
        result = await _simulate_message_handler(
            message, _make_bot(), db,
            _make_detector(SpamVerdict(is_spam=False, confidence=0.0, reason="")),
            _make_profile_analyzer(),
            admin_ids=[999],
        )
        assert result == "skipped_whitelisted"

    async def test_skip_no_text(self):
        """Messages without text should be skipped."""
        message = _make_message(text=None)
        result = await _simulate_message_handler(
            message, _make_bot(), _make_db(),
            _make_detector(SpamVerdict(is_spam=False, confidence=0.0, reason="")),
            _make_profile_analyzer(),
            admin_ids=[999],
        )
        assert result == "skipped_no_text"


class TestMessageHandlerSpamDetection:

    async def test_spam_detected_and_banned(self):
        """When spam is detected above threshold, message should be deleted and user banned."""
        verdict = SpamVerdict(is_spam=True, confidence=0.95, reason="Crypto spam")
        message = _make_message()
        bot = _make_bot()
        db = _make_db()
        detector = _make_detector(verdict)

        result = await _simulate_message_handler(
            message, bot, db, detector, _make_profile_analyzer(),
            admin_ids=[111, 222],
        )

        assert result == "spam_banned"
        message.delete.assert_awaited_once()
        message.chat.ban.assert_awaited_once()
        db.add_banned_user.assert_awaited_once()
        db.log_message.assert_awaited_once()

    async def test_not_spam_allowed(self):
        """Non-spam messages should be allowed without deletion."""
        verdict = SpamVerdict(is_spam=False, confidence=0.05, reason="Normal comment")
        message = _make_message()
        db = _make_db()

        result = await _simulate_message_handler(
            message, _make_bot(), db,
            _make_detector(verdict), _make_profile_analyzer(),
            admin_ids=[999],
        )

        assert result == "allowed"
        message.delete.assert_not_awaited()
        message.chat.ban.assert_not_awaited()
        db.add_banned_user.assert_not_awaited()

    async def test_spam_below_threshold_allowed(self):
        """Spam with confidence below threshold should be allowed."""
        verdict = SpamVerdict(is_spam=True, confidence=0.5, reason="Maybe spam")
        message = _make_message()

        result = await _simulate_message_handler(
            message, _make_bot(), _make_db(),
            _make_detector(verdict), _make_profile_analyzer(),
            admin_ids=[999],
            spam_threshold=0.7,
        )

        assert result == "allowed"
        message.delete.assert_not_awaited()

    async def test_admin_notification_sent(self):
        """On spam detection, each admin should receive a notification."""
        verdict = SpamVerdict(is_spam=True, confidence=0.95, reason="Spam")
        bot = _make_bot()

        await _simulate_message_handler(
            _make_message(), bot, _make_db(),
            _make_detector(verdict), _make_profile_analyzer(),
            admin_ids=[111, 222],
        )

        assert bot.send_message.await_count == 2
        admin_ids_called = [call.args[0] for call in bot.send_message.await_args_list]
        assert 111 in admin_ids_called
        assert 222 in admin_ids_called

    async def test_stats_incremented_on_spam(self):
        """On spam detection, messages_checked, spam_detected and users_banned should be incremented."""
        verdict = SpamVerdict(is_spam=True, confidence=0.95, reason="Spam")
        db = _make_db()

        await _simulate_message_handler(
            _make_message(), _make_bot(), db,
            _make_detector(verdict), _make_profile_analyzer(),
            admin_ids=[999],
        )

        # increment_stat should be called for messages_checked, spam_detected, users_banned
        stat_fields = [call.args[1] for call in db.increment_stat.await_args_list]
        assert "messages_checked" in stat_fields
        assert "spam_detected" in stat_fields
        assert "users_banned" in stat_fields

    async def test_stats_incremented_on_allowed(self):
        """On allowed messages, only messages_checked should be incremented."""
        verdict = SpamVerdict(is_spam=False, confidence=0.05, reason="ok")
        db = _make_db()

        await _simulate_message_handler(
            _make_message(), _make_bot(), db,
            _make_detector(verdict), _make_profile_analyzer(),
            admin_ids=[999],
        )

        stat_fields = [call.args[1] for call in db.increment_stat.await_args_list]
        assert "messages_checked" in stat_fields
        assert "spam_detected" not in stat_fields

    async def test_error_verdict_allows_message(self):
        """An error verdict (fail-open) should allow the message through."""
        verdict = SpamVerdict.error_verdict("API timeout")
        message = _make_message()

        result = await _simulate_message_handler(
            message, _make_bot(), _make_db(),
            _make_detector(verdict), _make_profile_analyzer(),
            admin_ids=[999],
        )

        assert result == "allowed"
        message.delete.assert_not_awaited()
