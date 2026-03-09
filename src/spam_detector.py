"""AI-powered spam detection via OpenRouter API.

Uses an LLM to classify Telegram channel comments as spam or not-spam,
with configurable confidence thresholds and retry logic.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

import httpx
import structlog

from src.exceptions import AIServiceError
from src.models import SpamVerdict, UserProfile

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an anti-spam moderator for a Telegram channel's comment section.
Analyze comments and determine if they are spam.

You receive: comment text + commenter's profile (name, username, bio).

SPAM indicators:
- Cryptocurrency/casino/gambling promotions
- Advertising other Telegram channels, bots, or groups
- Links to external scam/promotional sites
- Adult/pornographic content or links
- "Easy money" / investment schemes
- Mass-sent generic promotional messages
- Irrelevant advertising
- Fake giveaway/contest announcements
- Phishing or social engineering

Profile-based SPAM indicators:
- Bio with crypto/casino/adult/promotional keywords
- Random character username
- Promotional text in name
- Excessive emojis in name

NOT SPAM (allow):
- Genuine comments about the content
- Questions or discussions
- Emoji reactions or short responses
- Personal experiences
- Constructive criticism

Respond ONLY with JSON:
{"is_spam": true/false, "confidence": 0.0-1.0, "reason": "Brief explanation in Russian"}\
"""


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """Sliding-window rate limiter for async code."""

    def __init__(self, max_calls: int, window_seconds: int = 60) -> None:
        self._max_calls = max_calls
        self._window = window_seconds
        self._timestamps: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Block until a call slot is available within the sliding window."""
        while True:
            async with self._lock:
                now = time.monotonic()
                # Evict expired timestamps
                self._timestamps = [
                    ts for ts in self._timestamps if now - ts < self._window
                ]
                if len(self._timestamps) < self._max_calls:
                    self._timestamps.append(now)
                    return
                # Calculate how long to wait for the oldest slot to expire
                wait_time = self._window - (now - self._timestamps[0])

            log.debug("rate_limiter.waiting", wait_seconds=round(wait_time, 2))
            await asyncio.sleep(wait_time)


# ---------------------------------------------------------------------------
# Spam detector
# ---------------------------------------------------------------------------

class SpamDetector:
    """Classifies messages using an LLM via the OpenRouter API."""

    def __init__(
        self,
        api_key: str,
        model: str = "anthropic/claude-sonnet-4",
        base_url: str = "https://openrouter.ai/api/v1/chat/completions",
        timeout: int = 30,
        max_retries: int = 3,
        max_calls_per_minute: int = 20,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._timeout = timeout
        self._max_retries = max_retries
        self._rate_limiter = RateLimiter(max_calls_per_minute)
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        """Shut down the underlying HTTP client."""
        await self._client.aclose()
        log.info("spam_detector.closed")

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    @staticmethod
    def _build_messages(
        text: str,
        profile: UserProfile,
        few_shot_examples: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, str]]:
        """Build the OpenRouter messages array (system + few-shot + user)."""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

        # Few-shot examples
        if few_shot_examples:
            for example in few_shot_examples:
                example_profile_parts = []
                if example.get("first_name"):
                    name = example["first_name"]
                    if example.get("last_name"):
                        name += f" {example['last_name']}"
                    example_profile_parts.append(f"Name: {name}")
                if example.get("username"):
                    example_profile_parts.append(f"Username: @{example['username']}")
                if example.get("bio"):
                    example_profile_parts.append(f"Bio: {example['bio']}")
                has_photo = example.get("has_profile_photo", False)
                example_profile_parts.append(
                    f"Has profile photo: {'yes' if has_photo else 'no'}"
                )
                example_profile = "\n".join(example_profile_parts)
                example_text = example.get("message_text", "")

                messages.append({
                    "role": "user",
                    "content": (
                        f"[PROFILE]\n{example_profile}\n\n"
                        f"[COMMENT]\n{example_text}"
                    ),
                })
                messages.append({
                    "role": "assistant",
                    "content": json.dumps(
                        {"is_spam": True, "confidence": 0.95, "reason": "Confirmed spam example"},
                        ensure_ascii=False,
                    ),
                })

        # Actual message
        messages.append({
            "role": "user",
            "content": (
                f"[PROFILE]\n{profile.to_prompt_text()}\n\n"
                f"[COMMENT]\n{text}"
            ),
        })

        return messages

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(content: str) -> SpamVerdict:
        """Parse the LLM response into a SpamVerdict.

        Tries multiple extraction strategies:
        1. Direct JSON parse
        2. Markdown code-block extraction
        3. Regex extraction of JSON object
        4. Fail-open error verdict
        """
        # Strategy 1: direct JSON parse
        try:
            data = json.loads(content.strip())
            return SpamVerdict.from_dict(data)
        except (json.JSONDecodeError, ValueError):
            pass

        # Strategy 2: extract JSON from ```json ... ``` block
        md_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if md_match:
            try:
                data = json.loads(md_match.group(1))
                return SpamVerdict.from_dict(data)
            except (json.JSONDecodeError, ValueError):
                pass

        # Strategy 3: regex for first JSON object
        obj_match = re.search(r"\{[^{}]*\"is_spam\"[^{}]*\}", content, re.DOTALL)
        if obj_match:
            try:
                data = json.loads(obj_match.group(0))
                return SpamVerdict.from_dict(data)
            except (json.JSONDecodeError, ValueError):
                pass

        # Strategy 4: fail-open
        log.warning("spam_detector.unparseable_response", raw=content[:500])
        return SpamVerdict.error_verdict(f"Could not parse AI response: {content[:200]}")

    # ------------------------------------------------------------------
    # Main analysis method
    # ------------------------------------------------------------------

    async def analyze(
        self,
        message_text: str,
        profile: UserProfile,
        few_shot_examples: list[dict[str, Any]] | None = None,
    ) -> SpamVerdict:
        """Classify a message as spam or not-spam.

        Uses exponential back-off on retryable errors (429, 5xx, timeouts).
        Fails open on all errors -- never blocks a legitimate user.
        """
        messages = self._build_messages(message_text, profile, few_shot_examples)

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/antispam-bot",
        }
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 200,
        }

        last_error: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                await self._rate_limiter.acquire()

                log.debug(
                    "spam_detector.request",
                    attempt=attempt,
                    model=self._model,
                    user_id=profile.user_id,
                )

                response = await self._client.post(
                    self._base_url,
                    headers=headers,
                    json=payload,
                )

                # Retryable status codes
                if response.status_code in (429, 500, 502, 503, 504):
                    last_error = AIServiceError(
                        f"OpenRouter returned {response.status_code}: {response.text[:300]}"
                    )
                    log.warning(
                        "spam_detector.retryable_error",
                        status=response.status_code,
                        attempt=attempt,
                    )
                    backoff = 2 ** (attempt - 1)  # 1s, 2s, 4s
                    await asyncio.sleep(backoff)
                    continue

                # Non-retryable error
                if response.status_code != 200:
                    log.error(
                        "spam_detector.api_error",
                        status=response.status_code,
                        body=response.text[:500],
                    )
                    return SpamVerdict.error_verdict(
                        f"OpenRouter API error {response.status_code}"
                    )

                # Success -- parse the response
                data = response.json()
                content = data["choices"][0]["message"]["content"]

                verdict = self._parse_response(content)
                log.info(
                    "spam_detector.result",
                    user_id=profile.user_id,
                    is_spam=verdict.is_spam,
                    confidence=verdict.confidence,
                    reason=verdict.reason,
                )
                return verdict

            except httpx.TimeoutException as exc:
                last_error = exc
                log.warning("spam_detector.timeout", attempt=attempt)
                backoff = 2 ** (attempt - 1)
                await asyncio.sleep(backoff)
            except httpx.HTTPError as exc:
                last_error = exc
                log.warning("spam_detector.http_error", attempt=attempt, error=str(exc))
                backoff = 2 ** (attempt - 1)
                await asyncio.sleep(backoff)
            except (KeyError, IndexError) as exc:
                log.error("spam_detector.malformed_response", error=str(exc))
                return SpamVerdict.error_verdict(f"Malformed API response: {exc}")
            except Exception as exc:
                log.error("spam_detector.unexpected_error", error=str(exc))
                return SpamVerdict.error_verdict(f"Unexpected error: {exc}")

        # All retries exhausted -- fail open
        error_msg = f"All {self._max_retries} retries failed: {last_error}"
        log.error("spam_detector.all_retries_failed", error=error_msg)
        return SpamVerdict.error_verdict(error_msg)
