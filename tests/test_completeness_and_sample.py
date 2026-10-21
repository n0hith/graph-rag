"""Tests for the independent completeness counts and the stratified hand-check sample."""

from src.eval.completeness import check_directors, check_subsidiaries
from src.eval.sample_facts import stratified_sample
from src.extract.extractor import Fact


def _fact(fact_type, page=1, method="llm", symbol="EX", **data):
    return Fact(fact_type, method, "x", symbol, "s", page, "FY2023-24", data, "e")


def test_subsidiary_rows_missing_and_extra():
    text = "\n".join([
        "Sr. No", "Name of the subsidiary",
        "1", "Alpha Limited", "India", "100.00",
        "2 Beta GmbH", "Germany", "100.00",           # number and name on one line
        "3", "Gamma", "Consulting S.R.L.", "Romania",  # name wraps
        "4", "Gamma", "Consulting S.R.L.", "Argentina",  # same name, another row
        "13 ", "196 ",                                 # a value cell, not a serial row
        "Part B: Associates", "1", "Delta Limited",
    ])
    section = {"pages": [{"page": 46, "text": text}]}
    facts = [_fact("subsidiary", 46, subsidiary_name="Alpha Limited"),
             _fact("subsidiary", 46, subsidiary_name="Gamma Consulting S.R.L."),
             _fact("subsidiary", 46, subsidiary_name="Gamma Consulting S.R.L."),
             _fact("subsidiary", 46, subsidiary_name="Delta Limited")]
    check = check_subsidiaries(section, facts)
    assert check.rows == 4
    assert check.missing == [(2, "Beta GmbH")]
    assert check.extra == ["Delta Limited (p.46): outside the numbered rows"]


def test_directors_against_the_certificate():
    cert = "\n".join(["Certificate: none of the directors are disqualified",
                      "1.", "A One", "00000001", "2.", "B Two", "00000002", "3.", "C Three", "00000003"])
    section = {"pages": [{"page": 117, "text": cert}]}
    facts = [_fact("director", person_name="A One", din="00000001", status="current"),
             _fact("director", person_name="Mr. B. Two", din=None, status="current"),
             _fact("director", person_name="D Four", din="00000004", status="ceased", ceased_on="January 10, 2024"),
             _fact("director", person_name="E Five", din="00000005", status="appointed", after_fy_end=True,
                   appointed_on="May 15, 2024"),
             _fact("director", person_name="F Six", din="00000006", status="current")]
    check = check_directors(section, facts)
    assert (check.certificate, check.extracted, check.on_certificate) == (3, 5, 2)
    assert check.missing == ["C Three (00000003)"]
    assert check.ceased_in_year == ["D Four (00000004), ceased January 10, 2024"]
    assert check.after_fy_end == ["E Five (00000005), appointed May 15, 2024"]
    assert check.unexplained == ["F Six (00000006), status current"]
    assert check.without_din == ["Mr. B. Two (no DIN)"]


def test_stratified_sample_spreads_and_includes_required_facts():
    facts = []
    for symbol in ["AAA", "BBB"]:
        facts += [_fact("subsidiary", method="table", symbol=symbol, n=i) for i in range(30)]
        facts += [_fact("related_party", page=299, symbol=symbol, n=i) for i in range(30)]
        facts += [_fact("auditor", symbol=symbol, n=i) for i in range(2)]
    sample = stratified_sample(facts, 10, [(lambda f: f.nse_symbol == "AAA" and f.page == 299, 3)])
    assert len(sample) == 10
    assert sum(f.nse_symbol == "AAA" for f in sample) == 5
    assert sum(f.nse_symbol == "AAA" and f.page == 299 for f in sample) >= 3
    for symbol in ["AAA", "BBB"]:  # every fact type present in each company
        assert {f.fact_type for f in sample if f.nse_symbol == symbol} == {"subsidiary", "related_party", "auditor"}
    assert stratified_sample(facts, 10, seed=1) == stratified_sample(facts, 10, seed=1)
