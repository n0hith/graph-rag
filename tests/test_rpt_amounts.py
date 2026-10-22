"""Related-party amounts checked against page geometry (src/extract/amounts.py): the
party's row, the FY2024 column, and the nature heading the row sits under. Pages are built
from positioned words, laid out like the pilot reports' tables."""

from __future__ import annotations

from src.extract.amounts import Word, _matches, check_fact, find_headings, in_struck_off_table
from src.extract.extractor import Fact

_line_ids = iter(range(10_000))


def line(y: float, *cells: tuple[float, str]) -> list[Word]:
    """Words on one printed line: (x, text) pairs, each word ~5pt per character wide."""
    block = next(_line_ids)
    out = []
    for x, text in cells:
        for word in text.split():
            out.append(Word(x, y - 4, x + 5 * len(word), y + 4, word, (block, 0)))
            x += 5 * len(word) + 3
    return out


def page(*lines: list[Word]) -> list[Word]:
    return [w for ln in lines for w in ln]


def rpt(party: str, nature: str, amount: float | None, page_no: int = 1) -> Fact:
    return Fact("related_party", "llm", "Example Ltd", "EX", "related_party", page_no, "FY2023-24",
                {"party_name": party, "nature": nature, "amount_inr_crore": amount}, party)


def run(fact: Fact, words_by_page: dict[int, list[Word]]):
    natures = {"Trade receivables", "Other financial assets", "Unbilled revenues", "Sale of products",
               "Purchase of goods", "Loans given", fact.data["nature"]}
    return check_fact(fact, words_by_page, find_headings(words_by_page, natures))


# Infosys-like: two tables side by side, each with its own 2024 / 2023 columns and headings;
# the same party has rows in both.
INFOSYS_P1 = page(
    line(60, (40, "Infosys Integrated Annual Report 2023-24")),
    line(80, (240, "2024"), (285, "2023"), (509, "2024"), (554, "2023")),
    line(100, (40, "Trade receivables"), (310, "Other financial assets")),
    line(120, (48, "Panaya Ltd"), (240, "2"), (285, "1"), (317, "GuideVision"), (509, "5"), (554, "8")),
    line(134, (48, "Fluido Oy"), (240, "3"), (285, "1"), (317, "Panaya Ltd"), (509, "6"), (554, "2")),
    line(160, (310, "Unbilled revenues")),
    line(174, (317, "EdgeVerve"), (509, "101"), (554, "107")),
)
# The next page's left table carries on under p.1's last heading ('Unbilled revenues').
INFOSYS_P2 = page(
    line(80, (240, "2024"), (285, "2023")),
    line(100, (48, "Panaya Ltd"), (240, "7"), (285, "3")),
)


def test_amount_on_the_partys_row_in_the_fy2024_column_passes():
    status, page_no, cell, basis, _ = run(rpt("Panaya Ltd", "Trade receivables", 2.0), {1: INFOSYS_P1})
    assert (status, page_no, cell.printed) == ("pass", 1, "2")
    assert "column headed FY2024" in basis and "under its nature heading" in basis


def test_previous_year_figure_fails():
    status, *_ = run(rpt("Panaya Ltd", "Trade receivables", 1.0), {1: INFOSYS_P1})
    assert status == "fail"


def test_amount_under_another_heading_is_relabelled_to_that_heading():
    # 2 is Panaya's FY2024 trade receivable; its other-financial-assets figure is 6.
    status, _, cell, _, heading = run(rpt("Panaya Ltd", "Other financial assets", 2.0), {1: INFOSYS_P1})
    assert (status, cell.printed, heading) == ("relabel", "2", "Trade receivables")
    status, _, cell, *_ = run(rpt("Panaya Ltd", "Other financial assets", 6.0), {1: INFOSYS_P1})
    assert (status, cell.printed) == ("pass", "6")


def test_neighbouring_tables_row_on_the_same_line_is_not_read():
    # GuideVision's 5 sits on Panaya's line, in the right-hand table.
    status, *_ = run(rpt("Panaya Ltd", "Trade receivables", 5.0), {1: INFOSYS_P1})
    assert status == "fail"


def test_heading_carries_over_a_page_break():
    pages = {1: INFOSYS_P1, 2: INFOSYS_P2}
    status, page_no, cell, *_ = run(rpt("Panaya Ltd", "Unbilled revenues", 7.0, page_no=2), pages)
    assert (status, page_no, cell.printed) == ("pass", 2, "7")
    # The p.254 mislabel: the same row called "Trade receivables" is put back under the
    # heading it continues from the previous page.
    status, _, _, _, heading = run(rpt("Panaya Ltd", "Trade receivables", 7.0, page_no=2), pages)
    assert (status, heading) == ("relabel", "Unbilled revenues")


# Tata Steel-like matrix: parties head the columns, the current year is the row's first line
# and the previous year the line under it; the title names both years.
TATA_STEEL = page(
    line(60, (50, "The following table summarises transactions for the year ended as at March 31, 2024 and March 31, 2023:")),
    line(100, (260, "Subsidiaries"), (360, "Associates")),
    line(120, (50, "Purchase of goods"), (250, "37,389.65"), (370, "4.13")),
    line(132, (250, "42,922.33"), (370, "45.29")),
)


def test_matrix_cell_under_the_partys_column_on_the_current_year_line():
    status, _, cell, basis, _ = run(rpt("Associates", "Purchase of goods", 4.13), {1: TATA_STEEL})
    assert (status, cell.printed) == ("pass", "4.13")
    assert "nature row x party column" in basis and "current year first" in basis
    assert run(rpt("Associates", "Purchase of goods", 45.29), {1: TATA_STEEL})[0] == "fail"  # previous year
    assert run(rpt("Subsidiaries", "Purchase of goods", 4.13), {1: TATA_STEEL})[0] == "fail"  # other column


def test_wrapped_cell_beside_the_label_pushes_figures_down():
    # Tata Motors: the relationship column wraps, the figures sit on its second line.
    tm = page(
        line(600, (460, "2024"), (530, "2023")),
        line(620, (91, "Sale of products")),
        line(640, (91, "Tata Advance Systems Limited"), (271, "Tata Sons Pvt Ltd, its subsidiaries and")),
        line(650, (271, "joint arrangements"), (449, "625.77"), (517, "524.46")),
        line(670, (91, "TML Business Services Limited"), (271, "Subsidiary"), (449, "100.47"), (517, "100.93")),
    )
    status, _, cell, *_ = run(rpt("Tata Advance Systems Limited", "Sale of products", 625.77), {1: tm})
    assert (status, cell.printed) == ("pass", "625.77")


def test_nil_cell_is_nil_whether_the_amount_is_zero_or_missing():
    tc = page(
        line(80, (420, "2024"), (500, "2023")),
        line(100, (50, "Investment made")),
        line(120, (77, "Tata Starbucks Private Limited"), (420, "-"), (500, "100.00")),
        line(140, (77, "Tata Smartfoodz Ltd"), (420, "119.91"), (500, "41.50")),
    )
    status, _, cell, *_ = run(rpt("Tata Starbucks Private Limited", "Investment made", 0.0), {1: tc})
    assert (status, cell.printed) == ("nil", "-")
    assert run(rpt("Tata Starbucks Private Limited", "Investment made", None), {1: tc})[0] == "nil"
    # A missing amount where the FY2024 cell holds a figure is not nil.
    assert run(rpt("Tata Smartfoodz Ltd", "Investment made", None), {1: tc})[0] == "no_amount"


def test_a_heading_inside_a_longer_heading_does_not_count_on_its_own():
    # Infosys p.255: "Loans given" is also a heading elsewhere, but here it is part of
    # "Loans and advances in the nature of loans given to subsidiaries".
    infy = page(
        line(80, (240, "2024"), (285, "2023")),
        line(100, (40, "Loans and advances in the nature of")),
        line(110, (40, "loans given to subsidiaries")),
        line(124, (48, "Infosys Turkey"), (240, "57"), (285, "43")),
        line(150, (40, "Loans given")),
        line(164, (48, "Infosys Turkey"), (240, "–"), (285, "38")),
    )
    nature = "Loans and advances in the nature of loans given to subsidiaries"
    status, _, cell, *_ = run(rpt("Infosys Turkey", nature, 57.0), {1: infy})
    assert (status, cell.printed) == ("pass", "57")


def test_struck_off_companies_are_not_related_parties():
    pages = [{"page": 466, "text": "44. Details of significant investments Tata Motors Body Solutions Limited India "
                                   "45. Transactions with struck off companies The following table ... "
                                   "Taxi Films Pvt. Ltd. Services received - 0.00# External vendor"}]
    assert in_struck_off_table(rpt("Taxi Films Pvt. Ltd.", "Services received", None, page_no=466), pages)
    assert not in_struck_off_table(rpt("Tata Motors Body Solutions Limited", "Services received", 1.0, page_no=466), pages)


def test_amounts_match_as_printed_in_crore_only():
    assert _matches(37389.65, 37389.65) and _matches(-4.6, -4.6)
    assert not _matches(4.6, 4.7)
    assert not _matches(0.0, 5593.94)  # no rupee conversion: 5,593.94 / 1e7 rounds to 0
    assert not _matches(1.5, 150.0)  # no lakh conversion
    assert _matches(0.0, None) and not _matches(1.0, None)  # a dash is nil


def test_wrapped_party_name_takes_its_own_tables_figures():
    # Infosys p.256: the party name runs over three lines with its figures on the last;
    # its first line shares a height with the right-hand table's row (2 / 2).
    infy = page(
        line(80, (240, "2024"), (285, "2023"), (509, "2024"), (554, "2023")),
        line(100, (40, "Purchase of services"), (310, "Interest income")),
        line(138, (62, "Infosys (Malaysia) SDN. BHD. (formerly"), (330, "Infosys Turkey"), (509, "2"), (554, "2")),
        line(148, (62, "Global Enterprise International")),
        line(158, (62, "(Malaysia) Sdn. Bhd.)"), (231, "165"), (281, "19")),
        line(172, (62, "oddity space GmbH"), (240, "2"), (285, "4")),
    )
    status, _, cell, *_ = run(rpt("Infosys (Malaysia) SDN. BHD.", "Purchase of services", 165.0), {1: infy})
    assert (status, cell.printed) == ("pass", "165")
    assert run(rpt("Infosys (Malaysia) SDN. BHD.", "Purchase of services", 2.0), {1: infy})[0] == "fail"
