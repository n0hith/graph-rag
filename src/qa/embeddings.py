"""Local embedding model (sentence-transformers), used for both indexing and queries."""

from __future__ import annotations

from typing import Protocol


class Embedder(Protocol):
    """Anything that turns text into vectors."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Order matches the input."""
        ...


class SentenceTransformerEmbedder:
    """Wraps a local sentence-transformers model. Loaded once and reused."""

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # bge models are trained for cosine similarity, which needs normalized vectors.
        vectors = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vectors]
