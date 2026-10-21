"""Cross-report consistency check for directorships.

A director table often lists the director's seats on *other* listed companies' boards
("Directorship in other listed entity"). When that other company is also in the pilot,
its own report is the authority on its board, so every such claim should match a director
fact in that company's own extraction. A claim that doesn't is a mismatch: a missed
director in the other report's extraction, a wrong name/DIN, or a real difference between
the two reports' "as of" dates.

Names are matched with a light normalization only (case, punctuation, "Ltd." vs "Limited",
"Mr"/"Dr" titles). Proper entity resolution is Phase 4.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from src.ingest.companies import Company

TITLES_RE = re.compile(r"^(?:mr|mrs|ms|dr|prof|shri|smt)\.?\s+")


def norm_company(name: str) -> str:
    name = name.lower().replace("&", " and ")
    name = re.sub(r"\bltd\b\.?", "limited", name)
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    name = re.sub(r"^the\s+", "", " ".join(name.split()))
    return name


def norm_person(name: str) -> str:
    name = " ".join(re.sub(r"[.,]", " ", name.lower()).split())
    return TITLES_RE.sub("", name)


def _independence(category: str | None) -> bool | None:
    """True/False when the category text says (non-)independent outright, else None."""
    lowered = (category or "").lower()
    if "non-independent" in lowered or "non independent" in lowered:
        return False
    if "independent" in lowered:
        return True
    return None


@dataclass(frozen=True)
class DirectorshipCheck:
    person_name: str
    din: str | None
    reported_by: str  # NSE symbol of the report that made the claim
    target: str  # NSE symbol of the pilot company the claim is about
    company_name: str  # as the claiming report spelled it
    category: str | None
    status: str  # "match" | "missing" | "category differs" | "target not extracted"
    detail: str = ""


def _load_facts(extracted_dir: Path, symbol: str) -> list[dict] | None:
    path = extracted_dir / f"{symbol}.jsonl"
    if not path.exists():
        return None
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def check_directorships(extracted_dir: Path, companies: list[Company]) -> list[DirectorshipCheck]:
    """Every `other_directorship` claim aimed at another pilot company, checked against that
    company's own director facts (by DIN when both sides have one, else by normalized name)."""
    by_name = {norm_company(c.name): c.nse_symbol for c in companies}
    facts = {c.nse_symbol: _load_facts(extracted_dir, c.nse_symbol) for c in companies}

    checks = []
    for reporter, reporter_facts in facts.items():
        for fact in reporter_facts or []:
            if fact["fact_type"] != "other_directorship":
                continue
            data = fact["data"]
            target = by_name.get(norm_company(data["company_name"]))
            if target is None or target == reporter:
                continue
            base = dict(person_name=data["person_name"], din=data.get("din"), reported_by=reporter,
                        target=target, company_name=data["company_name"], category=data.get("category"))
            if facts[target] is None:
                checks.append(DirectorshipCheck(**base, status="target not extracted"))
                continue

            directors = [f["data"] for f in facts[target] if f["fact_type"] == "director"]
            match = None
            if data.get("din"):
                match = next((d for d in directors if d.get("din") == data["din"]), None)
            if match is None:
                match = next((d for d in directors if norm_person(d["person_name"]) == norm_person(data["person_name"])), None)
            if match is None:
                checks.append(DirectorshipCheck(**base, status="missing",
                                                detail=f"no director with this DIN/name in {target}'s own extraction"))
                continue

            detail = f"{target} lists {match['person_name']!r} (DIN {match.get('din') or '?'})"
            claimed = _independence(data.get("category"))
            if claimed is not None and claimed != match.get("is_independent"):
                detail += f", is_independent={match.get('is_independent')}"
                checks.append(DirectorshipCheck(**base, status="category differs", detail=detail))
            else:
                checks.append(DirectorshipCheck(**base, status="match", detail=detail))
    return checks
