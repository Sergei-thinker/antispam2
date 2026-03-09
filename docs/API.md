# OpenRouter API Reference

This document covers the OpenRouter API integration used by Антиспамер 2 for AI-powered spam detection.

---

## Overview

[OpenRouter](https://openrouter.ai) is a unified API gateway that provides access to multiple AI language models (Claude, GPT, Gemini, Llama, Mistral, and more) through a single API interface. Антиспамер 2 uses OpenRouter to classify Telegram messages as spam or legitimate content.

**Why OpenRouter instead of direct API access?**
- Single API key for multiple model providers
- Easy model switching without code changes (just update `AI_MODEL` env var)
- Unified billing and usage tracking
- Automatic failover between model providers
- Competitive pricing with pass-through rates

---

## Account Setup

### 1. Registration

1. Go to [openrouter.ai](https://openrouter.ai)
2. Click **Sign Up** (you can use Google, GitHub, or email)
3. Verify your email address

### 2. Add Credits

1. Navigate to **Credits** in your dashboard
2. Add funds via credit card or crypto
3. Recommended starting amount: **$5–10** (sufficient for thousands of spam checks)

### 3. Create an API Key

1. Go to **Keys** in your dashboard
2. Click **Create Key**
3. Name: `Antispamer 2` (or any descriptive name)
4. Optionally set a spending limit for safety
5. Copy the key immediately — it won't be shown again
6. The key format is: `sk-or-v1-...`

---

## API Key Security

**Critical rules for API key management:**

- **Never commit API keys to version control** — Use `.env` file (which is in `.gitignore`)
- **Never share API keys** in chat, email, or documentation
- **Rotate keys** if you suspect they've been compromised (delete old key, create new one)
- **Set spending limits** on the OpenRouter dashboard to prevent unexpected charges
- **Monitor usage** regularly in the OpenRouter dashboard

If a key is compromised:
1. Go to OpenRouter dashboard → **Keys**
2. Delete the compromised key immediately
3. Create a new key
4. Update your `.env` file with the new key
5. Restart the bot

---

## Model Selection Guide

Антиспамер 2 is compatible with any chat-completion model available on OpenRouter. The model is configured via the `AI_MODEL` environment variable.

### Recommended Models

| Model | OpenRouter ID | Speed | Cost | Accuracy | Best For |
|-------|---------------|-------|------|----------|----------|
| **Claude Sonnet 4** | `anthropic/claude-sonnet-4` | Medium | ~$3/$15 per 1M tokens | Excellent | Default choice, best accuracy-to-cost ratio |
| **Claude Haiku 4.5** | `anthropic/claude-haiku-4-5` | Fast | ~$0.80/$4 per 1M tokens | Very Good | High-volume channels, cost-sensitive setups |
| **GPT-4o mini** | `openai/gpt-4o-mini` | Fast | ~$0.15/$0.60 per 1M tokens | Good | Budget option with decent accuracy |
| **Claude Opus 4** | `anthropic/claude-opus-4` | Slow | ~$15/$75 per 1M tokens | Outstanding | Maximum accuracy, cost is secondary |
| **Gemini 2.0 Flash** | `google/gemini-2.0-flash-001` | Very Fast | ~$0.10/$0.40 per 1M tokens | Good | Fastest response times |

### Model Selection Criteria

**For most channels (< 100 comments/day):**
Use `anthropic/claude-sonnet-4` (default). It provides the best balance of accuracy, speed, and cost. Expected cost: $1–3/month.

**For high-volume channels (100–1000 comments/day):**
Use `anthropic/claude-haiku-4-5` or `openai/gpt-4o-mini`. These are faster and cheaper while maintaining good spam detection accuracy. Expected cost: $3–15/month.

**For channels where accuracy is critical:**
Use `anthropic/claude-opus-4`. This is the most capable model but significantly more expensive. Only recommended when false positives are extremely costly.

**To change the model:**
```env
AI_MODEL=anthropic/claude-haiku-4-5
```
Restart the bot after changing.

---

## Token Usage and Cost Estimation

### Understanding Tokens

Tokens are the units AI models use to process text. Roughly:
- 1 token ≈ 4 characters in English
- 1 token ≈ 1–2 characters in Russian/Cyrillic
- Average Telegram message: 20–100 tokens
- System prompt + few-shot examples: ~500–1000 tokens
- Total per request: ~600–1200 tokens input, ~50–150 tokens output

### Cost Estimation

**Per spam check (with Claude Sonnet 4):**
- Input: ~800 tokens × $3/1M = $0.0024
- Output: ~100 tokens × $15/1M = $0.0015
- **Total per check: ~$0.004**

**Monthly estimates (Claude Sonnet 4):**

| Daily Comments | Monthly Checks | Estimated Cost |
|---------------|----------------|----------------|
| 10 | 300 | $1.20 |
| 50 | 1,500 | $6.00 |
| 100 | 3,000 | $12.00 |
| 500 | 15,000 | $60.00 |

**Monthly estimates (Claude Haiku 4.5):**

| Daily Comments | Monthly Checks | Estimated Cost |
|---------------|----------------|----------------|
| 10 | 300 | $0.20 |
| 50 | 1,500 | $1.00 |
| 100 | 3,000 | $2.00 |
| 500 | 15,000 | $10.00 |

**Note:** Actual costs vary based on message length, number of few-shot examples, and model pricing changes. Check [openrouter.ai/models](https://openrouter.ai/models) for current pricing.

---

## Rate Limits

### OpenRouter Rate Limits

OpenRouter enforces per-key rate limits that vary by your account tier:
- **Free tier:** 10 requests/minute, 200 requests/day
- **Paid tier:** Typically 60+ requests/minute (varies by spending history)

Check your current limits at [openrouter.ai/keys](https://openrouter.ai/keys).

### Local Rate Limiter

Антиспамер 2 includes its own rate limiter (`MAX_AI_CALLS_PER_MINUTE`) to:
1. Stay within OpenRouter limits
2. Control costs during spam attacks (sudden flood of spam messages)
3. Provide predictable API usage

The local rate limiter uses a sliding window algorithm:
- Tracks timestamps of recent API calls
- Rejects new calls when the window is full
- Messages that exceed the rate limit are **allowed through** (fail-open)

**Recommended settings:**
| OpenRouter Tier | `MAX_AI_CALLS_PER_MINUTE` |
|----------------|---------------------------|
| Free | 8 |
| Paid (low) | 20 (default) |
| Paid (high) | 40 |

---

## API Request Format

Антиспамер 2 sends requests to OpenRouter's chat completion endpoint.

### Endpoint

```
POST https://openrouter.ai/api/v1/chat/completions
```

### Request Headers

```http
Authorization: Bearer sk-or-v1-your-api-key
Content-Type: application/json
HTTP-Referer: https://github.com/your-username/antispamer-2
X-Title: Antispamer 2
```

### Request Body

```json
{
  "model": "anthropic/claude-sonnet-4",
  "messages": [
    {
      "role": "system",
      "content": "You are a spam detection assistant for a Telegram channel..."
    },
    {
      "role": "user",
      "content": "Example spam message: 'Buy cheap followers now!'",
    },
    {
      "role": "assistant",
      "content": "{\"is_spam\": true, \"confidence\": 0.95, \"reason\": \"Promotional spam selling followers\"}"
    },
    {
      "role": "user",
      "content": "Classify this message:\n\nUser profile:\n- Name: John\n- Has photo: yes\n\nMessage: 'Great video, thanks for sharing!'"
    }
  ],
  "temperature": 0.1,
  "max_tokens": 200,
  "response_format": {
    "type": "json_object"
  }
}
```

### Response Body

```json
{
  "id": "gen-abc123",
  "model": "anthropic/claude-sonnet-4",
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "{\"is_spam\": false, \"confidence\": 0.15, \"reason\": \"Genuine positive comment about the video content\"}"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 850,
    "completion_tokens": 45,
    "total_tokens": 895
  }
}
```

### Parsed Classification Response

The AI response content is always JSON with this structure:

```json
{
  "is_spam": false,
  "confidence": 0.15,
  "reason": "Genuine positive comment about the video content"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `is_spam` | boolean | Whether the message is classified as spam |
| `confidence` | float (0.0–1.0) | How confident the model is in its classification |
| `reason` | string | Human-readable explanation of the classification |

---

## Error Codes and Handling

### HTTP Status Codes

| Status Code | Meaning | Bot Behavior |
|------------|---------|-------------|
| `200` | Success | Parse response, apply classification |
| `400` | Bad Request (invalid model, malformed JSON) | Log error, allow message (fail-open) |
| `401` | Invalid API key | Log critical error, allow message |
| `402` | Insufficient credits | Log critical error, allow message |
| `403` | Forbidden (key disabled) | Log critical error, allow message |
| `408` | Request timeout | Retry with backoff, then allow message |
| `429` | Rate limited by OpenRouter | Retry after delay from `Retry-After` header |
| `500` | OpenRouter server error | Retry with backoff, then allow message |
| `502` | Bad gateway (upstream model error) | Retry with backoff, then allow message |
| `503` | Service unavailable | Retry with backoff, then allow message |

### Error Response Format

```json
{
  "error": {
    "code": 429,
    "message": "Rate limit exceeded. Please retry after 2 seconds.",
    "metadata": {
      "retry_after": 2
    }
  }
}
```

### Retry Strategy

```
Attempt 1: Immediate
   ↓ (failed)
Wait 1 second
Attempt 2: Retry
   ↓ (failed)
Wait 2 seconds
Attempt 3: Retry
   ↓ (failed)
Wait 4 seconds
Attempt 4 (final): Retry
   ↓ (failed)
Give up → Allow message (fail-open)
```

**Non-retryable errors** (immediate fail-open):
- `400 Bad Request` — Configuration issue, retrying won't help
- `401 Unauthorized` — Invalid API key
- `402 Payment Required` — No credits
- `403 Forbidden` — Key disabled or access denied

---

## Monitoring API Usage

### OpenRouter Dashboard

Monitor your usage at [openrouter.ai/activity](https://openrouter.ai/activity):
- Total requests per day/week/month
- Token usage breakdown (input vs output)
- Cost per model
- Error rates

### Bot Statistics

Use the `/stats` bot command to see:
- Total AI calls made
- AI error count and error rate
- Average response time
- Messages processed vs AI calls (some messages are skipped)

### Cost Alerts

Set up spending limits on the OpenRouter dashboard:
1. Go to **Keys** → select your key
2. Set a **monthly limit** (e.g., $10)
3. OpenRouter will disable the key when the limit is reached
4. The bot will fail-open (allow all messages) until credits are added

---

## Troubleshooting API Issues

| Problem | Possible Cause | Solution |
|---------|---------------|----------|
| All messages allowed through | API key invalid or no credits | Check key in OpenRouter dashboard |
| Slow response times | Model overloaded | Switch to a faster model (Haiku, GPT-4o-mini) |
| High false positive rate | Model too aggressive | Lower `SPAM_CONFIDENCE_THRESHOLD` to 0.8 or higher |
| High false negative rate | Model too lenient | Raise `SPAM_CONFIDENCE_THRESHOLD` to 0.5–0.6 |
| Unexpected charges | Spam attack causing many API calls | Lower `MAX_AI_CALLS_PER_MINUTE` |
| `model not found` error | Invalid model ID | Check available models at openrouter.ai/models |
