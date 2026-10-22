"""Question -> Cypher with GEMINI_QA_MODEL, using the schema, rules and examples from
src/graph/schema_info.py and the uids the entity lookup found. The model may instead say the
question can't be answered from the graph (prose questions), which routes it to the baseline.
On a retry the previous query and the error it caused are added to the prompt."""

from __future__ import annotations

from pydantic import BaseModel

from src.graph.schema_info import describe_examples, describe_schema
from src.llm.client import LLMClient
from src.qa.entity_lookup import EntityMatch

SYSTEM = ("You translate questions about Indian companies' FY2023-24 annual reports into one read-only Cypher "
          "query for Neo4j 5, following the schema and rules exactly.")


class CypherPlan(BaseModel):
    answerable_from_graph: bool
    reason: str
    cypher: str | None = None


def _entity_block(entities: list[EntityMatch]) -> str:
    resolved = [e for e in entities if e.status == "resolved"]
    lines = [f"- '{e.mention}' = {e.node.label} '{e.node.name}' uid '{e.node.uid}'"
             + (f" ({e.node.detail})" if e.node.detail else "") for e in resolved]
    missing = [e.mention for e in entities if e.status == "not_found"]
    if missing:
        lines.append(f"- not in the graph: {', '.join(repr(m) for m in missing)}")
    return "\n".join(lines) or "- none named"


def build_prompt(question: str, entities: list[EntityMatch], previous: list[tuple[str, str]] = ()) -> str:
    parts = [describe_schema(), "", "Examples:", describe_examples(), "",
             "Entities named in the question (use these uids):", _entity_block(entities)]
    for cypher, error in previous:
        parts += ["", "Your previous query failed. Fix it.", f"Query: {cypher}", f"Error: {error}"]
    parts += ["", f"Question: {question}", "",
              "Reply with answerable_from_graph, a one-sentence reason, and the Cypher (null if not answerable)."]
    return "\n".join(parts)


def generate_cypher(client: LLMClient, question: str, entities: list[EntityMatch],
                    previous: list[tuple[str, str]] = ()) -> CypherPlan:
    return client.generate_structured(build_prompt(question, entities, previous), CypherPlan, system=SYSTEM,
                                      temperature=0.0, step="qa.cypher")
