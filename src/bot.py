"""Main bot class orchestrating all components of the Anti-Spam Bot v2.

Creates the aiogram Bot and Dispatcher, wires up middleware, routers,
and message handlers, then starts long-polling.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatType
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
import structlog

from .admin_commands import router as admin_router
from .config import Settings, get_settings
from .database import Database
from .middleware import DependencyMiddleware
from .models import SpamAction, SpamVerdict
from .profile_analyzer import ProfileAnalyzer
from .spam_detector import SpamDetector

logger = structlog.get_logger(__name__)

message_router = Router(name="messages")


# ---------------------------------------------------------------------------
# Message handlers (registered on message_router)
# ---------------------------------------------------------------------------

async def _process_message(
    message: Message,
    db: Database,
    detector: SpamDetector,
    settings: Settings,
    profile_analyzer: ProfileAnalyzer,
    is_edited: bool = False,
) -> None:
    """Core message processing logic shared by new and edited message handlers."""
    today_str = date.today().isoformat()

    logger.info(
        "message.received",
        chat_id=message.chat.id,
        chat_type=message.chat.type,
        user_id=message.from_user.id if message.from_user else None,
        text_preview=(message.text or message.caption or "")[:50],
    )

    # --- Guard clauses ---

    # Skip auto-forwarded channel posts (channel's own content mirrored to group)
    if getattr(message, "is_automatic_forward", False):
        logger.debug("message.skip_auto_forward")
        return

    if message.from_user is None:
        logger.info("message.skip_no_user")
        return

    # Determine the real sender: either a channel (sender_chat) or a user (from_user)
    sender_chat = getattr(message, "sender_chat", None)
    is_channel_comment = (
        message.from_user.id == 136817688  # Channel_Bot
        and sender_chat is not None
    )
    is_anon_admin = message.from_user.id == 1087968824  # GroupAnonymousBot

    if is_anon_admin:
        logger.debug("message.skip_anon_admin")
        return

    # Skip real bots (not Channel_Bot relaying channel messages)
    if message.from_user.is_bot and not is_channel_comment:
        logger.info("message.skip_is_bot", user_id=message.from_user.id)
        return

    # For channel comments, use sender_chat info; for users, use from_user
    if is_channel_comment:
        effective_user_id = sender_chat.id
        effective_username = getattr(sender_chat, "username", None)
        effective_name = sender_chat.title or "Channel"
        logger.info(
            "message.channel_comment",
            channel_id=sender_chat.id,
            channel_title=sender_chat.title,
        )
    else:
        effective_user_id = message.from_user.id
        effective_username = message.from_user.username
        effective_name = message.from_user.first_name or ""

    if not is_channel_comment and is_admin(message.from_user.id, settings):
        logger.info("message.skip_admin", user_id=message.from_user.id)
        return

    if await db.is_whitelisted(effective_user_id):
        logger.info("message.skip_whitelisted", user_id=effective_user_id)
        return

    text = message.text or message.caption or ""
    if not text.strip():
        logger.info("message.skip_empty")
        return

    # Always count as checked
    await db.increment_stat(today_str, "messages_checked")

    # --- Profile ---
    from .models import UserProfile
    if is_channel_comment:
        # Channel comment: build profile from sender_chat
        profile = UserProfile(
            user_id=effective_user_id,
            first_name=effective_name,
            last_name=None,
            username=effective_username,
        )
    else:
        try:
            profile = await profile_analyzer.get_profile(message.from_user, message.chat.id)
        except Exception as exc:
            logger.error("message.profile_error", user_id=message.from_user.id, error=str(exc))
            profile = UserProfile(
                user_id=message.from_user.id,
                first_name=message.from_user.first_name or "",
                last_name=message.from_user.last_name,
                username=message.from_user.username,
            )

    # --- Few-shot examples ---
    try:
        examples = await db.get_spam_examples(limit=settings.max_few_shot_examples)
    except Exception as exc:
        logger.warning("message.examples_error", error=str(exc))
        examples = []

    # --- AI analysis ---
    verdict: SpamVerdict = await detector.analyze(text, profile, examples)

    # --- Act on verdict ---
    if verdict.is_spam and verdict.confidence >= settings.spam_confidence_threshold:
        # 1. Delete the message
        try:
            await message.delete()
        except Exception as exc:
            logger.warning("message.delete_error", error=str(exc))

        # 2. Ban the sender (for channels: ban sender_chat; for users: ban user)
        try:
            if is_channel_comment and sender_chat:
                await message.chat.ban_sender_chat(sender_chat.id)
            else:
                await message.chat.ban(message.from_user.id)
        except Exception as exc:
            logger.warning("message.ban_error", error=str(exc))

        # 3. Log to DB
        await db.log_message(
            message_id=message.message_id,
            chat_id=message.chat.id,
            user_id=effective_user_id,
            username=effective_username,
            message_text=text,
            is_edited=is_edited,
            verdict_spam=verdict.is_spam,
            verdict_confidence=verdict.confidence,
            verdict_reason=verdict.reason,
            action_taken=SpamAction.DELETED_AND_BANNED.value,
        )

        # 4. Record banned user
        await db.add_banned_user(
            user_id=effective_user_id,
            chat_id=message.chat.id,
            username=effective_username,
            reason=verdict.reason,
            confidence=verdict.confidence,
            message_text=text[:500],
            banned_by="bot",
        )

        # 5. Save as spam example for few-shot learning
        await db.add_spam_example(
            user_id=effective_user_id,
            message_text=text,
            username=effective_username,
            first_name=profile.first_name,
            last_name=profile.last_name,
            bio=profile.bio,
            has_profile_photo=profile.has_profile_photo,
            source="auto_ban",
        )

        # 6. Update stats
        await db.increment_stat(today_str, "spam_detected")
        await db.increment_stat(today_str, "users_banned")

        # 7. Notify admins
        await _notify_admins(message, verdict, text, settings)

        logger.info(
            "message.spam_banned",
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            confidence=verdict.confidence,
            reason=verdict.reason,
            is_edited=is_edited,
        )
    else:
        # Not spam or below threshold -- allow
        action = SpamAction.ALLOWED.value
        if verdict.confidence == 0.0 and "error" in verdict.reason.lower():
            action = SpamAction.ERROR_ALLOWED.value

        await db.log_message(
            message_id=message.message_id,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            username=message.from_user.username,
            message_text=text,
            is_edited=is_edited,
            verdict_spam=verdict.is_spam,
            verdict_confidence=verdict.confidence,
            verdict_reason=verdict.reason,
            action_taken=action,
        )

        logger.debug(
            "message.allowed",
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            confidence=verdict.confidence,
            is_edited=is_edited,
        )


async def _notify_admins(
    message: Message,
    verdict: SpamVerdict,
    text: str,
    settings: Settings,
) -> None:
    """Send a ban notification to every configured admin."""
    user = message.from_user
    if user is None:
        return

    first_name = user.first_name or "Unknown"
    username_part = f" (@{user.username})" if user.username else ""
    chat_title = message.chat.title or str(message.chat.id)
    truncated_text = text[:200]
    if len(text) > 200:
        truncated_text += "..."

    notification = (
        "Авто-бан\n"
        "\n"
        f"Пользователь: {first_name}{username_part} [{user.id}]\n"
        f"Чат: {chat_title}\n"
        f"Причина: {verdict.reason}\n"
        f"Уверенность: {verdict.confidence:.0%}\n"
        "\n"
        f"Сообщение:\n"
        f"{truncated_text}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Разбанить",
                    callback_data=f"unban:{message.chat.id}:{user.id}",
                ),
            ],
        ],
    )

    bot: Bot = message.bot  # type: ignore[assignment]
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, notification, reply_markup=keyboard)
        except Exception as exc:
            logger.warning(
                "notify.admin_error",
                admin_id=admin_id,
                error=str(exc),
            )


def is_admin(user_id: int, settings: Settings) -> bool:
    """Check whether *user_id* is an admin."""
    return user_id in settings.admin_ids


# --- Register handlers on message_router ---

@message_router.message(F.chat.type == ChatType.SUPERGROUP)
async def handle_message(
    message: Message,
    db: Database,
    detector: SpamDetector,
    settings: Settings,
    **_: Any,
) -> None:
    """Process new messages in supergroups (channel comment sections)."""
    # profile_analyzer is attached to the bot instance at startup
    bot: Bot = message.bot  # type: ignore[assignment]
    profile_analyzer: ProfileAnalyzer = bot._profile_analyzer  # type: ignore[attr-defined]
    await _process_message(message, db, detector, settings, profile_analyzer, is_edited=False)


@message_router.edited_message(F.chat.type == ChatType.SUPERGROUP)
async def handle_edited_message(
    message: Message,
    db: Database,
    detector: SpamDetector,
    settings: Settings,
    **_: Any,
) -> None:
    """Process edited messages in supergroups."""
    bot: Bot = message.bot  # type: ignore[assignment]
    profile_analyzer: ProfileAnalyzer = bot._profile_analyzer  # type: ignore[attr-defined]
    await _process_message(message, db, detector, settings, profile_analyzer, is_edited=True)


# ---------------------------------------------------------------------------
# Main bot class
# ---------------------------------------------------------------------------

class AntispamBot:
    """Top-level orchestrator: creates the aiogram stack, connects services."""

    def __init__(self) -> None:
        self._settings: Settings = get_settings()
        self._bot: Bot = Bot(token=self._settings.bot_token)
        self._dp: Dispatcher = Dispatcher()
        self._db: Database = Database(self._settings.database_path)
        self._detector: SpamDetector = SpamDetector(
            api_key=self._settings.openrouter_api_key,
            model=self._settings.ai_model,
            base_url=self._settings.openrouter_base_url,
            timeout=self._settings.openrouter_timeout,
            max_retries=self._settings.openrouter_max_retries,
            max_calls_per_minute=self._settings.max_ai_calls_per_minute,
        )
        self._profile_analyzer: ProfileAnalyzer = ProfileAnalyzer(self._bot)
        # Attach profile_analyzer to the bot instance so handlers can access it
        self._bot._profile_analyzer = self._profile_analyzer  # type: ignore[attr-defined]

    def _setup_routers(self) -> None:
        """Register middleware on the dispatcher and include routers."""
        middleware = DependencyMiddleware(self._db, self._detector, self._settings)

        # Apply middleware to all relevant update types
        self._dp.message.middleware(middleware)
        self._dp.edited_message.middleware(middleware)
        self._dp.callback_query.middleware(middleware)

        # Include routers -- admin first so commands take priority over
        # the catch-all supergroup message handler
        self._dp.include_router(admin_router)
        self._dp.include_router(message_router)

    async def start(self) -> None:
        """Connect the database, wire up routers, and start polling."""
        await self._db.connect()
        self._setup_routers()

        bot_info = await self._bot.get_me()
        logger.info(
            "bot.started",
            bot_id=bot_info.id,
            bot_username=bot_info.username,
            model=self._settings.ai_model,
            threshold=self._settings.spam_confidence_threshold,
            admin_count=len(self._settings.admin_ids),
        )

        await self._dp.start_polling(
            self._bot,
            allowed_updates=[
                "message",
                "edited_message",
                "callback_query",
                "chat_member",
            ],
        )

    async def shutdown(self) -> None:
        """Gracefully shut down all components."""
        try:
            await self._detector.close()
        except Exception as exc:
            logger.warning("shutdown.detector_error", error=str(exc))

        try:
            await self._db.close()
        except Exception as exc:
            logger.warning("shutdown.db_error", error=str(exc))

        try:
            await self._bot.session.close()
        except Exception as exc:
            logger.warning("shutdown.bot_session_error", error=str(exc))

        logger.info("bot.shutdown_complete")
