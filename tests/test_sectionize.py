"""Section detection on a small synthetic annual report built with PyMuPDF."""

import json

import pymupdf
import pytest

from src.ingest.companies import Company
from src.ingest.sectionize import (
    SECTION_TYPES,
    _is_next_note,
    detect_sections,
    extract_tables,
    find_cin,
    read_pages,
    sectionize_company,
)

OWN_CIN = "L22210MH1995PLC084781"
SUB_CIN = "U72900MH2000PLC123456"
BODY = "This paragraph is ordinary body text of the annual report and it is set in the body size."

# Each page: list of (text, font size, bold). Body lines are added to every page so the
# median font size is the body size (9pt), as in a real report.
PAGES = [
    # 1: contents page that names several sections; must be ignored.
    [("Contents", 24, True), ("Report on Corporate Governance 6", 12, True),
     ("Secretarial Audit Report 3", 12, True), ("Form AOC-1 15", 12, True)],
    # 2: Board's report that only mentions the governance report in a small sub-heading.
    [("Board's Report", 24, True), ("Corporate Governance Report", 11, True),
     (f"CIN: {OWN_CIN}", 9, False)],
    # 3-4: secretarial audit report of the company, with a bold sub-heading on page 4.
    [("Board's Report", 24, True), ("Annexure 2", 16, True), ("Secretarial Audit Report", 16, True),
     ("Form No. MR-3", 9, False), ("To, The Members, Test Company Limited", 9, False)],
    [("Board's Report", 24, True), ("We further report that:", 16, True), ("Annexure A", 11, True)],
    # 5: next annexure ends the secretarial report.
    [("Board's Report", 24, True), ("Annexure 3", 16, True), ("Particulars of employees", 12, True)],
    # 6-7: governance report; page 7 repeats the running header and has a committee heading.
    [("Corporate Governance Report", 24, True), ("Board of Directors", 12, True),
     ("N Chandrasekaran DIN 00121863", 9, False), (f"CIN: {OWN_CIN}", 9, False)],
    [("Corporate Governance Report", 24, True), ("Corporate Social Responsibility Committee", 14, True),
     ("Certificate of non-disqualification of directors", 12, True)],
    # 8: next major section.
    [("Management Discussion and Analysis", 24, True)],
    # 9-10: standalone auditor's report and its annexure (big title, still part of the report).
    [("Independent Auditor's Report", 24, True), ("Report on the Audit of the Standalone", 14, True),
     ("Financial Statements", 14, True)],
    [("Annexure A to the Independent Auditor's Report", 24, True)],
    # 11: balance sheet ends the auditor's report.
    [("Balance Sheet", 24, True)],
    # 12-14: related-party note; a bold amount on page 13 must not end it; note 21 on page 14 does.
    [("Notes forming part of the Standalone Financial Statements", 14, True),
     ("20) Related party transactions", 11, True), ("Key Management Personnel", 9, False)],
    [("45 Crore", 11, True), ("Balances with related parties", 9, False)],
    [("21) Dividends", 11, True)],
    # 15-16: Form AOC-1 with its Part B.
    [("Form AOC-1", 20, True),
     ("Reporting currency Share capital Reserves Total assets Turnover", 9, False),
     (f"Subsidiary CIN {SUB_CIN}", 9, False), (f"CIN: {OWN_CIN}", 9, False)],
    [("Part B Associates and Joint Ventures", 20, True)],
    # 17: notice ends AOC-1.
    [("Notice", 24, True)],
    # 18-19: consolidated statements with their own related-party note (must not be picked).
    [("Independent Auditor's Report", 24, True), ("Report on the Audit of the Consolidated Financial Statements", 14, True)],
    [("30) Related party transactions", 11, True)],
    # 20-21: a material subsidiary's own secretarial audit report, kept separately and tagged
    # with the subsidiary's name; "Annexure 3A" ends it.
    [("Board's Report", 24, True), ("Annexure 2A", 16, True), ("Secretarial Audit Report", 16, True),
     ("Form No. MR-3", 9, False), ("To, The Members, ABC Subsidiary Private Limited", 9, False)],
    [("Annexure 3A", 16, True)],
]

EXPECTED = {
    "secretarial_audit": (3, 4),
    "corporate_governance": (6, 7),
    "auditor_report": (9, 10),
    "related_party": (12, 14),
    "subsidiaries_aoc1": (15, 16),
}


def _make_pdf(path, pages):
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page()
        y = 60
        for text, size, bold in lines:
            page.insert_text((50, y), text, fontsize=size, fontname="hebo" if bold else "helv")
            y += size + 10
        for _ in range(12):
            page.insert_text((50, y), BODY, fontsize=9, fontname="helv")
            y += 14
    doc.save(path)
    doc.close()


@pytest.fixture
def report(tmp_path):
    path = tmp_path / "TEST.pdf"
    _make_pdf(path, PAGES)
    return path


@pytest.fixture
def company():
    return Company("Test Company Limited", "TEST", OWN_CIN, "https://example.invalid/test.pdf")


def test_detects_every_section_with_its_page_range(report, company):
    detection = detect_sections(read_pages(report), company.name)
    assert detection.missing == {}
    found = {k: (s.page_start, s.page_end) for k, s in detection.sections.items()}
    assert found == EXPECTED


def test_contents_page_is_not_a_section_start(report):
    pages = read_pages(report)
    assert pages[0].is_toc
    assert not any(p.is_toc for p in pages[1:])


def test_subsidiary_secretarial_report_is_tagged_and_kept_separate(report, company):
    detection = detect_sections(read_pages(report), company.name)
    # The company's own report is still the one picked as "secretarial_audit".
    own = detection.sections["secretarial_audit"]
    assert (own.page_start, own.page_end) == EXPECTED["secretarial_audit"]
    # The subsidiary's report is kept, but separately, tagged with its own name.
    assert len(detection.subsidiary_secretarial) == 1
    sub = detection.subsidiary_secretarial[0]
    assert sub.subsidiary_name == "ABC Subsidiary Private Limited"
    assert (sub.page_start, sub.page_end) == (20, 20)


def test_most_frequent_cin_wins():
    texts = [f"CIN {OWN_CIN}", f"subsidiary {SUB_CIN}", f"footer {OWN_CIN}", "no cin here"]
    result = find_cin(texts)
    assert result.cin == OWN_CIN
    assert result.count == 2
    assert result.candidates == {OWN_CIN: 2, SUB_CIN: 1}


def test_cin_absent():
    assert find_cin(["nothing", ""]).cin is None


def test_missing_sections_are_reported_with_a_reason(tmp_path):
    path = tmp_path / "empty.pdf"
    _make_pdf(path, [[("Chairman's Message", 24, True)]])
    detection = detect_sections(read_pages(path))
    assert detection.sections == {}
    assert set(detection.missing) == set(SECTION_TYPES)
    assert all(detection.missing.values())


def _draw_ruled_table(page, rows, x0=50, y0=50, cw=80, rh=20):
    n_rows, n_cols = len(rows), len(rows[0])
    for r in range(n_rows + 1):
        page.draw_line((x0, y0 + r * rh), (x0 + n_cols * cw, y0 + r * rh))
    for c in range(n_cols + 1):
        page.draw_line((x0 + c * cw, y0), (x0 + c * cw, y0 + n_rows * rh))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            page.insert_text((x0 + c * cw + 10, y0 + r * rh + 15), value, fontsize=10)


def test_extract_tables_reads_a_rotated_page_instead_of_skipping_it(tmp_path):
    path = tmp_path / "rotated.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    _draw_ruled_table(page, [["Alpha", "Beta"], ["One", "Two"]])
    page.set_rotation(90)  # most AOC-1 tables are printed sideways like this
    doc.save(path)
    doc.close()

    tables = extract_tables(path, [1], rotated={1})

    # PyMuPDF reads the rotated page's text in the right order (unlike pdfplumber, which
    # would return it reversed), so the four cell values all come through correctly; the
    # exact row/column arrangement follows the page's rotated reading direction.
    assert 1 in tables and tables[1], "a rotated page should no longer be skipped entirely"
    cells = {cell for table in tables[1] for row in table for cell in row}
    assert cells == {"Alpha", "Beta", "One", "Two"}


def test_extract_tables_reads_a_ruled_table_on_an_upright_page(tmp_path):
    path = tmp_path / "upright.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    _draw_ruled_table(page, [["Name", "Role"], ["A N Other", "Director"]])
    doc.save(path)
    doc.close()

    tables = extract_tables(path, [1], rotated=set())
    assert tables[1][0] == [["Name", "Role"], ["A N Other", "Director"]]


def test_extract_tables_falls_back_to_pdfplumber_when_pymupdf_finds_nothing(tmp_path, monkeypatch):
    path = tmp_path / "upright.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    _draw_ruled_table(page, [["Name", "Role"], ["A N Other", "Director"]])
    doc.save(path)
    doc.close()

    import src.ingest.sectionize as sectionize_module

    class EmptyTableFinder:
        tables: list = []

    monkeypatch.setattr(
        sectionize_module.pymupdf.Page, "find_tables", lambda self, *a, **k: EmptyTableFinder()
    )
    tables = extract_tables(path, [1], rotated=set())
    assert tables[1][0] == [["Name", "Role"], ["A N Other", "Director"]]


@pytest.mark.parametrize(
    "key, note, expected",
    [
        ((21,), (20,), True),
        ((22,), (20,), True),
        ((45,), (20,), False),  # a bold amount, not a note
        ((19,), (20,), False),
        ((2, 25), (2, 24), True),
        ((3, 1), (2, 24), False),
        ((25,), (2, 24), False),
    ],
)
def test_is_next_note(key, note, expected):
    assert _is_next_note(key, note) is expected


def test_sectionize_company_writes_files_and_skips_rerun(report, company, tmp_path):
    out = tmp_path / "sections"
    first = sectionize_company(company, report, out)
    assert not first.skipped
    assert first.cin.cin == OWN_CIN

    files = {p.name for p in (out / "TEST").glob("*.json")}
    assert files == {f"{k}.json" for k in SECTION_TYPES} | {"summary.json", "secretarial_audit_subsidiary_1.json"}

    cg = json.loads((out / "TEST" / "corporate_governance.json").read_text(encoding="utf-8"))
    assert (cg["page_start"], cg["page_end"]) == EXPECTED["corporate_governance"]
    assert [p["page"] for p in cg["pages"]] == [6, 7]
    assert "DIN 00121863" in cg["pages"][0]["text"]
    assert cg["company"] == company.name and cg["section_type"] == "corporate_governance"

    sub = json.loads((out / "TEST" / "secretarial_audit_subsidiary_1.json").read_text(encoding="utf-8"))
    assert sub["is_subsidiary_report"] is True
    assert sub["subsidiary_name"] == "ABC Subsidiary Private Limited"
    assert sub["parent_company"] == company.name
    assert (sub["page_start"], sub["page_end"]) == (20, 20)

    summary = json.loads((out / "TEST" / "summary.json").read_text(encoding="utf-8"))
    assert summary["cin_found"] == OWN_CIN
    assert all(summary["sections"][k]["found"] for k in SECTION_TYPES)
    assert summary["subsidiary_secretarial_audit_reports"] == [
        {"subsidiary_name": "ABC Subsidiary Private Limited", "page_start": 20, "page_end": 20,
         "start_heading": sub["detection"]["start_heading"], "end_reason": sub["detection"]["end_reason"]}
    ]

    second = sectionize_company(company, report, out)
    assert second.skipped
    assert {k: (s.page_start, s.page_end) for k, s in second.detection.sections.items()} == EXPECTED
    assert [s.subsidiary_name for s in second.detection.subsidiary_secretarial] == ["ABC Subsidiary Private Limited"]

    third = sectionize_company(company, report, out, force=True)
    assert not third.skipped
