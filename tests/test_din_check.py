"""Tests for resolving certificate DIN conflicts from what the reports print."""

import json

from src.eval.din_check import check_dins
from src.extract.extractor import Fact, load_facts, save_facts
from src.ingest.companies import Company

TCS = Company("Tata Consultancy Services Limited", "TCS", "", "")
MOTORS = Company("Tata Motors Limited", "TATAMOTORS", "", "")


def _director(symbol, name, din, page, **extra):
    return Fact("director", "table", "x", symbol, "corporate_governance", page, "FY2023-24",
                {"person_name": name, "din": din, **extra}, name)


def _sections(tmp_path, symbol, pages):
    d = tmp_path / "sections" / symbol
    d.mkdir(parents=True)
    (d / "corporate_governance.json").write_text(json.dumps({"pages": pages}), encoding="utf-8")


def test_conflict_is_resolved_from_the_same_report_and_another_pilot_report(tmp_path):
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    conflict = {"certificate_din": "08326836", "certificate_page": 117}
    save_facts(extracted / "TCS.jsonl", [_director("TCS", "Al-Noor Ramji", "00230865", 98, din_conflict=conflict)])
    save_facts(extracted / "TATAMOTORS.jsonl", [_director("TATAMOTORS", "Mr Al-Noor Ramji", "00230865", 236)])
    _sections(tmp_path, "TCS", [
        {"page": 106, "text": "appointment of Mr. Al-Noor Ramji (DIN 00230865) as a Non-executive Independent Director"},
        {"page": 117, "text": "9. Al-Noor Ramji 08326836 October 12, 2023"},  # the certificate itself: ignored
    ])
    _sections(tmp_path, "TATAMOTORS", [])

    [finding] = check_dins(extracted, tmp_path / "sections", [TCS, MOTORS], apply=True)
    assert finding.same_report == {"00230865": 1}
    assert finding.other_reports == [("TATAMOTORS", "00230865", 236)]
    assert finding.resolved_din == "00230865"

    [fact] = load_facts(extracted / "TCS.jsonl")
    assert fact.data["din"] == "00230865"
    assert fact.data["din_conflict"] == conflict  # kept on record
    assert fact.data["din_resolution"]["din"] == "00230865"


def test_disagreeing_sources_stay_unresolved(tmp_path):
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    conflict = {"certificate_din": "11111111", "certificate_page": 9}
    save_facts(extracted / "TCS.jsonl", [_director("TCS", "A Person", "22222222", 1, din_conflict=conflict)])
    save_facts(extracted / "TATAMOTORS.jsonl", [_director("TATAMOTORS", "A Person", "33333333", 2)])
    _sections(tmp_path, "TCS", [{"page": 1, "text": "A Person (DIN 22222222)"}])
    _sections(tmp_path, "TATAMOTORS", [])

    [finding] = check_dins(extracted, tmp_path / "sections", [TCS, MOTORS], apply=True)
    assert finding.resolved_din is None and "disagree" in finding.basis
    [fact] = load_facts(extracted / "TCS.jsonl")
    assert fact.data["din"] == "22222222"
