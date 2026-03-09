"""Tests for src.spam_detector -- RateLimiter & SpamDetector.

All HTTP calls are mocked via httpx.AsyncClient -- no real network traffic.
"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.models import SpamVerdict, UserProfile
from src.spam_detector import RateLimiter, SpamDetector


# =========================================================================
# Helpers
# =========================================================================

def _make_profile(**overrides) -> UserProfile:
    defaults = dict(
        user_id=12345,
        first_name="Test",
        last_name="User",
        username="testuser",
        bio="A user bio",
        has_profile_photo=True,
    )
    defaults.update(overrides)
    return UserProfile(**defaults)


def _openrouter_success(payload: dict) -> httpx.Response:
    """Build a fake 200 response from OpenRouter."""
    body = {
        "choices": [
            {"message": {"content": json.dumps(payload, ensure_ascii=False)}}
        ]
    }
    return httpx.Response(200, json=body)


def _openrouter_error(status: int, text: str = "error") -> httpx.Response:
    return httpx.Response(status, text=text)


# =========================================================================
# _parse_response  (static method -- no HTTP needed)
# =========================================================================

class TestParseResponse:

    def test_parse_valid_json(self):
        raw = '{"is_spam": true, "confidence": 0.9, "reason": "Crypto spam"}'
        v = SpamDetector._parse_response(raw)
        assert v.is_spam is True
        assert v.confidence == 0.9
        assert v.reason == "Crypto spam"

    def test_parse_json_with_whitespace(self):
        raw = '  \n{"is_spam": false, "confidence": 0.05, "reason": "ok"}\n  '
        v = SpamDetector._parse_response(raw)
        assert v.is_spam is False

    def test_parse_markdown_json(self):
        raw = '```json\n{"is_spam": true, "confidence": 0.88, "reason": "ad"}\n```'
        v = SpamDetector._parse_response(raw)
        assert v.is_spam is True
        assert v.confidence == 0.88

    def test_parse_markdown_no_language_tag(self):
        raw = '```\n{"is_spam": false, "confidence": 0.1, "reason": "ok"}\n```'
        v = SpamDetector._parse_response(raw)
        assert v.is_spam is False

    def test_parse_invalid_json(self):
        """Completely invalid text should produce a fail-open error_verdict."""
        v = SpamDetector._parse_response("I don't know what to say")
        assert v.is_spam is False
        assert v.confidence == 0.0
        assert "Could not parse" in v.reason

    def test_parse_partial_json_missing_confidence(self):
        """JSON with only is_spam should fill defaults for missing fields."""
        raw = '{"is_spam": true}'
        v = SpamDetector._parse_response(raw)
        assert v.is_spam is True
        assert v.confidence == 0.0
        assert v.reason == "No reason provided"

    def test_parse_json_embedded_in_text(self):
        """Regex strategy should extract JSON even if surrounded by text."""
        raw = 'Here is my analysis:\n{"is_spam": true, "confidence": 0.77, "reason": "spam link"}\nThank you.'
        v = SpamDetector._parse_response(raw)
        assert v.is_spam is True
        assert v.confidence == 0.77


# =========================================================================
# _build_messages  (static method -- no HTTP needed)
# =========================================================================

class TestBuildMessages:

    def test_basic_messages(self):
        profile = _make_profile()
        msgs = SpamDetector._build_messages("Hello!", profile)
        assert msgs[0]["role"] == "system"
        assert msgs[-1]["role"] == "user"
        assert "[COMMENT]\nHello!" in msgs[-1]["content"]
        assert "[PROFILE]" in msgs[-1]["content"]

    def test_with_few_shot_examples(self):
        profile = _make_profile()
        examples = [
            {
                "first_name": "Spammer",
                "last_name": "Bot",
                "username": "spambot",
                "bio": "Earn money fast",
                "message_text": "Click here to win!",
                "has_profile_photo": False,
            }
        ]
        msgs = SpamDetector._build_messages("Test", profile, few_shot_examples=examples)
        # system + (user + assistant per example) + final user = 1 + 2 + 1 = 4
        assert len(msgs) == 4
        assert msgs[1]["role"] == "user"
        assert "Spammer Bot" in msgs[1]["content"]
        assert msgs[2]["role"] == "assistant"
        # The assistant response should be valid JSON with is_spam=True
        assistant_data = json.loads(msgs[2]["content"])
        assert assistant_data["is_spam"] is True


# =========================================================================
# RateLimiter
# =========================================================================

class TestRateLimiter:

    async def test_allows_within_limit(self):
        """Calls under the limit should return immediately."""
        limiter = RateLimiter(max_calls=5, window_seconds=60)
        for _ in range(5):
            await limiter.acquire()  # should not block

    async def test_blocks_over_limit(self):
        """Exceeding max_calls should cause acquire() to wait."""
        limiter = RateLimiter(max_calls=2, window_seconds=1)
        await limiter.acquire()
        await limiter.acquire()

        start = time.monotonic()
        await limiter.acquire()  # should wait ~1 second
        elapsed = time.monotonic() - start
        assert elapsed >= 0.8, f"Expected to wait ~1s, but waited {elapsed:.2f}s"


# =========================================================================
# SpamDetector.analyze -- mocked HTTP
# =========================================================================

class TestAnalyze:

    @pytest.fixture
    def detector(self):
        """SpamDetector with fast settings for testing."""
        d = SpamDetector(
            api_key="sk-test",
            model="test-model",
            timeout=5,
            max_retries=1,
            max_calls_per_minute=100,
        )
        return d

    @pytest.fixture
    def profile(self):
        return _make_profile()

    async def test_analyze_spam_detected(self, detector, profile):
        resp = _openrouter_success({"is_spam": True, "confidence": 0.92, "reason": "Crypto scam"})
        with patch.object(detector._client, "post", new_callable=AsyncMock, return_value=resp):
            verdict = await detector.analyze("Buy BTC now!", profile)
        assert verdict.is_spam is True
        assert verdict.confidence == 0.92
        assert verdict.reason == "Crypto scam"
        await detector.close()

    async def test_analyze_not_spam(self, detector, profile):
        resp = _openrouter_success({"is_spam": False, "confidence": 0.05, "reason": "Normal comment"})
        with patch.object(detector._client, "post", new_callable=AsyncMock, return_value=resp):
            verdict = await detector.analyze("Great video!", profile)
        assert verdict.is_spam is False
        assert verdict.confidence == 0.05
        await detector.close()

    async def test_analyze_api_error_500(self, detector, profile):
        """A 500 error after all retries should produce an error_verdict (fail-open)."""
        resp = _openrouter_error(500, "Internal Server Error")
        with patch.object(detector._client, "post", new_callable=AsyncMock, return_value=resp):
            with patch("src.spam_detector.asyncio.sleep", new_callable=AsyncMock):
                verdict = await detector.analyze("test", profile)
        assert verdict.is_spam is False
        assert "retries failed" in verdict.reason or "error" in verdict.reason.lower()
        await detector.close()

    async def test_analyze_non_retryable_error_401(self, detector, profile):
        """A 401 (invalid API key) should return error_verdict immediately."""
        resp = _openrouter_error(401, "Unauthorized")
        with patch.object(detector._client, "post", new_callable=AsyncMock, return_value=resp):
            verdict = await detector.analyze("test", profile)
        assert verdict.is_spam is False
        assert "401" in verdict.reason
        await detector.close()

    async def test_analyze_non_retryable_error_403(self, detector, profile):
        resp = _openrouter_error(403, "Forbidden")
        with patch.object(detector._client, "post", new_callable=AsyncMock, return_value=resp):
            verdict = await detector.analyze("test", profile)
        assert verdict.is_spam is False
        assert "403" in verdict.reason
        await detector.close()

    async def test_analyze_timeout(self, detector, profile):
        """httpx.TimeoutException should produce a fail-open error_verdict."""
        with patch.object(
            detector._client, "post",
            new_callable=AsyncMock,
            side_effect=httpx.TimeoutException("Connection timed out"),
        ):
            with patch("src.spam_detector.asyncio.sleep", new_callable=AsyncMock):
                verdict = await detector.analyze("test", profile)
        assert verdict.is_spam is False
        assert "retries failed" in verdict.reason.lower() or "error" in verdict.reason.lower()
        await detector.close()

    async def test_analyze_http_error(self, detector, profile):
        """Generic httpx.HTTPError should be handled gracefully."""
        with patch.object(
            detector._client, "post",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPError("Network unreachable"),
        ):
            with patch("src.spam_detector.asyncio.sleep", new_callable=AsyncMock):
                verdict = await detector.analyze("test", profile)
        assert verdict.is_spam is False
        await detector.close()

    async def test_analyze_malformed_api_response(self, detector, profile):
        """Response missing 'choices' key should produce error_verdict."""
        resp = httpx.Response(200, json={"error": "something"})
        with patch.object(detector._client, "post", new_callable=AsyncMock, return_value=resp):
            verdict = await detector.analyze("test", profile)
        assert verdict.is_spam is False
        assert "Malformed" in verdict.reason
        await detector.close()

    async def test_analyze_with_few_shot(self, detector, profile):
        """Analyze should pass few-shot examples through to _build_messages."""
        examples = [{"first_name": "X", "message_text": "spam", "has_profile_photo": False}]
        resp = _openrouter_success({"is_spam": False, "confidence": 0.1, "reason": "ok"})
        with patch.object(detector._client, "post", new_callable=AsyncMock, return_value=resp) as mock_post:
            verdict = await detector.analyze("Hi", profile, few_shot_examples=examples)
            # Verify the payload sent includes few-shot messages
            call_kwargs = mock_post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            messages = payload["messages"]
            # system + (user+assistant for 1 example) + user = 4
            assert len(messages) == 4
        assert verdict.is_spam is False
        await detector.close()
