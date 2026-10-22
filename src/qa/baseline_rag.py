"""Plain RAG baseline: retrieve chunks for a question, answer with page citations.

This is the system the graph pipeline has to beat, so it's built to be a fair, reasonably strong
baseline, not a strawman:

- Hybrid retrieval: the CANDIDATES best chunks by embedding similarity and the CANDIDATES best by
  BM25 keyword score are combined by reciprocal rank fusion, and the top `top_k` (12) are kept.
  Keywords find what embeddings of long chunks miss (a firm's registration number, a surname,
  "Firm's Registration No.").
- Company filter: when the question names pilot companies ("Tata Steel", "TCS", "TaMo"), only
  their reports are searched.
- The same answer model as the graph route (GEMINI_QA_MODEL), at temperature 0, told to answer
  only from the excerpts and cite every claim.

`hybrid=False, company_filter=False, top_k=6` reproduces the Phase 2 baseline (embeddings only),
which is how the before/after comparison in src/eval/baseline_notes.md was run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.llm.client import LLMClient
from src.qa.baseline_index import BaselineIndex, RetrievedChunk
from src.qa.bm25 import BM25
from src.qa.company_filter import companies_named
from src.qa.embeddings import Embedder

SYSTEM_PROMPT = (
    "You answer questions about Indian companies using only the report excerpts you are given. "
    "Each excerpt is labelled with its company and page number(s). Rules:\n"
    "- Base your answer only on the excerpts below; never use outside knowledge.\n"
    "- After every claim, cite the excerpt(s) it came from like [Company, p.12].\n"
    "- If the excerpts don't contain the answer, say so plainly instead of guessing.\n"
    "- Be concise and direct."
)
CANDIDATES = 40  # per retriever, before fusion
RRF_K = 60  # reciprocal rank fusion constant (the usual value)


@dataclass(frozen=True)
class Citation:
    """One chunk cited in an answer."""

    company: str
    nse_symbol: str
    page_start: int
    page_end: int

    @property
    def page_label(self) -> str:
        return f"p.{self.page_start}" if self.page_start == self.page_end else f"pp.{self.page_start}-{self.page_end}"


@dataclass(frozen=True)
class BaselineAnswer:
    """The baseline's reply to one question."""

    question: str
    answer: str
    route: str
    sources: list[Citation]
    companies: list[str] = field(default_factory=list)  # the company filter applied, if any
    retrieval: str = "hybrid"


class KeywordIndex:
    """BM25 over every chunk in the baseline index, built once per process."""

    def __init__(self, index: BaselineIndex) -> None:
        self.chunks = index.all_chunks()
        self.bm25 = BM25([c.text for c in self.chunks])

    def search(self, question: str, n: int, symbols: list[str] | None = None) -> list[RetrievedChunk]:
        allowed = {i for i, c in enumerate(self.chunks) if c.nse_symbol in symbols} if symbols else None
        return [self.chunks[i] for i, _ in self.bm25.scores(question, allowed)[:n]]


_keyword_indexes: dict[int, KeywordIndex] = {}


def _keyword_index(index: BaselineIndex) -> KeywordIndex:
    key = id(index)
    if key not in _keyword_indexes:
        _keyword_indexes[key] = KeywordIndex(index)
    return _keyword_indexes[key]


def fuse(rankings: list[list[RetrievedChunk]], top_k: int, guaranteed: int = 0) -> list[RetrievedChunk]:
    """Reciprocal rank fusion: a chunk's score is the sum of 1 / (RRF_K + rank) over the lists.
    The first `guaranteed` chunks of each list are kept whatever their fused score: fusion alone
    drops a chunk that one method ranks near the top and the other doesn't rank at all (TCS's
    directors' certificate, p.117, for "independent directors of TCS")."""
    keep: list[RetrievedChunk] = []
    for ranking in rankings:
        for chunk in ranking[:guaranteed]:
            if (chunk.nse_symbol, chunk.chunk_index) not in {(c.nse_symbol, c.chunk_index) for c in keep}:
                keep.append(chunk)
    scores: dict[tuple, float] = {}
    by_key: dict[tuple, RetrievedChunk] = {}
    for ranking in rankings:
        for rank, chunk in enumerate(ranking, 1):
            key = (chunk.nse_symbol, chunk.chunk_index)
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
            by_key.setdefault(key, chunk)
    kept = {(c.nse_symbol, c.chunk_index) for c in keep}
    rest = [by_key[k] for k in sorted(scores, key=lambda k: -scores[k]) if k not in kept]
    return (keep + rest)[:top_k]


def retrieve(question: str, index: BaselineIndex, embedder: Embedder, top_k: int, hybrid: bool = True,
             company_filter: bool = True) -> tuple[list[RetrievedChunk], list[str]]:
    symbols = companies_named(question) if company_filter else []
    [query_embedding] = embedder.embed([question])
    if not hybrid:
        return index.query(query_embedding, top_k, symbols or None), symbols
    if len(symbols) > 1:
        # Several companies named: each gets an equal share, so one report can't crowd out the other.
        share = max(1, top_k // len(symbols))
        parts = [_hybrid(question, query_embedding, index, share, [s]) for s in symbols]
        return [c for group in zip(*parts) for c in group] + [c for p in parts for c in p[min(map(len, parts)):]], symbols
    return _hybrid(question, query_embedding, index, top_k, symbols or None), symbols


def _hybrid(question: str, query_embedding, index: BaselineIndex, top_k: int, symbols) -> list[RetrievedChunk]:
    semantic = index.query(query_embedding, CANDIDATES, symbols)
    keyword = _keyword_index(index).search(question, CANDIDATES, symbols)
    return fuse([semantic, keyword], top_k, guaranteed=top_k // 3)


def _build_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    excerpts = "\n\n".join(
        f"Excerpt {i + 1} — {c.company} ({c.page_label}):\n{c.text}" for i, c in enumerate(chunks)
    )
    return f"Report excerpts:\n\n{excerpts}\n\nQuestion: {question}\n\nAnswer:"


def answer_baseline(
    question: str,
    index: BaselineIndex,
    embedder: Embedder,
    llm_client: LLMClient,
    top_k: int,
    hybrid: bool = True,
    company_filter: bool = True,
) -> BaselineAnswer:
    """Answer `question` using the baseline retrieve-then-generate pipeline."""
    retrieval = "hybrid" if hybrid else "semantic"
    if index.count() == 0:
        return BaselineAnswer(question, "The baseline index is empty. Run `baseline-index` first.", "baseline", [],
                              retrieval=retrieval)
    chunks, symbols = retrieve(question, index, embedder, top_k, hybrid, company_filter)
    if not chunks:
        return BaselineAnswer(question, "No relevant text was found.", "baseline", [], symbols, retrieval)

    prompt = _build_prompt(question, chunks)
    answer = llm_client.generate_text(prompt, system=SYSTEM_PROMPT, temperature=0.0, step="baseline.ask")

    sources = []
    seen = set()
    for c in chunks:
        key = (c.nse_symbol, c.page_start, c.page_end)
        if key in seen:
            continue
        seen.add(key)
        sources.append(Citation(c.company, c.nse_symbol, c.page_start, c.page_end))
    return BaselineAnswer(question, answer.strip(), "baseline", sources, symbols, retrieval)
