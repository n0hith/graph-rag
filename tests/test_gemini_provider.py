"""Tests for the Gemini provider's retry and quota handling, with the SDK mocked out."""

from types import SimpleNamespace

import pytest
from google.genai import errors

from src.llm.client import LLMError, LLMRequest, MissingAPIKeyError
from src.llm.gemini_provider import GeminiProvider
from src.llm.rate_limiter import DailyLimitReached, RateLimiter


def ok_response(text="hi"):
    usage = SimpleNamespace(prompt_token_count=7, candidates_token_count=3, thoughts_token_count=None)
    return SimpleNamespace(text=text, usage_metadata=usage, candidates=[])


def api_error(code, message="boom", quota_id=None):
    details = [{"violations": [{"quotaId": quota_id}]}] if quota_id else []
    body = {"error": {"code": code, "message": message, "status": "X", "details": details}}
    return (errors.ClientError if code < 500 else errors.ServerError)(code, body)


class FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_provider(outcomes, max_retries=3):
    models = FakeModels(outcomes)
    sleeps = []
    provider = GeminiProvider(
        api_key=None,
        rate_limiter=RateLimiter(rpm=0, rpd=0),
        max_retries=max_retries,
        sdk_client=SimpleNamespace(models=models),
        sleep=sleeps.append,
    )
    return provider, models, sleeps


REQUEST = LLMRequest(model="gemini-test", prompt="hello")


def test_success_returns_text_and_tokens():
    provider, models, sleeps = make_provider([ok_response("pong")])
    response = provider.generate(REQUEST)
    assert (response.text, response.prompt_tokens, response.output_tokens) == ("pong", 7, 3)
    assert sleeps == []


def test_retries_rate_limit_and_server_errors_then_succeeds():
    provider, models, sleeps = make_provider([api_error(429), api_error(503), ok_response()])
    assert provider.generate(REQUEST).text == "hi"
    assert len(models.calls) == 3
    assert len(sleeps) == 2 and sleeps[1] > 0


def test_gives_up_after_max_retries():
    provider, models, _ = make_provider([api_error(500)] * 3, max_retries=2)
    with pytest.raises(errors.ServerError):
        provider.generate(REQUEST)
    assert len(models.calls) == 3


def test_client_errors_are_not_retried():
    provider, models, sleeps = make_provider([api_error(400, "bad request")])
    with pytest.raises(errors.ClientError):
        provider.generate(REQUEST)
    assert len(models.calls) == 1 and sleeps == []


def test_daily_quota_429_stops_immediately():
    error = api_error(429, quota_id="GenerateRequestsPerDayPerProjectPerModel-FreeTier")
    provider, models, sleeps = make_provider([error])
    with pytest.raises(DailyLimitReached):
        provider.generate(REQUEST)
    assert sleeps == []


def test_client_side_daily_limit_blocks_before_calling_api():
    models = FakeModels([ok_response()])
    provider = GeminiProvider(
        api_key=None,
        rate_limiter=RateLimiter(rpm=0, rpd=1),
        sdk_client=SimpleNamespace(models=models),
    )
    provider.generate(REQUEST)
    with pytest.raises(DailyLimitReached):
        provider.generate(REQUEST)
    assert len(models.calls) == 1


def test_structured_request_sends_json_schema():
    provider, models, _ = make_provider([ok_response("{}")])
    schema = {"type": "object", "properties": {}}
    provider.generate(LLMRequest(model="m", prompt="p", system="be brief", json_schema=schema))
    config = models.calls[0]["config"]
    assert config["response_mime_type"] == "application/json"
    assert config["response_json_schema"] == schema
    assert config["system_instruction"] == "be brief"


def test_empty_response_raises():
    provider, _, _ = make_provider([ok_response(text=None)])
    with pytest.raises(LLMError):
        provider.generate(REQUEST)


def test_missing_api_key_gives_clear_error():
    with pytest.raises(MissingAPIKeyError, match="GEMINI_API_KEY"):
        GeminiProvider(api_key=None, rate_limiter=RateLimiter(0, 0))
