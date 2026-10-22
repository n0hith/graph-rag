"""The schema text Phase 6 prompts with (src/graph/schema_info.py) matches what the loader
loads, and every example query runs on the loaded pilot graph (skipped without Neo4j)."""

from __future__ import annotations

import pytest

from src.graph.load_neo4j import LABELS, REL_PROPS
from src.graph.schema_info import EXAMPLES, RELATIONSHIPS, describe_examples, describe_schema


def test_schema_text_covers_every_label_and_relationship_the_loader_writes():
    text = describe_schema()
    for label in LABELS:
        assert f"- {label} {{uid" in text
    assert {r[0] for r in RELATIONSHIPS} == set(REL_PROPS)
    for rtype in REL_PROPS:
        assert f"[:{rtype}" in text
    assert describe_examples().count("Cypher: ") == len(EXAMPLES)


@pytest.fixture
def driver():
    neo4j = pytest.importorskip("neo4j")
    from src.config import get_settings

    settings = get_settings()
    try:
        drv = neo4j.GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user,
                                                                   settings.neo4j_password.get_secret_value()))
        drv.verify_connectivity()
        if not drv.execute_query("MATCH (c:Company {dataset: 'pilot'}) RETURN count(c) AS n").records[0]["n"]:
            pytest.skip("pilot graph not loaded")
    except Exception as exc:
        pytest.skip(f"Neo4j not reachable: {exc}")
    yield drv
    drv.close()


@pytest.mark.parametrize("question, cypher", EXAMPLES)
def test_example_queries_run_and_return_rows(driver, question, cypher):
    records = driver.execute_query(cypher).records
    assert records, question
