"""Tests for the baseline answer pipeline. No real embedding model, vector store or
Gemini call: a fake index, a fake embedder and a fake LLM provider stand in for them."""

from __future__ import annotations

from src.llm.cache import LLMCache
from src.llm.client import LLMClient, LLMRequest, LLMResponse
from src.qa.baseline_index import RetrievedChunk
from src.qa.baseline_rag import answer_baseline


class FakeEmbedder:
    """Returns a fixed vector per call; the actual numbers don't matter for these tests."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class FakeIndex:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self._chunks = chunks

    def count(self) -> int:
        return len(self._chunks)

    def query(self, embedding, top_k):
        return self._chunks[:top_k]


class EchoProvider:
    """Records the prompt it was given and echoes it back, so tests can check what the
    QA model was asked without needing a real API."""

    name = "fake"

    def __init__(self) -> None:
        self.last_request: LLMRequest | None = None

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.last_request = request
        return LLMResponse("OK", prompt_tokens=1, output_tokens=1)


def make_client(tmp_path) -> tuple[LLMClient, EchoProvider]:
    provider = EchoProvider()
    return LLMClient(provider, "qa-model", LLMCache(tmp_path)), provider


def test_empty_index_returns_a_clear_message_without_calling_the_llm(tmp_path):
    client, provider = make_client(tmp_path)
    result = answer_baseline("Who audits Acme?", FakeIndex([]), FakeEmbedder(), client, top_k=5)
    assert "baseline-index" in result.answer
    assert result.sources == []
    assert provider.last_request is None


def test_answer_cites_each_distinct_page_once(tmp_path):
    chunks = [
        RetrievedChunk("Acme Ltd", "ACME", 0, 10, 10, "Acme's auditor is X & Co.", distance=0.1),
        RetrievedChunk("Acme Ltd", "ACME", 1, 10, 10, "X & Co. has audited Acme since 2019.", distance=0.2),
        RetrievedChunk("Beta Ltd", "BETA", 0, 4, 5, "Beta's auditor is Y & Co.", distance=0.3),
    ]
    client, provider = make_client(tmp_path)
    result = answer_baseline("Who audits Acme and Beta?", FakeIndex(chunks), FakeEmbedder(), client, top_k=3)

    assert result.route == "baseline"
    assert len(result.sources) == 2  # the two ACME chunks share the same page and collapse to one
    assert {(s.nse_symbol, s.page_start, s.page_end) for s in result.sources} == {("ACME", 10, 10), ("BETA", 4, 5)}

    prompt = provider.last_request.prompt
    assert "Acme's auditor is X & Co." in prompt
    assert "Beta Ltd (pp.4-5)" in prompt
    assert "Who audits Acme and Beta?" in prompt


def test_top_k_limits_how_many_chunks_are_sent(tmp_path):
    chunks = [RetrievedChunk("Acme", "ACME", i, i, i, f"chunk {i}", distance=float(i)) for i in range(5)]
    client, provider = make_client(tmp_path)
    answer_baseline("q", FakeIndex(chunks), FakeEmbedder(), client, top_k=2)
    assert provider.last_request.prompt.count("Excerpt ") == 2
