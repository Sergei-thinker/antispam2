"""Custom exception classes for the Telegram Anti-Spam Bot v2."""


class AntispamError(Exception):
    """Base exception for the antispam bot.

    All custom exceptions in this project inherit from this class,
    making it easy to catch any bot-specific error.
    """


class AIServiceError(AntispamError):
    """OpenRouter API is unavailable or returning errors.

    Raised when the AI service fails after all retries are exhausted,
    or returns an unexpected response format.
    """


class ConfigurationError(AntispamError):
    """Invalid or missing configuration.

    Raised when required environment variables are missing,
    or configuration values fail validation.
    """


class DatabaseError(AntispamError):
    """Database operation failed.

    Raised when an aiosqlite operation fails unexpectedly,
    such as connection errors or constraint violations.
    """
