"""Tests for src.config -- Settings loading and validation."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.config import Settings


# Helper: env keys that pydantic-settings would look up for required fields
_REQUIRED_KEYS = ("BOT_TOKEN", "OPENROUTER_API_KEY", "ADMIN_IDS", "CHANNEL_ID")


def _clean_env():
    """Return a dict suitable for patch.dict that removes all required env vars."""
    return {k: "" for k in _REQUIRED_KEYS}


class TestSettingsCreation:
    """Verify Settings can be constructed from explicit keyword arguments."""

    def test_settings_from_kwargs(self):
        """Settings should accept explicit keyword arguments."""
        s = Settings(
            bot_token="123:ABC",
            openrouter_api_key="sk-key",
            admin_ids=[111, 222],
            channel_id=-1001234567890,
        )
        assert s.bot_token == "123:ABC"
        assert s.openrouter_api_key == "sk-key"
        assert s.admin_ids == [111, 222]
        assert s.channel_id == -1001234567890

    def test_settings_from_env(self):
        """Settings should load values from environment variables."""
        env = {
            "BOT_TOKEN": "token-from-env",
            "OPENROUTER_API_KEY": "sk-env",
            "ADMIN_IDS": "[100,200,300]",
            "CHANNEL_ID": "-100999",
        }
        with patch.dict("os.environ", env, clear=False):
            s = Settings()  # type: ignore[call-arg]
        assert s.bot_token == "token-from-env"
        assert s.admin_ids == [100, 200, 300]


class TestAdminIdsParsing:
    """Verify the admin_ids field_validator handles various string inputs."""

    def test_admin_ids_from_string(self):
        s = Settings(
            bot_token="t",
            openrouter_api_key="k",
            admin_ids="111,222,333",  # type: ignore[arg-type]
            channel_id=-1,
        )
        assert s.admin_ids == [111, 222, 333]

    def test_admin_ids_with_spaces(self):
        s = Settings(
            bot_token="t",
            openrouter_api_key="k",
            admin_ids=" 111 , 222 ",  # type: ignore[arg-type]
            channel_id=-1,
        )
        assert s.admin_ids == [111, 222]

    def test_admin_ids_single_value(self):
        s = Settings(
            bot_token="t",
            openrouter_api_key="k",
            admin_ids="42",  # type: ignore[arg-type]
            channel_id=-1,
        )
        assert s.admin_ids == [42]


class TestValidation:
    """Test pydantic validators on Settings fields."""

    def test_missing_required_field_bot_token(self):
        """Omitting bot_token should raise a ValidationError.

        We strip all related env vars so pydantic-settings cannot fall back to them.
        """
        env_overrides = {k: "" for k in _REQUIRED_KEYS}
        # Remove them entirely so pydantic sees them as missing
        env_remove = list(_REQUIRED_KEYS)
        with patch.dict("os.environ", {}, clear=False):
            # Ensure the keys are absent
            for key in env_remove:
                os.environ.pop(key, None)
            with pytest.raises(ValidationError):
                Settings(
                    openrouter_api_key="k",
                    admin_ids=[1],
                    channel_id=-1,
                )  # type: ignore[call-arg]

    def test_missing_required_field_api_key(self):
        """Omitting openrouter_api_key should raise a ValidationError."""
        for key in _REQUIRED_KEYS:
            os.environ.pop(key, None)
        with pytest.raises(ValidationError):
            Settings(
                bot_token="t",
                admin_ids=[1],
                channel_id=-1,
            )  # type: ignore[call-arg]

    def test_confidence_threshold_valid_range(self):
        s = Settings(
            bot_token="t",
            openrouter_api_key="k",
            admin_ids=[1],
            channel_id=-1,
            spam_confidence_threshold=0.5,
        )
        assert s.spam_confidence_threshold == 0.5

    def test_confidence_threshold_out_of_range_high(self):
        with pytest.raises(ValidationError, match="between 0.0 and 1.0"):
            Settings(
                bot_token="t",
                openrouter_api_key="k",
                admin_ids=[1],
                channel_id=-1,
                spam_confidence_threshold=1.5,
            )

    def test_confidence_threshold_out_of_range_negative(self):
        with pytest.raises(ValidationError, match="between 0.0 and 1.0"):
            Settings(
                bot_token="t",
                openrouter_api_key="k",
                admin_ids=[1],
                channel_id=-1,
                spam_confidence_threshold=-0.1,
            )

    def test_invalid_log_format(self):
        with pytest.raises(ValidationError, match="log_format"):
            Settings(
                bot_token="t",
                openrouter_api_key="k",
                admin_ids=[1],
                channel_id=-1,
                log_format="yaml",
            )


class TestDefaultValues:
    """Verify that optional fields have the expected defaults."""

    def test_defaults(self, sample_settings):
        assert sample_settings.ai_model == "anthropic/claude-sonnet-4"
        assert sample_settings.spam_confidence_threshold == 0.7
        assert sample_settings.max_message_length == 4000
        assert sample_settings.max_few_shot_examples == 10
        assert sample_settings.openrouter_base_url == "https://openrouter.ai/api/v1/chat/completions"
        assert sample_settings.openrouter_timeout == 30
        assert sample_settings.openrouter_max_retries == 3
        assert sample_settings.max_ai_calls_per_minute == 20
        assert sample_settings.database_path == "data/antispam.db"
        assert sample_settings.log_level == "INFO"
        assert sample_settings.log_format == "json"
