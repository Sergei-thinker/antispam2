"""Admin command handlers for the Telegram Anti-Spam Bot v2.

Provides /start, /help, /stats, /status, /whitelist, /unban, /recent
commands and a callback handler for the inline unban button.

All handlers receive ``db``, ``detector``, and ``settings`` via
DependencyMiddleware kwargs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
import structlog

from .config import Settings
from .database import Database

logger = structlog.get_logger(__name__)

router = Router(name="admin_commands")

# Module-level start time -- set when the module is first imported.
_start_time: datetime = datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_admin(user_id: int, settings: Settings) -> bool:
    """Check whether *user_id* is in the configured admin list."""
    return user_id in settings.admin_ids


def _fmt_number(n: int) -> str:
    """Format an integer with thousands separator."""
    return f"{n:,}"


def _uptime() -> str:
    """Return a human-readable uptime string since module load."""
    delta = datetime.now(tz=timezone.utc) - _start_time
    total_seconds = int(delta.total_seconds())
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}д")
    if hours:
        parts.append(f"{hours}ч")
    if minutes:
        parts.append(f"{minutes}м")
    parts.append(f"{seconds}с")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------

@router.message(Command("start"))
async def cmd_start(message: Message, settings: Settings, **_: Any) -> None:
    """Welcome message -- only in private chats."""
    if message.chat.type != ChatType.PRIVATE:
        return

    text = (
        "Антиспам Бот v2\n"
        "\n"
        "AI-защита комментариев Telegram-канала от спама.\n"
        "\n"
        "Возможности:\n"
        "- Автоматическое обнаружение спама через LLM\n"
        "- Анализ профиля пользователя (имя, био, фото)\n"
        "- Обучение на подтверждённых примерах спама\n"
        "- Уведомления админам с кнопкой разбана\n"
        "- Управление вайтлистом и банами\n"
        "- Подробная статистика модерации\n"
        "\n"
        "Используйте /help для списка команд."
    )
    await message.answer(text)
    logger.info("cmd.start", user_id=message.from_user.id if message.from_user else None)


# ---------------------------------------------------------------------------
# /help
# ---------------------------------------------------------------------------

@router.message(Command("help"))
async def cmd_help(message: Message, settings: Settings, **_: Any) -> None:
    """List available commands -- private chat or admins in groups."""
    if message.chat.type != ChatType.PRIVATE:
        if not message.from_user or not is_admin(message.from_user.id, settings):
            return

    text = (
        "Доступные команды:\n"
        "\n"
        "/start — Приветствие и описание бота\n"
        "/help — Список команд\n"
        "/stats — Статистика модерации (сегодня / 7 дней / всё время)\n"
        "/status — Состояние бота и настройки\n"
        "/whitelist add <user_id> — Добавить в вайтлист\n"
        "/whitelist remove <user_id> — Убрать из вайтлиста\n"
        "/whitelist list — Показать вайтлист\n"
        "/unban <user_id> — Разбанить пользователя\n"
        "/recent — Последние 10 решений модерации\n"
        "\n"
        "Админ-команды доступны только администраторам."
    )
    await message.answer(text)


# ---------------------------------------------------------------------------
# /stats
# ---------------------------------------------------------------------------

@router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database, settings: Settings, **_: Any) -> None:
    """Show moderation statistics."""
    if not message.from_user or not is_admin(message.from_user.id, settings):
        await message.answer("У вас нет прав для этой команды.")
        return

    today = await db.get_stats(days=1)
    week = await db.get_stats(days=7)
    total = await db.get_stats()

    text = (
        "Статистика\n"
        "\n"
        "Сегодня:\n"
        f"  Проверено сообщений: {_fmt_number(today['messages_checked'])}\n"
        f"  Обнаружено спама: {_fmt_number(today['spam_detected'])}\n"
        f"  Забанено: {_fmt_number(today['users_banned'])}\n"
        "\n"
        "За 7 дней:\n"
        f"  Проверено: {_fmt_number(week['messages_checked'])}\n"
        f"  Спам: {_fmt_number(week['spam_detected'])}\n"
        f"  Забанено: {_fmt_number(week['users_banned'])}\n"
        f"  Ложные срабатывания: {_fmt_number(week['false_positives'])}\n"
        "\n"
        "За всё время:\n"
        f"  Проверено: {_fmt_number(total['messages_checked'])}\n"
        f"  Спам: {_fmt_number(total['spam_detected'])}\n"
        f"  Забанено: {_fmt_number(total['users_banned'])}\n"
        f"  Ложные срабатывания: {_fmt_number(total['false_positives'])}"
    )
    await message.answer(text)
    logger.info("cmd.stats", admin_id=message.from_user.id)


# ---------------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------------

@router.message(Command("status"))
async def cmd_status(message: Message, settings: Settings, **_: Any) -> None:
    """Show bot operational status."""
    if not message.from_user or not is_admin(message.from_user.id, settings):
        await message.answer("У вас нет прав для этой команды.")
        return

    text = (
        "Состояние бота\n"
        "\n"
        f"Аптайм: {_uptime()}\n"
        f"AI модель: {settings.ai_model}\n"
        f"Порог уверенности: {settings.spam_confidence_threshold:.0%}\n"
        f"Лимит запросов: {settings.max_ai_calls_per_minute}/мин\n"
        f"Макс. повторов: {settings.openrouter_max_retries}\n"
        f"Таймаут: {settings.openrouter_timeout}с"
    )
    await message.answer(text)
    logger.info("cmd.status", admin_id=message.from_user.id)


# ---------------------------------------------------------------------------
# /whitelist
# ---------------------------------------------------------------------------

@router.message(Command("whitelist"))
async def cmd_whitelist(message: Message, db: Database, settings: Settings, **_: Any) -> None:
    """Manage the whitelist: add / remove / list."""
    if not message.from_user or not is_admin(message.from_user.id, settings):
        await message.answer("У вас нет прав для этой команды.")
        return

    parts = (message.text or "").split()
    # Expected: /whitelist <subcommand> [<user_id>]
    if len(parts) < 2:
        await message.answer(
            "Использование:\n"
            "/whitelist add <user_id>\n"
            "/whitelist remove <user_id>\n"
            "/whitelist list"
        )
        return

    subcommand = parts[1].lower()

    # --- list ---
    if subcommand == "list":
        users = await db.get_whitelist()
        if not users:
            await message.answer("Вайтлист пуст.")
            return

        lines: list[str] = ["Пользователи в вайтлисте:\n"]
        for u in users:
            username_part = f" (@{u['username']})" if u.get("username") else ""
            lines.append(f"  {u['user_id']}{username_part}")
        await message.answer("\n".join(lines))
        logger.info("cmd.whitelist_list", admin_id=message.from_user.id, count=len(users))
        return

    # --- add / remove ---
    if subcommand in ("add", "remove"):
        if len(parts) < 3:
            await message.answer(f"Использование: /whitelist {subcommand} <user_id>")
            return

        try:
            target_user_id = int(parts[2])
        except ValueError:
            await message.answer("Неверный user_id. Должно быть число.")
            return

        if subcommand == "add":
            await db.add_to_whitelist(target_user_id, added_by=message.from_user.id)
            await message.answer(f"Пользователь {target_user_id} добавлен в вайтлист.")
            logger.info(
                "cmd.whitelist_add",
                admin_id=message.from_user.id,
                target_user_id=target_user_id,
            )
        else:
            removed = await db.remove_from_whitelist(target_user_id)
            if removed:
                await message.answer(f"Пользователь {target_user_id} удалён из вайтлиста.")
            else:
                await message.answer(f"Пользователь {target_user_id} не был в вайтлисте.")
            logger.info(
                "cmd.whitelist_remove",
                admin_id=message.from_user.id,
                target_user_id=target_user_id,
                removed=removed,
            )
        return

    await message.answer(
        "Неизвестная подкоманда. Используйте: add, remove или list."
    )


# ---------------------------------------------------------------------------
# /unban
# ---------------------------------------------------------------------------

@router.message(Command("unban"))
async def cmd_unban(message: Message, db: Database, settings: Settings, **_: Any) -> None:
    """Unban a user by user_id."""
    if not message.from_user or not is_admin(message.from_user.id, settings):
        await message.answer("У вас нет прав для этой команды.")
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /unban <user_id>")
        return

    try:
        target_user_id = int(parts[1])
    except ValueError:
        await message.answer("Неверный user_id. Должно быть число.")
        return

    # Unban in all chats where the user is banned
    # Use channel_id from settings as the primary chat
    chat_id = settings.channel_id

    unbanned = await db.remove_banned_user(
        target_user_id, chat_id, unbanned_by=message.from_user.id,
    )

    # Try to lift the Telegram ban
    try:
        bot: Bot = message.bot  # type: ignore[assignment]
        await bot.unban_chat_member(chat_id, target_user_id, only_if_banned=True)
    except Exception as exc:
        logger.warning(
            "cmd.unban_telegram_error",
            user_id=target_user_id,
            chat_id=chat_id,
            error=str(exc),
        )

    if unbanned:
        await message.answer(f"Пользователь {target_user_id} разбанен.")
    else:
        await message.answer(
            f"Пользователь {target_user_id} не найден в списке банов "
            "(возможно, уже разбанен). Бан в Telegram снят, если был."
        )

    logger.info(
        "cmd.unban",
        admin_id=message.from_user.id,
        target_user_id=target_user_id,
        db_unbanned=unbanned,
    )


# ---------------------------------------------------------------------------
# /recent
# ---------------------------------------------------------------------------

@router.message(Command("recent"))
async def cmd_recent(message: Message, db: Database, settings: Settings, **_: Any) -> None:
    """Show last 10 moderation decisions."""
    if not message.from_user or not is_admin(message.from_user.id, settings):
        await message.answer("У вас нет прав для этой команды.")
        return

    try:
        cursor = await db.db.execute(
            """
            SELECT message_id, user_id, username, verdict_spam,
                   verdict_confidence, verdict_reason, action_taken, created_at
            FROM messages
            ORDER BY created_at DESC
            LIMIT 10
            """,
        )
        rows = await cursor.fetchall()
    except Exception as exc:
        logger.error("cmd.recent_db_error", error=str(exc))
        await message.answer("Не удалось получить данные.")
        return

    if not rows:
        await message.answer("Решений модерации пока нет.")
        return

    lines: list[str] = ["Последние 10 решений:\n"]
    for row in rows:
        r = dict(row)
        spam_icon = "SPAM" if r["verdict_spam"] else "OK"
        confidence = r["verdict_confidence"]
        confidence_str = f"{confidence:.0%}" if confidence is not None else "N/A"
        username_str = f"@{r['username']}" if r.get("username") else str(r["user_id"])
        action = r["action_taken"] or "unknown"
        reason = r["verdict_reason"] or "-"
        # Truncate long reasons
        if len(reason) > 60:
            reason = reason[:57] + "..."

        lines.append(
            f"[{spam_icon}] {username_str} | {confidence_str} | {action}\n"
            f"   {reason}"
        )

    await message.answer("\n".join(lines))
    logger.info("cmd.recent", admin_id=message.from_user.id, count=len(rows))


# ---------------------------------------------------------------------------
# Callback: inline unban button
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("unban:"))
async def callback_unban(callback: CallbackQuery, db: Database, settings: Settings, **_: Any) -> None:
    """Handle the inline 'Unban' button from admin notifications.

    Callback data format: ``unban:<chat_id>:<user_id>``
    """
    if not callback.from_user or not is_admin(callback.from_user.id, settings):
        await callback.answer("У вас нет прав.", show_alert=True)
        return

    data = (callback.data or "").split(":")
    if len(data) != 3:
        await callback.answer("Неверные данные.", show_alert=True)
        return

    try:
        chat_id = int(data[1])
        user_id = int(data[2])
    except ValueError:
        await callback.answer("Неверные данные.", show_alert=True)
        return

    # 1. Unban via Telegram API
    try:
        bot: Bot = callback.bot  # type: ignore[assignment]
        await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
    except Exception as exc:
        logger.warning(
            "callback.unban_telegram_error",
            user_id=user_id,
            chat_id=chat_id,
            error=str(exc),
        )

    # 2. Mark as unbanned in DB
    await db.remove_banned_user(user_id, chat_id, unbanned_by=callback.from_user.id)

    # 3. Increment false_positives stat
    from datetime import date as date_cls
    today_str = date_cls.today().isoformat()
    await db.increment_stat(today_str, "false_positives")

    # 4. Edit the notification message
    if callback.message:
        try:
            admin_name = callback.from_user.first_name or str(callback.from_user.id)
            await callback.message.edit_text(
                f"{callback.message.text}\n\n"
                f"Разбанен администратором ({admin_name})",
                reply_markup=None,
            )
        except Exception as exc:
            logger.warning("callback.edit_message_error", error=str(exc))

    await callback.answer("Пользователь разбанен.", show_alert=False)
    logger.info(
        "callback.unban",
        admin_id=callback.from_user.id,
        user_id=user_id,
        chat_id=chat_id,
    )
