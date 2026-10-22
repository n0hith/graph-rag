"""Stable entity ids (src/resolve/ids.py): CIN/DIN when present, else an id saved in the
registry and reused on every later run, never given to a different entity."""

from __future__ import annotations

from src.extract.extractor import Fact, save_facts
from src.ingest.companies import Company
from src.resolve.ids import Registry, assign_uids
from src.resolve.merge_entities import apply_uids, resolve

A = Company("Alpha Limited", "ALPHA", "L00000MH2000PLC000001", "https://example.invalid/a.pdf")
B = Company("Beta Limited", "BETA", "L00000MH2000PLC000002", "https://example.invalid/b.pdf")


def fact(company, fact_type, data, page=1):
    return Fact(fact_type, "llm", company.name, company.nse_symbol, "x", page, "FY2023-24", data, "quote")


def sub(company, name, country="UK"):
    return fact(company, "subsidiary", {"subsidiary_name": name, "country": country, "stake_pct": 100.0})


BASE_A = [
    fact(A, "director", {"person_name": "Mr N Chandrasekaran", "din": "00121863", "status": "current"}),
    fact(A, "kmp", {"person_name": "Sivakumar Sivasankaran", "role": "CFO", "status": "current"}),
    sub(A, "Jaguar Land Rover Limited"), sub(A, "Tata Motors Finance Limited", "India"),
    fact(A, "auditor", {"firm_name": "B S R & Co. LLP", "firm_registration_no": "101248W/W-100022", "audit_type": "statutory"}),
    fact(A, "related_party", {"party_name": "Subsidiaries", "nature": "Sales", "amount_inr_crore": 1.0}),
]
BASE_B = [
    fact(B, "director", {"person_name": "N. Chandrasekaran", "din": "00121863", "status": "current"}),
    fact(B, "related_party", {"party_name": "Jaguar Land Rover Limited", "nature": "Revenue", "amount_inr_crore": 2.0}),
]


def run(tmp_path, facts_a, facts_b, overrides=()):
    data = tmp_path / "extracted"
    data.mkdir(exist_ok=True)
    save_facts(data / "ALPHA.jsonl", facts_a)
    save_facts(data / "BETA.jsonl", facts_b)
    res = resolve(data, [A, B], list(overrides))
    registry = Registry.load(tmp_path / "id_registry.csv")
    uids, notes = assign_uids(res.entities, registry, today="2026-10-22")
    registry.save(tmp_path / "id_registry.csv")
    res = apply_uids(res, uids)
    return {e["name"]: e["id"] for e in res.entities}, res, notes


def test_cin_and_din_are_the_ids_when_present(tmp_path):
    ids, _, _ = run(tmp_path, BASE_A, BASE_B)
    assert ids["Alpha Limited"] == "L00000MH2000PLC000001"
    assert ids["N. Chandrasekaran"] == "00121863"
    assert ids["Sivakumar Sivasankaran"].startswith("P-")
    assert ids["Jaguar Land Rover Limited"].startswith("C-")
    assert ids["B S R & Co. LLP"].startswith("F-") and ids["Subsidiaries"].startswith("G-")


def test_resolution_run_twice_keeps_every_id(tmp_path):
    first, res1, _ = run(tmp_path, BASE_A, BASE_B)
    registry_after_first = (tmp_path / "id_registry.csv").read_text(encoding="utf-8")
    second, res2, notes = run(tmp_path, BASE_A, BASE_B)
    assert second == first
    assert [r["from"] + r["to"] for r in res2.relations] == [r["from"] + r["to"] for r in res1.relations]
    assert (tmp_path / "id_registry.csv").read_text(encoding="utf-8") == registry_after_first
    assert notes == []


def test_only_new_entities_get_new_ids_and_ids_survive_reordering(tmp_path):
    first, _, _ = run(tmp_path, BASE_A, BASE_B)
    # New facts, and the old ones in a different order.
    second, _, _ = run(tmp_path, [sub(A, "Tata Hispano Motors Carrocera S.A", "Spain")] + BASE_A[::-1], BASE_B)
    assert {k: v for k, v in second.items() if k in first} == first
    new = set(second.values()) - set(first.values())
    assert new == {second["Tata Hispano Motors Carrocera S.A"]}


def test_an_id_is_never_reused_for_a_different_entity(tmp_path):
    first, _, _ = run(tmp_path, BASE_A, BASE_B)
    jlr = first["Jaguar Land Rover Limited"]
    # JLR disappears from the data, a new company appears: it doesn't inherit JLR's id.
    without = [f for f in BASE_A if "Jaguar" not in str(f.data)]
    second, _, _ = run(tmp_path, without + [sub(A, "Brabo Robotics and Automation Limited", "India")], BASE_B[:1])
    assert jlr not in second.values()
    registry = Registry.load(tmp_path / "id_registry.csv")
    assert registry.rows[jlr].status == "unused"
    # When JLR comes back, it gets its old id again.
    third, _, _ = run(tmp_path, BASE_A, BASE_B)
    assert third["Jaguar Land Rover Limited"] == jlr


def test_two_saved_entities_merged_later_keep_one_id_and_retire_the_other(tmp_path):
    facts_b = BASE_B + [fact(B, "related_party", {"party_name": "Tata AIG General Insurance Limited", "nature": "x",
                                                  "amount_inr_crore": 1.0})]
    facts_a = BASE_A + [fact(A, "related_party", {"party_name": "Tata AIG General Insurance Company Limited",
                                                  "nature": "x", "amount_inr_crore": 1.0})]
    first, _, _ = run(tmp_path, facts_a, facts_b)
    a, b = first["Tata AIG General Insurance Company Limited"], first["Tata AIG General Insurance Limited"]
    override = [{"nse_symbol": "BETA", "fact_type": "company", "from_name": "Tata AIG General Insurance Limited",
                 "to_name": "Tata AIG General Insurance Company Limited", "action": "merge"}]
    second, _, notes = run(tmp_path, facts_a, facts_b, override)
    kept = second["Tata AIG General Insurance Company Limited"]
    assert kept in (a, b)
    retired = ({a, b} - {kept}).pop()
    row = Registry.load(tmp_path / "id_registry.csv").rows[retired]
    assert (row.status, row.replaced_by) == ("retired", kept)
    assert any(retired in n for n in notes)
