"""Export a random sample of extracted facts to CSV, with a blank "correct?" column for
hand-checking against the source PDFs (PROJECT_SPEC.md Phase 3)."""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

from src.extract.extractor import Fact

COLUMNS = ["fact_type", "method", "company", "section_type", "page", "fy", "details", "evidence", "correct?"]


def export_sample(facts: list[Fact], path: Path, n: int, seed: int = 42) -> Path:
    """Write up to `n` facts (all of them if there are fewer) to `path` as CSV."""
    rng = random.Random(seed)
    sample = facts if len(facts) <= n else rng.sample(facts, n)
    _write(sorted(sample, key=lambda f: (f.fact_type, f.page or 0)), path)
    return path


def weight(f: Fact) -> float:
    """LLM facts are where mistakes hide, related-party amounts most of all."""
    w = 3.0 if f.method == "llm" else 1.0
    if f.fact_type == "related_party":
        w *= 2.0
    return w


def stratified_sample(
    facts: list[Fact],
    n: int,
    must_include: list[tuple[callable, int]] = (),
    seed: int = 42,
) -> list[Fact]:
    """`n` facts spread across companies and fact types, weighted by `weight`.

    First each (predicate, k) in `must_include` contributes k random matching facts. Then
    every company gets an equal share of `n`; within a company, each fact type present gets
    one fact first, and the rest of the share is drawn without replacement by weight."""
    rng = random.Random(seed)
    chosen: list[Fact] = []
    taken: set[int] = set()

    def take(f):
        chosen.append(f)
        taken.add(id(f))

    for predicate, k in must_include:
        pool = [f for f in facts if predicate(f) and id(f) not in taken]
        for f in rng.sample(pool, min(k, len(pool))):
            take(f)

    companies = sorted({f.nse_symbol for f in facts})
    for i, symbol in enumerate(companies):
        share = n // len(companies) + (1 if i < n % len(companies) else 0)
        pool = [f for f in facts if f.nse_symbol == symbol and id(f) not in taken]
        need = max(0, share - sum(f.nse_symbol == symbol for f in chosen))  # must-includes count toward it
        for fact_type in sorted({f.fact_type for f in pool}):
            if need and not any(f.fact_type == fact_type for f in chosen if f.nse_symbol == symbol):
                candidates = [f for f in pool if f.fact_type == fact_type and id(f) not in taken]
                take(rng.choices(candidates, weights=[weight(f) for f in candidates])[0])
                need -= 1
        while need > 0:
            candidates = [f for f in pool if id(f) not in taken]
            if not candidates:
                break
            take(rng.choices(candidates, weights=[weight(f) for f in candidates])[0])
            need -= 1
    return sorted(chosen, key=lambda f: (f.nse_symbol, f.fact_type, f.page or 0))


def export_stratified_sample(facts: list[Fact], path: Path, n: int, must_include=(), seed: int = 42) -> list[Fact]:
    sample = stratified_sample(facts, n, must_include, seed)
    _write(sample, path)
    return sample


def _write(sample: list[Fact], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for f in sample:
            writer.writerow(
                [f.fact_type, f.method, f.company, f.section_type, f.page, f.fy,
                 json.dumps(f.data, ensure_ascii=False), f.evidence, ""]
            )
