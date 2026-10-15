"""Find the sections of an annual report that later phases extract facts from.

How it works:
1. Every page is read with PyMuPDF. Lines that are bold or noticeably larger than the page's
   body text are treated as *heading lines*. Matching headings (instead of the whole page)
   avoids false hits from sentences like "see the Report on Corporate Governance".
2. Each section type has a start pattern. Among the pages whose headings match it, the one
   whose matching heading has the largest font wins (a real title beats a sub-heading in the
   Board's report that merely mentions the section); ties go to the earliest page. AOC-1
   and the secretarial report use content checks instead (see `detect_sections`).
3. The section ends just before the first later page with a *new* heading (not seen on the
   previous two pages, so running headers like "Directors' Report" don't count) that is
   either a named boundary ("Management Discussion and Analysis", "Annexure 4", ...) at
   least nearly as large as the section's title, or any title as large as the section's
   own. Sub-headings such as "CSR Committee" inside the governance report are smaller, so
   they don't end it.
4. The related-party note is searched only inside the standalone financial statements,
   and it ends at the next note with a higher number.

Page numbers are 1-based PDF page numbers (what a PDF viewer shows), not the printed numbers.
"""

from __future__ import annotations

import json
import logging
import os
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
import pymupdf

from src.ingest.companies import Company
from src.ingest.download import sha256_file

logger = logging.getLogger(__name__)

# Bump when detection rules change, so `sectionize` redoes companies processed by older rules.
DETECTOR_VERSION = 1

SECTION_TYPES = (
    "corporate_governance",
    "subsidiaries_aoc1",
    "auditor_report",
    "secretarial_audit",
    "related_party",
)

CIN_RE = re.compile(r"\b[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b")

_I = re.IGNORECASE
_APOS = r"[’'`]?"
CG_START = re.compile(r"report\s+on\s+corporate\s+governance|corporate\s+governance\s+report", _I)
AOC1_START = re.compile(
    r"form\s*(no\.?)?\s*aoc\s*[-–]?\s*1\b"
    r"|salient\s+features\s+of\s+(the\s+)?financial\s+statements?\s+of\s+(the\s+)?subsidiar",
    _I,
)
AUDIT_STANDALONE_START = re.compile(r"report\s+on\s+the\s+audit\s+of\s+the\s+standalone\s+financial\s+statements", _I)
AUDIT_CONSOLIDATED_START = re.compile(r"report\s+on\s+the\s+audit\s+of\s+the\s+consolidated\s+financial\s+statements", _I)
SECRETARIAL_START = re.compile(r"secretarial\s+audit\s+report|form\s*(no\.?)?\s*mr\s*[-–]?\s*3\b", _I)
# A numbered note heading: "20) Related party transactions", "2.24 Related party transactions",
# "42. Related-party transactions", "37. A) RELATED PARTY DISCLOSURE".
RPT_HEADING = re.compile(
    r"^\s*(?:note\s*)?(\d{1,2}(?:\.\d{1,2})?)\s*[.):]?\s*(?:\(?[a-z]\)\s*)?"
    r"related[-\s]+part(?:y|ies)\s*(?:transactions?|disclosures?)",
    _I,
)
# Any numbered note heading: "21) Dividends", "2.25 Corporate Social Responsibility", "38.A INTERESTS".
NOTE_HEADING = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2})?)\s*[.)]?\s*(?:\(?[A-Za-z]\)\s*)?[A-Z(]")
BALANCE_SHEET = re.compile(r"^\s*(standalone\s+)?balance\s+sheet\b", _I)

# Headings that start some other major part of an annual report.
_MAJOR = (
    r"management\s+discussion\s+(and|&)\s+analysis"
    r"|business\s+responsibility\s+(and|&)\s+sustainability"
    r"|corporate\s+social\s+responsibility|annual\s+report\s+on\s+csr"
    r"|report\s+on\s+the\s+audit\s+of\s+the"
    r"|^\s*independent\s+auditor" + _APOS + r"s?\s+report"
    r"|^\s*(standalone\s+|consolidated\s+)?balance\s+sheet\b"
    r"|^\s*notice\b|notice\s+of\s+(the\s+)?(annual\s+general\s+meeting|agm)"
    r"|^\s*(board|directors)" + _APOS + r"s?" + _APOS + r"\s+report\b"
    r"|^\s*glossary\b|^\s*corporate\s+information\b"
)
_ANNEXURE_NUMBERED = r"^\s*annexure\s*[-–:]?\s*(\d+|[ivx]+\b)"
CG_END = re.compile(_MAJOR + r"|" + _ANNEXURE_NUMBERED, _I | re.M)
SECRETARIAL_END = re.compile(
    _MAJOR + r"|" + _ANNEXURE_NUMBERED
    + r"|report\s+on\s+corporate\s+governance|corporate\s+governance\s+report"
    + r"|particulars\s+of\s+(contracts|employees)|conservation\s+of\s+energy|form\s*(no\.?)?\s*aoc",
    _I | re.M,
)
AOC1_END = re.compile(
    _MAJOR + r"|" + _ANNEXURE_NUMBERED
    + r"|report\s+on\s+corporate\s+governance|corporate\s+governance\s+report"
    + r"|form\s*(no\.?)?\s*aoc\s*[-–]?\s*2|particulars\s+of\s+contracts"
    + r"|secretarial\s+audit\s+report|corporate\s+information|financial\s+highlights",
    _I | re.M,
)


@dataclass(frozen=True)
class EndRule:
    """When a section ends: see `_find_end`."""

    pattern: re.Pattern
    continues: re.Pattern | None = None
    any_title: bool = True


END_RULES = {
    "corporate_governance": EndRule(CG_END, continues=CG_START),
    "subsidiaries_aoc1": EndRule(
        AOC1_END,
        continues=re.compile(AOC1_START.pattern + r"|part\s*[-–]?\s*['‘’\"]?\s*b\b|associate|joint\s+venture|section\s*129", _I),
    ),
    # The auditor's annexures (CARO, internal financial controls) have big titles of their
    # own but belong to the report, so only the balance sheet ends it.
    "auditor_report": EndRule(BALANCE_SHEET, any_title=False),
    # Secretarial reports have small titles and bold sub-headings of the same size
    # ("We further report that:"), so only named headings end them.
    "secretarial_audit": EndRule(
        SECRETARIAL_END,
        continues=re.compile(SECRETARIAL_START.pattern + r"|annexure\s*[-–]?\s*['‘’\"]?\s*a\b", _I),
        any_title=False,
    ),
}
PATTERN_SIZE_RATIO = 0.8
TITLE_SIZE_RATIO = 0.95
# A same-size heading only counts as a new title if it also stands out from the body text.
TITLE_BODY_RATIO = 1.3

MAX_PAGES = {
    "corporate_governance": 60,
    "subsidiaries_aoc1": 15,
    "auditor_report": 25,
    "secretarial_audit": 8,
    "related_party": 12,
}
# A page that matches the start pattern of this many different sections is a contents page.
TOC_MIN_SECTION_HITS = 3


# ---------------------------------------------------------------- reading pages


@dataclass
class Heading:
    text: str
    size: float


@dataclass
class Page:
    number: int
    text: str
    headings: list[Heading]
    body_size: float = 0.0
    rotated: bool = False
    is_toc: bool = False

    @property
    def heading_keys(self) -> set[str]:
        return {_norm(h.text) for h in self.headings}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def read_pages(pdf_path: Path) -> list[Page]:
    """Read text and heading lines of every page."""
    pages = []
    with pymupdf.open(pdf_path) as doc:
        for index, pdf_page in enumerate(doc):
            pages.append(_read_page(index + 1, pdf_page))
    for page in pages:
        page.is_toc = _looks_like_toc(page)
    return pages


def _read_page(number: int, pdf_page) -> Page:
    # Building the text layer is the slow part, so build it once for both reads.
    textpage = pdf_page.get_textpage()
    data = pdf_page.get_text("dict", textpage=textpage)
    lines: list[tuple[str, float, bool]] = []
    char_sizes: list[float] = []
    sideways = upright = 0
    for block in data["blocks"]:
        for line in block.get("lines", []):
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            text = " ".join("".join(s["text"] for s in line["spans"]).split())
            size = max(s["size"] for s in spans)
            bold = all((s["flags"] & 16) or "bold" in s["font"].lower() for s in spans)
            lines.append((text, size, bold))
            n_chars = sum(len(s["text"]) for s in spans)
            char_sizes.extend(s["size"] for s in spans for _ in s["text"])
            if abs(line["dir"][0]) < 0.5:
                sideways += n_chars
            else:
                upright += n_chars
    body = statistics.median(char_sizes) if char_sizes else 0.0
    headings = [Heading(t, s) for t, s, b in lines if b or s >= body * 1.15]
    return Page(
        number=number,
        text=pdf_page.get_text(textpage=textpage),
        headings=headings,
        body_size=body,
        rotated=sideways > upright,
    )


def _looks_like_toc(page: Page) -> bool:
    dotted = len(re.findall(r"\.{6,}", page.text))
    if dotted >= 3:
        return True
    starts = (CG_START, AOC1_START, AUDIT_STANDALONE_START, AUDIT_CONSOLIDATED_START, SECRETARIAL_START)
    hits = sum(1 for pattern in starts if _match_headings(page, pattern))
    return hits >= TOC_MIN_SECTION_HITS


def _match_headings(page: Page, pattern: re.Pattern, window: int = 3) -> Heading | None:
    """Best heading match on a page. Up to `window` consecutive heading lines are joined, so
    titles that wrap ("Corporate / Governance / Report") still match. The score is the
    smallest font size among the joined lines."""
    best: Heading | None = None
    heads = page.headings
    for i in range(len(heads)):
        for w in range(1, window + 1):
            part = heads[i : i + w]
            if len(part) < w:
                break
            text = " ".join(h.text for h in part)
            if pattern.search(text):
                size = min(h.size for h in part)
                if best is None or size > best.size:
                    best = Heading(text, size)
                break
    return best


# ---------------------------------------------------------------- CIN


@dataclass
class CinResult:
    cin: str | None
    count: int
    candidates: dict[str, int]


def find_cin(texts: list[str]) -> CinResult:
    """The most frequent CIN in the document. Cover letters and subsidiary lists also contain
    CINs, but the company's own one is printed far more often (notice, footers, forms)."""
    counts: Counter[str] = Counter()
    for text in texts:
        counts.update(CIN_RE.findall(text))
    if not counts:
        return CinResult(None, 0, {})
    cin, count = counts.most_common(1)[0]
    return CinResult(cin, count, dict(counts.most_common(5)))


# ---------------------------------------------------------------- detection


@dataclass
class Section:
    section_type: str
    page_start: int
    page_end: int
    start_heading: str
    end_reason: str


@dataclass
class Detection:
    sections: dict[str, Section] = field(default_factory=dict)
    missing: dict[str, str] = field(default_factory=dict)


def _candidates(pages: list[Page], pattern: re.Pattern, lo: int = 1, hi: int | None = None) -> list[tuple[Page, Heading]]:
    hi = hi or len(pages)
    found = []
    for page in pages[lo - 1 : hi]:
        if page.is_toc:
            continue
        match = _match_headings(page, pattern)
        if match:
            found.append((page, match))
    return found


def _best(cands: list[tuple[Page, Heading]]) -> tuple[Page, Heading] | None:
    """Largest-font match wins; earliest page breaks ties (within 0.5pt)."""
    if not cands:
        return None
    top = max(h.size for _, h in cands)
    return next(c for c in cands if c[1].size >= top - 0.5)


def _find_end(
    pages: list[Page],
    start: Page,
    title: Heading,
    rule: EndRule,
    max_pages: int,
) -> tuple[int, str]:
    """Last page of a section whose title `title` is on page `start`.

    A later page ends the section (the section stops on the page before it) when it has a
    new heading, i.e. one not seen on the previous two pages, that either
    - matches `rule.pattern` and is at least `PATTERN_SIZE_RATIO` of the title's font size, or
    - (if `rule.any_title`) is at least `TITLE_SIZE_RATIO` of the title's size: a new title
      at the same level as ours, whatever it says, as long as it is also clearly larger
      than the page's body text (`TITLE_BODY_RATIO`).
    Headings that match `rule.continues` (e.g. "Annexure 1 of Corporate Governance Report")
    never end the section.
    """
    limit = min(len(pages), start.number + max_pages - 1)
    for number in range(start.number + 1, limit + 1):
        page = pages[number - 1]
        recent = set().union(*(pages[n - 1].heading_keys for n in range(max(start.number, number - 2), number)))
        heads = page.headings
        for i in range(len(heads)):
            for w in (1, 2, 3):
                part = heads[i : i + w]
                if len(part) < w:
                    break
                text = " ".join(h.text for h in part)
                # Skip windows that include a running header, or the header joined with the
                # next line would look like a new "Board's Report ..." heading.
                if any(_norm(h.text) in recent for h in part):
                    continue
                if rule.continues and rule.continues.search(text):
                    continue
                size = min(h.size for h in part)
                by_pattern = rule.pattern.search(text) and size >= title.size * PATTERN_SIZE_RATIO
                by_title = (
                    rule.any_title
                    and w == 1
                    and size >= title.size * TITLE_SIZE_RATIO
                    and size >= page.body_size * TITLE_BODY_RATIO
                    and _is_wordy(text)
                )
                if by_pattern or by_title:
                    return number - 1, f"next heading on page {number}: {text[:80]!r}"
    if limit == len(pages):
        return limit, "end of document"
    return limit, f"reached the {max_pages}-page limit"


def _is_wordy(text: str) -> bool:
    """True for real titles, false for big numbers or single letters in infographics."""
    words = re.findall(r"[A-Za-z]{2,}", text)
    return len(words) >= 2 or (len(words) == 1 and len(words[0]) >= 6)


def detect_sections(pages: list[Page], company_name: str = "") -> Detection:
    """Locate each section type in a report's pages."""
    det = Detection()

    def add(kind: str, page: Page, heading: Heading, end: int, reason: str) -> None:
        det.sections[kind] = Section(kind, page.number, end, heading.text[:200], reason)

    def found(kind: str, best: tuple[Page, Heading]) -> None:
        end, reason = _find_end(pages, best[0], best[1], END_RULES[kind], MAX_PAGES[kind])
        add(kind, *best, end, reason)

    # Corporate governance report.
    best = _best(_candidates(pages, CG_START))
    if best:
        found("corporate_governance", best)
    else:
        det.missing["corporate_governance"] = "no 'Report on Corporate Governance' heading found"

    # Form AOC-1 (subsidiaries, associates, joint ventures). Prefer a page that has the
    # form's table, over a Board's report paragraph that only refers to the form.
    cands = _candidates(pages, AOC1_START)
    strong = [c for c in cands if _aoc1_table_words(c[0].text) >= 3]
    if strong or cands:
        found("subsidiaries_aoc1", (strong or cands)[0])
    else:
        det.missing["subsidiaries_aoc1"] = "no 'Form AOC-1' / 'salient features ... of subsidiaries' heading found"

    # Independent auditor's report on the standalone statements; it ends before the balance sheet.
    standalone = _best(_candidates(pages, AUDIT_STANDALONE_START))
    if standalone:
        found("auditor_report", standalone)
    else:
        det.missing["auditor_report"] = "no 'Report on the Audit of the Standalone Financial Statements' heading found"

    # Secretarial audit report (Form MR-3) of the company itself. Reports of material
    # subsidiaries often follow it; the company's own is the first one that names the company.
    cands = [c for c in _candidates(pages, SECRETARIAL_START) if _is_mr3_page(c[0].text)]
    own = [c for c in cands if company_name and _norm(company_name) in _norm(c[0].text)]
    if own or cands:
        found("secretarial_audit", (own or cands)[0])
    else:
        det.missing["secretarial_audit"] = "no 'Secretarial Audit Report' / 'Form MR-3' page found"

    # Related-party note, searched only within the standalone financial statements: from the
    # standalone auditor's report to the next consolidated auditor's report or AOC-1.
    if standalone:
        lo = standalone[0].number
        later_starts = [p.number for p, _ in _candidates(pages, AUDIT_CONSOLIDATED_START, lo + 1)]
        aoc1 = det.sections.get("subsidiaries_aoc1")
        if aoc1 and aoc1.page_start > lo:
            later_starts.append(aoc1.page_start)
        hi = min(later_starts) - 1 if later_starts else len(pages)
        rpt = _find_rpt(pages, lo, hi)
        if rpt:
            det.sections["related_party"] = rpt
        else:
            det.missing["related_party"] = f"no numbered 'Related party transactions/disclosures' note on pages {lo}-{hi}"
    else:
        det.missing["related_party"] = "standalone financial statements not found, so the note can't be located"

    return det


def _aoc1_table_words(text: str) -> int:
    words = ("reporting currency", "share capital", "reserves", "total assets", "turnover",
             "profit before tax", "shareholding", "proposed dividend", "total liabilities")
    lowered = " ".join(text.lower().split())
    return sum(1 for w in words if w in lowered)


def _is_mr3_page(text: str) -> bool:
    lowered = " ".join(text.lower().split())
    return bool(re.search(r"mr\s*[-–]?\s*3|section\s*204\s*\(1\)|secretarial\s+audit\s+report\s+for\s+the\s+financial\s+year", lowered))


def _note_key(number: str) -> tuple[int, ...]:
    return tuple(int(part) for part in number.split("."))


def _find_rpt(pages: list[Page], lo: int, hi: int) -> Section | None:
    for page in pages[lo - 1 : hi]:
        if page.is_toc:
            continue
        for heading in page.headings:
            match = RPT_HEADING.match(heading.text)
            if not match:
                continue
            note = _note_key(match.group(1))
            end, reason = _rpt_end(pages, page.number, note, hi)
            return Section("related_party", page.number, end, heading.text[:200], reason)
    return None


def _is_next_note(key: tuple[int, ...], note: tuple[int, ...]) -> bool:
    """`key` is one of the next few notes after `note`, at the same depth ("21" after "20",
    "2.25" after "2.24"). The small gap limit stops bold amounts like "45 Crore" counting."""
    if len(key) != len(note) or key <= note:
        return False
    if len(key) == 1:
        return key[0] - note[0] <= 2
    return key[:-1] == note[:-1] and key[-1] - note[-1] <= 2


def _rpt_end(pages: list[Page], start: int, note: tuple[int, ...], hi: int) -> tuple[int, str]:
    """The note runs until the page where the next note's heading appears. That page is kept,
    because the related-party text usually continues at its top."""
    limit = min(hi, start + MAX_PAGES["related_party"] - 1)
    for number in range(start + 1, limit + 1):
        for heading in pages[number - 1].headings:
            match = NOTE_HEADING.match(heading.text)
            if match and _is_next_note(_note_key(match.group(1)), note):
                return number, f"next note {heading.text[:60]!r} on page {number}"
    if limit == hi:
        return limit, f"end of the standalone financial statements (page {hi})"
    return limit, "reached the page limit for this note"


# ---------------------------------------------------------------- tables and output


def extract_tables(pdf_path: Path, page_numbers: list[int], rotated: set[int]) -> dict[int, list[list[list[str]]]]:
    """Tables pdfplumber finds on the given pages (rows of cell strings). Pages with sideways
    text are skipped because pdfplumber returns their text reversed. Empty tables are dropped."""
    tables: dict[int, list[list[list[str]]]] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for number in page_numbers:
            if number in rotated:
                continue
            found = []
            for table in pdf.pages[number - 1].extract_tables():
                rows = [[" ".join((cell or "").split()) for cell in row] for row in table]
                rows = [r for r in rows if any(r)]
                if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
                    found.append(rows)
            if found:
                tables[number] = found
    return tables


@dataclass
class SectionizeResult:
    company: Company
    skipped: bool
    page_count: int
    cin: CinResult
    detection: Detection


def sectionize_company(company: Company, pdf_path: Path, out_dir: Path, force: bool = False) -> SectionizeResult:
    """Detect sections in one report and write one JSON per section plus summary.json.

    Skips the work when summary.json was produced from the same PDF (sha256) by the same
    detector version, unless `force` is set."""
    company_dir = out_dir / company.nse_symbol
    summary_path = company_dir / "summary.json"
    digest = sha256_file(pdf_path)

    if summary_path.exists() and not force:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("pdf_sha256") == digest and summary.get("detector_version") == DETECTOR_VERSION:
            return _result_from_summary(company, summary)

    pages = read_pages(pdf_path)
    cin = find_cin([p.text for p in pages])
    detection = detect_sections(pages, company.name)
    numbers = sorted({n for s in detection.sections.values() for n in range(s.page_start, s.page_end + 1)})
    tables = extract_tables(pdf_path, numbers, {p.number for p in pages if p.rotated})

    company_dir.mkdir(parents=True, exist_ok=True)
    for old in company_dir.glob("*.json"):
        old.unlink()
    for kind, section in detection.sections.items():
        payload = {
            "company": company.name,
            "nse_symbol": company.nse_symbol,
            "cin": company.cin,
            "section_type": kind,
            "source_pdf": pdf_path.name,
            "pdf_sha256": digest,
            "page_start": section.page_start,
            "page_end": section.page_end,
            "detection": {"start_heading": section.start_heading, "end_reason": section.end_reason},
            "pages": [
                {
                    "page": n,
                    "text": pages[n - 1].text,
                    "tables": tables.get(n, []),
                    "rotated": pages[n - 1].rotated,
                }
                for n in range(section.page_start, section.page_end + 1)
            ],
        }
        _write_json(company_dir / f"{kind}.json", payload)

    summary = {
        "company": company.name,
        "nse_symbol": company.nse_symbol,
        "source_pdf": pdf_path.name,
        "pdf_sha256": digest,
        "detector_version": DETECTOR_VERSION,
        "page_count": len(pages),
        "cin_csv": company.cin,
        "cin_found": cin.cin,
        "cin_count": cin.count,
        "cin_candidates": cin.candidates,
        "sections": {
            kind: (
                {"found": True, "page_start": s.page_start, "page_end": s.page_end,
                 "start_heading": s.start_heading, "end_reason": s.end_reason}
                if (s := detection.sections.get(kind))
                else {"found": False, "reason": detection.missing.get(kind, "")}
            )
            for kind in SECTION_TYPES
        },
    }
    _write_json(summary_path, summary)
    logger.info("%s: %d/%d sections found", company.nse_symbol, len(detection.sections), len(SECTION_TYPES))
    return SectionizeResult(company, False, len(pages), cin, detection)


def _result_from_summary(company: Company, summary: dict) -> SectionizeResult:
    det = Detection()
    for kind, info in summary["sections"].items():
        if info["found"]:
            det.sections[kind] = Section(kind, info["page_start"], info["page_end"], info["start_heading"], info["end_reason"])
        else:
            det.missing[kind] = info.get("reason", "")
    cin = CinResult(summary.get("cin_found"), summary.get("cin_count", 0), summary.get("cin_candidates", {}))
    return SectionizeResult(company, True, summary["page_count"], cin, det)


def _write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
