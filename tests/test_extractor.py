"""Tests for the extraction orchestrator: table-first for directors/subsidiaries, the
evidence-quote check and page resolution for LLM facts, page-group splitting, and dedup.
No real Gemini calls: a fake provider returns canned JSON per fact type."""

from __future__ import annotations

import json

import pytest

from src.ingest.companies import Company
from src.llm.cache import LLMCache
from src.llm.client import LLMClient, LLMRequest, LLMResponse
from src.extract.extractor import Fact, _dedupe, _find_page, estimate_calls, extract_company

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
    cg = _section("corporate_governance", [_page(10, "Board of Directors page text. No KMP here.", tables=[table])])
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
    rpt = _section("related_party", pages)
    sections_dir = write_sections(tmp_path, {"related_party": rpt})
    client, provider = make_client(tmp_path, responses={})

    result = extract_company(COMPANY, sections_dir, client)

    assert result.calls_used == 3
    assert len(provider.calls) == 3


def test_estimate_calls_counts_zero_for_a_table_backed_section(tmp_path):
    table = [["A Director (Chairman) DIN 00000001", "Independent, Non-Executive"],
             ["B Director DIN 00000002", "Non-Independent, Executive"]]
    cg = _section("corporate_governance", [_page(1, "text", tables=[table])])
    sections_dir = write_sections(tmp_path, {"corporate_governance": cg})

    estimate = estimate_calls(sections_dir, COMPANY.nse_symbol)
    assert estimate["directors"] == 0
    assert estimate["kmp"] == 1
