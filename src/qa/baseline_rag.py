"""Plain RAG baseline: retrieve top-k chunks for a question, answer with page citations.

This is the system the graph pipeline (Phase 6+) has to beat, so it's a fair baseline,
not a weak one: a real local embedding model, a real vector index, and a prompt that
asks the QA model to answer only from the retrieved text and cite every claim.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.llm.client import LLMClient
from src.qa.baseline_index import BaselineIndex, RetrievedChunk
from src.qa.embeddings import Embedder

SYSTEM_PROMPT = (
    "You answer questions about Indian companies using only the report excerpts you are given. "
    "Each excerpt is labelled with its company and page number(s). Rules:\n"
    "- Base your answer only on the excerpts below; never use outside knowledge.\n"
    "- After every claim, cite the excerpt(s) it came from like [Company, p.12].\n"
    "- If the excerpts don't contain the answer, say so plainly instead of guessing.\n"
    "- Be concise and direct."
)


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
) -> BaselineAnswer:
    """Answer `question` using the baseline retrieve-then-generate pipeline."""
    if index.count() == 0:
        return BaselineAnswer(
            question=question,
            answer="The baseline index is empty. Run `baseline-index` first.",
            route="baseline",
            sources=[],
        )

    [query_embedding] = embedder.embed([question])
    chunks = index.query(query_embedding, top_k)
    if not chunks:
        return BaselineAnswer(question, "No relevant text was found.", "baseline", [])

    prompt = _build_prompt(question, chunks)
    answer = llm_client.generate_text(prompt, system=SYSTEM_PROMPT, step="baseline.ask")

    sources = []
    seen = set()
    for c in chunks:
        key = (c.nse_symbol, c.page_start, c.page_end)
        if key in seen:
            continue
        seen.add(key)
        sources.append(Citation(c.company, c.nse_symbol, c.page_start, c.page_end))
    return BaselineAnswer(question, answer.strip(), "baseline", sources)
