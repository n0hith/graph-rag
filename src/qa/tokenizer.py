"""Token boundaries for chunking, using the same tokenizer as the embedding model.

Chunk sizes are measured in the embedding model's own tokens (not words or characters),
so a "500 token" chunk actually fills about 500 tokens of the model's 512-token window.
"""

from __future__ import annotations

from typing import Protocol


class Tokenizer(Protocol):
    """Anything that can split text into tokens and report each token's character span."""

    def token_offsets(self, text: str) -> list[tuple[int, int]]:
        """Return (start, end) character offsets for each token, in order, no special tokens."""
        ...


class HFTokenizer:
    """Wraps a HuggingFace fast tokenizer for a sentence-transformers model."""

    def __init__(self, model_name: str) -> None:
        from transformers import AutoTokenizer

        self._tokenizer = AutoTokenizer.from_pretrained(model_name)
        if not self._tokenizer.is_fast:
            raise RuntimeError(f"{model_name} has no fast tokenizer; offset mapping needs one")
        # We tokenize a whole report at once just to get offsets, far past the model's own
        # 512-token window; that's fine here, so silence the "sequence too long" warning.
        self._tokenizer.model_max_length = int(1e12)

    def token_offsets(self, text: str) -> list[tuple[int, int]]:
        encoding = self._tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
        return [tuple(span) for span in encoding["offset_mapping"]]
