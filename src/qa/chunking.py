"""Split a report's full text into overlapping chunks, each labelled with its page range.

Chunks are windows over the embedding model's own tokens (see `tokenizer.py`), not words,
so chunk sizes match what the embedding model actually sees. A chunk that spans a page
break records both the first and last page it touches, so citations stay honest.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.qa.tokenizer import Tokenizer

PAGE_SEPARATOR = "\n\n"


@dataclass(frozen=True)
class Chunk:
    """One retrievable piece of a company's report."""

    company: str
    nse_symbol: str
    chunk_index: int
    text: str
    token_count: int
    page_start: int
    page_end: int

    @property
    def chunk_id(self) -> str:
        return f"{self.nse_symbol}:{self.chunk_index}"

    @property
    def page_label(self) -> str:
        return f"p.{self.page_start}" if self.page_start == self.page_end else f"pp.{self.page_start}-{self.page_end}"


def chunk_pages(
    pages: list[tuple[int, str]],
    tokenizer: Tokenizer,
    chunk_tokens: int,
    overlap_tokens: int,
) -> list[tuple[str, int, int, int]]:
    """Chunk a sequence of (page_number, page_text) pairs.

    Returns a list of (text, token_count, page_start, page_end) tuples, in order. Pages
    are joined in the given order with a blank line between them before tokenizing, so a
    sentence split across a page boundary still forms one chunk when it falls mid-window.
    """
    pages = [(n, t) for n, t in pages if t.strip()]
    if not pages:
        return []

    joined_parts: list[str] = []
    page_ranges: list[tuple[int, int, int]] = []  # (page_number, start_offset, end_offset)
    offset = 0
    for page_number, text in pages:
        start = offset
        joined_parts.append(text)
        offset += len(text)
        page_ranges.append((page_number, start, offset))
        joined_parts.append(PAGE_SEPARATOR)
        offset += len(PAGE_SEPARATOR)
    joined = "".join(joined_parts)

    token_spans = [span for span in tokenizer.token_offsets(joined) if span[1] > span[0]]
    if not token_spans:
        return []

    stride = max(chunk_tokens - overlap_tokens, 1)
    total = len(token_spans)
    results: list[tuple[str, int, int, int]] = []
    i = 0
    while i < total:
        j = min(i + chunk_tokens, total)
        char_start = token_spans[i][0]
        char_end = token_spans[j - 1][1]
        page_start, page_end = _pages_for_range(page_ranges, char_start, char_end)
        results.append((joined[char_start:char_end], j - i, page_start, page_end))
        if j == total:
            break
        i += stride
    return results


def _pages_for_range(page_ranges: list[tuple[int, int, int]], char_start: int, char_end: int) -> tuple[int, int]:
    overlapping = [number for number, start, end in page_ranges if end > char_start and start < char_end]
    if not overlapping:
        overlapping = [page_ranges[0][0]]
    return min(overlapping), max(overlapping)


def chunk_company(
    company_name: str,
    nse_symbol: str,
    pages: list[tuple[int, str]],
    tokenizer: Tokenizer,
    chunk_tokens: int,
    overlap_tokens: int,
) -> list[Chunk]:
    """Chunk one company's pages into labelled, citable `Chunk` objects."""
    raw = chunk_pages(pages, tokenizer, chunk_tokens, overlap_tokens)
    return [
        Chunk(
            company=company_name,
            nse_symbol=nse_symbol,
            chunk_index=index,
            text=text,
            token_count=token_count,
            page_start=page_start,
            page_end=page_end,
        )
        for index, (text, token_count, page_start, page_end) in enumerate(raw)
    ]
