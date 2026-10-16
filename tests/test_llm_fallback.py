"""Tests for switching to the fallback model when the main model stays overloaded
or has run out of its daily quota."""

import pytest

from src.llm.cache import LLMCache
from src.llm.client import LLMClient, LLMRequest, LLMResponse, ModelUnavailableError
from src.llm.rate_limiter import DailyLimitReached


class ModelAwareProvider:
    """Fails for models listed in `down`, answers with the model name otherwise.

    `down` maps a model name to the error it should raise: `ModelUnavailableError` for
    "still overloaded after retries", `DailyLimitReached` for "today's quota is used up"
    (either our own counter or Gemini's own error ends up as this exception).
    """

    name = "fake"

    def __init__(self, down: dict[str, type[Exception]] | set[str]) -> None:
        if isinstance(down, set):
            down = {model: ModelUnavailableError for model in down}
        self.down = down
        self.calls: list[str] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request.model)
        error = self.down.get(request.model)
        if error is not None:
            raise error(f"{request.model} unavailable")
        return LLMResponse(f"answer from {request.model}", prompt_tokens=4, output_tokens=2)


def make_client(tmp_path, down, fallback="backup"):
    provider = ModelAwareProvider(down)
    return LLMClient(provider, "main", LLMCache(tmp_path), fallback_model=fallback), provider


def test_main_model_answers_when_available(tmp_path):
    client, provider = make_client(tmp_path, down=set())
    assert client.generate_text("q") == "answer from main"
    assert client.last_model == "main"
    assert provider.calls == ["main"]


def test_switches_to_fallback_when_main_is_unavailable(tmp_path):
    client, provider = make_client(tmp_path, down={"main"})
    assert client.generate_text("q", step="s") == "answer from backup"
    assert client.last_model == "backup"
    assert provider.calls == ["main", "backup"]
    assert client.tracker.steps["s"].answers_by_model == {"backup": 1}
    assert "backup" in client.tracker.summary()


def test_fallback_answer_is_cached_under_the_model_that_gave_it(tmp_path):
    client, _ = make_client(tmp_path, down={"main"})
    client.generate_text("q")
    entry = LLMCache(tmp_path).get(client._cache_key(LLMRequest("backup", "q")))
    assert entry["model"] == "backup" and entry["requested_model"] == "main"
    assert LLMCache(tmp_path).get(client._cache_key(LLMRequest("main", "q"))) is None


def test_rerun_reuses_cached_fallback_answer_without_calling_api(tmp_path):
    make_client(tmp_path, down={"main"})[0].generate_text("q")
    client, provider = make_client(tmp_path, down=set())  # main is healthy again
    assert client.generate_text("q") == "answer from backup"
    assert client.last_call_cached and client.last_model == "backup"
    assert provider.calls == []


def test_raises_when_both_models_are_unavailable(tmp_path):
    client, provider = make_client(tmp_path, down={"main", "backup"})
    with pytest.raises(ModelUnavailableError):
        client.generate_text("q")
    assert provider.calls == ["main", "backup"]


def test_no_fallback_configured_raises_after_main_fails(tmp_path):
    client, provider = make_client(tmp_path, down={"main"}, fallback=None)
    with pytest.raises(ModelUnavailableError):
        client.generate_text("q")
    assert provider.calls == ["main"]


def test_switches_to_fallback_when_main_is_out_of_daily_quota(tmp_path):
    client, provider = make_client(tmp_path, down={"main": DailyLimitReached})
    assert client.generate_text("q") == "answer from backup"
    assert client.last_model == "backup"
    assert provider.calls == ["main", "backup"]


def test_stops_cleanly_when_fallback_is_also_out_of_daily_quota(tmp_path):
    client, provider = make_client(tmp_path, down={"main": DailyLimitReached, "backup": DailyLimitReached})
    with pytest.raises(DailyLimitReached):
        client.generate_text("q")
    assert provider.calls == ["main", "backup"]


def test_overloaded_main_can_fall_back_to_a_quota_exhausted_backup_and_still_raise(tmp_path):
    client, provider = make_client(tmp_path, down={"main": ModelUnavailableError, "backup": DailyLimitReached})
    with pytest.raises(DailyLimitReached):
        client.generate_text("q")
    assert provider.calls == ["main", "backup"]
