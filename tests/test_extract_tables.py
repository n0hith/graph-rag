"""Tests for parsing facts directly out of a table (no LLM involved)."""

from src.extract.tables import (
    parse_category_legend,
    parse_directors_table,
    parse_listed_directorships,
    parse_subsidiaries_table,
)


def test_parses_a_director_row_with_role_and_din():
    table = [
        ["Name of the Director and DIN", "Category"],
        ["N Chandrasekaran (Chairman) DIN 00121863", "Non-Independent, Non-Executive"],
    ]
    [row] = parse_directors_table(table)
    assert row == {
        "person_name": "N Chandrasekaran",
        "din": "00121863",
        "role": "Chairman",
        "is_independent": False,
        "is_executive": False,
        "status": "current",
        "appointed_on": None,
        "ceased_on": None,
        "footnote": None,
        "other_listed_directorships": [],
        "evidence": "N Chandrasekaran (Chairman) DIN 00121863 | Non-Independent, Non-Executive",
    }


def test_director_without_a_role_or_footnote_marker():
    table = [["O P Bhatt^ DIN 00548091", "Independent, Non-Executive"]]
    [row] = parse_directors_table(table)
    assert row["person_name"] == "O P Bhatt"
    assert row["role"] == ""
    assert row["is_independent"] is True


def test_executive_director_is_flagged_independent_and_executive_correctly():
    table = [["K Krithivasan (CEO & MD) DIN 10106739", "Non-Independent, Executive"]]
    [row] = parse_directors_table(table)
    assert row["is_independent"] is False
    assert row["is_executive"] is True


def test_erstwhile_director_is_marked_ceased():
    table = [["Rajesh Gopinathan** (Erstwhile CEO & MD) DIN 06365813", "Non-Independent, Executive"]]
    [row] = parse_directors_table(table)
    assert row["status"] == "ceased"


def test_rows_without_a_din_are_skipped():
    table = [["Material Topic", "TCS Approach"], ["Board effectiveness", "some prose, no DIN here"]]
    assert parse_directors_table(table) == []


def test_parses_a_transposed_aoc1_subsidiary_table():
    table = [
        ["Country", "", "U.S.A.", "Canada"],
        ["% of Shareholding", "", "100%", "74.5%"],
        ["Name of the Subsidiary Company", "", "Example America Inc", "Example Canada Ltd"],
    ]
    rows = parse_subsidiaries_table(table)
    assert rows == [
        {"subsidiary_name": "Example America Inc", "country": "U.S.A.", "cin": None, "stake_pct": 100.0,
         "evidence": "Name of the Subsidiary Company: Example America Inc; % of Shareholding: 100%"},
        {"subsidiary_name": "Example Canada Ltd", "country": "Canada", "cin": None, "stake_pct": 74.5,
         "evidence": "Name of the Subsidiary Company: Example Canada Ltd; % of Shareholding: 74.5%"},
    ]


def test_subsidiary_table_without_the_right_rows_returns_nothing():
    table = [["Country", "U.S.A."], ["Turnover", "5,398"]]
    assert parse_subsidiaries_table(table) == []


def test_subsidiary_table_skips_empty_name_columns():
    table = [
        ["Country", "", "U.S.A.", ""],
        ["% of Shareholding", "", "100%", ""],
        ["Name of the Subsidiary Company", "", "Example Inc", ""],
    ]
    rows = parse_subsidiaries_table(table)
    assert len(rows) == 1
    assert rows[0]["subsidiary_name"] == "Example Inc"


# ---------------------------------------------------------------- other listed directorships

TCS_LEGEND_TEXT = (
    "Category of directorship held: \n(N) Non-Independent, Non-Executive Director, "
    "(I) Independent, Non-Executive Director, (ED) Executive Director\n"
)


def test_parses_the_category_legend_under_the_table():
    assert parse_category_legend(TCS_LEGEND_TEXT) == {
        "N": "Non-Independent, Non-Executive Director",
        "I": "Independent, Non-Executive Director",
        "ED": "Executive Director",
    }


def test_legend_is_only_read_after_its_heading():
    assert parse_category_legend("(N) Non-Independent Director appears in prose") == {}


def test_parses_numbered_directorships_with_codes_and_notes():
    cell = ("1. HDFC Bank Limited (N) 2. HDFC ERGO General Insurance Company Limited [(N) Debt Listed] "
            "3. Aadhar Housing Finance Limited (Debt Listed) (I) 4. Torrent Power Limited (I) [ceased w.e.f. March 31, 2024]")
    rows = parse_listed_directorships(cell, parse_category_legend(TCS_LEGEND_TEXT))
    assert [(r["company_name"], r["category"], r["note"]) for r in rows] == [
        ("HDFC Bank Limited", "Non-Independent, Non-Executive Director", None),
        ("HDFC ERGO General Insurance Company Limited", "Non-Independent, Non-Executive Director", "Debt Listed"),
        ("Aadhar Housing Finance Limited", "Independent, Non-Executive Director", "Debt Listed"),
        ("Torrent Power Limited", "Independent, Non-Executive Director", "ceased w.e.f. March 31, 2024"),
    ]
    assert rows[0]["evidence"] == "HDFC Bank Limited (N)"


def test_unnumbered_single_directorship_and_unknown_code():
    [row] = parse_listed_directorships("Tata Motors Limited (NINED)")
    assert row["company_name"] == "Tata Motors Limited"
    assert row["category"] == "NINED"  # no legend: the code is kept as stated


def test_dash_means_no_other_directorships():
    assert parse_listed_directorships("-") == []
    assert parse_listed_directorships("") == []


def test_director_table_reads_the_other_listed_entity_column():
    table = [
        ["Name of the Director and DIN", "Category", "Directorship in other listed entity (Category of Directorship)"],
        ["N Chandrasekaran (Chairman) DIN 00121863", "Non-Independent, Non-Executive",
         "1. Tata Steel Limited (N) 2. Tata Motors Limited (N)"],
        ["K Krithivasan* (CEO & MD) DIN 10106739", "Non-Independent, Executive", "-"],
    ]
    chandra, krithi = parse_directors_table(table, TCS_LEGEND_TEXT)
    assert [d["company_name"] for d in chandra["other_listed_directorships"]] == ["Tata Steel Limited", "Tata Motors Limited"]
    assert chandra["other_listed_directorships"][0]["category"] == "Non-Independent, Non-Executive Director"
    assert krithi["other_listed_directorships"] == []
