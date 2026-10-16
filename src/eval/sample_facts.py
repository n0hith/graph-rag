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
    sample = sorted(sample, key=lambda f: (f.fact_type, f.page or 0))

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for f in sample:
            writer.writerow(
                [f.fact_type, f.method, f.company, f.section_type, f.page, f.fy,
                 json.dumps(f.data, ensure_ascii=False), f.evidence, ""]
            )
    return path
