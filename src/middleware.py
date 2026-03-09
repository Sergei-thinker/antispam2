"""aiogram middleware for dependency injection.

Injects shared dependencies (database, spam detector, settings) into
every handler's ``data`` dict so they are available as keyword arguments.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from src.config import Settings
from src.database import Database
from src.spam_detector import SpamDetector


class DependencyMiddleware(BaseMiddleware):
    """Injects core dependencies into aiogram handler data.

    Usage::

        dp.message.middleware(DependencyMiddleware(db, detector, settings))
        dp.edited_message.middleware(DependencyMiddleware(db, detector, settings))
    """

    def __init__(
        self,
        db: Database,
        detector: SpamDetector,
        settings: Settings,
    ) -> None:
        super().__init__()
        self.db = db
        self.detector = detector
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Add dependencies to the data dict and call the next handler."""
        data["db"] = self.db
        data["detector"] = self.detector
        data["settings"] = self.settings
        return await handler(event, data)
