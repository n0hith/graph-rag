"""Parse facts directly out of a detected table, when its shape is recognizable.

Tried before the LLM for directors (a clean "Name ... DIN nnnnnnn" + category table) and
subsidiaries (Form AOC-1's table, which lists one subsidiary per *column*, not per row).
A fact parsed this way needs no evidence-quote check: its `evidence` is the exact cell
text it came from, not a claim the LLM could have hallucinated.
"""

from __future__ import annotations

import datetime
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
FOOTNOTE_MARKER_RE = re.compile(r"[\s*^†‡#@$]+$")
# A footnote definition starts a line: marker, then the note text up to a blank line.
FOOTNOTE_DEF_RE = re.compile(r"(?m)^[ \t]*([*^†‡#@$]{1,4})(?=[A-Za-z])(.+?)(?=\n[ \t]*\n|\Z)", re.S)
_DATE = r"(\w+ \d{1,2}, \d{4}|\d{1,2}(?:st|nd|rd|th)? \w+,? \d{4}|\d{1,2}[./-]\d{1,2}[./-]\d{4})"
CHANGE_DATE_RE = re.compile(rf"(?:w\.?\s?e\.?\s?f\.?|with effect from|effective(?: from)?|from|on)\s+{_DATE}", re.I)
CERT_DIN_LINE_RE = re.compile(r"\(?(\d{8})\)?")


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


def parse_footnotes(text: str) -> dict[str, str]:
    """Footnote definitions like "^^appointed as Independent Director w.e.f. October 12, 2023",
    keyed by marker. A marker's first definition wins: TCS reuses "*" for a later table's
    note on the same page."""
    notes: dict[str, str] = {}
    for m in FOOTNOTE_DEF_RE.finditer(text):
        notes.setdefault(m.group(1), " ".join(m.group(2).split()))
    return notes


def parse_change(note: str) -> tuple[str, str | None]:
    """("appointed" | "ceased" | "current", date or None) from a footnote or sentence about
    a director. "re-appointed" is not a change of board membership."""
    lowered = note.lower()
    date = CHANGE_DATE_RE.search(note)
    when = date.group(1) if date else None
    if re.search(r"ceased|resigned|retired|completion of (?:his|her|their) term|stepped down", lowered):
        return "ceased", when
    if re.search(r"(?<!re-)(?<!re)appointed", lowered):
        return "appointed", when
    return "current", None


def parse_date(text: str | None) -> datetime.date | None:
    """"October 12, 2023", "12 October 2023", "12/10/2023", "12.10.2023" -> a date."""
    if not text:
        return None
    cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", " ".join(text.replace(",", " ").split()))
    for fmt in ("%B %d %Y", "%d %B %Y", "%b %d %Y", "%d %b %Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def parse_din_certificate(page_text: str) -> list[dict]:
    """The certificate of non-disqualification of directors (SEBI LODR Schedule V) lists
    the board on March 31 as rows of serial no., name, DIN and appointment date, one value
    per line. Every pilot report has one. Returns [{"name", "din"}] in table order; empty
    if `page_text` isn't such a certificate. The name is the line next to the DIN that has
    letters and no digits (before it in most reports, after it in Tata Consumer's)."""
    if not re.search(r"disqualif", page_text, re.I):
        return []
    lines = [line.strip() for line in page_text.split("\n")]
    rows = []
    for i, line in enumerate(lines):
        m = CERT_DIN_LINE_RE.fullmatch(line)
        if not m:
            continue
        before = lines[i - 1] if i else ""
        after = lines[i + 1] if i + 1 < len(lines) else ""
        name = before if re.search(r"[A-Za-z]{2}", before) and not re.search(r"\d", before) else after
        if re.search(r"[A-Za-z]{2}", name):
            rows.append({"name": name, "din": m.group(1)})
    return rows if len(rows) >= 3 else []


def parse_directors_table(table: Table, page_text: str = "", footnote_text: str = "") -> list[dict]:
    """Rows shaped like "N Chandrasekaran (Chairman) DIN 00121863" | "Non-Independent,
    Non-Executive" | ... -> one dict per matching row. Non-matching rows (headers, blank
    spacer rows) are silently skipped; an empty result means this table isn't one.

    If the table has a "Directorship in other listed entity" column, each row also gets
    `other_listed_directorships` from it (category codes expanded with the legend found in
    `page_text`); otherwise that list is empty. A footnote marker after a name ("Don
    Callahan^^^") is looked up in `footnote_text` (the table's page and the next, where TCS
    prints them) and sets the status and its date ("^^^ceased to be Director w.e.f. January
    10, 2024")."""
    other_col = next(
        (i for row in table for i, cell in enumerate(row) if cell and OTHER_LISTED_HEADER_RE.search(cell)),
        None,
    )
    legend = parse_category_legend(page_text)
    footnotes = parse_footnotes(footnote_text or page_text)
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
        marker_match = FOOTNOTE_MARKER_RE.search(name)
        marker = marker_match.group(0).strip() if marker_match else ""
        name = FOOTNOTE_MARKER_RE.sub("", name)
        category = " ".join(row[1].split()) if len(row) > 1 and row[1] else ""
        lowered = category.lower()
        is_independent = "independent" in lowered and "non-independent" not in lowered
        is_executive = "exec" in lowered and "non-exec" not in lowered
        footnote = footnotes.get(marker, "")
        status, change_date = parse_change(footnote)
        if "erstwhile" in rest.lower():
            status = "ceased"
        other_cell = row[other_col] if other_col is not None and other_col < len(row) else ""
        results.append(
            {
                "person_name": name,
                "din": din,
                "role": role,
                "is_independent": is_independent,
                "is_executive": is_executive,
                "status": status,
                "appointed_on": change_date if status == "appointed" else None,
                "ceased_on": change_date if status == "ceased" else None,
                "footnote": footnote or None,
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
    country_row = next((r for r in table if r and r[0] and r[0].strip().lower() == "country"), None)
    if not name_row or not stake_row:
        return []
    results = []
    for col in range(2, len(name_row)):
        name = " ".join((name_row[col] or "").split())
        if not name:
            continue
        stake_text = " ".join((stake_row[col] or "").split()) if col < len(stake_row) else ""
        stake_match = STAKE_PCT_RE.search(stake_text)
        country = " ".join((country_row[col] or "").split()) if country_row and col < len(country_row) else ""
        results.append(
            {
                "subsidiary_name": name,
                "country": country or None,
                "cin": None,
                "stake_pct": float(stake_match.group(1)) if stake_match else None,
                "evidence": f"{name_row[0]}: {name}; {stake_row[0]}: {stake_text}",
            }
        )
    return results
