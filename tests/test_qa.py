"""Phase 6: the Cypher guard (it must block writes), the router's retries and fallbacks with a
fake model and database, the practice-question scoring, and (with the docker-compose Neo4j
running) entity lookup and read-only execution against the loaded graph."""

from __future__ import annotations

import pytest

from src.qa import answer as answer_mod
from src.qa.answer import answer_question
from src.qa.cypher_guard import CypherRejected, ensure_limit, guard
from src.qa.dev_run import contains, score
from src.qa.entity_lookup import Candidate, EntityMatch, lucene_query
from src.qa.text_to_cypher import CypherPlan

# ---------------------------------------------------------------- guard


@pytest.mark.parametrize("cypher", [
    "CREATE (n:Company {name: 'x'})",
    "MATCH (n) DETACH DELETE n",
    "MATCH (n:Company) SET n.name = 'x' RETURN n",
    "MATCH (n) REMOVE n.name",
    "MERGE (n:Person {uid: '1'}) RETURN n",
    "DROP CONSTRAINT company_uid",
    "LOAD CSV FROM 'file:///x.csv' AS row RETURN row",
    "MATCH (n) FOREACH (x IN [1] | SET n.y = x)",
    "CALL apoc.periodic.iterate('MATCH (n) RETURN n', 'DELETE n', {})",
    "CALL dbms.killQuery('1')",
    "MATCH (n) CALL { WITH n DELETE n } RETURN 1",
    "match (n) delete n",
    "",
])
def test_guard_blocks_writes_and_unknown_procedures(cypher):
    with pytest.raises(CypherRejected):
        guard(cypher)


def test_guard_ignores_keywords_inside_strings_and_allows_read_procedures():
    g = guard("MATCH (c:Company {name: 'Merge Set Delete Ltd'}) RETURN c.name // create nothing")
    assert g.cypher.endswith("LIMIT 100")
    guard("CALL db.index.fulltext.queryNodes('entity_names', 'tata') YIELD node RETURN node")


def test_limit_is_added_only_when_missing():
    assert ensure_limit("MATCH (n) RETURN n LIMIT 5;").limit_added is False
    added = ensure_limit("MATCH (n) RETURN count(n)")
    assert added.limit_added and added.cypher.endswith("\nLIMIT 100")


# ---------------------------------------------------------------- router (fake model and database)


class FakeClient:
    def __init__(self, answer="The answer."):
        self.answer = answer

    def generate_text(self, prompt, **kwargs):
        return self.answer


class FakeRunner:
    def __init__(self, results):
        self.results = list(results)  # one per run(): a list of records, or an Exception
        self.ran = []

    def explain(self, cypher):
        if "SYNTAX ERROR" in cypher:
            raise ValueError("Invalid input 'ERROR'")

    def run(self, cypher):
        self.ran.append(cypher)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def setup(monkeypatch, entities, plans, results):
    plans = list(plans)
    seen_previous = []

    def fake_generate(client, question, ents, previous=()):
        seen_previous.append(list(previous))
        return plans.pop(0)

    runner = FakeRunner(results)
    monkeypatch.setattr(answer_mod, "lookup_entities", lambda client, driver, q, db=None: entities)
    monkeypatch.setattr(answer_mod, "generate_cypher", fake_generate)
    monkeypatch.setattr(answer_mod, "ReadOnlyRunner", lambda driver, db=None: runner)
    return runner, seen_previous


def baseline(question):
    return "baseline answer", ["TCS.pdf p.90"]


TATA = EntityMatch("TaMo", "resolved", Candidate("L28920MH1945PLC004520", "Company", "Tata Motors Limited"), how="pilot")


def test_ambiguous_name_stops_and_lists_the_candidates(monkeypatch):
    ambiguous = EntityMatch("Krishnakumar", "ambiguous", candidates=[
        Candidate("08002754", "Person", "Ajit Krishnakumar"), Candidate("00423616", "Person", "Lakshmanan Krishna Kumar")])
    setup(monkeypatch, [ambiguous], [], [])
    result = answer_question("What role does Krishnakumar hold?", FakeClient(), None, baseline)
    assert result.route == "clarify" and result.cypher is None
    assert "Ajit Krishnakumar" in result.answer and "Lakshmanan Krishna Kumar" in result.answer


def test_prose_question_goes_to_the_baseline(monkeypatch):
    setup(monkeypatch, [], [CypherPlan(answerable_from_graph=False, reason="headcount is prose")], [])
    result = answer_question("How many employees?", FakeClient(), None, baseline)
    assert (result.route, result.answer, result.sources) == ("baseline", "baseline answer", ["TCS.pdf p.90"])


def test_rejected_write_and_syntax_error_are_retried_with_the_error(monkeypatch):
    plans = [CypherPlan(answerable_from_graph=True, reason="", cypher="MATCH (n) DELETE n"),
             CypherPlan(answerable_from_graph=True, reason="", cypher="MATCH SYNTAX ERROR"),
             CypherPlan(answerable_from_graph=True, reason="", cypher="MATCH (n) RETURN n.name AS name")]
    runner, seen = setup(monkeypatch, [TATA], plans, [[{"name": "Tata Motors Limited"}]])
    result = answer_question("q", FakeClient("Tata Motors Limited."), None, baseline)
    assert result.route == "graph" and result.cypher.endswith("LIMIT 100")
    assert "rejected: write operation not allowed: DELETE" in seen[1][0][1]
    assert "Invalid input" in seen[2][1][1]
    assert runner.ran == ["MATCH (n) RETURN n.name AS name\nLIMIT 100"]  # nothing else reached the database


def test_empty_result_is_retried_then_falls_back(monkeypatch):
    plans = [CypherPlan(answerable_from_graph=True, reason="", cypher=f"MATCH (n) RETURN n LIMIT {i}") for i in (1, 2, 3)]
    runner, seen = setup(monkeypatch, [TATA], plans, [[], [], []])
    result = answer_question("q", FakeClient(), None, baseline)
    assert result.route == "baseline" and len(runner.ran) == 3
    assert "returned no rows" in seen[1][0][1]


def test_failing_query_falls_back_after_two_retries(monkeypatch):
    plans = [CypherPlan(answerable_from_graph=True, reason="", cypher="MATCH (n) RETURN n LIMIT 1")] * 3
    runner, _ = setup(monkeypatch, [TATA], plans, [RuntimeError("timeout")] * 3)
    result = answer_question("q", FakeClient(), None, baseline)
    assert result.route == "baseline" and "graph query failed after retries" in result.notes


# ---------------------------------------------------------------- practice-question scoring and lookup helpers


def test_scoring_matches_numbers_without_separators_and_checks_route():
    assert contains("TCS had 6,01,546 employees", "601,546") and not contains("FY2024", "9")
    assert contains("There were 9 directors", "9")
    q = {"expected_route": "graph", "must_contain": ["Price Waterhouse"], "must_not_contain": ["Deloitte"]}
    ok = answer_mod.QAResult("q", "Price Waterhouse & Co", "graph")
    assert score(q, ok).passed
    assert score(q, answer_mod.QAResult("q", "Price Waterhouse", "baseline")).problems == ["route baseline, expected graph"]


def test_lucene_query_escapes_and_fuzzes_long_words():
    assert lucene_query("Al-Noor Ramji") == r"Al\-Noor~ AND Ramji~"
    assert lucene_query("TCS") == "TCS"


# ---------------------------------------------------------------- live graph (skipped without Neo4j)


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


@pytest.mark.parametrize("mention, status, name", [
    ("TaMo", "resolved", "Tata Motors Limited"),
    ("Tata Motors", "resolved", "Tata Motors Limited"),
    ("Chandrasekaran", "resolved", "N. Chandrasekaran"),
    ("Neelachal lspat", "resolved", "Neelachal Ispat Nigam Limited"),
    ("Krishnakumar", "ambiguous", None),
    ("JLR", "ambiguous", None),
    ("Acme Widgets", "not_found", None),
])
def test_entity_lookup_on_the_loaded_graph(driver, mention, status, name):
    from src.qa.entity_lookup import resolve_mention

    match = resolve_mention(driver, mention)
    assert match.status == status
    if name:
        assert match.node.name == name


def test_database_refuses_writes_in_the_read_only_runner(driver):
    from src.qa.cypher_guard import ReadOnlyRunner

    with pytest.raises(Exception, match="(?i)read access|not allowed"):
        ReadOnlyRunner(driver).run("CREATE (n:GuardTest) RETURN n")
    assert driver.execute_query("MATCH (n:GuardTest) RETURN count(n) AS n").records[0]["n"] == 0
