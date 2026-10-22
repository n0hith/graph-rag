"""Okapi BM25 keyword scoring over the baseline's chunks (in memory; ~3,600 chunks).

Complements the embedding search: exact words such as a firm's registration number, a person's
surname or "Firm's Registration No." score high here even when the embedding of a long chunk
doesn't sit close to the question's."""

from __future__ import annotations

import math
import re
from collections import Counter

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {"the", "of", "and", "a", "an", "in", "to", "for", "is", "are", "was", "were", "on", "by", "with",
             "as", "at", "from", "or", "that", "this", "which", "who", "what", "its", "it", "be", "did", "does",
             "do", "has", "have", "how", "many", "much"}


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


class BM25:
    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(d)) for d in documents]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_length = sum(self.lengths) / len(self.lengths) if self.lengths else 0.0
        df = Counter(t for d in self.docs for t in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str, allowed: set[int] | None = None) -> list[tuple[int, float]]:
        """(document index, score) for documents matching any query word, best first."""
        terms = set(tokenize(query))
        out = []
        for i, doc in enumerate(self.docs):
            if allowed is not None and i not in allowed:
                continue
            score = 0.0
            for t in terms:
                f = doc.get(t)
                if f:
                    norm = f + self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avg_length)
                    score += self.idf[t] * f * (self.k1 + 1) / norm
            if score > 0:
                out.append((i, score))
        return sorted(out, key=lambda x: -x[1])
