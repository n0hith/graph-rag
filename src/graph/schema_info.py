"""The graph schema as compact text for the Phase 6 text-to-Cypher prompt, plus example
question -> Cypher pairs. The node and relationship lists come from the loader's own
definitions (src/graph/load_neo4j.py), so the description can't drift from what is loaded.
Every example query has been run against the loaded pilot graph (tests/test_schema_info.py)."""

from __future__ import annotations

from src.graph.load_neo4j import LABELS, NODE_PROPS, REL_PROPS

NODE_NOTES = {
    "Company": "uid = CIN for the five pilot companies (they also have nse_symbol: TCS, TATAMOTORS, TATASTEEL, "
               "TATACONSUM, INFY), otherwise a generated id. countries: list. aliases: every spelling seen.",
    "Person": "uid = DIN when known (din property), otherwise a generated id. name without titles.",
    "AuditFirm": "statutory auditor firm or secretarial auditor (a firm or an individual).",
    "RelatedPartyGroup": "a category of related parties named in one report's related-party note "
                         "(e.g. 'Subsidiaries', 'Associates', 'Promoter'), not one company; reported_by = that report.",
}
RELATIONSHIPS = [
    ("DIRECTOR_OF", "Person", "Company", "board seat. status: 'current' or 'ceased' ('appointed' during the year "
     "counts as current); null when only another company's report mentions the seat (own_report = false). "
     "roles, appointed_on, ceased_on and categories are lists. after_fy_end = joined after March 31, 2024."),
    ("KMP_OF", "Person", "Company", "role: 'CEO' | 'CFO' | 'Company Secretary'; status, appointed_on, ceased_on."),
    ("SUBSIDIARY_OF", "Company", "Company", "subsidiary -> parent (from the parent's Form AOC-1); stake_pct."),
    ("AUDITED_BY", "Company", "AuditFirm", "audit_type: 'statutory' | 'secretarial'; firm_registration_no."),
    ("RELATED_PARTY_TXN", "Company", "Company|RelatedPartyGroup", "reporting company -> party; nature (e.g. "
     "'Purchase of goods'), amount_inr_crore (FY2024 figure, crore), amount_as_printed. One per nature and amount."),
    ("GROUP_OF", "RelatedPartyGroup", "Company", "the company a group label names ('Subsidiaries of Tata Sons ...')."),
    ("MERGED_INTO", "Company", "Company", "company merged into another (two companies); note has the date."),
    ("FORMERLY_NAMED", "Company", "Company", "the first company once had the name the second company has now "
     "(a name link, not a company link); former_name."),
]
COMMON_REL_PROPS = ("source_doc", "page", "evidence", "reported_by", "fy")

EXAMPLES = [
    ("Who is a director of more than one of the pilot companies?",
     "MATCH (p:Person)-[d:DIRECTOR_OF]->(c:Company) WHERE c.nse_symbol IS NOT NULL AND d.own_report "
     "WITH p, collect(c.nse_symbol) AS companies WHERE size(companies) > 1 "
     "RETURN p.name, p.din, companies"),
    ("Who audits Tata Steel's financial statements?",
     "MATCH (:Company {nse_symbol: 'TATASTEEL'})-[a:AUDITED_BY {audit_type: 'statutory'}]->(f:AuditFirm) "
     "RETURN f.name, f.firm_registration_no, a.source_doc, a.page"),
    ("Which companies are connected to both Tata Motors and TCS within two steps?",
     "MATCH (tm:Company {nse_symbol: 'TATAMOTORS'}) MATCH (tcs:Company {nse_symbol: 'TCS'}) "
     "MATCH (c:Company) WHERE c <> tm AND c <> tcs AND EXISTS { MATCH (c)-[*1..2]-(tm) } "
     "AND EXISTS { MATCH (c)-[*1..2]-(tcs) } RETURN c.name"),
    ("How many subsidiaries does Infosys list?",
     "MATCH (s:Company)-[:SUBSIDIARY_OF]->(:Company {nse_symbol: 'INFY'}) RETURN count(s) AS subsidiaries"),
    ("Who was TCS's CEO during FY2024?",
     "MATCH (p:Person)-[k:KMP_OF {role: 'CEO'}]->(:Company {nse_symbol: 'TCS'}) "
     "RETURN p.name, k.status, k.appointed_on, k.ceased_on"),
    ("Which other listed companies does N Chandrasekaran sit on the board of?",
     "MATCH (p:Person {din: '00121863'})-[d:DIRECTOR_OF]->(c:Company) RETURN c.name, d.status, d.reported_by"),
]


def describe_schema() -> str:
    """The schema as compact text for an LLM prompt."""
    lines = ["Graph of FY2023-24 annual-report facts for five Indian listed companies (pilot).", "", "Nodes:"]
    for label in LABELS:
        lines.append(f"- {label} {{uid, {', '.join(NODE_PROPS[label])}}}: {NODE_NOTES[label]}")
    lines += ["", "Relationships (every one also has " + ", ".join(COMMON_REL_PROPS) + "; source_doc, page, "
              "evidence and reported_by are parallel lists, one entry per source):"]
    for rtype, a, b, note in RELATIONSHIPS:
        props = ", ".join(REL_PROPS[rtype])
        lines.append(f"- ({a})-[:{rtype}{' {' + props + '}' if props else ''}]->({b}): {note}")
    lines += ["", "Name lookup: full-text index `entity_names` over name and aliases_text, e.g. "
              "CALL db.index.fulltext.queryNodes('entity_names', 'Chandrasekaran') YIELD node, score."]
    return "\n".join(lines)


def describe_examples() -> str:
    return "\n\n".join(f"Q: {q}\nCypher: {c}" for q, c in EXAMPLES)
