"""Domain data models for the Telegram Anti-Spam Bot v2.

All models are plain dataclasses -- no ORM coupling, easy to serialise/test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SpamAction(str, Enum):
    """Action taken on a processed message."""

    ALLOWED = "allowed"
    DELETED_AND_BANNED = "deleted_and_banned"
    ERROR_ALLOWED = "error_allowed"


# ---------------------------------------------------------------------------
# SpamVerdict
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SpamVerdict:
    """Result of AI spam analysis for a single message."""

    is_spam: bool
    confidence: float
    reason: str
    raw_response: str | None = field(default=None, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpamVerdict:
        """Build a SpamVerdict from a parsed JSON dict.

        Expected keys: ``is_spam``, ``confidence``, ``reason``.
        Missing/invalid values fall back to safe defaults (not spam).
        """
        return cls(
            is_spam=bool(data.get("is_spam", False)),
            confidence=float(data.get("confidence", 0.0)),
            reason=str(data.get("reason", "No reason provided")),
        )

    @classmethod
    def error_verdict(cls, error_msg: str) -> SpamVerdict:
        """Return a fail-open verdict used when AI analysis fails.

        The bot defaults to *allowing* messages when the AI service
        is unreachable so legitimate users are not silenced.
        """
        return cls(
            is_spam=False,
            confidence=0.0,
            reason=f"AI analysis error (message allowed): {error_msg}",
        )


# ---------------------------------------------------------------------------
# UserProfile
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class UserProfile:
    """Telegram user profile data collected for spam analysis."""

    user_id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    bio: str | None = None
    has_profile_photo: bool = False
    profile_photo_base64: str | None = field(default=None, repr=False)

    def to_prompt_text(self) -> str:
        """Format profile information as a human-readable block for the AI prompt."""
        parts: list[str] = [f"Name: {self.first_name}"]
        if self.last_name:
            parts[0] += f" {self.last_name}"
        if self.username:
            parts.append(f"Username: @{self.username}")
        if self.bio:
            parts.append(f"Bio: {self.bio}")
        parts.append(f"Has profile photo: {'yes' if self.has_profile_photo else 'no'}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# MessageContext
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class MessageContext:
    """All context needed for spam analysis of a single message."""

    message_id: int
    chat_id: int
    user_id: int
    text: str
    profile: UserProfile
    is_edited: bool = False
