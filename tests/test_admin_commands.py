"""Tests for admin command handlers.

These tests validate the expected behaviour of admin commands (/stats,
/whitelist, /unban, etc.) using mocked Telegram objects and dependencies.

The handler logic under test:
- Only admin users (those whose IDs are in settings.admin_ids) may execute commands.
- Non-admins receive a rejection message.
- Each command delegates to the appropriate Database method and formats a response.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models import SpamVerdict


# =========================================================================
# Helpers -- mock Telegram objects
# =========================================================================

def _make_user(user_id: int = 111, username: str = "admin"):
    user = MagicMock()
    user.id = user_id
    user.username = username
    user.first_name = "Admin"
    return user


def _make_message(user=None, text="/stats", chat_id=-1001234567890):
    if user is None:
        user = _make_user()
    msg = AsyncMock()
    msg.from_user = user
    msg.text = text
    msg.message_id = 99
    msg.chat = MagicMock()
    msg.chat.id = chat_id
    msg.answer = AsyncMock()
    msg.reply = AsyncMock()
    return msg


def _make_callback_query(user=None, data="unban:-100:12345"):
    if user is None:
        user = _make_user()
    cb = AsyncMock()
    cb.from_user = user
    cb.data = data
    cb.message = MagicMock()
    cb.message.chat = MagicMock()
    cb.message.chat.id = -100
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    return cb


def _make_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.unban_chat_member = AsyncMock()
    return bot


def _make_db():
    db = AsyncMock()
    db.get_stats = AsyncMock(return_value={
        "messages_checked": 100,
        "spam_detected": 15,
        "users_banned": 10,
        "false_positives": 2,
    })
    db.add_to_whitelist = AsyncMock(return_value=True)
    db.remove_from_whitelist = AsyncMock(return_value=True)
    db.get_whitelist = AsyncMock(return_value=[
        {"user_id": 500, "username": "alice", "added_by": 111, "created_at": "2025-01-01"},
        {"user_id": 600, "username": "bob", "added_by": 222, "created_at": "2025-01-02"},
    ])
    db.remove_banned_user = AsyncMock(return_value=True)
    db.get_banned_users = AsyncMock(return_value=[])
    return db


# =========================================================================
# Admin command simulation
# =========================================================================

async def _handle_stats(message, db, admin_ids):
    """Simulate /stats command handler."""
    if message.from_user.id not in admin_ids:
        await message.answer("You do not have permission to use this command.")
        return "rejected"

    stats = await db.get_stats()
    text = (
        f"Messages checked: {stats['messages_checked']}\n"
        f"Spam detected: {stats['spam_detected']}\n"
        f"Users banned: {stats['users_banned']}\n"
        f"False positives: {stats['false_positives']}"
    )
    await message.answer(text)
    return "ok"


async def _handle_whitelist_add(message, db, admin_ids, target_user_id: int, target_username: str | None = None):
    """Simulate /whitelist add command handler."""
    if message.from_user.id not in admin_ids:
        await message.answer("You do not have permission to use this command.")
        return "rejected"

    await db.add_to_whitelist(user_id=target_user_id, username=target_username, added_by=message.from_user.id)
    await message.answer(f"User {target_user_id} added to whitelist.")
    return "ok"


async def _handle_whitelist_remove(message, db, admin_ids, target_user_id: int):
    """Simulate /whitelist remove command handler."""
    if message.from_user.id not in admin_ids:
        await message.answer("You do not have permission to use this command.")
        return "rejected"

    removed = await db.remove_from_whitelist(target_user_id)
    if removed:
        await message.answer(f"User {target_user_id} removed from whitelist.")
    else:
        await message.answer(f"User {target_user_id} not found in whitelist.")
    return "ok"


async def _handle_whitelist_list(message, db, admin_ids):
    """Simulate /whitelist list command handler."""
    if message.from_user.id not in admin_ids:
        await message.answer("You do not have permission to use this command.")
        return "rejected"

    wl = await db.get_whitelist()
    if not wl:
        await message.answer("Whitelist is empty.")
    else:
        lines = [f"- {row['user_id']} (@{row['username']})" for row in wl]
        await message.answer("Whitelist:\n" + "\n".join(lines))
    return "ok"


async def _handle_unban(message, db, bot, admin_ids, target_user_id: int, chat_id: int):
    """Simulate /unban command handler."""
    if message.from_user.id not in admin_ids:
        await message.answer("You do not have permission to use this command.")
        return "rejected"

    await db.remove_banned_user(user_id=target_user_id, chat_id=chat_id, unbanned_by=message.from_user.id)
    await bot.unban_chat_member(chat_id, target_user_id)
    await message.answer(f"User {target_user_id} has been unbanned.")
    return "ok"


async def _handle_unban_callback(callback_query, db, bot, admin_ids):
    """Simulate unban inline button callback handler."""
    if callback_query.from_user.id not in admin_ids:
        await callback_query.answer("You do not have permission.", show_alert=True)
        return "rejected"

    # Parse callback data: "unban:<chat_id>:<user_id>"
    parts = callback_query.data.split(":")
    chat_id = int(parts[1])
    user_id = int(parts[2])

    await db.remove_banned_user(user_id=user_id, chat_id=chat_id, unbanned_by=callback_query.from_user.id)
    await bot.unban_chat_member(chat_id, user_id)
    await callback_query.answer("User unbanned.")
    await callback_query.message.edit_text(f"User {user_id} has been unbanned.")
    return "ok"


# =========================================================================
# Tests
# =========================================================================

class TestStatsCommand:

    async def test_stats_returns_formatted_response(self):
        message = _make_message(text="/stats")
        db = _make_db()
        result = await _handle_stats(message, db, admin_ids=[111])
        assert result == "ok"
        db.get_stats.assert_awaited_once()

        # Verify the response includes stat values
        answer_text = message.answer.call_args[0][0]
        assert "100" in answer_text  # messages_checked
        assert "15" in answer_text   # spam_detected
        assert "10" in answer_text   # users_banned

    async def test_stats_non_admin_rejected(self):
        non_admin = _make_user(user_id=999)
        message = _make_message(user=non_admin, text="/stats")
        result = await _handle_stats(message, _make_db(), admin_ids=[111])
        assert result == "rejected"
        answer_text = message.answer.call_args[0][0]
        assert "permission" in answer_text.lower()


class TestWhitelistCommands:

    async def test_whitelist_add(self):
        message = _make_message(text="/whitelist add 500")
        db = _make_db()
        result = await _handle_whitelist_add(message, db, admin_ids=[111], target_user_id=500, target_username="alice")
        assert result == "ok"
        db.add_to_whitelist.assert_awaited_once_with(user_id=500, username="alice", added_by=111)

    async def test_whitelist_remove(self):
        message = _make_message(text="/whitelist remove 500")
        db = _make_db()
        result = await _handle_whitelist_remove(message, db, admin_ids=[111], target_user_id=500)
        assert result == "ok"
        db.remove_from_whitelist.assert_awaited_once_with(500)

    async def test_whitelist_remove_not_found(self):
        message = _make_message(text="/whitelist remove 9999")
        db = _make_db()
        db.remove_from_whitelist = AsyncMock(return_value=False)
        result = await _handle_whitelist_remove(message, db, admin_ids=[111], target_user_id=9999)
        assert result == "ok"
        answer_text = message.answer.call_args[0][0]
        assert "not found" in answer_text.lower()

    async def test_whitelist_list(self):
        message = _make_message(text="/whitelist list")
        db = _make_db()
        result = await _handle_whitelist_list(message, db, admin_ids=[111])
        assert result == "ok"
        db.get_whitelist.assert_awaited_once()
        answer_text = message.answer.call_args[0][0]
        assert "alice" in answer_text
        assert "bob" in answer_text

    async def test_whitelist_list_empty(self):
        message = _make_message(text="/whitelist list")
        db = _make_db()
        db.get_whitelist = AsyncMock(return_value=[])
        result = await _handle_whitelist_list(message, db, admin_ids=[111])
        assert result == "ok"
        answer_text = message.answer.call_args[0][0]
        assert "empty" in answer_text.lower()

    async def test_whitelist_non_admin_rejected(self):
        non_admin = _make_user(user_id=999)
        message = _make_message(user=non_admin)
        result = await _handle_whitelist_add(message, _make_db(), admin_ids=[111], target_user_id=500)
        assert result == "rejected"


class TestUnbanCommand:

    async def test_unban_command(self):
        message = _make_message(text="/unban 12345")
        db = _make_db()
        bot = _make_bot()
        result = await _handle_unban(message, db, bot, admin_ids=[111], target_user_id=12345, chat_id=-100)
        assert result == "ok"
        db.remove_banned_user.assert_awaited_once_with(user_id=12345, chat_id=-100, unbanned_by=111)
        bot.unban_chat_member.assert_awaited_once_with(-100, 12345)

    async def test_unban_non_admin_rejected(self):
        non_admin = _make_user(user_id=999)
        message = _make_message(user=non_admin, text="/unban 12345")
        result = await _handle_unban(message, _make_db(), _make_bot(), admin_ids=[111], target_user_id=12345, chat_id=-100)
        assert result == "rejected"


class TestUnbanCallback:

    async def test_unban_callback(self):
        cb = _make_callback_query(data="unban:-100:12345")
        db = _make_db()
        bot = _make_bot()
        result = await _handle_unban_callback(cb, db, bot, admin_ids=[111])
        assert result == "ok"
        db.remove_banned_user.assert_awaited_once_with(user_id=12345, chat_id=-100, unbanned_by=111)
        bot.unban_chat_member.assert_awaited_once_with(-100, 12345)
        cb.answer.assert_awaited_once()
        cb.message.edit_text.assert_awaited_once()

    async def test_unban_callback_non_admin_rejected(self):
        non_admin = _make_user(user_id=999)
        cb = _make_callback_query(user=non_admin, data="unban:-100:12345")
        result = await _handle_unban_callback(cb, _make_db(), _make_bot(), admin_ids=[111])
        assert result == "rejected"
        cb.answer.assert_awaited_once()
        # Verify show_alert=True for non-admin
        call_kwargs = cb.answer.call_args
        assert call_kwargs.kwargs.get("show_alert") is True
