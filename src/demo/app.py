"""Phase 8 demo page: ask a question, answered by the graph (with its fallback), the baseline, or both.

Run with `streamlit run src/demo/app.py`. It reuses the Phase 6 pipeline unchanged
(src/qa/answer.py for the graph route, the CLI's baseline answerer), so answers match `ask`.

Read-only: the page itself sends no queries. The pipeline's only database access is the fixed entity
lookups and the generated Cypher, which goes through cypher_guard and runs in READ_ACCESS sessions.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # streamlit puts the script's folder on the path, not the project root
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402
from google.genai.errors import APIError  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

from src.cli import _baseline_answerer  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.demo.support import (COLOURS, answer_nodes, cited_sources, graph_data, render_html,  # noqa: E402
                              supporting_sources)
from src.llm.client import LLMError, build_client  # noqa: E402
from src.llm.rate_limiter import DailyLimitReached  # noqa: E402
from src.qa.answer import QAResult, answer_question  # noqa: E402

# One of each kind the graph handles: lookup, 2-hop, 3-hop, count, and a question with no answer.
EXAMPLES = [
    ("Lookup", "Who is the statutory auditor of Tata Steel?"),
    ("2-hop", "Which directors were on the boards of both TCS and Tata Steel on March 31, 2024?"),
    ("3-hop", "Hanne Sorensen sits on the boards of two pilot companies. Who are the Chief Financial Officers "
              "of those companies?"),
    ("Count", "How many subsidiaries does Tata Steel list in its Form AOC-1?"),
    ("No answer", "What is the CIN of Tata Consultancy Services Japan, Ltd.?"),
]
MODES = ("Graph", "Baseline", "Both")
ROUTE_LABELS = {"graph": "graph", "baseline": "baseline (plain RAG over the report text)",
                "clarify": "clarify (a name matches several entries)"}
ROUTE_BADGES = {"graph": ("green", ":material/hub:"), "baseline": ("orange", ":material/description:"),
                "clarify": ("gray", ":material/help:")}
GRAPH_HEIGHT = 620
LEGEND = (f'<span style="font-size:0.85em;opacity:0.85">'
          f'<span style="color:{COLOURS["answer"]}">●</span> answer &nbsp; '
          f'<span style="color:{COLOURS["question"]}">●</span> from your question &nbsp; '
          f'<span style="color:{COLOURS["other"]}">●</span> other &nbsp;·&nbsp; hover for details, '
          f'scroll to zoom, drag to pan</span>')


@st.cache_resource
def _resources():
    """The QA client, the Neo4j driver and the baseline answerer, built once per server."""
    settings = get_settings()
    client = build_client(settings, purpose="qa")
    auth = (settings.neo4j_user, settings.neo4j_password.get_secret_value())
    driver = GraphDatabase.driver(settings.neo4j_uri, auth=auth, notifications_min_severity="WARNING")
    return client, driver, _baseline_answerer(settings, client)


def _ask(question: str, mode: str) -> dict[str, QAResult]:
    client, driver, baseline = _resources()
    results = {}
    if mode in ("Graph", "Both"):
        results["Graph"] = answer_question(question, client, driver, baseline)
    if mode in ("Baseline", "Both"):
        answer, sources = baseline(question)
        results["Baseline"] = QAResult(question, answer, "baseline", sources=sources)
    return results


def _source_lines(sources: list[str]) -> list[str]:
    """'TATASTEEL.pdf pp.211-212' -> 'TATASTEEL.pdf, pages 211-212'."""
    lines = []
    for s in sources:
        m = re.match(r"(\S+\.pdf) pp?\.(\S+)(.*)", s)
        lines.append(f"{m.group(1)}, page{'s' if '-' in m.group(2) else ''} {m.group(2)}{m.group(3)}" if m else s)
    return lines


def _show(title: str, result: QAResult) -> None:
    st.subheader(title)
    colour, icon = ROUTE_BADGES.get(result.route, ("gray", None))
    st.badge(f"Route: {ROUTE_LABELS.get(result.route, result.route)}", color=colour, icon=icon)
    st.markdown(result.answer)
    data = answer_ids = None
    if result.route == "graph" and result.records:
        data = graph_data(result.records)
        entity_uids = {e.node.uid for e in result.entities if e.status == "resolved" and e.node}
        answer_ids = answer_nodes(data, result.answer, entity_uids)
        sources = supporting_sources(data, answer_ids)
    elif result.route == "baseline":
        sources = cited_sources(result.answer, result.sources)
    else:
        sources = result.sources
    if sources:
        st.markdown("**Sources** (PDF page numbers):")
        st.markdown("\n".join(f"- {line}" for line in _source_lines(sources)))
    else:
        st.markdown("**Sources:** none")
    if data is not None and data.paths:
        question_ids = {n.id for n in data.nodes.values()
                        if n.uid in {e.node.uid for e in result.entities if e.node}}
        st.markdown("**Graph paths**")
        st.markdown(LEGEND, unsafe_allow_html=True)
        st.iframe(render_html(data, answer_ids, question_ids), width="stretch", height=GRAPH_HEIGHT)
        if data.truncated:
            st.caption(f"Showing {len(data.paths)} paths; {data.truncated} more not drawn.")
    if result.cypher:
        label = "Generated Cypher" if result.route == "graph" else "Generated Cypher (not used: fell back to the baseline)"
        with st.expander(label):
            st.code(result.cypher, language="cypher")


def main() -> None:
    st.set_page_config(page_title="Graph RAG demo", layout="wide")
    st.title("Graph RAG vs plain RAG")
    st.caption("Questions about the FY2023-24 annual reports of TCS, Tata Motors, Tata Steel, Tata Consumer "
               "Products and Infosys. Graph: Cypher over the knowledge graph, falling back to the baseline "
               "when the graph can't answer. Baseline: hybrid search over the report text.")

    st.session_state.setdefault("question", "")
    st.write("**Examples**")
    cols = st.columns(len(EXAMPLES))
    clicked = None
    for col, (label, question) in zip(cols, EXAMPLES):
        if col.button(label, help=question, use_container_width=True):
            st.session_state["question"] = question
            clicked = question

    question = st.text_input("Question", key="question")
    mode = st.radio("System", MODES, horizontal=True, index=2)
    asked = st.button("Ask", type="primary") or clicked
    if not (asked and question.strip()):
        return
    with st.spinner("Answering...", show_time=True):
        try:
            results = _ask(question.strip(), mode)
        except DailyLimitReached as exc:
            st.error(f"The daily API quota is used up; try again after it resets. ({exc})")
            return
        except (APIError, LLMError) as exc:
            st.error(f"The model call failed: {exc}")
            return
    cols = st.columns(len(results))
    for col, (title, result) in zip(cols, results.items()):
        with col, st.container(border=True):
            _show(title, result)


main()
