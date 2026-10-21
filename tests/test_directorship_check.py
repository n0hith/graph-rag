"""Tests for the cross-report directorship consistency check."""

import json

from src.eval.directorship_check import check_directorships, norm_company, norm_person
from src.ingest.companies import Company

TCS = Company("Tata Consultancy Services Limited", "TCS", "", "")
MOTORS = Company("Tata Motors Limited", "TATAMOTORS", "", "")
STEEL = Company("Tata Steel Limited", "TATASTEEL", "", "")


def _write(tmp_path, symbol, facts):
    with (tmp_path / f"{symbol}.jsonl").open("w", encoding="utf-8") as fh:
        for fact_type, data in facts:
            fh.write(json.dumps({"fact_type": fact_type, "data": data}) + "\n")


def _claim(person, din, company, category=None):
    return ("other_directorship", {"person_name": person, "din": din, "company_name": company,
                                   "category": category, "reported_by": "TCS"})


def _director(person, din, independent):
    return ("director", {"person_name": person, "din": din, "is_independent": independent})


def test_name_normalization():
    assert norm_company("Tata Consumer Products Ltd.") == norm_company("Tata Consumer Products Limited")
    assert norm_company("The Tata Power Company Limited") == norm_company("Tata Power Company Limited")
    assert norm_person("Mr. N. Chandrasekaran") == norm_person("N Chandrasekaran")


def test_claims_are_matched_by_din_then_name_and_mismatches_listed(tmp_path):
    _write(tmp_path, "TCS", [
        _claim("N Chandrasekaran", "00121863", "Tata Motors Ltd.", "Non-Independent, Non-Executive Director"),
        _claim("O P Bhatt", "00548091", "Tata Motors Limited", "Independent, Non-Executive Director"),
        _claim("Hanne Sorensen", None, "Tata Motors Limited", "Non-Independent, Non-Executive Director"),
        _claim("N Chandrasekaran", "00121863", "Tata Steel Limited"),
        _claim("N Chandrasekaran", "00121863", "Tata Chemicals Limited"),  # not a pilot company: ignored
    ])
    _write(tmp_path, "TATAMOTORS", [
        _director("Mr N Chandrasekaran", "00121863", False),
        _director("Ms Hanne Sorensen", "08035439", True),
    ])
    # TATASTEEL has no extraction file yet.

    checks = {(c.person_name, c.target): c for c in check_directorships(tmp_path, [TCS, MOTORS, STEEL])}

    assert len(checks) == 4
    assert checks[("N Chandrasekaran", "TATAMOTORS")].status == "match"
    assert checks[("O P Bhatt", "TATAMOTORS")].status == "missing"
    assert checks[("Hanne Sorensen", "TATAMOTORS")].status == "category differs"  # matched by name
    assert checks[("N Chandrasekaran", "TATASTEEL")].status == "target not extracted"
