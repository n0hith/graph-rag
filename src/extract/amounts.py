"""Check related-party amounts against the PDF page itself, without calling the LLM.

A related-party fact's evidence quote is usually just the party's name, so nothing ties its
amount to the report. This check reads the cited page's words with their positions and, for
each fact, finds the row the amount should sit on and the FY2024 column:

- list tables (Infosys, Tata Motors, Tata Consumer, TCS p.302): the party is the row label
  and each year has its own column, headed "2024" / "Year ended March 31, 2024" etc.;
- matrix tables (TCS p.299, Tata Steel): the nature is the row label and the party heads a
  column; the year comes from the table's title ("Year ended March 31, 2024"), or, where the
  title gives both years (Tata Steel), from the row's first line (the current year is printed
  first, the previous year on the line below).

A fact passes when its `amount_inr_crore` equals the FY2024 cell of such a row (the tables
are all in crore); `amount_as_printed` then records that cell as printed. In a list table
the row must also sit under the fact's nature heading, which can carry over from the previous
column or page; otherwise a party with rows in several tables could match the wrong one. If
the cited page has no matching row, the section's other pages are tried, since the page a
fact cites is the first page of its group containing the (often short) quote.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.extract.extractor import Fact

NUMBER_RE = re.compile(r"^\(?-?(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?\)?$")
DASHES = {"-", "–", "—"}
MARKERS = "#*^@$"
# "2024", "2023-24", "FY2024": the year a column or title refers to (FY ending that year).
YEAR_RE = re.compile(r"^\(?(?:FY)?(20\d\d)(?:[-–/](\d\d|20\d\d))?[,:.;)]*$")
CURRENT_FY_END = 2024
# A column's year heading sits on a short line ("2024", "March 31, 2024"); a long line with
# years in it is a title or sentence.
MAX_HEADER_LINE_WORDS = 4
COLUMN_TOLERANCE = 30.0


@dataclass(frozen=True)
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    line: tuple[int, int]  # (block, line) as PyMuPDF numbers them

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass(frozen=True)
class Cell:
    word: Word
    value: float | None  # None for a dash (nil)

    @property
    def printed(self) -> str:
        return self.word.text


@dataclass
class AmountCheck:
    symbol: str
    index: int  # position in the company's facts file
    party_name: str
    nature: str
    amount: float | None
    cited_page: int | None
    status: str  # "pass" | "fail" | "no_amount"
    page: int | None = None
    amount_as_printed: str | None = None
    basis: str = ""
    detail: str = ""


def page_words(pdf_page) -> list[Word]:
    return [Word(x0, y0, x1, y1, text, (block, line))
            for x0, y0, x1, y1, text, block, line, _ in pdf_page.get_text("words")]


def _key(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", text.lower())


def _cell(word: Word) -> Cell | None:
    text = word.text.rstrip(MARKERS)
    if text in DASHES:
        return Cell(word, None)
    if not NUMBER_RE.match(text):
        return None
    value = float(text.strip("()").replace(",", ""))
    return Cell(word, -value if text.startswith("(") or text.startswith("-") else value)


def find_label(words: list[Word], label: str) -> list[list[Word]]:
    """Every run of consecutive words (in PyMuPDF's reading order) spelling `label`,
    ignoring case, spacing and punctuation, and footnote numbers glued to its last word
    ("officers(1)(2)")."""
    target = _key(label)
    if not target:
        return []
    keys = [_key(w.text) for w in words]
    found = []
    for i, k in enumerate(keys):
        if not k or not target.startswith(k):
            continue
        acc, j = "", i
        while j < len(words) and len(acc) < len(target):
            acc += keys[j]
            j += 1
        if acc == target or (acc.startswith(target) and acc[len(target):].isdigit()
                              and len(acc) - len(target) < len(keys[j - 1])):
            found.append(words[i:j])
    return found


def _bbox(ws: list[Word]) -> tuple[float, float, float, float]:
    return min(w.x0 for w in ws), min(w.y0 for w in ws), max(w.x1 for w in ws), max(w.y1 for w in ws)


MAX_WRAPPED_LINES = 3


def row_cells(words: list[Word], label: list[Word]) -> list[Cell]:
    """The numeric cells on `label`'s row: words to its right whose middle lies within the
    label's height, taken from the first such line that has a number (a two-line label in
    Tata Steel's table has the previous year's figures on its second line), from the first
    number up to the next non-numeric word (Infosys prints two tables side by side).

    Where the label's line has no figures, two kinds of wrapping are followed: the label's
    own cell running on ("Infosys (Malaysia) SDN. BHD. (formerly / Global ... / Sdn.
    Bhd.)", figures on its last line), and a wrapped cell beside it pushing the figures
    below the label (Tata Motors' relationship column)."""
    x0, y0, x1, y1 = _bbox(label)
    cells = _row_cells(words, label, y0 - 1, y1 + 1)
    if cells:
        return cells
    line = [w for w in words if abs(w.yc - label[-1].yc) <= 3 and w.x0 >= label[-1].x1]
    if line and min(line, key=lambda w: w.x0).x0 - label[-1].x1 < 10 and _cell(min(line, key=lambda w: w.x0)) is None:
        cell = list(label)
        height = y1 - y0
        for _ in range(MAX_WRAPPED_LINES):
            last = max(w.yc for w in cell)
            nxt = sorted((w for w in words if abs(w.x0 - x0) <= 3 and last + 3 < w.yc <= last + 1.5 * height),
                         key=lambda w: w.yc)
            if not nxt:
                break
            cell += [w for w in words if abs(w.yc - nxt[0].yc) <= 3 and x0 - 3 <= w.x0 and _cell(w) is None
                     and w.x0 < x1 + 60]
            cells = _row_cells(words, cell, nxt[0].yc - 2, nxt[0].yc + 2)
            if cells:
                return cells
        return []
    below = min((w.y0 for w in words if abs(w.x0 - x0) <= 3 and w.y0 > y1), default=y1 + 1) - 1
    wrapped = [w for w in words if w.x0 >= x1 - 1 and y1 + 1 < w.yc <= below and _cell(w) is None]
    if wrapped:
        cells = _row_cells(words, label, y0 - 1, below)
    return cells


# Running headers/footers name the report's year ("Integrated Report & Annual Accounts
# 2023-24", "Standalone Financial Statements 2023-24"), not a table's columns.
RUNNING_HEAD_RE = re.compile(r"^(?:report|annual|accounts|statements|integrated)$", re.I)


def _without_running_heads(words: list[Word]) -> list[Word]:
    heads = {w.line for w in words if RUNNING_HEAD_RE.match(w.text)}
    return [w for w in words if w.line not in heads]


def _first_column_edge(words: list[Word], label: list[Word]) -> float:
    """How far right this row's figures may start: the right edge of the first year column
    heading to the right of the label (Infosys prints a second table, with its own year
    columns, beside the first). No limit where columns aren't headed by years."""
    _, y0, x1, _ = _bbox(label)
    sizes: dict = {}
    for w in words:
        sizes[w.line] = sizes.get(w.line, 0) + 1
    headers = [w for w in _without_running_heads(words) if w.y1 <= y0 and w.x0 > x1 and _year(w.text)
               and sizes[w.line] <= MAX_HEADER_LINE_WORDS]
    if not headers:
        return float("inf")
    nearest = max(w.y1 for w in headers)  # the table's own header row, not a date further up
    return min(w.x1 for w in headers if w.y1 >= nearest - 3) + COLUMN_TOLERANCE


def _row_cells(words: list[Word], label: list[Word], top: float, bottom: float) -> list[Cell]:
    x1 = _bbox(label)[2]
    limit = _first_column_edge(words, label)
    ids = {id(w) for w in label}
    band = [w for w in words if id(w) not in ids and w.x0 >= x1 - 1 and top <= w.yc <= bottom]
    lines: list[list[Word]] = []
    for w in sorted(band, key=lambda w: w.yc):
        if lines and abs(lines[-1][0].yc - w.yc) <= 3:
            lines[-1].append(w)
        else:
            lines.append([w])
    runs = []
    for line in lines:
        cells: list[Cell] = []
        for w in sorted(line, key=lambda w: w.x0):
            c = _cell(w)
            if c is None and cells:
                break
            if c is not None:
                cells.append(c)
        if cells and cells[0].word.x0 <= limit:
            runs.append(cells)
    # The run starting nearest the label is this table's (a band can also catch the
    # neighbouring table's line); on a tie, the top line (the current year in Tata Steel's).
    return min(runs, key=lambda r: round(r[0].word.x0 / 5)) if runs else []


def _year(text: str) -> int | None:
    m = YEAR_RE.match(text)
    if not m:
        return None
    start, end = int(m.group(1)), m.group(2)
    if end is None:
        return start
    return int(end) if len(end) == 4 else start // 100 * 100 + int(end)


def column_year(words: list[Word], cell: Cell, line_sizes: dict) -> int | None:
    """The year heading the column `cell` is in: the nearest year word above it, on a
    short line, horizontally within COLUMN_TOLERANCE of the cell."""
    best = None
    for w in words:
        if w.y1 > cell.word.y0 or abs(w.xc - cell.word.xc) > COLUMN_TOLERANCE:
            continue
        year = _year(w.text)
        if year is None or line_sizes[w.line] > MAX_HEADER_LINE_WORDS:
            continue
        if best is None or w.y1 > best[0]:
            best = (w.y1, year)
    return best[1] if best else None


def table_years(words: list[Word], row_top: float, previous_page: list[Word] = ()) -> set[int]:
    """Years named on the nearest line above the row that names any (a table title such as
    TCS's "Year ended March 31, 2024"); for a table continued from the previous page with
    no year above it (Tata Steel p.409), the last such line on that page."""
    lines: dict[tuple, list[Word]] = {}
    for w in words:
        if w.y1 <= row_top:
            lines.setdefault(w.line, []).append(w)
    for ws in sorted(lines.values(), key=lambda ws: -max(w.y1 for w in ws)):
        years = {y for w in ws if (y := _year(w.text))}
        if years:
            return years
    return table_years(previous_page, float("inf")) if previous_page else set()


def _matches(amount: float, value: float | None) -> bool:
    """`amount` (crore) is the printed `value`. Every pilot report's related-party tables are
    in crore, so no unit conversion: converting from lakh or rupees let unrelated figures
    match (5,593.94 rupees "is" 0.0 crore). A dash (`value` None) means nil and matches 0."""
    if value is None:
        return amount == 0
    return abs(abs(value) - abs(amount)) <= 0.005


def fy2024_cells(words: list[Word], label: list[Word], column_header: list[Word] | None = None,
                 previous_page: list[Word] = ()) -> tuple[list[Cell], str]:
    """The cells of `label`'s row that are in the FY2024 column, and how that was decided.
    With `column_header` (a matrix table), only the cell under that header counts."""
    cells = row_cells(words, label)
    if not cells:
        return [], "no figures on the row"
    if column_header:
        hx0, _, hx1, _ = _bbox(column_header)
        cells = [c for c in cells if hx0 - 10 <= c.word.xc <= hx1 + 10]
        if not cells:
            return [], "no figure under the party's column"
    line_sizes: dict = {}
    for w in words:
        line_sizes[w.line] = line_sizes.get(w.line, 0) + 1
    body = _without_running_heads(words)
    years = [column_year(body, c, line_sizes) for c in cells]
    if any(y is not None for y in years):
        return [c for c, y in zip(cells, years) if y == CURRENT_FY_END], "column headed FY2024"
    title = table_years(body, _bbox(label)[1], _without_running_heads(previous_page))
    if title == {CURRENT_FY_END}:
        return cells, "table titled FY2024"
    if CURRENT_FY_END in title and len(title) > 1:
        return cells, "row's first line (title gives both years, current year first)"
    return [], f"table year {sorted(title) or 'unknown'}"


def _labels(fact: Fact, key: str) -> list[str]:
    out = [fact.data.get(key) or ""]
    if key == "party_name":
        # The quote, without any figures in it, when it is (part of) the party's name as
        # printed; Tata Steel's quotes are the nature (row label) instead.
        quote = " ".join(l for l in fact.evidence.splitlines() if l.strip() and not _cell(Word(0, 0, 0, 0, l.strip(), (0, 0))))
        if _key(quote) and _key(quote) in _key(out[0]):
            out.append(quote)
    return [l for l in out if l.strip()]


@dataclass(frozen=True)
class Heading:
    page: int
    column: int  # 0 = left half of the page, 1 = right (Infosys prints two tables side by side)
    y: float
    nature: str  # _key() of the heading text


def _column(words: list[Word], w: Word) -> int:
    mid = (min(v.x0 for v in words) + max(v.x1 for v in words)) / 2
    return 0 if w.x0 < mid else 1


def _has_own_figures(words: list[Word], label: list[Word]) -> bool:
    """Whether a figure follows `label` on its line with no other text in between (the
    same line can carry the neighbouring table's row, which has its own label first)."""
    _, y0, x1, y1 = _bbox(label)
    ids = {id(w) for w in label}
    right = sorted((w for w in words if id(w) not in ids and w.x0 >= x1 - 1 and y0 - 1 <= w.yc <= y1 + 1),
                   key=lambda w: w.x0)
    return bool(right) and _cell(right[0]) is not None


def find_headings(words_by_page: dict[int, list[Word]], natures: set[str]) -> list[Heading]:
    """Where each nature the facts name is printed as a heading (a line with no figures),
    in reading order: page, then column, then top to bottom."""
    out = set()
    for page, words in words_by_page.items():
        for nature in natures:
            for label in find_label(words, nature):
                if not _has_own_figures(words, label):
                    out.add(Heading(page, _column(words, label[0]), _bbox(label)[1], _key(nature)))
    # One heading can contain another nature's text ("Purchases of goods and services
    # (including reimbursements) and net of cost recovery"); the longest reading wins.
    longest: dict[tuple, Heading] = {}
    for h in out:
        at = (h.page, h.column, round(h.y))
        if at not in longest or len(h.nature) > len(longest[at].nature):
            longest[at] = h
    return sorted(longest.values(), key=lambda h: (h.page, h.column, h.y))


def heading_above(headings: list[Heading], page: int, column: int, y: float) -> str | None:
    """The nearest heading before a row in reading order. A table can carry on into the
    next column or page under the same heading (Infosys p.254 continues p.253's 'Unbilled
    revenues')."""
    before = [h for h in headings if (h.page, h.column, h.y) < (page, column, y)]
    return before[-1].nature if before else None


def _nature_on_row(words: list[Word], label: list[Word], nature: str) -> bool:
    """Whether `nature` is printed on the party's own line (Tata Motors' struck-off
    companies table has a 'Nature of transactions' column instead of headings)."""
    _, y0, _, y1 = _bbox(label)
    line = [w for w in words if y0 - 1 <= w.yc <= y1 + 1]
    return bool(find_label(line, nature))


@dataclass(frozen=True)
class RowMatch:
    page: int
    cell: Cell
    basis: str
    heading: str | None


def _party_rows(fact: Fact, words_by_page: dict[int, list[Word]], headings: list[Heading]):
    """Every row labelled with the fact's party in the section: (page, FY2024 cells, basis,
    heading above it)."""
    for page, words in words_by_page.items():
        seen = set()
        for text in _labels(fact, "party_name"):
            for label in find_label(words, text):
                if id(label[0]) in seen:
                    continue
                seen.add(id(label[0]))
                cells, basis = fy2024_cells(words, label, previous_page=words_by_page.get(page - 1, ()))
                if cells or basis != "no figures on the row":
                    y = _bbox(label)[1]
                    heading = heading_above(headings, page, _column(words, label[0]), y)
                    on_row = _nature_on_row(words, label, fact.data.get("nature") or "")
                    yield page, cells, basis, _key(fact.data.get("nature") or "") if on_row else heading


def _matrix_match(fact: Fact, words: list[Word], previous_page: list[Word]) -> tuple[Cell | None, str, list[str]]:
    """Matrix table: the nature is the row label, the party heads a column above it."""
    amount = fact.data["amount_inr_crore"]
    seen: list[str] = []
    for nature in find_label(words, fact.data.get("nature") or ""):
        top = _bbox(nature)[1]
        for text in _labels(fact, "party_name"):
            for header in find_label(words, text):
                if _bbox(header)[3] > top or _bbox(header)[0] < _bbox(nature)[2]:
                    continue
                cells, basis = fy2024_cells(words, nature, header, previous_page)
                seen += [c.printed for c in cells]
                for c in cells:
                    if _matches(amount, c.value):
                        return c, f"nature row x party column, {basis}", seen
    return None, "", seen


def check_fact(fact: Fact, words_by_page: dict[int, list[Word]], headings: list[Heading] = ()
               ) -> tuple[str, int | None, Cell | None, str, str]:
    """(status, page, cell, basis, detail) for one related-party fact.

    List tables: the amount must be the FY2024 figure on a row labelled with the party. A
    party often has rows in several tables (receivables, other financial assets, sale of
    services, ...), so where its nature is printed as a heading, the row must sit under that
    heading; otherwise only a party with a single row in the section can pass."""
    amount = fact.data.get("amount_inr_crore")
    if amount is None:
        return "no_amount", None, None, "", ""
    nature = _key(fact.data.get("nature") or "")
    rows = list(_party_rows(fact, words_by_page, headings))
    matches = [RowMatch(page, c, f"party row, {basis}", heading) for page, cells, basis, heading in rows
               for c in cells if _matches(amount, c.value)]
    printed_as_heading = any(h.nature == nature for h in headings)
    under = [m for m in matches if m.heading == nature]
    if under:
        m = min(under, key=lambda m: (m.page != fact.page, abs(m.page - (fact.page or m.page))))
        return "pass", m.page, m.cell, m.basis + ", under its nature heading" + _moved(m.page, fact), ""
    if matches and not printed_as_heading and len(rows) == 1:
        m = matches[0]
        return "pass", m.page, m.cell, m.basis + ", party's only row (nature not printed as a heading)" + _moved(m.page, fact), ""

    order = sorted(words_by_page, key=lambda p: (p != fact.page, abs(p - (fact.page or p))))
    seen_by_page = {}
    for page in order:
        cell, basis, seen = _matrix_match(fact, words_by_page[page], words_by_page.get(page - 1, ()))
        if cell:
            return "pass", page, cell, basis + _moved(page, fact), ""
        if seen:
            seen_by_page[page] = seen

    if matches:
        names = sorted({m.heading or "no heading" for m in matches})
        return "fail", None, None, "", (f"amount is on the party's row only under other heading(s): {', '.join(names)}"
                                        if printed_as_heading else
                                        f"amount is on one of the party's {len(rows)} rows, nature not printed as a heading")
    figures = [f"p.{page} [{heading or '-'}]: {', '.join(c.printed for c in cells) or basis}"
               for page, cells, basis, heading in rows] + [f"p.{p}: {', '.join(s)}" for p, s in seen_by_page.items()]
    if figures:
        return "fail", None, None, "", "FY2024 figures on the fact's rows: " + "; ".join(figures[:6])
    return "fail", None, None, "", "no row found for this party/nature in the section"


def _moved(page: int, fact: Fact) -> str:
    return f"; found on p.{page}, not the cited p.{fact.page}" if page != fact.page else ""


def check_amounts(facts: list[Fact], pdf_path: Path, pages: list[int]
                  ) -> list[tuple[int, str, int | None, Cell | None, str, str]]:
    """`check_fact` for every related-party fact in `facts`, over the section's `pages` of
    `pdf_path`: (index in `facts`, status, page, cell, basis, detail)."""
    import pymupdf

    with pymupdf.open(pdf_path) as doc:
        words_by_page = {p: page_words(doc[p - 1]) for p in pages}
    rpt = [(i, f) for i, f in enumerate(facts) if f.fact_type == "related_party"]
    headings = find_headings(words_by_page, {f.data.get("nature") or "" for _, f in rpt} - {""})
    return [(i, *check_fact(f, words_by_page, headings)) for i, f in rpt]


def with_checked_amount(f: Fact, page: int | None, cell: Cell | None) -> Fact:
    """`f` with `amount_as_printed` set from a passing check (and moved to the page its row
    is on), or cleared."""
    from src.extract.extractor import Fact

    data = {k: v for k, v in f.data.items() if k != "amount_as_printed"}
    if cell:
        data["amount_as_printed"] = cell.printed
    return Fact(**{**f.__dict__, "data": data, "page": page if cell else f.page})
