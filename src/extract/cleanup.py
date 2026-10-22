"""Clean-up of extracted facts that needs no LLM call (fixes from the 50-fact sample check).

- Names: line breaks collapsed and trailing footnote markers dropped ("Kaleidoscope \\nAnimations
  \\nInc (6)" -> "Kaleidoscope Animations Inc"). The evidence quote keeps the printed text.
- Other-directorship pages: a fact cites the page where its company name is printed (Tata
  Consumer's directorship column is on p.290; the facts had the director's attendance-table
  page, p.289).
- KMP appointed after March 31, 2024 get after_fy_end: true, like directors.
- Directors get both a `category` (the independence/executive category the report gives,
  "Independent, Non-Executive Director") and a `title` (Chairman, CEO & MD, Lead Independent
  Director, ... where the report prints one next to the name); `role` shows the title if any,
  else the category. An extracted role that changes is kept as role_as_extracted.
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


# Designations a report prints for a director, beyond the independence category.
TITLE_RE = re.compile(
    r"(?:Erstwhile\s+)?(?:Non-Executive\s+)?(?:Vice[- ]?)?Chair(?:man|person)\b"
    r"|Lead Independent Director"
    r"|Chief Executive Officer\s*(?:&|and)\s*Managing Director|Managing Director\s*(?:&|and)\s*Chief Executive Officer"
    r"|(?:Erstwhile\s+)?CEO\s*&\s*MD|MD\s*&\s*CEO|COO\s*&\s*ED"
    r"|Executive Director\s*(?:&|and)\s*(?:Group\s+)?(?:Chief (?:Financial|Operating) Officer|CFO|COO)",
    re.I)


def _is_title(role: str) -> bool:
    return bool(TITLE_RE.search(role or ""))


def _name_variants(name: str) -> list[str]:
    words = [w for w in name.split() if w.rstrip(".").lower() not in {"mr", "mrs", "ms", "dr", "shri", "smt"}]
    plain = " ".join(words)
    return list(dict.fromkeys([plain, plain.replace(". ", " ").replace(".", ""), name]))


# In running text, a bare "Chairman"/"Chairperson" next to a name is usually a committee chair
# ("Michael Gibbs, Chairperson" in a committee list, "O P Bhatt, Chairman of the NRC"). From text,
# only board designations are taken, and a chair title only as "Name, Chairman," or "Chairman of
# the Board" ("Nandan M. Nilekani, Chairman, voluntarily chose ...").
TEXT_TITLE_RE = re.compile(
    r"Lead Independent Director"
    r"|Chief Executive Officer\s*(?:&|and)\s*Managing Director|Managing Director\s*(?:&|and)\s*Chief Executive Officer"
    r"|Executive Director\s*(?:&|and)\s*(?:Group\s+)?(?:Chief (?:Financial|Operating) Officer|CFO|COO)",
    re.I)
TEXT_CHAIR_RE = re.compile(r"(?:Vice[- ]?)?Chair(?:man|person)(?=\s*[,.;]|\s+of the Board)", re.I)


def find_title(name: str, page_texts: dict[int, str]) -> tuple[str, int] | None:
    """A board designation printed right after the director's name (see TEXT_TITLE_RE and
    TEXT_CHAIR_RE): the most frequent one and the first page it is on."""
    found: dict[str, list[int]] = {}
    for variant in _name_variants(name):
        patterns = [re.compile(re.escape(variant) + r"\s*[,–-]?\s*(" + TEXT_TITLE_RE.pattern + r")", re.I),
                    re.compile(re.escape(variant) + r",\s*(" + TEXT_CHAIR_RE.pattern + r")", re.I)]
        for pattern in patterns:
            for page, text in page_texts.items():
                for m in pattern.finditer(text):
                    found.setdefault(" ".join(m.group(1).split()), []).append(page)
    if not found:
        return None
    title = max(found, key=lambda t: (len(found[t]), len(t)))
    return title, min(found[title])


def set_titles_and_categories(facts: list, page_texts: dict[int, str] | None = None) -> tuple[list, list[str]]:
    """Every director gets `category` (the independence/executive category the report gives, e.g.
    "Independent, Non-Executive Director") and `title` (a designation such as Chairman, CEO & MD,
    Lead Independent Director, or None). The extracted role is used when it is a title; otherwise
    the report text is searched for the name followed by a designation. `role` is the title if
    there is one, else the category. Line breaks are collapsed; role_as_extracted keeps an
    extracted role that changed."""
    out, notes = [], []
    for f in facts:
        if f.fact_type != "director":
            out.append(f)
            continue
        raw = f.data.get("role") or ""
        extracted = f.data.get("role_as_extracted") or raw
        candidates = [" ".join(r.split()) for r in (raw, extracted) if r]
        title = next((r for r in candidates if _is_title(r)), f.data.get("title"))
        source = "extracted role" if title else None
        if not title and page_texts:
            hit = find_title(f.data["person_name"], page_texts)
            if hit:
                title, page = hit
                source = f"report text p.{page}"
        category = category_role(f)
        role = title or category
        data = {**f.data, "title": title, "category": category, "role": role}
        if source and source != "extracted role":
            data["title_source"] = source
        if raw and " ".join(raw.split()) not in (role, title):
            data.setdefault("role_as_extracted", raw)
        if data != f.data:
            if title and title != f.data.get("title"):
                notes.append(f"title: {f.data['person_name']}: {title!r} ({source})")
            out.append(_with_data(f, data=data))
        else:
            out.append(f)
    return out, notes


def clean_facts(facts: list, cg_pages: list[dict], report_pages: dict[int, str] | None = None
                ) -> tuple[list, list[str], dict]:
    """All of the above. `report_pages` (page -> text of the whole report) is where director
    titles are looked up; without it, the governance section's pages are used. Returns (facts,
    notes, name counts)."""
    facts, counts = clean_names(facts)
    facts, moved = relocate_directorships(facts, cg_pages)
    facts, kmp = mark_kmp_after_fy_end(facts)
    texts = report_pages or {p["page"]: _flat(p["text"]) for p in cg_pages}
    facts, roles = set_titles_and_categories(facts, texts)
    return facts, moved + kmp + roles, counts
