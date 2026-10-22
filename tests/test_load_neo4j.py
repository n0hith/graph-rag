"""Phase 5 loading (src/graph/load_neo4j.py). Row building is tested without a database; the
load-twice test needs the docker-compose Neo4j and is skipped when it isn't running. It loads
a small graph under its own `dataset` and uid prefix, so the real graph is not touched."""

from __future__ import annotations

import pytest

from src.graph.load_neo4j import graph_counts, load_graph, node_rows, relation_rows


def src(page=1, evidence="quote", doc="ALPHA.pdf"):
    return {"source_doc": doc, "page": page, "evidence": evidence, "fy": "FY2023-24", "reported_by": "ALPHA"}


ENTITIES = [
    {"id": "PYTEST-CIN-1", "type": "Company", "name": "Alpha Limited", "aliases": ["Alpha Limited", "Alpha Ltd"],
     "nse_symbol": "PYTESTALPHA", "reports": ["ALPHA"]},
    {"id": "PYTEST-C-1", "type": "Company", "name": "Jaguar Land Rover Limited", "aliases": ["Jaguar Land Rover Limited"],
     "countries": ["UK"], "reports": ["ALPHA"]},
    {"id": "PYTEST-P-1", "type": "Person", "name": "N. Chandrasekaran", "aliases": ["N Chandrasekaran"], "reports": ["ALPHA"]},
    {"id": "PYTEST-G-1", "type": "RelatedPartyGroup", "name": "Subsidiaries", "reported_by": "ALPHA", "aliases": ["Subsidiaries"]},
    {"id": "PYTEST-F-1", "type": "AuditFirm", "name": "B S R & Co. LLP", "aliases": ["B S R & Co. LLP"]},
]
RELATIONS = [
    {"type": "DIRECTOR_OF", "from": "PYTEST-P-1", "to": "PYTEST-CIN-1", "status": "current", "roles": ["Chairman"],
     "own_report": True, "din_conflict": {"certificate_din": "x"}, "sources": [src(98), src(117, "certificate")]},
    {"type": "SUBSIDIARY_OF", "from": "PYTEST-C-1", "to": "PYTEST-CIN-1", "stake_pct": 100.0, "sources": [src(477)]},
    {"type": "RELATED_PARTY_TXN", "from": "PYTEST-CIN-1", "to": "PYTEST-G-1", "nature": "Sales", "amount_inr_crore": 1.0,
     "amount_as_printed": "1.00", "sources": [src(423)]},
    {"type": "RELATED_PARTY_TXN", "from": "PYTEST-CIN-1", "to": "PYTEST-G-1", "nature": "Rent", "amount_inr_crore": 2.0,
     "amount_as_printed": "2.00", "sources": [src(423)]},
    {"type": "AUDITED_BY", "from": "PYTEST-CIN-1", "to": "PYTEST-F-1", "audit_type": "statutory", "sources": [src(245)]},
]
LABEL_OF = {e["id"]: e["type"] for e in ENTITIES}


def test_sources_become_parallel_lists_and_maps_become_json():
    rows = relation_rows(RELATIONS, LABEL_OF)
    [director] = rows[("DIRECTOR_OF", "Person", "Company")]
    assert director["props"]["page"] == [98, 117]
    assert director["props"]["evidence"] == ["quote", "certificate"]
    assert director["props"]["source_doc"] == ["ALPHA.pdf", "ALPHA.pdf"]
    assert director["props"]["din_conflict"] == '{"certificate_din": "x"}'
    assert len(rows[("RELATED_PARTY_TXN", "Company", "RelatedPartyGroup")]) == 2  # different natures: two relations
    company = next(r for r in node_rows(ENTITIES)["Company"] if r["uid"] == "PYTEST-CIN-1")
    assert company["props"]["aliases_text"] == "Alpha Limited | Alpha Ltd"


def test_a_relation_without_a_page_or_a_duplicate_key_is_refused():
    with pytest.raises(ValueError, match="source"):
        relation_rows([{**RELATIONS[1], "sources": [src(None)]}], LABEL_OF)
    with pytest.raises(ValueError, match="share the key"):
        relation_rows([RELATIONS[2], RELATIONS[2]], LABEL_OF)


@pytest.fixture
def driver():
    neo4j = pytest.importorskip("neo4j")
    from src.config import get_settings

    settings = get_settings()
    try:
        drv = neo4j.GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user,
                                                                   settings.neo4j_password.get_secret_value()))
        drv.verify_connectivity()
    except Exception as exc:  # no database running: nothing to test against
        pytest.skip(f"Neo4j not reachable: {exc}")
    yield drv
    drv.execute_query("MATCH (n) WHERE n.dataset = 'pytest' DETACH DELETE n")
    drv.close()


def test_loading_twice_creates_no_duplicates_and_prunes_removed_facts(driver):
    load_graph(driver, ENTITIES, RELATIONS, dataset="pytest")
    first = graph_counts(driver, dataset="pytest")
    assert first == ({"AuditFirm": 1, "Company": 2, "Person": 1, "RelatedPartyGroup": 1},
                     {"AUDITED_BY": 1, "DIRECTOR_OF": 1, "RELATED_PARTY_TXN": 2, "SUBSIDIARY_OF": 1})
    second_load = load_graph(driver, ENTITIES, RELATIONS, dataset="pytest")
    assert graph_counts(driver, dataset="pytest") == first
    assert (second_load["pruned_nodes"], second_load["pruned_relationships"]) == (0, 0)
    [record] = driver.execute_query(
        "MATCH (:Person {uid: 'PYTEST-P-1'})-[d:DIRECTOR_OF]->(:Company {uid: 'PYTEST-CIN-1'}) "
        "RETURN d.page AS page, d.status AS status").records
    assert (record["page"], record["status"]) == ([98, 117], "current")
    # A fact gone from the data disappears from the graph on the next load.
    third_load = load_graph(driver, ENTITIES, RELATIONS[:-1], dataset="pytest")
    assert third_load["pruned_relationships"] == 1
    assert "AUDITED_BY" not in graph_counts(driver, dataset="pytest")[1]
