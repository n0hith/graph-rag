"""Demo page: answer nodes, supporting sources and baseline citations (plain data, no database)."""

from src.demo.support import GEdge, GNode, GraphData, answer_nodes, cited_sources, supporting_sources


def _directors() -> GraphData:
    """N Chandrasekaran on TCS's and Tata Steel's boards; each fact also repeated in another report."""
    d = GraphData()
    d.nodes = {"p": GNode("p", "N Chandrasekaran", "Person", "00121863", aliases=["N. Chandrasekaran"]),
               "tcs": GNode("tcs", "Tata Consultancy Services Limited", "Company", "CIN-TCS", "TCS"),
               "ts": GNode("ts", "Tata Steel Limited", "Company", "CIN-TS", "TATASTEEL")}
    d.edges = {"e1": GEdge("e1", "p", "tcs", "DIRECTOR_OF", [("TCS", "TCS.pdf", 98), ("TATAMOTORS", "TATAMOTORS.pdf", 236)]),
               "e2": GEdge("e2", "p", "ts", "DIRECTOR_OF", [("TATASTEEL", "TATASTEEL.pdf", 230),
                                                             ("TATACONSUM", "TATACONSUM.pdf", 290)])}
    d.paths = [(["p", "tcs"], ["e1"]), (["p", "ts"], ["e2"])]
    return d


def test_answer_nodes_leave_out_the_question_entities():
    d = _directors()
    ids = answer_nodes(d, "N. Chandrasekaran was on the boards of both TCS and Tata Steel Limited.", {"CIN-TCS", "CIN-TS"})
    assert ids == {"p"}


def test_sources_keep_the_own_report_and_drop_repeats_elsewhere():
    d = _directors()
    assert supporting_sources(d, {"p"}) == ["TCS.pdf p.98", "TATASTEEL.pdf p.230"]


def test_sources_only_from_paths_that_reach_an_answer_node():
    d = _directors()
    d.nodes["q"] = GNode("q", "O P Bhatt", "Person", "00548091")
    d.edges["e3"] = GEdge("e3", "q", "tcs", "DIRECTOR_OF", [("TCS", "TCS.pdf", 99)])
    d.paths.append((["q", "tcs"], ["e3"]))
    assert supporting_sources(d, {"q"}) == ["TCS.pdf p.99"]
    assert "TCS.pdf p.99" in supporting_sources(d, set())  # nothing named (e.g. a count): every path


def test_a_fact_only_other_reports_state_keeps_their_pages():
    d = GraphData(nodes={"a": GNode("a", "Hindustan Unilever Limited", "Company", "X"),
                         "p": GNode("p", "O P Bhatt", "Person", "00548091")},
                  edges={"e": GEdge("e", "p", "a", "DIRECTOR_OF", [("TCS", "TCS.pdf", 98)])},
                  paths=[(["p", "a"], ["e"])])
    assert supporting_sources(d, {"a"}) == ["TCS.pdf p.98"]


def test_baseline_cited_pages_checked_against_retrieved_excerpts():
    answer = ("O. P. Bhatt is on both boards [Tata Consultancy Services Limited, p. 98; Tata Motors Limited, "
              "pp. 248-249] and left Tata Steel [Tata Steel Limited, pp. 233, 500].")
    retrieved = ["TCS.pdf pp.98-99", "TATAMOTORS.pdf pp.248-249", "TATASTEEL.pdf p.233"]
    assert cited_sources(answer, retrieved) == [
        "TCS.pdf p.98", "TATAMOTORS.pdf p.248", "TATAMOTORS.pdf p.249", "TATASTEEL.pdf p.233",
        "TATASTEEL.pdf p.500 (not in the retrieved excerpts)"]


def test_baseline_without_citations_cites_nothing():
    assert cited_sources("The excerpts do not contain the answer.", ["TCS.pdf p.1"]) == []
