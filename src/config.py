"""Application configuration via pydantic-settings.

Settings are loaded from environment variables and/or a .env file.
Do NOT instantiate Settings at module level -- use get_settings() instead
so the app fails gracefully when .env is absent (e.g. during tests).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings

from src.exceptions import ConfigurationError


class Settings(BaseSettings):
    """Bot configuration loaded from environment / .env file."""

    # --- Required ----------------------------------------------------------------
    bot_token: str
    openrouter_api_key: str
    admin_ids: list[int]
    channel_id: int

    # --- AI settings -------------------------------------------------------------
    ai_model: str = "anthropic/claude-sonnet-4"
    spam_confidence_threshold: float = 0.7
    max_message_length: int = 4000
    max_few_shot_examples: int = 10

    # --- OpenRouter connection ---------------------------------------------------
    openrouter_base_url: str = "https://openrouter.ai/api/v1/chat/completions"
    openrouter_timeout: int = 30
    openrouter_max_retries: int = 3

    # --- Rate limiting -----------------------------------------------------------
    max_ai_calls_per_minute: int = 20

    # --- Database ----------------------------------------------------------------
    database_path: str = "data/antispam.db"

    # --- Logging -----------------------------------------------------------------
    log_level: str = "INFO"
    log_format: str = "json"  # "json" or "console"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    # --- Validators --------------------------------------------------------------

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: str | list[int]) -> list[int]:
        """Accept a comma-separated string like ``"123,456"`` and convert to list[int]."""
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    @field_validator("spam_confidence_threshold")
    @classmethod
    def validate_threshold(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("spam_confidence_threshold must be between 0.0 and 1.0")
        return v

    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        allowed = {"json", "console"}
        if v not in allowed:
            raise ValueError(f"log_format must be one of {allowed}")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Raises ConfigurationError if required env vars are missing.
    """
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as exc:
        raise ConfigurationError(f"Failed to load settings: {exc}") from exc
