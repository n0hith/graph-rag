"""Clean-up fixes from the 50-fact sample check (src/extract/cleanup.py)."""

from __future__ import annotations

from src.extract.cleanup import clean_facts, clean_name, clean_roles, mark_kmp_after_fy_end, relocate_directorships
from src.extract.extractor import Fact


def fact(fact_type, data, page=1, evidence="quote", symbol="EX"):
    return Fact(fact_type, "llm", "Example Ltd", symbol, "corporate_governance", page, "FY2023-24", data, evidence)


def test_names_lose_line_breaks_and_trailing_footnote_markers():
    assert clean_name("Kaleidoscope \nAnimations \nInc (6)") == "Kaleidoscope Animations Inc"
    assert clean_name("Infosys Consulting \nS.R.L.(2)(9)") == "Infosys Consulting S.R.L."
    assert clean_name("TML Holdings Pte. Limited Singapore**") == "TML Holdings Pte. Limited Singapore"
    # A short name in brackets is part of the name, not a footnote.
    assert clean_name("Infosys Technologies (China) Co. Limited (Infosys China)") == \
        "Infosys Technologies (China) Co. Limited (Infosys China)"
    assert clean_name("InMotion Ventures 2 Limited") == "InMotion Ventures 2 Limited"


def test_directorship_moves_to_the_page_that_prints_the_company():
    pages = [{"page": 289, "text": "Attendance: Siraj Chaudhry 7 out of 7"},
             {"page": 290, "text": "Siraj Chaudhry Independent Director of: - Dhanuka Agritech Limited"}]
    f = fact("other_directorship", {"person_name": "Siraj Chaudhry", "company_name": "Dhanuka Agritech Limited"}, 289)
    [moved], notes = relocate_directorships([f], pages)
    assert moved.page == 290 and "p.289 -> p.290" in notes[0]
    [kept], notes = relocate_directorships([moved], pages)
    assert kept.page == 290 and notes == []


def test_kmp_appointed_after_the_year_end_is_marked():
    after = fact("kmp", {"person_name": "Jayesh Sanghrajka", "role": "CFO", "appointed_on": "April 1, 2024"})
    during = fact("kmp", {"person_name": "K Krithivasan", "role": "CEO", "appointed_on": "June 1, 2023"})
    [a, d], notes = mark_kmp_after_fy_end([after, during])
    assert a.data["after_fy_end"] is True and "after_fy_end" not in d.data and len(notes) == 1


def test_roles_from_the_reports_category_replace_empty_generic_and_heading_roles():
    tcs = fact("director", {"person_name": "Don Callahan", "role": "", "is_independent": True, "is_executive": False},
               evidence="Don Callahan^^^ DIN 08326836 | Independent, Non-Executive")
    heading = fact("director", {"person_name": "Koushik Chatterjee", "role": "Executive Directors",
                                "is_independent": False, "is_executive": True})
    generic = fact("director", {"person_name": "Nandan M. Nilekani", "role": "Director", "is_independent": False,
                                "is_executive": False})
    wrapped = fact("director", {"person_name": "Sunil D'Souza", "role": "Managing Director \n& Chief Executive \nOfficer"})
    chairman = fact("director", {"person_name": "N Chandrasekaran", "role": "Chairman"})
    out, _ = clean_roles([tcs, heading, generic, wrapped, chairman])
    assert [f.data["role"] for f in out] == ["Independent, Non-Executive Director", "Executive Director",
                                             "Non-Executive, Non-Independent Director",
                                             "Managing Director & Chief Executive Officer", "Chairman"]
    assert out[1].data["role_as_extracted"] == "Executive Directors"
    assert "role_as_extracted" not in out[3].data  # only whitespace changed


def test_clean_facts_twice_changes_nothing_the_second_time():
    facts = [fact("subsidiary", {"subsidiary_name": "Kaleidoscope \nAnimations \nInc (6)"}),
             fact("director", {"person_name": "A B", "role": "Independent Directors", "is_independent": True})]
    once, notes, counts = clean_facts(facts, [])
    twice, notes2, counts2 = clean_facts(once, [])
    assert counts == {"footnote": 1, "line_break": 1} and notes
    assert twice == once and notes2 == [] and counts2 == {"footnote": 0, "line_break": 0}
