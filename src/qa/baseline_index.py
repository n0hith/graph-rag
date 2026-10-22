"""Build and query the Chroma vector index used by the plain RAG baseline.

Each company's full report text is chunked (see `chunking.py`), embedded, and stored as
one row per chunk with its company name, NSE symbol and page range as metadata, so answers
can always cite a source. A small manifest file tracks which PDF (by sha256) and embedding
model produced each company's chunks, so re-running `baseline-index` skips companies that
haven't changed.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from src.ingest.companies import Company
from src.ingest.download import sha256_file
from src.ingest.sectionize import read_pages
from src.qa.chunking import Chunk, chunk_company
from src.qa.embeddings import Embedder
from src.qa.tokenizer import Tokenizer

logger = logging.getLogger(__name__)

COLLECTION_NAME = "baseline_chunks"
MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True)
class RetrievedChunk:
    """One chunk returned for a query, with its similarity distance (lower is closer)."""

    company: str
    nse_symbol: str
    chunk_index: int
    page_start: int
    page_end: int
    text: str
    distance: float

    @property
    def page_label(self) -> str:
        return f"p.{self.page_start}" if self.page_start == self.page_end else f"pp.{self.page_start}-{self.page_end}"


class BaselineIndex:
    """Thin wrapper around a persistent Chroma collection."""

    def __init__(self, vector_store_dir: Path, collection_name: str = COLLECTION_NAME) -> None:
        import chromadb

        vector_store_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(vector_store_dir))
        self.collection = self._client.get_or_create_collection(collection_name)

    def delete_company(self, nse_symbol: str) -> None:
        if self.collection.count():
            self.collection.delete(where={"nse_symbol": nse_symbol})

    def add(self, chunks: list[Chunk], embeddings: list[list[float]], source_pdf: str) -> None:
        if not chunks:
            return
        self.collection.add(
            ids=[c.chunk_id for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=embeddings,
            metadatas=[
                {
                    "company": c.company,
                    "nse_symbol": c.nse_symbol,
                    "chunk_index": c.chunk_index,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "source_pdf": source_pdf,
                }
                for c in chunks
            ],
        )

    def count(self) -> int:
        return self.collection.count()

    def query(self, embedding: list[float], top_k: int, symbols: list[str] | None = None) -> list[RetrievedChunk]:
        """The `top_k` chunks closest to `embedding`, only from `symbols`' reports if given."""
        if self.collection.count() == 0:
            return []
        where = {"nse_symbol": {"$in": list(symbols)}} if symbols else None
        result = self.collection.query(
            query_embeddings=[embedding],
            n_results=min(top_k, self.collection.count()),
            where=where,
        )
        return [_chunk(doc, meta, distance)
                for doc, meta, distance in zip(result["documents"][0], result["metadatas"][0], result["distances"][0])]

    def all_chunks(self) -> list[RetrievedChunk]:
        """Every chunk (for keyword search), in a stable order."""
        result = self.collection.get(include=["documents", "metadatas"])
        chunks = [_chunk(doc, meta, 0.0) for doc, meta in zip(result["documents"], result["metadatas"])]
        return sorted(chunks, key=lambda c: (c.nse_symbol, c.chunk_index))


def _chunk(doc: str, meta: dict, distance: float) -> RetrievedChunk:
    return RetrievedChunk(company=meta["company"], nse_symbol=meta["nse_symbol"], chunk_index=meta["chunk_index"],
                          page_start=meta["page_start"], page_end=meta["page_end"], text=doc, distance=distance)


@dataclass(frozen=True)
class IndexStats:
    nse_symbol: str
    chunk_count: int
    skipped: bool


def build_index(
    companies: list[Company],
    raw_pdf_dir: Path,
    vector_store_dir: Path,
    embedder: Embedder,
    tokenizer: Tokenizer,
    chunk_tokens: int,
    overlap_tokens: int,
    embedding_model_name: str,
    force: bool = False,
) -> list[IndexStats]:
    """Chunk, embed and store every company's report. Skips a company whose PDF and
    embedding model match what's already indexed, unless `force` is set."""
    index = BaselineIndex(vector_store_dir)
    manifest = _load_manifest(vector_store_dir)
    stats = []
    for company in companies:
        pdf_path = raw_pdf_dir / company.pdf_name
        digest = sha256_file(pdf_path)
        prev = manifest.get(company.nse_symbol)
        if (
            not force
            and prev
            and prev.get("pdf_sha256") == digest
            and prev.get("embedding_model") == embedding_model_name
        ):
            stats.append(IndexStats(company.nse_symbol, prev.get("chunk_count", 0), skipped=True))
            continue

        pages = read_pages(pdf_path)
        chunks = chunk_company(
            company.name,
            company.nse_symbol,
            [(p.number, p.text) for p in pages],
            tokenizer,
            chunk_tokens,
            overlap_tokens,
        )
        index.delete_company(company.nse_symbol)
        if chunks:
            embeddings = embedder.embed([c.text for c in chunks])
            index.add(chunks, embeddings, pdf_path.name)
        manifest[company.nse_symbol] = {
            "pdf_sha256": digest,
            "chunk_count": len(chunks),
            "embedding_model": embedding_model_name,
        }
        logger.info("%s: indexed %d chunks", company.nse_symbol, len(chunks))
        stats.append(IndexStats(company.nse_symbol, len(chunks), skipped=False))
    _save_manifest(vector_store_dir, manifest)
    return stats


def _load_manifest(vector_store_dir: Path) -> dict:
    path = vector_store_dir / MANIFEST_NAME
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read %s; treating as empty", path)
        return {}


def _save_manifest(vector_store_dir: Path, manifest: dict) -> None:
    vector_store_dir.mkdir(parents=True, exist_ok=True)
    path = vector_store_dir / MANIFEST_NAME
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    os.replace(tmp, path)
