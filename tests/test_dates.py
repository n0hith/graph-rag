"""Dates later than the report's own date (src/extract/dates.py)."""

from __future__ import annotations

import datetime

from src.extract.dates import fix_impossible_dates
from src.extract.extractor import Fact

PUBLISHED = datetime.date(2024, 5, 21)  # Tata Consumer's PDF


def kmp(name, ceased_on, page):
    return Fact("kmp", "llm", "Example Ltd", "EX", "corporate_governance", page, "FY2023-24",
                {"person_name": name, "role": "CFO", "status": "ceased", "appointed_on": None, "ceased_on": ceased_on}, name)


def director(name, din, ceased_on, page):
    return Fact("director", "llm", "Example Ltd", "EX", "corporate_governance", page, "FY2023-24",
                {"person_name": name, "din": din, "status": "ceased", "ceased_on": ceased_on}, name)


def test_impossible_date_takes_the_other_mention_and_keeps_the_conflict():
    facts = [kmp("L. Krishnakumar", "October 31, 2023", 289), kmp("L Krishnakumar", "October 31, 2024", 295)]
    fixed, notes = fix_impossible_dates(facts, PUBLISHED, "EX")
    assert fixed[0] == facts[0]
    assert fixed[1].data["ceased_on"] == "October 31, 2023"
    assert fixed[1].data["date_conflict"]["as_printed"] == "October 31, 2024"
    assert fixed[1].data["date_conflict"]["other_pages"] == [289]
    assert len(notes) == 1 and "-> 'October 31, 2023'" in notes[0]


def test_same_person_found_through_a_confirmed_merge_and_the_dins():
    # "L Krishnakumar" = Lakshmanan Krishna Kumar only via data/overrides/merges.csv.
    facts = [director("Mr. Lakshmanan Krishna Kumar", "00423616", "October 31, 2023", 317),
             kmp("L Krishnakumar", "October 31, 2024", 295)]
    overrides = [{"nse_symbol": "EX", "fact_type": "director", "from_name": "L. Krishnakumar", "to_din": "00423616"}]
    fixed, _ = fix_impossible_dates(facts, PUBLISHED, "EX", overrides)
    assert fixed[1].data["ceased_on"] == "October 31, 2023"
    assert fixed[1].data["date_conflict"]["other_pages"] == [317]


def test_without_another_mention_the_date_is_only_flagged():
    facts = [kmp("Someone Else", "October 31, 2024", 295)]
    fixed, notes = fix_impossible_dates(facts, PUBLISHED, "EX")
    assert fixed == facts and "left as printed" in notes[0]


def test_dates_up_to_the_report_date_are_left_alone():
    facts = [kmp("A Person", "May 21, 2024", 1), director("B Person", "00000001", "March 31, 2024", 2)]
    assert fix_impossible_dates(facts, PUBLISHED, "EX") == (facts, [])
