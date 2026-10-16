"""Chunking tests. Uses a plain whitespace tokenizer instead of the real embedding
model's tokenizer, so these tests stay fast and don't need a model download."""

from __future__ import annotations

import re

from src.qa.chunking import chunk_company, chunk_pages


class WhitespaceTokenizer:
    """Treats each run of non-space characters as one token. Deterministic and offline."""

    def token_offsets(self, text: str) -> list[tuple[int, int]]:
        return [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]


def words(n: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_short_text_is_a_single_chunk():
    pages = [(1, words(10))]
    chunks = chunk_pages(pages, WhitespaceTokenizer(), chunk_tokens=500, overlap_tokens=60)
    assert len(chunks) == 1
    text, token_count, page_start, page_end = chunks[0]
    assert token_count == 10
    assert page_start == page_end == 1
    assert text == words(10)


def test_long_text_is_split_with_overlap():
    pages = [(1, words(1000))]
    chunks = chunk_pages(pages, WhitespaceTokenizer(), chunk_tokens=500, overlap_tokens=60)
    assert len(chunks) == 3  # stride 440: windows at 0, 440, 880
    assert [c[1] for c in chunks] == [500, 500, 120]
    # consecutive chunks overlap: the tail of chunk 1 reappears at the head of chunk 2
    first_tail = chunks[0][0].split()[-60:]
    second_head = chunks[1][0].split()[:60]
    assert first_tail == second_head


def test_chunk_records_the_pages_it_spans():
    pages = [(5, words(300)), (6, words(300)), (7, words(300))]
    chunks = chunk_pages(pages, WhitespaceTokenizer(), chunk_tokens=500, overlap_tokens=60)
    # the first chunk (tokens 0-499) spans page 5 fully and part of page 6
    assert chunks[0][2] == 5
    assert chunks[0][3] == 6
    # the last chunk reaches page 7
    assert chunks[-1][3] == 7


def test_empty_pages_produce_no_chunks():
    assert chunk_pages([], WhitespaceTokenizer(), 500, 60) == []
    assert chunk_pages([(1, "   "), (2, "")], WhitespaceTokenizer(), 500, 60) == []


def test_chunk_company_assigns_ids_and_metadata():
    pages = [(1, words(10))]
    chunks = chunk_company("Acme Ltd", "ACME", pages, WhitespaceTokenizer(), 500, 60)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.company == "Acme Ltd"
    assert chunk.nse_symbol == "ACME"
    assert chunk.chunk_index == 0
    assert chunk.chunk_id == "ACME:0"
    assert chunk.page_label == "p.1"


def test_page_label_for_a_multi_page_chunk():
    pages = [(1, words(300)), (2, words(300))]
    chunks = chunk_company("Acme Ltd", "ACME", pages, WhitespaceTokenizer(), 500, 60)
    assert chunks[0].page_label == "pp.1-2"
