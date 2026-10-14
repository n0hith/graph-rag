"""Tests for the on-disk LLM cache and the client's caching behaviour."""

import pytest
from pydantic import BaseModel

from src.llm.cache import LLMCache
from src.llm.client import LLMClient, LLMRequest, LLMResponse, StructuredOutputError


class FakeProvider:
    """Returns queued replies and records every request it receives."""

    name = "fake"

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(self.replies.pop(0), prompt_tokens=10, output_tokens=5)


class Director(BaseModel):
    name: str
    din: str


def test_cache_miss_then_hit(tmp_path):
    cache = LLMCache(tmp_path)
    key = LLMCache.make_key(model="m", prompt="p")
    assert cache.get(key) is None
    cache.set(key, {"text": "hello"})
    assert cache.get(key) == {"text": "hello"}


def test_key_changes_with_any_input():
    base = dict(provider="gemini", model="m", prompt="p", schema=None)
    key = LLMCache.make_key(**base)
    assert key == LLMCache.make_key(**base)
    assert key != LLMCache.make_key(**{**base, "model": "other"})
    assert key != LLMCache.make_key(**{**base, "prompt": "p2"})
    assert key != LLMCache.make_key(**{**base, "schema": {"type": "object"}})


def test_unreadable_cache_file_is_a_miss(tmp_path):
    cache = LLMCache(tmp_path)
    key = LLMCache.make_key(prompt="p")
    cache.set(key, {"text": "x"})
    cache._path(key).write_text("{broken")
    assert cache.get(key) is None


def test_disabled_cache_never_stores(tmp_path):
    cache = LLMCache(tmp_path, enabled=False)
    cache.set("k", {"text": "x"})
    assert cache.get("k") is None


def test_second_identical_text_call_is_served_from_cache(tmp_path):
    provider = FakeProvider(["answer"])
    client = LLMClient(provider, "m", LLMCache(tmp_path))
    assert client.generate_text("q", step="s") == "answer"
    assert client.last_call_cached is False
    assert client.generate_text("q", step="s") == "answer"
    assert client.last_call_cached is True
    assert len(provider.requests) == 1
    usage = client.tracker.steps["s"]
    assert (usage.calls, usage.cache_hits, usage.prompt_tokens) == (1, 1, 10)


def test_cache_persists_across_client_instances(tmp_path):
    LLMClient(FakeProvider(["answer"]), "m", LLMCache(tmp_path)).generate_text("q")
    provider = FakeProvider([])
    client = LLMClient(provider, "m", LLMCache(tmp_path))
    assert client.generate_text("q") == "answer"
    assert provider.requests == []


def test_structured_output_is_validated_and_cached(tmp_path):
    provider = FakeProvider(['{"name": "A. Sample Person", "din": "00000001"}'])
    client = LLMClient(provider, "m", LLMCache(tmp_path))
    first = client.generate_structured("who?", Director)
    second = client.generate_structured("who?", Director)
    assert first == second == Director(name="A. Sample Person", din="00000001")
    assert len(provider.requests) == 1
    assert provider.requests[0].json_schema == Director.model_json_schema()


def test_invalid_structured_output_raises_and_is_not_cached(tmp_path):
    provider = FakeProvider(['{"name": "Someone"}', '{"name": "Someone", "din": "1"}'])
    client = LLMClient(provider, "m", LLMCache(tmp_path))
    with pytest.raises(StructuredOutputError) as info:
        client.generate_structured("who?", Director)
    assert info.value.raw_text == '{"name": "Someone"}'
    # A retry must hit the API again, not replay the bad answer from the cache.
    assert client.generate_structured("who?", Director).din == "1"
    assert len(provider.requests) == 2


def test_usage_summary_mentions_each_step(tmp_path):
    client = LLMClient(FakeProvider(["a", "b"]), "m", LLMCache(tmp_path))
    client.generate_text("x", step="extract.directors")
    client.generate_text("y", step="qa.cypher")
    summary = client.tracker.summary()
    assert "extract.directors" in summary and "qa.cypher" in summary
