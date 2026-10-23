"""Phase 6 router: try the graph first, fall back to the baseline.

1. Look up the names in the question (src/qa/entity_lookup.py). If a name fits several nodes,
   stop and say which, instead of guessing.
2. Generate Cypher (src/qa/text_to_cypher.py). If the model says the graph can't answer it (a
   question about prose), go to the baseline.
3. Guard it (no writes, LIMIT, read-only session, timeout), EXPLAIN it, run it. A rejected,
   invalid or failing query is regenerated with the error, up to MAX_RETRIES times.
4. No rows, or still failing: baseline. Otherwise the QA model words the answer from the rows
   only, and the paths and sources (document + page) are read off the returned paths.

Every result carries: the answer, the route, the Cypher, the path(s) and the sources.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Callable

from neo4j.graph import Node, Path, Relationship

from src.llm.client import LLMClient, StructuredOutputError
from src.qa.cypher_guard import CypherRejected, ReadOnlyRunner, guard
from src.qa.entity_lookup import EntityMatch, lookup_entities
from src.qa.text_to_cypher import generate_cypher

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
MAX_ROWS_FOR_ANSWER = 40
MAX_SOURCES = 20

ANSWER_SYSTEM = (
    "You answer a question about Indian companies' FY2023-24 annual reports using only the query results "
    "given (rows from a graph built from those reports). Rules: use only the rows; never add outside "
    "knowledge; name every entity the rows give as the answer; mention status (current / ceased) and dates "
    "when the rows have them; for a count, give the number and list the items only if the question asks for "
    "them; if the rows don't answer the question, say so. Answer directly (no 'Based on the query results'). "
    "Be concise: a sentence or a short list."
)


@dataclass
class QAResult:
    question: str
    answer: str
    route: str  # graph | baseline | clarify (a name fits several nodes)
    cypher: str | None = None
    paths: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    entities: list[EntityMatch] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    records: list = field(default_factory=list, repr=False)  # the raw Neo4j records, for the demo's graph view


# ---------------------------------------------------------------- reading results


def _node_name(n: Node) -> str:
    return n.get("name") or n.get("uid") or "?"


def format_path(p: Path) -> str:
    text = _node_name(p.nodes[0])
    for i, rel in enumerate(p.relationships):
        a, b = p.nodes[i], p.nodes[i + 1]
        forward = rel.start_node is not None and rel.start_node.element_id == a.element_id
        text += f" -[{rel.type}]-> " if forward else f" <-[{rel.type}]- "
        text += _node_name(b)
    return text


def _walk(value, paths: list[Path], rels: list[Relationship]) -> None:
    if isinstance(value, Path):
        paths.append(value)
        rels.extend(value.relationships)
    elif isinstance(value, Relationship):
        rels.append(value)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _walk(v, paths, rels)
    elif isinstance(value, dict):
        for v in value.values():
            _walk(v, paths, rels)


def paths_and_sources(records) -> tuple[list[str], list[str]]:
    paths: list[Path] = []
    rels: list[Relationship] = []
    for record in records:
        for value in record.values():
            _walk(value, paths, rels)
    path_text = list(dict.fromkeys(format_path(p) for p in paths))
    sources = []
    for rel in rels:
        for doc, page in zip(rel.get("source_doc") or [], rel.get("page") or []):
            sources.append(f"{doc} p.{page}")
    return path_text, list(dict.fromkeys(sources))[:MAX_SOURCES]


def _plain(value):
    """A row value as JSON-friendly data for the answer prompt (paths as text)."""
    if isinstance(value, Path):
        return format_path(value)
    if isinstance(value, Node):
        return {k: value.get(k) for k in ("name", "uid", "nse_symbol", "din") if value.get(k) is not None}
    if isinstance(value, Relationship):
        return {"type": value.type, **{k: v for k, v in value.items()
                                       if k not in ("evidence", "source_doc", "page", "reported_by", "load_id", "dataset")}}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


def plain_rows(records) -> list[dict]:
    return [{k: _plain(v) for k, v in r.items()} for r in records]


# ---------------------------------------------------------------- router


def _clarify(question: str, entities: list[EntityMatch]) -> QAResult:
    parts = []
    for e in entities:
        if e.status == "ambiguous":
            options = "; ".join(c.describe() for c in e.candidates)
            parts.append(f"'{e.mention}' matches several entries in the graph: {options}.")
    return QAResult(question, " ".join(parts) + " Which one do you mean?", "clarify", entities=entities,
                    notes=["stopped before writing Cypher: ambiguous name"])


def answer_question(question: str, client: LLMClient, driver,
                    baseline: Callable[[str], tuple[str, list[str]]] | None = None,
                    database: str | None = None) -> QAResult:
    """Answer `question`, graph first. `baseline(question) -> (answer, sources)` is the fallback."""
    entities = lookup_entities(client, driver, question, database)
    if any(e.status == "ambiguous" for e in entities):
        return _clarify(question, entities)

    runner = ReadOnlyRunner(driver, database)
    notes: list[str] = [f"'{e.mention}' -> {e.node.name} ({e.how})" for e in entities if e.status == "resolved"]
    notes += [f"'{e.mention}' is not in the graph" for e in entities if e.status == "not_found"]
    previous: list[tuple[str, str]] = []
    cypher = None
    records = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            plan = generate_cypher(client, question, entities, previous)
        except StructuredOutputError as exc:
            previous.append(("(no valid reply)", str(exc)))
            continue
        if not plan.answerable_from_graph or not plan.cypher:
            notes.append(f"graph can't answer it: {plan.reason}")
            return _fallback(question, baseline, notes, entities, None)
        try:
            guarded = guard(plan.cypher)
            cypher = guarded.cypher
            runner.explain(cypher)
            records = runner.run(cypher)
        except CypherRejected as exc:
            previous.append((plan.cypher, f"rejected: {exc}"))
        except Exception as exc:  # syntax error, unknown property type, timeout: retry with the message
            previous.append((plan.cypher, " ".join(str(exc).split())[:500]))
        else:
            if records or attempt == MAX_RETRIES:
                if guarded.limit_added:
                    notes.append("LIMIT added by the guard")
                break
            # No rows is often a reversed relationship or an over-strict filter: try again.
            previous.append((plan.cypher, "the query ran but returned no rows; check relationship directions "
                                          "and filters"))
        notes.append(f"attempt {attempt + 1} failed: {previous[-1][1][:160]}")
    if records is None:
        return _fallback(question, baseline, notes + ["graph query failed after retries"], entities,
                         previous[-1][0] if previous else None)
    if not records:
        return _fallback(question, baseline, notes + ["graph query returned no rows"], entities, cypher)

    rows = plain_rows(records)
    paths, sources = paths_and_sources(records)
    prompt = (f"Question: {question}\n\nQuery results ({len(rows)} rows):\n"
              f"{json.dumps(rows[:MAX_ROWS_FOR_ANSWER], ensure_ascii=False, default=str)}\n\nAnswer:")
    answer = client.generate_text(prompt, system=ANSWER_SYSTEM, temperature=0.0, step="qa.answer").strip()
    return QAResult(question, answer, "graph", cypher, paths, sources, entities, notes, rows, list(records))


def _fallback(question: str, baseline, notes: list[str], entities, cypher) -> QAResult:
    if baseline is None:
        return QAResult(question, "The graph can't answer this and no baseline is available.", "graph", cypher,
                        entities=entities, notes=notes)
    answer, sources = baseline(question)
    return QAResult(question, answer, "baseline", cypher, [], sources, entities, notes)
