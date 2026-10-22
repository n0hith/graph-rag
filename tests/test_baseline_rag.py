"""Tests for the baseline answer pipeline. No real embedding model, vector store or
Gemini call: a fake index, a fake embedder and a fake LLM provider stand in for them."""

from __future__ import annotations

from src.llm.cache import LLMCache
from src.llm.client import LLMClient, LLMRequest, LLMResponse
from src.qa.baseline_index import RetrievedChunk
from src.qa.baseline_rag import _keyword_indexes, answer_baseline, fuse
from src.qa.bm25 import BM25
from src.qa.company_filter import companies_named


class FakeEmbedder:
    """Returns a fixed vector per call; the actual numbers don't matter for these tests."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class FakeIndex:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self._chunks = chunks

    def count(self) -> int:
        return len(self._chunks)

    def query(self, embedding, top_k, symbols=None):
        chunks = [c for c in self._chunks if not symbols or c.nse_symbol in symbols]
        return chunks[:top_k]

    def all_chunks(self):
        return list(self._chunks)


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


# ---------------------------------------------------------------- Phase 7 step 1: stronger baseline


def chunk(symbol, i, text):
    return RetrievedChunk(symbol.title() + " Ltd", symbol, i, i, i, text, distance=float(i))


def test_keyword_search_brings_in_a_chunk_the_embeddings_missed(tmp_path):
    # The fake embedder ranks chunks in list order; the auditor's signature block is last.
    chunks = [chunk("ACME", i, f"filler text about strategy {i}") for i in range(5)]
    chunks.append(chunk("ACME", 5, "For B S R & Co. LLP Chartered Accountants Firm's Registration No. 101248W"))
    _keyword_indexes.clear()
    client, provider = make_client(tmp_path)
    answer_baseline("Firm's Registration No. of the auditor", FakeIndex(chunks), FakeEmbedder(), client, top_k=3)
    assert "B S R & Co. LLP" in provider.last_request.prompt
    _keyword_indexes.clear()
    answer_baseline("Firm's Registration No. of the auditor", FakeIndex(chunks), FakeEmbedder(), client, top_k=3,
                    hybrid=False)
    assert "B S R & Co. LLP" not in provider.last_request.prompt  # the Phase 2 baseline misses it


def test_company_filter_searches_only_the_named_companies(tmp_path):
    chunks = [chunk("TATASTEEL", 0, "Tata Steel auditor Price Waterhouse"), chunk("TCS", 1, "TCS auditor B S R")]
    _keyword_indexes.clear()
    client, provider = make_client(tmp_path)
    result = answer_baseline("Who is the statutory auditor of Tata Steel?", FakeIndex(chunks), FakeEmbedder(),
                             client, top_k=5)
    assert result.companies == ["TATASTEEL"]
    assert "Price Waterhouse" in provider.last_request.prompt and "B S R" not in provider.last_request.prompt
    assert companies_named("Directors of both TaMo and Tata Steel?") == ["TATAMOTORS", "TATASTEEL"]
    assert companies_named("What is the HTML version?") == []


def test_answer_runs_at_temperature_zero(tmp_path):
    _keyword_indexes.clear()
    client, provider = make_client(tmp_path)
    answer_baseline("q", FakeIndex([chunk("ACME", 0, "text")]), FakeEmbedder(), client, top_k=1)
    assert provider.last_request.temperature == 0.0


def test_reciprocal_rank_fusion_favours_chunks_both_lists_rank_high():
    a, b, c = chunk("X", 0, "a"), chunk("X", 1, "b"), chunk("X", 2, "c")
    assert [x.chunk_index for x in fuse([[a, b, c], [b, c, a]], 2)] == [1, 0]


def test_bm25_scores_rare_words_higher():
    bm = BM25(["the auditor is B S R", "the auditor of the company", "registration number 101248W"])
    assert bm.scores("101248W registration")[0][0] == 2
    assert [i for i, _ in bm.scores("auditor")] in ([0, 1], [1, 0])


def test_each_methods_top_hits_survive_fusion():
    # c0 is the keyword list's best hit but absent from the semantic list; plain fusion drops it.
    sem = [chunk("X", i, str(i)) for i in range(1, 8)]
    kw = [chunk("X", 0, "0")] + [chunk("X", i, str(i)) for i in range(7, 1, -1)]
    assert 0 not in [c.chunk_index for c in fuse([sem, kw], 3)]
    assert 0 in [c.chunk_index for c in fuse([sem, kw], 3, guaranteed=1)]


def test_two_named_companies_share_the_chunks(tmp_path):
    chunks = [chunk("TATASTEEL", i, f"Tata Steel board director {i}") for i in range(6)]
    chunks += [chunk("TATAMOTORS", 10 + i, f"Tata Motors board {i}") for i in range(6)]
    _keyword_indexes.clear()
    client, provider = make_client(tmp_path)
    result = answer_baseline("Directors on the boards of both Tata Motors and Tata Steel?", FakeIndex(chunks),
                             FakeEmbedder(), client, top_k=4)
    assert result.companies == ["TATAMOTORS", "TATASTEEL"]
    assert {s.nse_symbol for s in result.sources} == {"TATAMOTORS", "TATASTEEL"}
    assert provider.last_request.prompt.count("Excerpt ") == 4
