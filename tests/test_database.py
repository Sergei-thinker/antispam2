"""Tests for src.database -- async SQLite CRUD operations.

Every test uses a fresh in-memory-like temporary database via the ``db`` fixture.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.database import Database
from src.exceptions import DatabaseError


# =========================================================================
# Connection & lifecycle
# =========================================================================

class TestDatabaseLifecycle:

    async def test_connect_creates_tables(self, db):
        """After connect(), all required tables should exist."""
        cursor = await db.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        rows = await cursor.fetchall()
        table_names = sorted(row["name"] for row in rows)
        for expected in ("banned_users", "messages", "spam_examples", "stats", "whitelist"):
            assert expected in table_names, f"Table {expected} not found"

    async def test_db_property_raises_when_not_connected(self, db_path):
        """Accessing .db before connect() should raise DatabaseError."""
        database = Database(db_path)
        with pytest.raises(DatabaseError, match="not connected"):
            _ = database.db


# =========================================================================
# Messages
# =========================================================================

class TestMessages:

    async def test_log_message(self, db):
        row_id = await db.log_message(
            message_id=1,
            chat_id=-100,
            user_id=42,
            username="alice",
            message_text="Hello!",
            is_edited=False,
            verdict_spam=False,
            verdict_confidence=0.1,
            verdict_reason="Normal",
            action_taken="allowed",
        )
        assert isinstance(row_id, int)
        assert row_id > 0

    async def test_log_message_with_none_fields(self, db):
        """Optional fields can be None."""
        row_id = await db.log_message(
            message_id=2,
            chat_id=-100,
            user_id=42,
            username=None,
            message_text=None,
            is_edited=False,
            verdict_spam=None,
            verdict_confidence=None,
            verdict_reason=None,
        )
        assert row_id > 0

    async def test_log_multiple_messages(self, db):
        """Inserting multiple messages should produce different row ids."""
        ids = []
        for i in range(5):
            rid = await db.log_message(
                message_id=i,
                chat_id=-100,
                user_id=42,
                username="bob",
                message_text=f"msg {i}",
                is_edited=False,
                verdict_spam=False,
                verdict_confidence=0.0,
                verdict_reason="ok",
            )
            ids.append(rid)
        assert len(set(ids)) == 5  # all unique


# =========================================================================
# Banned users
# =========================================================================

class TestBannedUsers:

    async def test_add_banned_user(self, db):
        row_id = await db.add_banned_user(
            user_id=100,
            chat_id=-1001,
            username="spammer",
            reason="Crypto spam",
            confidence=0.95,
            message_text="Buy BTC now!!!",
        )
        assert isinstance(row_id, int)

    async def test_is_banned(self, db):
        await db.add_banned_user(user_id=100, chat_id=-1001)
        assert await db.is_banned(100, -1001) is True

    async def test_is_not_banned(self, db):
        assert await db.is_banned(999, -1001) is False

    async def test_remove_banned_user(self, db):
        """Removing a ban (soft delete) should make is_banned return False."""
        await db.add_banned_user(user_id=100, chat_id=-1001)
        assert await db.is_banned(100, -1001) is True

        removed = await db.remove_banned_user(user_id=100, chat_id=-1001, unbanned_by=777)
        assert removed is True
        assert await db.is_banned(100, -1001) is False

    async def test_remove_nonexistent_user(self, db):
        """Removing a non-existent ban should return False."""
        removed = await db.remove_banned_user(user_id=9999, chat_id=-1001)
        assert removed is False

    async def test_get_banned_users(self, db):
        """get_banned_users should return all currently banned users for a chat."""
        await db.add_banned_user(user_id=100, chat_id=-1001, username="a")
        await db.add_banned_user(user_id=200, chat_id=-1001, username="b")
        await db.add_banned_user(user_id=300, chat_id=-9999, username="c")  # different chat

        banned = await db.get_banned_users(-1001)
        user_ids = [row["user_id"] for row in banned]
        assert 100 in user_ids
        assert 200 in user_ids
        assert 300 not in user_ids  # different chat

    async def test_add_banned_user_duplicate_upsert(self, db):
        """Adding the same user+chat twice should upsert, not raise."""
        await db.add_banned_user(user_id=100, chat_id=-1001, reason="first")
        # Should not raise
        await db.add_banned_user(user_id=100, chat_id=-1001, reason="second")
        assert await db.is_banned(100, -1001) is True

    async def test_reban_after_unban(self, db):
        """Unbanning then re-banning should work via upsert."""
        await db.add_banned_user(user_id=100, chat_id=-1001)
        await db.remove_banned_user(user_id=100, chat_id=-1001)
        assert await db.is_banned(100, -1001) is False

        await db.add_banned_user(user_id=100, chat_id=-1001, reason="re-banned")
        assert await db.is_banned(100, -1001) is True


# =========================================================================
# Whitelist
# =========================================================================

class TestWhitelist:

    async def test_add_to_whitelist(self, db):
        result = await db.add_to_whitelist(user_id=500, username="trusted", added_by=111)
        assert result is True

    async def test_is_whitelisted(self, db):
        await db.add_to_whitelist(user_id=500)
        assert await db.is_whitelisted(500) is True

    async def test_is_not_whitelisted(self, db):
        assert await db.is_whitelisted(9999) is False

    async def test_remove_from_whitelist(self, db):
        await db.add_to_whitelist(user_id=500)
        assert await db.is_whitelisted(500) is True

        removed = await db.remove_from_whitelist(500)
        assert removed is True
        assert await db.is_whitelisted(500) is False

    async def test_remove_nonexistent_from_whitelist(self, db):
        removed = await db.remove_from_whitelist(9999)
        assert removed is False

    async def test_get_whitelist(self, db):
        await db.add_to_whitelist(user_id=500, username="a")
        await db.add_to_whitelist(user_id=600, username="b")
        await db.add_to_whitelist(user_id=700, username="c")

        wl = await db.get_whitelist()
        user_ids = [row["user_id"] for row in wl]
        assert 500 in user_ids
        assert 600 in user_ids
        assert 700 in user_ids

    async def test_add_to_whitelist_duplicate(self, db):
        """Adding the same user twice should not raise (INSERT OR IGNORE)."""
        await db.add_to_whitelist(user_id=500)
        # Should not raise
        result = await db.add_to_whitelist(user_id=500)
        assert result is True

        # Should still appear only once
        wl = await db.get_whitelist()
        ids = [row["user_id"] for row in wl]
        assert ids.count(500) == 1


# =========================================================================
# Spam examples
# =========================================================================

class TestSpamExamples:

    async def test_add_spam_example(self, db):
        row_id = await db.add_spam_example(
            user_id=100,
            message_text="Buy crypto now!!!",
            username="spammer",
            first_name="Spam",
            last_name="Bot",
            bio="Crypto trader",
            has_profile_photo=False,
            source="admin_ban",
        )
        assert isinstance(row_id, int)
        assert row_id > 0

    async def test_get_spam_examples(self, db):
        """Add several examples, verify limit and newest-first order."""
        for i in range(5):
            await db.add_spam_example(user_id=i, message_text=f"spam {i}")

        examples = await db.get_spam_examples(limit=3)
        assert len(examples) == 3
        # Newest first -- last inserted should come first
        assert examples[0]["message_text"] == "spam 4"

    async def test_get_spam_examples_default_limit(self, db):
        for i in range(15):
            await db.add_spam_example(user_id=i, message_text=f"spam {i}")

        examples = await db.get_spam_examples()  # default limit=10
        assert len(examples) == 10

    async def test_get_spam_examples_empty(self, db):
        examples = await db.get_spam_examples()
        assert examples == []


# =========================================================================
# Statistics
# =========================================================================

class TestStatistics:

    async def test_increment_stat(self, db):
        today = date.today().isoformat()
        await db.increment_stat(today, "messages_checked")

        stats = await db.get_stats()
        assert stats["messages_checked"] == 1

    async def test_increment_stat_multiple(self, db):
        """Incrementing the same field several times should accumulate."""
        today = date.today().isoformat()
        for _ in range(5):
            await db.increment_stat(today, "messages_checked")
        await db.increment_stat(today, "spam_detected", amount=3)

        stats = await db.get_stats()
        assert stats["messages_checked"] == 5
        assert stats["spam_detected"] == 3

    async def test_increment_stat_invalid_field(self, db):
        """An invalid stat field should raise DatabaseError."""
        with pytest.raises(DatabaseError, match="Invalid stat field"):
            await db.increment_stat(date.today().isoformat(), "nonexistent_field")

    async def test_get_stats_all_time(self, db):
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        await db.increment_stat(today, "messages_checked", amount=10)
        await db.increment_stat(yesterday, "messages_checked", amount=5)
        await db.increment_stat(today, "spam_detected", amount=3)

        stats = await db.get_stats()  # no day filter
        assert stats["messages_checked"] == 15
        assert stats["spam_detected"] == 3

    async def test_get_stats_filtered_by_days(self, db):
        today = date.today().isoformat()
        old = (date.today() - timedelta(days=60)).isoformat()

        await db.increment_stat(today, "messages_checked", amount=10)
        await db.increment_stat(old, "messages_checked", amount=100)

        stats_30 = await db.get_stats(days=30)
        assert stats_30["messages_checked"] == 10  # old data excluded

        stats_all = await db.get_stats()
        assert stats_all["messages_checked"] == 110  # all data included

    async def test_get_stats_empty(self, db):
        stats = await db.get_stats()
        assert stats["messages_checked"] == 0
        assert stats["spam_detected"] == 0
        assert stats["users_banned"] == 0
        assert stats["false_positives"] == 0

    async def test_get_daily_stats(self, db):
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        await db.increment_stat(today, "messages_checked", amount=10)
        await db.increment_stat(today, "spam_detected", amount=2)
        await db.increment_stat(yesterday, "messages_checked", amount=5)

        daily = await db.get_daily_stats(days=7)
        assert len(daily) == 2
        # Newest first
        assert daily[0]["date"] == today
        assert daily[0]["messages_checked"] == 10
        assert daily[1]["date"] == yesterday

    async def test_get_daily_stats_empty(self, db):
        daily = await db.get_daily_stats(days=7)
        assert daily == []
