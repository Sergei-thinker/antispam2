"""Entry point for the Telegram Anti-Spam Bot v2.

Run with:
    python main.py
"""

from __future__ import annotations

import asyncio
import sys

import structlog


def setup_logging(log_level: str, log_format: str) -> None:
    """Configure structlog with the given level and renderer.

    Args:
        log_level: Python log level name (e.g. ``"INFO"``, ``"DEBUG"``).
        log_format: ``"json"`` for machine-readable output or
                    ``"console"`` for coloured human-readable output.
    """
    import logging

    # Set the root logger level so structlog respects it
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if log_format == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer(
            ensure_ascii=False,
        )
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    # Replace handlers on the root logger with our formatter
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)


async def main() -> None:
    """Initialise configuration, logging, and start the bot."""
    from src.config import get_settings
    from src.bot import AntispamBot

    settings = get_settings()
    setup_logging(settings.log_level, settings.log_format)

    logger = structlog.get_logger("main")

    bot = AntispamBot()
    logger.info(
        "bot_starting",
        model=settings.ai_model,
        channel=settings.channel_id,
        threshold=settings.spam_confidence_threshold,
    )

    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("bot_stopping", reason="keyboard_interrupt")
    finally:
        await bot.shutdown()
        logger.info("bot_stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
