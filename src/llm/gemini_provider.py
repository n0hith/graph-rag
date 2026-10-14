"""Google Gemini provider, using the official `google-genai` SDK."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

import httpx
from google.genai import errors

from src.llm.client import (
    LLMError,
    LLMRequest,
    LLMResponse,
    MissingAPIKeyError,
    ModelUnavailableError,
)
from src.llm.rate_limiter import DailyLimitReached, RateLimiter, backoff_delay

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def _is_daily_quota_error(exc: errors.APIError) -> bool:
    """True if a 429 is about the per-day quota (waiting a minute won't help)."""
    if exc.code != 429:
        return False
    text = (exc.message or "") + json.dumps(exc.details or {}, default=str)
    return "PerDay" in text or "per day" in text.lower()


class GeminiProvider:
    """Calls Gemini with client-side rate limiting and retries on 429/5xx/network errors.

    If those errors continue past `max_retries`, raises `ModelUnavailableError` so the
    client can switch to a fallback model.
    """

    name = "gemini"

    def __init__(
        self,
        api_key: str | None,
        rate_limiter: RateLimiter,
        max_retries: int = 5,
        base_delay: float = 2.0,
        max_delay: float = 60.0,
        sdk_client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if sdk_client is None:
            if not api_key:
                raise MissingAPIKeyError(
                    "GEMINI_API_KEY is not set. Add it to .env (see README: 'Get a Gemini API key')."
                )
            from google import genai

            sdk_client = genai.Client(api_key=api_key)
        self._client = sdk_client
        self.rate_limiter = rate_limiter
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._sleep = sleep

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Make one Gemini call, retrying transient failures with exponential backoff."""
        config = self._build_config(request)
        for attempt in range(self.max_retries + 1):
            self.rate_limiter.acquire(request.model)
            try:
                raw = self._client.models.generate_content(
                    model=request.model, contents=request.prompt, config=config
                )
                return self._to_response(raw)
            except errors.APIError as exc:
                if _is_daily_quota_error(exc):
                    raise DailyLimitReached(
                        f"Gemini reports the daily quota for {request.model} is used up. "
                        "Progress is saved; run the same command again after the quota resets."
                    ) from exc
                if exc.code not in RETRYABLE_STATUS:
                    raise
                reason = f"HTTP {exc.code} {exc.status or ''}".strip()
                last_error: Exception = exc
            except httpx.TransportError as exc:
                reason = f"network error ({type(exc).__name__})"
                last_error = exc
            if attempt == self.max_retries:
                raise ModelUnavailableError(
                    f"{request.model} still unavailable after {attempt + 1} attempts ({reason})"
                ) from last_error
            delay = backoff_delay(attempt, self.base_delay, self.max_delay)
            logger.warning(
                "Gemini %s on attempt %d/%d; retrying in %.1fs",
                reason, attempt + 1, self.max_retries + 1, delay,
            )
            self._sleep(delay)
        raise AssertionError("unreachable")  # the loop always returns or raises

    @staticmethod
    def _build_config(request: LLMRequest) -> dict:
        config: dict[str, Any] = {}
        if request.system:
            config["system_instruction"] = request.system
        if request.temperature is not None:
            config["temperature"] = request.temperature
        if request.json_schema is not None:
            config["response_mime_type"] = "application/json"
            config["response_json_schema"] = request.json_schema
        return config

    @staticmethod
    def _to_response(raw: Any) -> LLMResponse:
        text = raw.text
        if not text:
            reason = None
            if getattr(raw, "candidates", None):
                reason = raw.candidates[0].finish_reason
            raise LLMError(f"Gemini returned an empty response (finish reason: {reason})")
        usage = raw.usage_metadata
        return LLMResponse(
            text=text,
            prompt_tokens=(usage.prompt_token_count or 0) if usage else 0,
            output_tokens=(usage.candidates_token_count or 0) if usage else 0,
            thinking_tokens=(usage.thoughts_token_count or 0) if usage else 0,
        )
