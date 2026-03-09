"""Async SQLite database layer using aiosqlite.

Provides CRUD operations for messages, bans, whitelist, spam examples,
and daily statistics.  All public methods handle aiosqlite errors
gracefully and re-raise them as ``DatabaseError``.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

import aiosqlite
import structlog

from src.exceptions import DatabaseError

log = structlog.get_logger(__name__)


class Database:
    """Async wrapper around an SQLite database for the antispam bot."""

    def __init__(self, database_path: str) -> None:
        self._path = database_path
        self._db: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the database connection and ensure tables exist."""
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        try:
            self._db = await aiosqlite.connect(self._path)
            self._db.row_factory = aiosqlite.Row
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA foreign_keys=ON")
            await self._create_tables()
            log.info("database.connected", path=self._path)
        except Exception as exc:
            raise DatabaseError(f"Failed to connect to database: {exc}") from exc

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            log.info("database.closed")

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise DatabaseError("Database is not connected. Call connect() first.")
        return self._db

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    async def _create_tables(self) -> None:
        await self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id      INTEGER NOT NULL,
                chat_id         BIGINT  NOT NULL,
                user_id         BIGINT  NOT NULL,
                username        TEXT,
                message_text    TEXT,
                is_edited       BOOLEAN DEFAULT 0,
                verdict_spam    BOOLEAN,
                verdict_confidence REAL,
                verdict_reason  TEXT,
                action_taken    TEXT    DEFAULT 'allowed',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_messages_chat_date
                ON messages (chat_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_messages_user
                ON messages (user_id);

            CREATE TABLE IF NOT EXISTS banned_users (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         BIGINT  NOT NULL,
                chat_id         BIGINT  NOT NULL,
                username        TEXT,
                reason          TEXT,
                confidence      REAL,
                message_text    TEXT,
                banned_by       TEXT    DEFAULT 'bot',
                unbanned        BOOLEAN DEFAULT 0,
                unbanned_by     BIGINT,
                unbanned_at     TIMESTAMP,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, chat_id)
            );

            CREATE TABLE IF NOT EXISTS whitelist (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         BIGINT  NOT NULL UNIQUE,
                username        TEXT,
                added_by        BIGINT,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS spam_examples (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         BIGINT  NOT NULL,
                username        TEXT,
                first_name      TEXT,
                last_name       TEXT,
                bio             TEXT,
                message_text    TEXT,
                has_profile_photo BOOLEAN DEFAULT 0,
                source          TEXT    DEFAULT 'admin_ban',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS stats (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            DATE    NOT NULL UNIQUE,
                messages_checked INTEGER DEFAULT 0,
                spam_detected   INTEGER DEFAULT 0,
                users_banned    INTEGER DEFAULT 0,
                false_positives INTEGER DEFAULT 0
            );
            """
        )
        await self.db.commit()

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    async def log_message(
        self,
        message_id: int,
        chat_id: int,
        user_id: int,
        username: str | None,
        message_text: str | None,
        is_edited: bool,
        verdict_spam: bool | None,
        verdict_confidence: float | None,
        verdict_reason: str | None,
        action_taken: str = "allowed",
    ) -> int:
        """Insert a processed message record. Returns the row id."""
        try:
            cursor = await self.db.execute(
                """
                INSERT INTO messages
                    (message_id, chat_id, user_id, username, message_text,
                     is_edited, verdict_spam, verdict_confidence, verdict_reason,
                     action_taken)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    chat_id,
                    user_id,
                    username,
                    message_text,
                    is_edited,
                    verdict_spam,
                    verdict_confidence,
                    verdict_reason,
                    action_taken,
                ),
            )
            await self.db.commit()
            log.debug(
                "database.message_logged",
                message_id=message_id,
                chat_id=chat_id,
                user_id=user_id,
                action=action_taken,
            )
            return cursor.lastrowid  # type: ignore[return-value]
        except Exception as exc:
            raise DatabaseError(f"Failed to log message: {exc}") from exc

    # ------------------------------------------------------------------
    # Banned users
    # ------------------------------------------------------------------

    async def add_banned_user(
        self,
        user_id: int,
        chat_id: int,
        username: str | None = None,
        reason: str | None = None,
        confidence: float | None = None,
        message_text: str | None = None,
        banned_by: str = "bot",
    ) -> int:
        """Record a ban. Uses INSERT OR REPLACE to handle re-bans."""
        try:
            cursor = await self.db.execute(
                """
                INSERT INTO banned_users
                    (user_id, chat_id, username, reason, confidence,
                     message_text, banned_by, unbanned, unbanned_by, unbanned_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL)
                ON CONFLICT(user_id, chat_id) DO UPDATE SET
                    username     = excluded.username,
                    reason       = excluded.reason,
                    confidence   = excluded.confidence,
                    message_text = excluded.message_text,
                    banned_by    = excluded.banned_by,
                    unbanned     = 0,
                    unbanned_by  = NULL,
                    unbanned_at  = NULL,
                    created_at   = CURRENT_TIMESTAMP
                """,
                (user_id, chat_id, username, reason, confidence, message_text, banned_by),
            )
            await self.db.commit()
            log.info(
                "database.user_banned",
                user_id=user_id,
                chat_id=chat_id,
                banned_by=banned_by,
            )
            return cursor.lastrowid  # type: ignore[return-value]
        except Exception as exc:
            raise DatabaseError(f"Failed to ban user: {exc}") from exc

    async def remove_banned_user(
        self,
        user_id: int,
        chat_id: int,
        unbanned_by: int | None = None,
    ) -> bool:
        """Mark a user as unbanned (soft-delete). Returns True if a row was updated."""
        try:
            cursor = await self.db.execute(
                """
                UPDATE banned_users
                SET unbanned    = 1,
                    unbanned_by = ?,
                    unbanned_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND chat_id = ? AND unbanned = 0
                """,
                (unbanned_by, user_id, chat_id),
            )
            await self.db.commit()
            updated = cursor.rowcount > 0
            if updated:
                log.info(
                    "database.user_unbanned",
                    user_id=user_id,
                    chat_id=chat_id,
                    unbanned_by=unbanned_by,
                )
            return updated
        except Exception as exc:
            raise DatabaseError(f"Failed to unban user: {exc}") from exc

    async def is_banned(self, user_id: int, chat_id: int) -> bool:
        """Check whether a user is currently banned in a chat."""
        try:
            cursor = await self.db.execute(
                """
                SELECT 1 FROM banned_users
                WHERE user_id = ? AND chat_id = ? AND unbanned = 0
                LIMIT 1
                """,
                (user_id, chat_id),
            )
            return (await cursor.fetchone()) is not None
        except Exception as exc:
            raise DatabaseError(f"Failed to check ban status: {exc}") from exc

    async def get_banned_users(self, chat_id: int, limit: int = 50) -> list[dict[str, Any]]:
        """Return a list of currently banned users for a chat."""
        try:
            cursor = await self.db.execute(
                """
                SELECT user_id, chat_id, username, reason, confidence,
                       message_text, banned_by, created_at
                FROM banned_users
                WHERE chat_id = ? AND unbanned = 0
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (chat_id, limit),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            raise DatabaseError(f"Failed to get banned users: {exc}") from exc

    # ------------------------------------------------------------------
    # Whitelist
    # ------------------------------------------------------------------

    async def add_to_whitelist(
        self,
        user_id: int,
        username: str | None = None,
        added_by: int | None = None,
    ) -> bool:
        """Add a user to the whitelist. Returns True on success, False if already present."""
        try:
            await self.db.execute(
                """
                INSERT OR IGNORE INTO whitelist (user_id, username, added_by)
                VALUES (?, ?, ?)
                """,
                (user_id, username, added_by),
            )
            await self.db.commit()
            log.info("database.whitelist_added", user_id=user_id, added_by=added_by)
            return True
        except Exception as exc:
            raise DatabaseError(f"Failed to add to whitelist: {exc}") from exc

    async def remove_from_whitelist(self, user_id: int) -> bool:
        """Remove a user from the whitelist. Returns True if a row was deleted."""
        try:
            cursor = await self.db.execute(
                "DELETE FROM whitelist WHERE user_id = ?",
                (user_id,),
            )
            await self.db.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                log.info("database.whitelist_removed", user_id=user_id)
            return deleted
        except Exception as exc:
            raise DatabaseError(f"Failed to remove from whitelist: {exc}") from exc

    async def is_whitelisted(self, user_id: int) -> bool:
        """Check whether a user is on the whitelist."""
        try:
            cursor = await self.db.execute(
                "SELECT 1 FROM whitelist WHERE user_id = ? LIMIT 1",
                (user_id,),
            )
            return (await cursor.fetchone()) is not None
        except Exception as exc:
            raise DatabaseError(f"Failed to check whitelist: {exc}") from exc

    async def get_whitelist(self) -> list[dict[str, Any]]:
        """Return all whitelisted users."""
        try:
            cursor = await self.db.execute(
                "SELECT user_id, username, added_by, created_at FROM whitelist ORDER BY created_at DESC"
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            raise DatabaseError(f"Failed to get whitelist: {exc}") from exc

    # ------------------------------------------------------------------
    # Spam examples (few-shot)
    # ------------------------------------------------------------------

    async def add_spam_example(
        self,
        user_id: int,
        message_text: str,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        bio: str | None = None,
        has_profile_photo: bool = False,
        source: str = "admin_ban",
    ) -> int:
        """Store a confirmed spam example for few-shot prompting."""
        try:
            cursor = await self.db.execute(
                """
                INSERT INTO spam_examples
                    (user_id, username, first_name, last_name, bio,
                     message_text, has_profile_photo, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, username, first_name, last_name, bio, message_text,
                 has_profile_photo, source),
            )
            await self.db.commit()
            log.info("database.spam_example_added", user_id=user_id, source=source)
            return cursor.lastrowid  # type: ignore[return-value]
        except Exception as exc:
            raise DatabaseError(f"Failed to add spam example: {exc}") from exc

    async def get_spam_examples(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return the most recent spam examples for few-shot prompting."""
        try:
            cursor = await self.db.execute(
                """
                SELECT user_id, username, first_name, last_name, bio,
                       message_text, has_profile_photo, source, created_at
                FROM spam_examples
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            raise DatabaseError(f"Failed to get spam examples: {exc}") from exc

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    async def increment_stat(
        self,
        date_str: str,
        field: str,
        amount: int = 1,
    ) -> None:
        """Increment a daily stat counter (upsert).

        Args:
            date_str: Date in ``YYYY-MM-DD`` format.
            field: One of ``messages_checked``, ``spam_detected``,
                   ``users_banned``, ``false_positives``.
            amount: Amount to add (default 1).
        """
        allowed_fields = {"messages_checked", "spam_detected", "users_banned", "false_positives"}
        if field not in allowed_fields:
            raise DatabaseError(f"Invalid stat field: {field}. Must be one of {allowed_fields}")

        try:
            await self.db.execute(
                f"""
                INSERT INTO stats (date, {field})
                VALUES (?, ?)
                ON CONFLICT(date) DO UPDATE
                SET {field} = {field} + ?
                """,
                (date_str, amount, amount),
            )
            await self.db.commit()
        except Exception as exc:
            raise DatabaseError(f"Failed to increment stat: {exc}") from exc

    async def get_stats(self, days: int | None = None) -> dict[str, int]:
        """Return aggregated totals, optionally filtered to the last N days."""
        try:
            if days is not None:
                since = (date.today() - timedelta(days=days)).isoformat()
                cursor = await self.db.execute(
                    """
                    SELECT
                        COALESCE(SUM(messages_checked), 0) AS messages_checked,
                        COALESCE(SUM(spam_detected), 0)    AS spam_detected,
                        COALESCE(SUM(users_banned), 0)     AS users_banned,
                        COALESCE(SUM(false_positives), 0)  AS false_positives
                    FROM stats
                    WHERE date >= ?
                    """,
                    (since,),
                )
            else:
                cursor = await self.db.execute(
                    """
                    SELECT
                        COALESCE(SUM(messages_checked), 0) AS messages_checked,
                        COALESCE(SUM(spam_detected), 0)    AS spam_detected,
                        COALESCE(SUM(users_banned), 0)     AS users_banned,
                        COALESCE(SUM(false_positives), 0)  AS false_positives
                    FROM stats
                    """
                )
            row = await cursor.fetchone()
            return dict(row) if row else {
                "messages_checked": 0,
                "spam_detected": 0,
                "users_banned": 0,
                "false_positives": 0,
            }
        except Exception as exc:
            raise DatabaseError(f"Failed to get stats: {exc}") from exc

    async def get_daily_stats(self, days: int = 30) -> list[dict[str, Any]]:
        """Return per-day statistics for the last N days."""
        try:
            since = (date.today() - timedelta(days=days)).isoformat()
            cursor = await self.db.execute(
                """
                SELECT date, messages_checked, spam_detected,
                       users_banned, false_positives
                FROM stats
                WHERE date >= ?
                ORDER BY date DESC
                """,
                (since,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            raise DatabaseError(f"Failed to get daily stats: {exc}") from exc
