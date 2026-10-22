"""Phase 5: load the resolved graph (data/resolved/entities.jsonl, relations.jsonl) into Neo4j.

Constraints and indexes come first. Nodes are MERGEd on their stable `uid` (CIN, DIN, or the
id saved in data/resolved/id_registry.csv) and relationships on their natural key (type, both
ends, and e.g. `role` for KMP_OF, `nature` + `amount_as_printed` for RELATED_PARTY_TXN), so
loading twice changes nothing. Everything loaded is stamped with `dataset` and `load_id`; after
a load, nodes and relationships of the same dataset that the load didn't touch (facts since
removed) are deleted, so the graph always equals the resolved data.

Neo4j properties can't hold maps or lists of maps, so each relationship's sources become
parallel lists: `source_doc[i]`, `page[i]`, `evidence[i]`, `reported_by[i]` describe source i.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from pathlib import Path

from src.resolve.merge_entities import RELATION_KEY

logger = logging.getLogger(__name__)

LABELS = ("Company", "Person", "AuditFirm", "RelatedPartyGroup")
SCHEMA_STATEMENTS = [
    *(f"CREATE CONSTRAINT {label.lower()}_uid IF NOT EXISTS FOR (n:{label}) REQUIRE n.uid IS UNIQUE" for label in LABELS),
    "CREATE CONSTRAINT company_cin IF NOT EXISTS FOR (n:Company) REQUIRE n.cin IS UNIQUE",
    "CREATE CONSTRAINT person_din IF NOT EXISTS FOR (n:Person) REQUIRE n.din IS UNIQUE",
    "CREATE INDEX company_name_normalized IF NOT EXISTS FOR (n:Company) ON (n.name_normalized)",
    "CREATE INDEX person_name_normalized IF NOT EXISTS FOR (n:Person) ON (n.name_normalized)",
    "CREATE INDEX company_nse_symbol IF NOT EXISTS FOR (n:Company) ON (n.nse_symbol)",
    *(f"CREATE INDEX {label.lower()}_dataset IF NOT EXISTS FOR (n:{label}) ON (n.dataset)" for label in LABELS),
    # Phase 6 maps names in questions ("TaMo", "Chandrasekaran") to nodes with this.
    "CREATE FULLTEXT INDEX entity_names IF NOT EXISTS FOR (n:Company|Person|AuditFirm|RelatedPartyGroup) "
    "ON EACH [n.name, n.aliases_text]",
]

NODE_PROPS = {
    "Company": ("name", "name_normalized", "cin", "nse_symbol", "countries", "aliases", "former_names", "reports"),
    "Person": ("name", "name_normalized", "din", "dins", "aliases", "reports"),
    "AuditFirm": ("name", "firm_registration_no", "aliases", "reports"),
    "RelatedPartyGroup": ("name", "reported_by", "anchor", "aliases", "reports"),
}
# Relationship properties besides the sources; maps are stored as JSON text.
REL_PROPS = {
    "DIRECTOR_OF": ("roles", "is_independent", "is_executive", "status", "status_conflict", "appointed_on", "ceased_on",
                    "categories", "after_fy_end", "own_report", "din_conflict", "din_resolution"),
    "KMP_OF": ("role", "status", "status_conflict", "appointed_on", "ceased_on", "date_conflict"),
    "SUBSIDIARY_OF": ("stake_pct",),
    "AUDITED_BY": ("audit_type", "firm_registration_no"),
    "RELATED_PARTY_TXN": ("nature", "amount_inr_crore", "amount_as_printed"),
    "GROUP_OF": (),
    "MERGED_INTO": ("note",),
    "FORMERLY_NAMED": ("former_name", "note"),
}


def _value(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, dict) else v


def node_rows(entities: list[dict]) -> dict[str, list[dict]]:
    """Rows per label: {uid, props}."""
    rows = defaultdict(list)
    for e in entities:
        props = {k: _value(e.get(k)) for k in NODE_PROPS[e["type"]] if e.get(k) not in (None, [], "")}
        props["aliases_text"] = " | ".join(e.get("aliases", []))
        rows[e["type"]].append({"uid": e["id"], "props": props})
    return rows


def relation_rows(relations: list[dict], label_of: dict[str, str]) -> dict[tuple[str, str, str], list[dict]]:
    """Rows per (type, from label, to label): {from, to, key (MERGE properties), props}."""
    rows = defaultdict(list)
    seen = set()
    for r in relations:
        key = {k: r.get(k) if r.get(k) is not None else "" for k in RELATION_KEY[r["type"]]}
        ident = (r["type"], r["from"], r["to"], *key.values())
        if ident in seen:
            raise ValueError(f"two relations share the key {ident}; resolution should have folded them")
        seen.add(ident)
        sources = r["sources"]
        if not sources or any(s.get("page") is None for s in sources):
            raise ValueError(f"relation without a full source (doc, page, evidence): {ident}")
        props = {k: _value(r.get(k)) for k in REL_PROPS[r["type"]] if r.get(k) not in (None, [], "")}
        props.update(source_doc=[s["source_doc"] for s in sources], page=[int(s["page"]) for s in sources],
                     evidence=[" ".join(s["evidence"].split()) for s in sources],
                     reported_by=[s.get("reported_by") or "" for s in sources],
                     fy=sorted({s["fy"] for s in sources if s.get("fy")})[0] if any(s.get("fy") for s in sources) else None)
        rows[(r["type"], label_of[r["from"]], label_of[r["to"]])].append(
            {"from": r["from"], "to": r["to"], "key": key, "props": {k: v for k, v in props.items() if v is not None}})
    return rows


def load_resolved(resolved_dir: Path) -> tuple[list[dict], list[dict]]:
    def read(name):
        return [json.loads(line) for line in (resolved_dir / name).read_text(encoding="utf-8").splitlines() if line.strip()]
    return read("entities.jsonl"), read("relations.jsonl")


def load_graph(driver, entities: list[dict], relations: list[dict], dataset: str = "pilot",
               database: str | None = None, batch: int = 500) -> dict:
    """Create constraints/indexes, MERGE every node and relationship, then delete what this
    dataset had and this load didn't touch. Returns counts of what was pruned."""
    load_id = uuid.uuid4().hex
    for statement in SCHEMA_STATEMENTS:
        driver.execute_query(statement, database_=database)
    label_of = {e["id"]: e["type"] for e in entities}

    for label, rows in node_rows(entities).items():
        for i in range(0, len(rows), batch):
            driver.execute_query(
                f"UNWIND $rows AS r MERGE (n:{label} {{uid: r.uid}}) "
                "SET n = r.props, n.uid = r.uid, n.dataset = $dataset, n.load_id = $load_id",
                rows=rows[i:i + batch], dataset=dataset, load_id=load_id, database_=database)

    for (rtype, from_label, to_label), rows in relation_rows(relations, label_of).items():
        key_fields = RELATION_KEY[rtype]
        merge_key = ", ".join(f"{k}: r.key.{k}" for k in key_fields)
        for i in range(0, len(rows), batch):
            driver.execute_query(
                f"UNWIND $rows AS r MATCH (a:{from_label} {{uid: r.from}}) MATCH (b:{to_label} {{uid: r.to}}) "
                f"MERGE (a)-[x:{rtype}{' {' + merge_key + '}' if merge_key else ''}]->(b) "
                "SET x = r.props, x += r.key, x.dataset = $dataset, x.load_id = $load_id",
                rows=rows[i:i + batch], dataset=dataset, load_id=load_id, database_=database)

    pruned_rels = driver.execute_query(
        "MATCH ()-[x]->() WHERE x.dataset = $dataset AND x.load_id <> $load_id DELETE x RETURN count(*) AS n",
        dataset=dataset, load_id=load_id, database_=database).records[0]["n"]
    pruned_nodes = 0
    for label in LABELS:
        pruned_nodes += driver.execute_query(
            f"MATCH (n:{label}) WHERE n.dataset = $dataset AND n.load_id <> $load_id DETACH DELETE n RETURN count(*) AS n",
            dataset=dataset, load_id=load_id, database_=database).records[0]["n"]
    return {"load_id": load_id, "pruned_nodes": pruned_nodes, "pruned_relationships": pruned_rels}


def graph_counts(driver, dataset: str = "pilot", database: str | None = None) -> tuple[dict, dict]:
    nodes = {r["label"]: r["n"] for r in driver.execute_query(
        "MATCH (n) WHERE n.dataset = $dataset UNWIND labels(n) AS label RETURN label, count(*) AS n ORDER BY label",
        dataset=dataset, database_=database).records}
    rels = {r["type"]: r["n"] for r in driver.execute_query(
        "MATCH ()-[x]->() WHERE x.dataset = $dataset RETURN type(x) AS type, count(*) AS n ORDER BY type",
        dataset=dataset, database_=database).records}
    return nodes, rels


# ---------------------------------------------------------------- sanity queries

SANITY_QUERIES = {
    "Directors of more than one pilot company": """
        MATCH (p:Person)-[d:DIRECTOR_OF]->(c:Company)
        WHERE c.nse_symbol IS NOT NULL AND d.own_report
        WITH p, collect(c.nse_symbol + ' (' + coalesce(d.status, '?')
                         + CASE WHEN d.after_fy_end THEN ', joined after FY end' ELSE '' END + ')') AS seats
        WHERE size(seats) > 1
        RETURN p.name AS person, p.din AS din, size(seats) AS pilot_companies, seats
        ORDER BY pilot_companies DESC, person""",
    "Companies within 2 steps of both Tata Motors and TCS": """
        MATCH (tm:Company {nse_symbol: 'TATAMOTORS'}), (tcs:Company {nse_symbol: 'TCS'})
        MATCH (c:Company) WHERE c <> tm AND c <> tcs
          AND EXISTS { MATCH (c)-[*1..2]-(tm) } AND EXISTS { MATCH (c)-[*1..2]-(tcs) }
        OPTIONAL MATCH p1 = shortestPath((c)-[*1..2]-(tm))
        OPTIONAL MATCH p2 = shortestPath((c)-[*1..2]-(tcs))
        RETURN c.name AS company, c.nse_symbol AS pilot,
               [n IN nodes(p1)[1..-1] | n.name] AS via_tata_motors, [r IN relationships(p1) | type(r)] AS tm_path,
               [n IN nodes(p2)[1..-1] | n.name] AS via_tcs, [r IN relationships(p2) | type(r)] AS tcs_path
        ORDER BY company""",
    "Each pilot company's statutory auditor": """
        MATCH (c:Company) WHERE c.nse_symbol IS NOT NULL
        OPTIONAL MATCH (c)-[a:AUDITED_BY {audit_type: 'statutory'}]->(f:AuditFirm)
        RETURN c.nse_symbol AS company, f.name AS statutory_auditor, f.firm_registration_no AS frn,
               a.source_doc[0] + ' p.' + toString(a.page[0]) AS source
        ORDER BY company""",
}


def run_sanity_queries(driver, database: str | None = None) -> dict[str, list[dict]]:
    return {name: [r.data() for r in driver.execute_query(q, database_=database).records]
            for name, q in SANITY_QUERIES.items()}
