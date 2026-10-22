"""Phase 4 entity resolution: name normalisation (src/resolve/normalize.py) and the merge
rules (src/resolve/merge_entities.py), on small fact files laid out like the real ones."""

from __future__ import annotations

from src.extract.extractor import Fact, save_facts
from src.ingest.companies import Company
from src.resolve.merge_entities import combined_status, resolve
from src.resolve.normalize import (
    canonical_country,
    company_key,
    company_name,
    initials_only,
    person_key,
    persons_may_match,
)

# ---------------------------------------------------------------- names


def test_person_key_drops_titles_and_punctuation():
    assert person_key("Mr. N. Chandrasekaran") == person_key("N Chandrasekaran") == person_key("Shri N Chandrasekaran")
    assert initials_only("Mr. O. P. Bhatt") and not initials_only("Om Prakash Bhatt")


def test_lookalike_l_and_capital_i_compare_equal():
    assert company_key("Neelachal lspat Nigam Limited") == company_key("Neelachal Ispat Nigam Limited")


def test_people_who_only_might_match_get_a_reason():
    assert persons_may_match("Om Prakash Bhatt", "O P Bhatt") == "same surname, compatible initials"
    assert persons_may_match("Lakshmanan Krishna Kumar", "L Krishnakumar") is not None
    assert persons_may_match("K Krithivasan", "K. Krithivasan") is None  # same key: not a "maybe"


def test_company_legal_forms_and_punctuation():
    assert company_key("Tata Sons Pvt Ltd") == company_key("Tata Sons Private Limited")
    assert company_key("GuideVision Polska SP. Z O.O.") == company_key("GuideVision Polska Sp.z.o.o")
    assert company_key("The Tata Power Company Limited") == company_key("Tata Power Co. Ltd.")


def test_company_name_splits_former_and_short_names_and_countries():
    c = company_name("Infosys (Malaysia) SDN. BHD. (formerly Global Enterprise International (Malaysia) Sdn. Bhd.)")
    assert c.display == "Infosys (Malaysia) SDN. BHD."
    assert c.former_names == ["Global Enterprise International (Malaysia) Sdn. Bhd."]
    c = company_name("Infosys \nTechnologies \n(China) Co. \nLimited (Infosys \nChina)(2)")
    assert (c.display, c.short_names) == ("Infosys Technologies (China) Co. Limited", ["Infosys China"])
    assert company_name("Infosys Consulting S.R.L. (Argentina)").country == "Argentina"
    c = company_name("TML Holdings Pte. Limited Singapore**")
    assert (c.display, c.country) == ("TML Holdings Pte. Limited", "Singapore")
    # A country that is part of the legal name stays.
    assert company_name("Tata Consultancy Services Belgium").display == "Tata Consultancy Services Belgium"
    assert canonical_country("U.S.A.") == canonical_country("US") == "US"
    assert canonical_country("The \nNetherlands") == "Netherlands"


# ---------------------------------------------------------------- merging

A = Company("Alpha Limited", "ALPHA", "L00000MH2000PLC000001", "https://example.invalid/a.pdf")
B = Company("Beta Limited", "BETA", "L00000MH2000PLC000002", "https://example.invalid/b.pdf")


def fact(company: Company, fact_type: str, data: dict, page: int = 1) -> Fact:
    return Fact(fact_type, "llm", company.name, company.nse_symbol, "x", page, "FY2023-24", data, "quote")


def director(company, name, din=None, status="current", **extra):
    return fact(company, "director", {"person_name": name, "din": din, "status": status, **extra})


def run(tmp_path, facts_a, facts_b, overrides=()):
    save_facts(tmp_path / "ALPHA.jsonl", facts_a)
    save_facts(tmp_path / "BETA.jsonl", facts_b)
    return resolve(tmp_path, [A, B], list(overrides))


def people(res):
    return sorted(e["name"] for e in res.entities if e["type"] == "Person")


def test_people_merge_by_din_across_reports(tmp_path):
    res = run(tmp_path, [director(A, "Mr N Chandrasekaran", "00121863")],
              [director(B, "N. Chandrasekaran", "00121863"),
               fact(B, "other_directorship", {"person_name": "N. Chandrasekaran", "din": "00121863",
                                               "company_name": "Alpha Ltd.", "reported_by": "BETA"})])
    [person] = [e for e in res.entities if e["type"] == "Person"]
    assert person["reports"] == ["ALPHA", "BETA"]
    # Beta's claim about Alpha's board lands on Alpha's own seat (Alpha Ltd. = Alpha Limited).
    [seat] = [r for r in res.relations if r["type"] == "DIRECTOR_OF" and r["to"] == "company:0001"]
    assert {s["reported_by"] for s in seat["sources"]} == {"ALPHA", "BETA"}


def test_initials_only_name_in_two_reports_without_a_shared_din_is_only_listed(tmp_path):
    res = run(tmp_path, [director(A, "O P Bhatt", "00548091")], [director(B, "Mr. O. P. Bhatt")])
    assert len(people(res)) == 2
    assert [u.reason for u in res.uncertain] == ["same initials-only name in two reports, no shared DIN"]


def test_full_name_merges_across_reports_but_different_dins_never_do(tmp_path):
    res = run(tmp_path, [director(A, "Hanne Sorensen", "08035439")], [fact(B, "kmp", {"person_name": "Ms Hanne Sorensen",
                                                                                         "role": "CEO", "status": "current"})])
    assert people(res) == ["Hanne Sorensen"]
    res = run(tmp_path, [director(A, "Rahul Mehta", "00000001")], [director(B, "Rahul Mehta", "00000002")])
    assert len(people(res)) == 2 and "different DINs" in res.uncertain[0].reason


def test_override_maps_a_name_to_a_din_within_its_report(tmp_path):
    overrides = [{"nse_symbol": "BETA", "fact_type": "director", "from_name": "L. Krishnakumar", "to_din": "00423616"}]
    res = run(tmp_path, [], [director(B, "Mr. Lakshmanan Krishna Kumar", "00423616"),
                             fact(B, "kmp", {"person_name": "L Krishnakumar", "role": "CFO", "status": "ceased"})], overrides)
    assert people(res) == ["Lakshmanan Krishna Kumar"]


def test_same_company_in_different_roles_is_one_node(tmp_path):
    # Jaguar Land Rover: a related party in one report, a subsidiary in the other.
    res = run(tmp_path, [fact(A, "related_party", {"party_name": "Jaguar Land Rover Limited", "nature": "Revenue",
                                                    "amount_inr_crore": 1.0})],
              [fact(B, "subsidiary", {"subsidiary_name": "Jaguar Land Rover Limited", "country": "UK", "stake_pct": 100.0})])
    [jlr] = [e for e in res.entities if e["name"] == "Jaguar Land Rover Limited"]
    assert jlr["reports"] == ["ALPHA", "BETA"] and set(jlr["roles"]) == {"related_party", "subsidiary"}


def test_same_name_in_two_countries_stays_two_companies(tmp_path):
    res = run(tmp_path, [fact(A, "subsidiary", {"subsidiary_name": "Infosys Consulting S.R.L.", "country": "Argentina"}),
                         fact(A, "subsidiary", {"subsidiary_name": "Infosys Consulting S.R.L.", "country": "Romania"}),
                         fact(A, "related_party", {"party_name": "Infosys Consulting S.R.L. (Romania)",
                                                   "nature": "x", "amount_inr_crore": 1.0})], [])
    srl = [e for e in res.entities if e["name"] == "Infosys Consulting S.R.L."]
    assert sorted(e["countries"][0] for e in srl) == ["Argentina", "Romania"]
    assert next(e for e in srl if e["countries"] == ["Romania"])["mentions"] == 2


def test_short_name_merges_but_a_former_name_is_only_listed(tmp_path):
    res = run(tmp_path, [
        fact(A, "subsidiary", {"subsidiary_name": "Infosys Technologies (China) Co. Limited (Infosys China)", "country": "China"}),
        fact(A, "related_party", {"party_name": "Infosys China", "nature": "x", "amount_inr_crore": 1.0}),
        fact(A, "related_party", {"party_name": "TMF Business Services Limited (formerly known as Tata Motors Finance Limited)",
                                  "nature": "x", "amount_inr_crore": 1.0}),
        fact(A, "subsidiary", {"subsidiary_name": "Tata Motors Finance Limited", "country": "India"}),
    ], [])
    names = sorted(e["name"] for e in res.entities if e["type"] == "Company")
    assert "Infosys China" not in names and "Infosys Technologies (China) Co. Limited" in names
    assert {"TMF Business Services Limited", "Tata Motors Finance Limited"} <= set(names)
    assert any("formerly called" in u.reason for u in res.uncertain)


def test_company_overrides_merge_split_merged_into_and_formerly_named(tmp_path):
    overrides = [
        {"nse_symbol": "BETA", "fact_type": "company", "from_name": "Infosys McCamish System LLC",
         "to_name": "Infosys McCamish Systems LLC", "action": "merge"},
        {"nse_symbol": "ALPHA", "fact_type": "company", "from_name": "Saudi Desert Rose Holding B.V.",
         "to_name": "Tata Consultancy Services Netherlands BV", "action": "merged_into", "note": "w.e.f. August 29, 2023"},
        {"nse_symbol": "ALPHA", "fact_type": "company", "from_name": "Jaguar Land Rover Limited",
         "to_name": "Jaguar Cars Limited", "action": "formerly_named"},
    ]
    subs = [fact(A, "subsidiary", {"subsidiary_name": n, "country": None}) for n in
            ["Infosys McCamish Systems LLC", "Saudi Desert Rose Holding B.V.", "Tata Consultancy Services Netherlands BV",
             "Jaguar Land Rover Limited (previously Jaguar Cars Limited)", "Jaguar Cars Limited"]]
    rpt = [fact(B, "related_party", {"party_name": "Infosys McCamish System LLC", "nature": "x", "amount_inr_crore": 1.0})]
    res = run(tmp_path, subs, rpt, overrides)
    names = sorted(e["name"] for e in res.entities if e["type"] == "Company")
    assert "Infosys McCamish System LLC" not in names
    assert "Saudi Desert Rose Holding B.V." in names  # merged into another company, not the same company
    assert [r["note"] for r in res.relations if r["type"] == "MERGED_INTO"] == ["w.e.f. August 29, 2023"]
    assert {"Jaguar Land Rover Limited", "Jaguar Cars Limited"} <= set(names)
    assert [r["former_name"] for r in res.relations if r["type"] == "FORMERLY_NAMED"] == ["Jaguar Cars Limited"]
    assert res.uncertain == []  # the former-name match is decided, so not asked again
    split = [{"nse_symbol": "ALPHA", "fact_type": "company", "from_name": "Alpha Ltd", "to_name": "Alpha Limited",
              "action": "split"}]
    res = run(tmp_path, [fact(A, "related_party", {"party_name": "Alpha Ltd", "nature": "x", "amount_inr_crore": 1.0})], [], split)
    assert sum(e["type"] == "Company" for e in res.entities) == 3  # Alpha, Beta, and the split-off "Alpha Ltd"


def test_two_rows_of_one_subsidiary_list_are_never_merged(tmp_path):
    # Tata Steel's AOC-1 rows 55 and 56: even a merge in merges.csv doesn't join them.
    overrides = [{"nse_symbol": "ALPHA", "fact_type": "company", "from_name": "Norsk Stal Tynnplater AS",
                  "to_name": "Norsk Stal Tynnplater AB", "action": "merge"}]
    subs = [fact(A, "subsidiary", {"subsidiary_name": n, "country": None})
            for n in ["Norsk Stal Tynnplater AS", "Norsk Stal Tynnplater AB"]]
    res = run(tmp_path, subs, [], overrides)
    names = [e["name"] for e in res.entities if e["type"] == "Company"]
    assert "Norsk Stal Tynnplater AS" in names and "Norsk Stal Tynnplater AB" in names
    assert any(r["rule"].startswith("never merged: separate rows of ALPHA") for r in res.log)
    # A different report's mention of one of them still joins it.
    res = run(tmp_path, subs, [fact(B, "related_party", {"party_name": "Norsk Stal Tynnplater AS", "nature": "x",
                                                         "amount_inr_crore": 1.0})])
    [norsk_as] = [e for e in res.entities if e["name"] == "Norsk Stal Tynnplater AS"]
    assert norsk_as["reports"] == ["ALPHA", "BETA"]


def test_status_rule_appointed_and_current_mean_current_only_ceased_means_left():
    assert combined_status(["appointed", "current"], []) == ("current", False)
    assert combined_status(["appointed"], []) == ("current", False)
    assert combined_status(["ceased", "ceased"], ["June 1, 2023"]) == ("ceased", False)
    assert combined_status(["current", "ceased"], ["June 1, 2023"]) == ("ceased", True)
    assert combined_status(["current", "ceased"], []) == ("current", True)
