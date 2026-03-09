"""Telegram user profile analyzer.

Extracts user profile data (name, bio, profile photo) from the Telegram API
for use in AI-powered spam classification.
"""

from __future__ import annotations

import base64
import io

import structlog
from aiogram import Bot
from aiogram.types import User

from src.models import UserProfile

log = structlog.get_logger(__name__)


class ProfileAnalyzer:
    """Collects Telegram user profile information for spam analysis."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def get_profile(self, user: User, chat_id: int) -> UserProfile:
        """Build a UserProfile from Telegram API data.

        Gracefully handles all Telegram API errors -- returns a partial
        profile rather than raising, so spam detection can still proceed
        with whatever information is available.
        """
        profile = UserProfile(
            user_id=user.id,
            first_name=user.first_name or "",
            last_name=user.last_name,
            username=user.username,
        )

        # --- Bio (from ChatMember.user or Chat full info) ---
        await self._fetch_bio(profile, user.id, chat_id)

        # --- Profile photo ---
        await self._fetch_profile_photo(profile, user.id)

        return profile

    async def _fetch_bio(self, profile: UserProfile, user_id: int, chat_id: int) -> None:
        """Attempt to get the user's bio via get_chat_member."""
        try:
            chat_member = await self._bot.get_chat_member(chat_id, user_id)
            # The bio is available on the User object inside ChatMember
            # in some aiogram versions; also try full chat info.
            member_user = chat_member.user
            if member_user and hasattr(member_user, "bio") and member_user.bio:
                profile.bio = member_user.bio
        except Exception as exc:
            log.debug(
                "profile_analyzer.bio_unavailable",
                user_id=user_id,
                error=str(exc),
            )

        # If bio still not fetched, try getting the user's private chat info
        if profile.bio is None:
            try:
                user_chat = await self._bot.get_chat(user_id)
                if user_chat.bio:
                    profile.bio = user_chat.bio
            except Exception as exc:
                log.debug(
                    "profile_analyzer.chat_bio_unavailable",
                    user_id=user_id,
                    error=str(exc),
                )

    async def _fetch_profile_photo(self, profile: UserProfile, user_id: int) -> None:
        """Download the first profile photo and encode it as base64."""
        try:
            photos = await self._bot.get_user_profile_photos(user_id, limit=1)
            if not photos.photos:
                return

            profile.has_profile_photo = True

            # Get the smallest size of the first photo for efficiency
            photo_sizes = photos.photos[0]
            if not photo_sizes:
                return

            # Use the last (largest) size for better quality
            photo = photo_sizes[-1]

            # Download the photo
            file = await self._bot.get_file(photo.file_id)
            if not file.file_path:
                return

            buffer = io.BytesIO()
            await self._bot.download_file(file.file_path, destination=buffer)
            buffer.seek(0)

            profile.profile_photo_base64 = base64.b64encode(buffer.read()).decode("ascii")
            log.debug("profile_analyzer.photo_downloaded", user_id=user_id)

        except Exception as exc:
            log.debug(
                "profile_analyzer.photo_unavailable",
                user_id=user_id,
                error=str(exc),
            )
