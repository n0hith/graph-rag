"""Parse facts directly out of a detected table, when its shape is recognizable.

Tried before the LLM for directors (a clean "Name ... DIN nnnnnnn" + category table) and
subsidiaries (Form AOC-1's table, which lists one subsidiary per *column*, not per row).
A fact parsed this way needs no evidence-quote check: its `evidence` is the exact cell
text it came from, not a claim the LLM could have hallucinated.
"""

from __future__ import annotations

import re

Table = list[list[str]]

DIRECTOR_ROW_RE = re.compile(r"^(?P<rest>.+?)\s+DIN\s*[:\-]?\s*(?P<din>\d{6,8})\s*$", re.I)
SUBSIDIARY_NAME_ROW_RE = re.compile(r"name\s+of\s+the\s+subsidiary", re.I)
STAKE_ROW_RE = re.compile(r"%\s*of\s*shareholding", re.I)
STAKE_PCT_RE = re.compile(r"([\d.]+)\s*%")
OTHER_LISTED_HEADER_RE = re.compile(r"directorships?\s+in\s+other\s+listed\s+entit", re.I)
# "1. Tata Steel Limited (N) 2. Tata Motors Limited (N)" -> one entry per number.
LISTED_ENTRY_SPLIT_RE = re.compile(r"(?:^|\s)\d{1,2}\.\s+")
CATEGORY_CODE_RE = re.compile(r"\(([A-Z]{1,6})\)")
# The legend under TCS's table: "(N) Non-Independent, Non-Executive Director, (I) ...".
LEGEND_ENTRY_RE = re.compile(r"\(([A-Z]{1,6})\)\s*([^()]+?Director)")


def parse_category_legend(page_text: str) -> dict[str, str]:
    """Category codes a page explains, e.g. {"N": "Non-Independent, Non-Executive Director"}.
    Only read after a "Category of directorship" line, so other "(X) ..." text is ignored."""
    flat = " ".join(page_text.split())
    start = re.search(r"category of directorship[^:]*:", flat, re.I)
    if not start:
        return {}
    return {code: label.strip(" ,") for code, label in LEGEND_ENTRY_RE.findall(flat[start.end():])}


def parse_listed_directorships(cell: str, legend: dict[str, str] | None = None) -> list[dict]:
    """A "Directorship in other listed entity (Category)" cell -> one dict per company.
    "-" or blank means none. The category code is expanded with `legend` when it has it;
    anything else in brackets ("Debt Listed", "ceased w.e.f. ...") is kept as `note`."""
    text = " ".join((cell or "").split())
    if text in ("", "-", "–", "Nil", "NIL", "None"):
        return []
    legend = legend or {}
    results = []
    for entry in LISTED_ENTRY_SPLIT_RE.split(text):
        entry = entry.strip()
        if not entry:
            continue
        code_match = CATEGORY_CODE_RE.search(entry)
        code = code_match.group(1) if code_match else None
        name = re.sub(r"\[[^\]]*\]|\([^)]*\)", "", entry).strip(" ,;")
        notes = []
        for bracketed, parenthesized in re.findall(r"\[([^\]]*)\]|\(([^)]*)\)", entry):
            piece = CATEGORY_CODE_RE.sub("", bracketed or parenthesized).strip(" ,")  # "[(N) Debt Listed]"
            if piece and piece != code:
                notes.append(piece)
        results.append(
            {
                "company_name": name,
                "category": legend.get(code, code) if code else None,
                "note": "; ".join(notes) or None,
                "evidence": entry,
            }
        )
    return results


def parse_directors_table(table: Table, page_text: str = "") -> list[dict]:
    """Rows shaped like "N Chandrasekaran (Chairman) DIN 00121863" | "Non-Independent,
    Non-Executive" | ... -> one dict per matching row. Non-matching rows (headers, blank
    spacer rows) are silently skipped; an empty result means this table isn't one.

    If the table has a "Directorship in other listed entity" column, each row also gets
    `other_listed_directorships` from it (category codes expanded with the legend found in
    `page_text`); otherwise that list is empty."""
    other_col = next(
        (i for row in table for i, cell in enumerate(row) if cell and OTHER_LISTED_HEADER_RE.search(cell)),
        None,
    )
    legend = parse_category_legend(page_text)
    results = []
    for row in table:
        if not row or not row[0]:
            continue
        match = DIRECTOR_ROW_RE.search(" ".join(row[0].split()))
        if not match:
            continue
        rest, din = match.group("rest"), match.group("din")
        role_match = re.search(r"\(([^)]+)\)\s*$", rest)
        role = role_match.group(1) if role_match else ""
        name = re.sub(r"\([^)]*\)", "", rest).strip()
        name = re.sub(r"[\s*^†‡#]+$", "", name)  # footnote markers after the name
        category = " ".join(row[1].split()) if len(row) > 1 and row[1] else ""
        lowered = category.lower()
        is_independent = "independent" in lowered and "non-independent" not in lowered
        is_executive = "exec" in lowered and "non-exec" not in lowered
        status = "ceased" if "erstwhile" in rest.lower() else "current"
        other_cell = row[other_col] if other_col is not None and other_col < len(row) else ""
        results.append(
            {
                "person_name": name,
                "din": din,
                "role": role,
                "is_independent": is_independent,
                "is_executive": is_executive,
                "status": status,
                "other_listed_directorships": parse_listed_directorships(other_cell, legend),
                "evidence": f"{row[0]} | {category}" if category else row[0],
            }
        )
    return results


def parse_subsidiaries_table(table: Table) -> list[dict]:
    """Form AOC-1's table is transposed: each row is a field (e.g. "Name of the Subsidiary
    Company", "% of Shareholding"), each column (from index 2 on) is one subsidiary."""
    name_row = next((r for r in table if r and r[0] and SUBSIDIARY_NAME_ROW_RE.search(r[0])), None)
    stake_row = next((r for r in table if r and r[0] and STAKE_ROW_RE.search(r[0])), None)
    if not name_row or not stake_row:
        return []
    results = []
    for col in range(2, len(name_row)):
        name = " ".join((name_row[col] or "").split())
        if not name:
            continue
        stake_text = " ".join((stake_row[col] or "").split()) if col < len(stake_row) else ""
        stake_match = STAKE_PCT_RE.search(stake_text)
        results.append(
            {
                "subsidiary_name": name,
                "cin": None,
                "stake_pct": float(stake_match.group(1)) if stake_match else None,
                "evidence": f"{name_row[0]}: {name}; {stake_row[0]}: {stake_text}",
            }
        )
    return results
