"""Clean-up of extracted facts that needs no LLM call (fixes from the 50-fact sample check).

- Names: line breaks collapsed and trailing footnote markers dropped ("Kaleidoscope \\nAnimations
  \\nInc (6)" -> "Kaleidoscope Animations Inc"). The evidence quote keeps the printed text.
- Other-directorship pages: a fact cites the page where its company name is printed (Tata
  Consumer's directorship column is on p.290; the facts had the director's attendance-table
  page, p.289).
- KMP appointed after March 31, 2024 get after_fy_end: true, like directors.
- Director roles: line breaks collapsed; an empty role, the generic "Director", or a table
  heading ("Executive Directors") is replaced by the category the report gives for that
  director ("Independent, Non-Executive Director"); the old value is kept as role_as_extracted.
"""

from __future__ import annotations

import datetime
import re

from src.extract.tables import parse_date
from src.resolve.normalize import FOOTNOTE_RE, person_tokens

FY_END = datetime.date(2024, 3, 31)
NAME_FIELDS = ("person_name", "company_name", "subsidiary_name", "firm_name", "party_name")
GENERIC_ROLE_RE = re.compile(r"^(?:director|.*directors)$", re.I)
TABLE_CATEGORY_RE = re.compile(r"\|\s*([^|]+?)\s*$")


def clean_name(name: str) -> str:
    return FOOTNOTE_RE.sub("", " ".join(name.split())).strip()


def _with_data(f, **changes):
    from src.extract.extractor import Fact

    return Fact(**{**f.__dict__, **changes})


def clean_names(facts: list) -> tuple[list, dict]:
    """Returns (facts, counts of names changed: {"footnote": n, "line_break": n})."""
    out, counts = [], {"footnote": 0, "line_break": 0}
    for f in facts:
        data = dict(f.data)
        for key in NAME_FIELDS:
            value = data.get(key)
            if not isinstance(value, str):
                continue
            cleaned = clean_name(value)
            if cleaned != value:
                if "\n" in value:
                    counts["line_break"] += 1
                if FOOTNOTE_RE.search(" ".join(value.split())):
                    counts["footnote"] += 1
                data[key] = cleaned
        out.append(_with_data(f, data=data) if data != f.data else f)
    return out, counts


def _flat(text: str) -> str:
    return " ".join(text.split())


def relocate_directorships(facts: list, cg_pages: list[dict]) -> tuple[list, list[str]]:
    """Move each other_directorship fact to the page that prints its company name, preferring a
    page that also names the person, then the page nearest the one it cited."""
    texts = {p["page"]: _flat(p["text"]) for p in cg_pages}
    out, notes = [], []
    for f in facts:
        if f.fact_type != "other_directorship" or not texts:
            out.append(f)
            continue
        name = _flat(f.data["company_name"])
        if name in texts.get(f.page, ""):
            out.append(f)
            continue
        surname = (person_tokens(f.data.get("person_name", "")) or [""])[-1]
        pages = [p for p, t in texts.items() if name in t]
        if not pages:
            out.append(f)
            continue
        best = min(pages, key=lambda p: (surname not in texts[p].lower(), abs(p - (f.page or p))))
        notes.append(f"directorship page: {f.data.get('person_name')} / {name}: p.{f.page} -> p.{best}")
        out.append(_with_data(f, page=best))
    return out, notes


def mark_kmp_after_fy_end(facts: list) -> tuple[list, list[str]]:
    out, notes = [], []
    for f in facts:
        date = parse_date(f.data.get("appointed_on")) if f.fact_type == "kmp" else None
        if date and date > FY_END and not f.data.get("after_fy_end"):
            notes.append(f"KMP appointed after the year end: {f.data['person_name']} ({f.data['role']}, "
                         f"{f.data['appointed_on']})")
            out.append(_with_data(f, data={**f.data, "after_fy_end": True}))
        else:
            out.append(f)
    return out, notes


def category_role(f) -> str:
    """The director's category as the report gives it: the table's category cell ("O P Bhatt DIN
    00548091 | Independent, Non-Executive"), else the independent/executive flags."""
    cell = TABLE_CATEGORY_RE.search(f.evidence or "")
    if cell and re.search(r"independent|executive", cell.group(1), re.I):
        text = cell.group(1).strip().rstrip(",")
        return text if text.lower().endswith("director") else f"{text} Director"
    if f.data.get("is_executive"):
        return "Executive Director"
    if f.data.get("is_independent"):
        return "Independent Director"
    return "Non-Executive, Non-Independent Director"


def clean_roles(facts: list) -> tuple[list, list[str]]:
    out, notes = [], []
    for f in facts:
        if f.fact_type != "director":
            out.append(f)
            continue
        raw = f.data.get("role") or ""
        role = " ".join(raw.split())
        if not role or GENERIC_ROLE_RE.match(role):
            role = category_role(f)
            notes.append(f"role: {f.data['person_name']}: {raw!r} -> {role!r}")
        if role != raw:
            data = {**f.data, "role": role}
            if raw and " ".join(raw.split()) != role:
                data.setdefault("role_as_extracted", raw)
            out.append(_with_data(f, data=data))
        else:
            out.append(f)
    return out, notes


def clean_facts(facts: list, cg_pages: list[dict]) -> tuple[list, list[str], dict]:
    """All of the above. Returns (facts, notes, name counts)."""
    facts, counts = clean_names(facts)
    facts, moved = relocate_directorships(facts, cg_pages)
    facts, kmp = mark_kmp_after_fy_end(facts)
    facts, roles = clean_roles(facts)
    return facts, moved + kmp + roles, counts
