"""Tests for src.models -- SpamVerdict, UserProfile, MessageContext, SpamAction."""

from __future__ import annotations

from src.models import MessageContext, SpamAction, SpamVerdict, UserProfile


class TestSpamAction:
    """Verify SpamAction enum members and their string values."""

    def test_allowed_value(self):
        assert SpamAction.ALLOWED == "allowed"
        assert SpamAction.ALLOWED.value == "allowed"

    def test_deleted_and_banned_value(self):
        assert SpamAction.DELETED_AND_BANNED == "deleted_and_banned"

    def test_error_allowed_value(self):
        assert SpamAction.ERROR_ALLOWED == "error_allowed"

    def test_enum_members_count(self):
        assert len(SpamAction) == 3


class TestSpamVerdict:
    """SpamVerdict creation, from_dict, and error_verdict."""

    def test_creation(self):
        v = SpamVerdict(is_spam=True, confidence=0.9, reason="spam detected")
        assert v.is_spam is True
        assert v.confidence == 0.9
        assert v.reason == "spam detected"
        assert v.raw_response is None

    def test_creation_with_raw_response(self):
        v = SpamVerdict(is_spam=False, confidence=0.1, reason="ok", raw_response='{"raw": true}')
        assert v.raw_response == '{"raw": true}'

    def test_frozen(self):
        """SpamVerdict is frozen -- attributes cannot be reassigned."""
        v = SpamVerdict(is_spam=True, confidence=0.9, reason="x")
        import pytest
        with pytest.raises(AttributeError):
            v.is_spam = False  # type: ignore[misc]

    def test_from_dict_valid(self):
        data = {"is_spam": True, "confidence": 0.85, "reason": "Crypto promotion"}
        v = SpamVerdict.from_dict(data)
        assert v.is_spam is True
        assert v.confidence == 0.85
        assert v.reason == "Crypto promotion"

    def test_from_dict_missing_fields(self):
        """Missing keys should fall back to safe defaults (not spam)."""
        v = SpamVerdict.from_dict({})
        assert v.is_spam is False
        assert v.confidence == 0.0
        assert v.reason == "No reason provided"

    def test_from_dict_partial(self):
        """Only some keys present -- missing ones get defaults."""
        v = SpamVerdict.from_dict({"is_spam": True})
        assert v.is_spam is True
        assert v.confidence == 0.0
        assert v.reason == "No reason provided"

    def test_error_verdict(self):
        """error_verdict should create a fail-open verdict."""
        v = SpamVerdict.error_verdict("API timeout")
        assert v.is_spam is False
        assert v.confidence == 0.0
        assert "API timeout" in v.reason
        assert "AI analysis error" in v.reason


class TestUserProfile:
    """UserProfile creation and to_prompt_text formatting."""

    def test_to_prompt_text_full(self, sample_profile):
        text = sample_profile.to_prompt_text()
        assert "Name: Test User" in text
        assert "Username: @testuser" in text
        assert "Bio: Just a test user" in text
        assert "Has profile photo: yes" in text

    def test_to_prompt_text_minimal(self, minimal_profile):
        """Profile with only required fields -- no last_name, no username, no bio."""
        text = minimal_profile.to_prompt_text()
        assert "Name: Minimal" in text
        assert "Username:" not in text
        assert "Bio:" not in text
        assert "Has profile photo: no" in text

    def test_to_prompt_text_no_last_name(self):
        p = UserProfile(user_id=1, first_name="Alice", username="alice")
        text = p.to_prompt_text()
        # Name line should be just "Alice", not "Alice None"
        assert "Name: Alice\n" in text or text.startswith("Name: Alice\n") or "Name: Alice" in text
        assert "Alice None" not in text

    def test_profile_has_slots(self):
        """UserProfile uses __slots__ so arbitrary attributes cannot be set."""
        p = UserProfile(user_id=1, first_name="X")
        import pytest
        with pytest.raises(AttributeError):
            p.nonexistent_field = "value"  # type: ignore[attr-defined]


class TestMessageContext:
    """MessageContext dataclass creation."""

    def test_creation(self, sample_profile):
        ctx = MessageContext(
            message_id=42,
            chat_id=-100123,
            user_id=sample_profile.user_id,
            text="Hello!",
            profile=sample_profile,
            is_edited=False,
        )
        assert ctx.message_id == 42
        assert ctx.chat_id == -100123
        assert ctx.text == "Hello!"
        assert ctx.is_edited is False
        assert ctx.profile is sample_profile

    def test_is_edited_default(self, sample_profile):
        ctx = MessageContext(
            message_id=1,
            chat_id=-1,
            user_id=1,
            text="t",
            profile=sample_profile,
        )
        assert ctx.is_edited is False
