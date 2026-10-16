"""Tests for parsing facts directly out of a table (no LLM involved)."""

from src.extract.tables import parse_directors_table, parse_subsidiaries_table


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
        {"subsidiary_name": "Example America Inc", "cin": None, "stake_pct": 100.0,
         "evidence": "Name of the Subsidiary Company: Example America Inc; % of Shareholding: 100%"},
        {"subsidiary_name": "Example Canada Ltd", "cin": None, "stake_pct": 74.5,
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
