"""Tests for the extraction orchestrator: table-first for directors/subsidiaries, the
evidence-quote check and page resolution for LLM facts, page-group splitting, and dedup.
No real Gemini calls: a fake provider returns canned JSON per fact type."""

from __future__ import annotations

import json

import pytest

from src.ingest.companies import Company
from src.llm.cache import LLMCache
from src.llm.client import LLMClient, LLMRequest, LLMResponse
from src.extract.extractor import (
    Fact,
    _checked_frn,
    _dedupe,
    _find_page,
    _merge_directors,
    estimate_calls,
    extract_company,
    keep_previous_if_fewer,
    load_facts,
    save_facts,
)

COMPANY = Company("Example Ltd", "EX", "L00000MH0000PLC000000", "https://example.invalid/ar.pdf")


def _section(section_type: str, pages: list[dict]) -> dict:
    return {
        "company": COMPANY.name, "nse_symbol": COMPANY.nse_symbol, "section_type": section_type,
        "source_pdf": "EX.pdf", "pdf_sha256": "x", "page_start": pages[0]["page"], "page_end": pages[-1]["page"],
        "detection": {}, "pages": pages,
    }


def _page(number: int, text: str, tables: list | None = None) -> dict:
    return {"page": number, "text": text, "tables": tables or [], "rotated": False}


def write_sections(tmp_path, sections: dict[str, dict]):
    company_dir = tmp_path / COMPANY.nse_symbol
    company_dir.mkdir(parents=True)
    for section_type, payload in sections.items():
        (company_dir / f"{section_type}.json").write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path


class FakeStructuredProvider:
    """Returns canned JSON based on which prompt matched; no real API, no real schema check."""

    name = "fake"

    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses  # marker substring -> JSON text
        self.calls: list[str] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request.prompt)
        for marker, text in self.responses.items():
            if marker in request.prompt:
                return LLMResponse(text, prompt_tokens=10, output_tokens=10)
        return LLMResponse('{"kmp": [], "directors": [], "subsidiaries": [], "auditors": [], "related_party_transactions": []}')


def make_client(tmp_path, responses):
    provider = FakeStructuredProvider(responses)
    return LLMClient(provider, "fake-model", LLMCache(tmp_path / "cache")), provider


# ---------------------------------------------------------------- _find_page


def test_find_page_locates_the_right_page():
    pages = [_page(1, "Alpha text"), _page(2, "Bravo text with a quote in it")]
    assert _find_page("a quote in it", pages) == 2


def test_find_page_tolerates_whitespace_differences():
    pages = [_page(5, "This  has\nextra   whitespace in the source")]
    assert _find_page("This has extra whitespace", pages) == 5


def test_find_page_returns_none_when_not_found():
    pages = [_page(1, "Alpha text")]
    assert _find_page("never appears here", pages) is None


# ---------------------------------------------------------------- _dedupe


def test_dedupe_collapses_same_director_across_groups():
    facts = [
        Fact("director", "llm", "Example Ltd", "EX", "corporate_governance", 1, "FY2023-24", {"din": "123", "person_name": "A"}, "ev1"),
        Fact("director", "llm", "Example Ltd", "EX", "corporate_governance", 2, "FY2023-24", {"din": "123", "person_name": "A"}, "ev2"),
        Fact("director", "llm", "Example Ltd", "EX", "corporate_governance", 3, "FY2023-24", {"din": "456", "person_name": "B"}, "ev3"),
    ]
    assert [f.data["din"] for f in _dedupe(facts)] == ["123", "456"]


# ---------------------------------------------------------------- extract_company


def test_directors_use_the_table_and_skip_the_llm(tmp_path):
    table = [["N Chandrasekaran (Chairman) DIN 00121863", "Non-Independent, Non-Executive"]]
    cg = _section("corporate_governance", [_page(10, "Board of Directors: number of Board meetings attended. N Chandrasekaran. No KMP here.", tables=[table])])
    sections_dir = write_sections(tmp_path, {"corporate_governance": cg})

    client, provider = make_client(tmp_path, responses={"Chief Executive Officer (CEO)": '{"kmp": []}'})
    result = extract_company(COMPANY, sections_dir, client)

    director_facts = [f for f in result.facts if f.fact_type == "director"]
    assert len(director_facts) == 1
    assert director_facts[0].method == "table"
    assert director_facts[0].page == 10
    # the kmp call still ran (LLM-only fact type), but no LLM call was needed for directors
    assert all("Board of Directors member mentioned" not in p for p in provider.calls)
    assert result.calls_used == 1  # just the kmp call


def test_llm_fact_with_bad_evidence_is_dropped_and_logged(tmp_path):
    cg = _section("corporate_governance", [_page(50, "The Company Secretary is Jane Doe.")])
    sections_dir = write_sections(tmp_path, {"corporate_governance": cg})

    good = {"person_name": "Jane Doe", "role": "Company Secretary", "evidence": "Company Secretary is Jane Doe"}
    bad = {"person_name": "Someone Else", "role": "CFO", "evidence": "this quote is not in the source text"}
    responses = {"Chief Executive Officer (CEO)": json.dumps({"kmp": [good, bad]})}
    client, _ = make_client(tmp_path, responses)

    result = extract_company(COMPANY, sections_dir, client)

    kept = [f for f in result.facts if f.fact_type == "kmp"]
    assert len(kept) == 1
    assert kept[0].data["person_name"] == "Jane Doe"
    assert kept[0].page == 50

    assert len(result.dropped) == 1
    assert result.dropped[0].reason == "evidence not found in source text"
    assert result.dropped[0].data["person_name"] == "Someone Else"


def test_kmp_captures_status_and_dates_like_directors(tmp_path):
    cg = _section("corporate_governance", [_page(
        50, "Jane Doe was appointed Chief Financial Officer effective June 1, 2023. "
            "John Roe ceased to be Company Secretary effective March 31, 2024."
    )])
    sections_dir = write_sections(tmp_path, {"corporate_governance": cg})

    kmp = {
        "kmp": [
            {"person_name": "Jane Doe", "role": "CFO", "status": "appointed", "appointed_on": "June 1, 2023",
             "evidence": "Jane Doe was appointed Chief Financial Officer effective June 1, 2023"},
            {"person_name": "John Roe", "role": "Company Secretary", "status": "ceased", "ceased_on": "March 31, 2024",
             "evidence": "John Roe ceased to be Company Secretary effective March 31, 2024"},
        ]
    }
    client, _ = make_client(tmp_path, responses={"Chief Executive Officer (CEO)": json.dumps(kmp)})

    result = extract_company(COMPANY, sections_dir, client)
    kmp_facts = {f.data["person_name"]: f.data for f in result.facts if f.fact_type == "kmp"}

    assert kmp_facts["Jane Doe"]["status"] == "appointed"
    assert kmp_facts["Jane Doe"]["appointed_on"] == "June 1, 2023"
    assert kmp_facts["Jane Doe"]["ceased_on"] is None

    assert kmp_facts["John Roe"]["status"] == "ceased"
    assert kmp_facts["John Roe"]["ceased_on"] == "March 31, 2024"


def test_page_groups_split_long_sections_into_several_calls(tmp_path):
    pages = [_page(n, f"page {n} text") for n in range(1, 14)]  # 13 pages, group size 6 -> 3 calls
    report = _section("auditor_report", pages)
    sections_dir = write_sections(tmp_path, {"auditor_report": report})
    client, provider = make_client(tmp_path, responses={})

    result = extract_company(COMPANY, sections_dir, client)

    assert result.calls_used == 3
    assert len(provider.calls) == 3


def test_dense_table_sections_use_smaller_page_groups(tmp_path):
    pages = [_page(n, f"page {n} text") for n in range(1, 6)]  # 5 pages, group size 2 -> 3 calls
    sections_dir = write_sections(tmp_path, {"related_party": _section("related_party", pages)})
    client, _ = make_client(tmp_path, responses={})

    assert extract_company(COMPANY, sections_dir, client).calls_used == 3
    assert estimate_calls(sections_dir, COMPANY.nse_symbol)["related_party"] == 3


def test_extraction_asks_for_temperature_zero(tmp_path):
    sections_dir = write_sections(tmp_path, {"related_party": _section("related_party", [_page(1, "text")])})
    client, provider = make_client(tmp_path, responses={})
    seen = []
    original = provider.generate
    provider.generate = lambda request: (seen.append(request.temperature), original(request))[1]

    extract_company(COMPANY, sections_dir, client)
    assert seen == [0.0]


def test_estimate_calls_counts_zero_for_a_table_backed_section(tmp_path):
    table = [["A Director (Chairman) DIN 00000001", "Independent, Non-Executive"],
             ["B Director DIN 00000002", "Non-Independent, Executive"]]
    cg = _section("corporate_governance", [_page(1, "text", tables=[table])])
    sections_dir = write_sections(tmp_path, {"corporate_governance": cg})

    estimate = estimate_calls(sections_dir, COMPANY.nse_symbol)
    assert estimate["directors"] == 0
    assert estimate["kmp"] == 1


# ---------------------------------------------------------------- auditor FRN check


@pytest.mark.parametrize(
    "value, evidence, expected",
    [
        ("101248W/W-100022", "For B S R & Co. LLP\nChartered Accountants\nFirm’s Registration No.: 101248W/W-100022", "101248W/W-100022"),
        ("117366W/W-100018", "Firm Registration Number 117366W/W-100018", "117366W/W-100018"),
        ("117366W", "ICAI FRN: 117366W", "117366W"),
        # TCS's secretarial auditor: a peer-review certificate number is not an FRN.
        ("PR No.: 1129/2021", "For Parikh & Associates\nFCS No: 327 CP No: 1228\nPR No.: 1129/2021", None),
        ("1129/2021", "For Parikh & Associates\nFCS No: 327 CP No: 1228\nPR No.: 1129/2021", None),
        ("327", "FCS No: 327 CP No: 1228", None),
        # Label present, but the value isn't what it labels.
        ("999999X", "Firm’s Registration No.: 101248W", None),
        (None, "Firm’s Registration No.: 101248W", None),
    ],
)
def test_checked_frn_keeps_only_labelled_firm_registration_numbers(value, evidence, expected):
    assert _checked_frn(value, evidence) == expected


def test_auditor_fact_with_a_peer_review_number_gets_no_frn(tmp_path):
    text = "For Parikh & Associates\nCompany Secretaries\nFCS No: 327 CP No: 1228\nPR No.: 1129/2021"
    sec = _section("secretarial_audit", [_page(68, text)])
    sections_dir = write_sections(tmp_path, {"secretarial_audit": sec})
    auditors = {"auditors": [{"firm_name": "Parikh & Associates", "firm_registration_no": "PR No.: 1129/2021",
                              "evidence": text}]}
    client, _ = make_client(tmp_path, responses={"secretarial audit report": json.dumps(auditors)})

    [fact] = extract_company(COMPANY, sections_dir, client).facts
    assert fact.data["firm_name"] == "Parikh & Associates"
    assert fact.data["firm_registration_no"] is None


# ---------------------------------------------------------------- other listed directorships


def test_table_directorships_become_facts_reported_by_this_company(tmp_path):
    table = [
        ["Name of the Director and DIN", "Category", "Directorship in other listed entity (Category of Directorship)"],
        ["N Chandrasekaran (Chairman) DIN 00121863", "Non-Independent, Non-Executive", "1. Tata Steel Limited (N) 2. Tata Motors Limited (N)"],
    ]
    cg = _section("corporate_governance", [_page(98, "Number of Board Meetings attended N Chandrasekaran Category of directorship held: (N) Non-Independent, Non-Executive Director", tables=[table])])
    sections_dir = write_sections(tmp_path, {"corporate_governance": cg})
    client, _ = make_client(tmp_path, responses={})

    result = extract_company(COMPANY, sections_dir, client)
    [director] = [f for f in result.facts if f.fact_type == "director"]
    others = [f for f in result.facts if f.fact_type == "other_directorship"]

    assert "other_listed_directorships" not in director.data
    assert [(f.data["company_name"], f.data["din"], f.data["reported_by"], f.page) for f in others] == [
        ("Tata Steel Limited", "00121863", "EX", 98),
        ("Tata Motors Limited", "00121863", "EX", 98),
    ]
    assert others[0].data["category"] == "Non-Independent, Non-Executive Director"
    assert others[0].evidence == "Tata Steel Limited (N)"


def test_llm_directorships_are_dropped_when_the_company_name_is_not_in_the_text(tmp_path):
    text = "Board meetings attended: Mr N Chandrasekaran DIN: 00121863 NINED (C) Tata Chemicals Limited (NINED)"
    cg = _section("corporate_governance", [_page(236, text)])
    sections_dir = write_sections(tmp_path, {"corporate_governance": cg})
    directors = {"directors": [{
        "person_name": "N Chandrasekaran", "din": "00121863", "role": "Chairman",
        "is_independent": False, "is_executive": False, "evidence": "Mr N Chandrasekaran DIN: 00121863",
        "other_listed_directorships": [
            {"company_name": "Tata Chemicals Limited", "category": "NINED"},
            {"company_name": "Invented Holdings Limited", "category": "NINED"},
        ],
    }]}
    client, _ = make_client(tmp_path, responses={"Board of Directors member mentioned": json.dumps(directors)})

    result = extract_company(COMPANY, sections_dir, client)
    others = [f for f in result.facts if f.fact_type == "other_directorship"]

    assert [f.data["company_name"] for f in others] == ["Tata Chemicals Limited"]
    assert others[0].method == "llm"
    assert [d.evidence for d in result.dropped] == ["Invented Holdings Limited"]


# ---------------------------------------------------------------- director merging


def _director(name, din=None, page=1):
    return Fact("director", "llm", "Example Ltd", "EX", "corporate_governance", page, "FY2023-24",
                {"person_name": name, "din": din, "role": "", "is_independent": True, "is_executive": False,
                 "status": "current"}, name)


def test_director_without_din_merges_into_same_name_with_din():
    facts = [_director("L. Krishnakumar", "00423616", page=317), _director("L Krishnakumar", page=290),
             _director("Mr. L. Krishnakumar", page=291)]
    kept, merges, ambiguous = _merge_directors(facts)
    assert [(f.data["person_name"], f.data["din"]) for f in kept] == [("L. Krishnakumar", "00423616")]
    assert len(merges) == 2 and "00423616" in merges[0]
    assert ambiguous == []


def test_same_name_copies_without_any_din_merge_into_each_other():
    kept, merges, _ = _merge_directors([_director("David Crean", page=3), _director("David  Crean", page=5)])
    assert [f.page for f in kept] == [3]
    assert len(merges) == 1


def test_ambiguous_names_are_listed_not_merged():
    facts = [_director("A Kumar", "00000001"), _director("A. Kumar", "00000002"), _director("A Kumar", page=9),
             _director("O P Bhatt", "00548091"), _director("Om Prakash Bhatt", page=7)]
    kept, merges, ambiguous = _merge_directors(facts)
    assert len(kept) == 5 and merges == []
    assert any("several DINs" in a for a in ambiguous)
    assert any("'Om Prakash Bhatt'" in a and "00548091" in a for a in ambiguous)


def test_merged_copys_other_directorships_point_at_the_kept_director():
    other = Fact("other_directorship", "llm", "Example Ltd", "EX", "corporate_governance", 2, "FY2023-24",
                 {"person_name": "Mr N Chandrasekaran", "din": None, "company_name": "Tata Steel Limited",
                  "category": None, "note": None, "reported_by": "EX"}, "Tata Steel Limited")
    facts = [_director("N Chandrasekaran", "00121863"), _director("Mr N Chandrasekaran", page=2), other]
    kept, _, _ = _merge_directors(facts)
    [moved] = [f for f in kept if f.fact_type == "other_directorship"]
    assert (moved.data["person_name"], moved.data["din"]) == ("N Chandrasekaran", "00121863")


# ---------------------------------------------------------------- regression guard


def _sub(name):
    return Fact("subsidiary", "llm", "Example Ltd", "EX", "subsidiaries_aoc1", 1, "FY2023-24",
                {"subsidiary_name": name, "cin": None, "stake_pct": 100.0}, name)


def test_rerun_with_fewer_facts_keeps_the_previous_ones_and_flags_it():
    previous = [_sub("A Ltd"), _sub("B Ltd"), _sub("C Ltd"), _director("X", "00000001")]
    new = [_sub("A Ltd"), _director("X", "00000001"), _director("Y", "00000002")]
    kept, flags = keep_previous_if_fewer(previous, new)
    assert sorted(f.data.get("subsidiary_name", f.data.get("person_name")) for f in kept) == ["A Ltd", "B Ltd", "C Ltd", "X", "Y"]
    assert flags == ["subsidiary / subsidiaries_aoc1: new run found 1, previous run 3; kept the previous facts"]


def test_accept_fewer_keeps_the_new_facts_but_still_flags():
    kept, flags = keep_previous_if_fewer([_sub("A Ltd"), _sub("B Ltd")], [_sub("A Ltd")], accept_fewer=True)
    assert [f.data["subsidiary_name"] for f in kept] == ["A Ltd"]
    assert len(flags) == 1


def test_a_director_merge_is_not_mistaken_for_a_regression():
    previous = [_director("L Krishnakumar", "00423616"), _director("L. Krishnakumar")]  # 2 before merging
    new = [_director("L Krishnakumar", "00423616")]
    kept, flags = keep_previous_if_fewer(previous, new)
    assert flags == [] and len(kept) == 1


def test_facts_round_trip_through_jsonl(tmp_path):
    facts = [_sub("A Ltd"), _director("X", "00000001")]
    save_facts(tmp_path / "EX.jsonl", facts)
    assert load_facts(tmp_path / "EX.jsonl") == facts


def test_same_name_subsidiaries_in_different_countries_are_both_kept():
    def sub(country):
        return Fact("subsidiary", "llm", "Example Ltd", "EX", "subsidiaries_aoc1", 1, "FY2023-24",
                    {"subsidiary_name": "Infosys Consulting S.R.L.", "country": country, "cin": None, "stake_pct": 100.0}, "x")
    assert [f.data["country"] for f in _dedupe([sub("Romania"), sub("Argentina"), sub("Romania")])] == ["Romania", "Argentina"]


# ---------------------------------------------------------------- context page


def test_each_group_after_the_first_sees_the_previous_page_as_context(tmp_path):
    pages = [_page(253, "Unbilled revenues\nEdgeVerve 101"), _page(254, "Panaya Ltd 7"), _page(255, "Danske IT 4")]
    sections_dir = write_sections(tmp_path, {"related_party": _section("related_party", pages)})
    # Every call returns the same item, quoting text that is only on p.254.
    item = {"related_party_transactions": [{"party_name": "Panaya Ltd", "nature": "Unbilled revenues",
                                            "amount_inr_crore": 7.0, "evidence": "Panaya Ltd"}]}
    client, provider = make_client(tmp_path, responses={"related-party transactions note": json.dumps(item)})

    result = extract_company(COMPANY, sections_dir, client)

    first, second = provider.calls
    assert "CONTEXT ONLY" not in first
    assert "[PAGE 254 - CONTEXT ONLY" in second and "Panaya Ltd 7" in second and "[PAGE 255]" in second
    # Found on p.254 in the first group; the second group can only see it on its context page.
    assert [(f.page, f.data["party_name"]) for f in result.facts] == [(254, "Panaya Ltd")]
    assert [d.reason for d in result.dropped] == ["quoted from the context page only"]
    # No PDF beside the sections in this test: amounts are left unchecked, and that is said.
    assert any("amounts not checked" in n for n in result.notes)
