"""The graph schema as compact text for the Phase 6 text-to-Cypher prompt: nodes,
relationships, relationship categories, the rules for "connected", "board" and time, the
path convention answers rely on, and example question -> Cypher pairs. The node and
relationship lists come from the loader's own definitions (src/graph/load_neo4j.py), so the
description can't drift from what is loaded. Every example query is run against the loaded
pilot graph by tests/test_schema_info.py."""

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
    ("DIRECTOR_OF", "Person", "Company", "board seat. title: the designation the report prints (Chairman, "
     "Vice-Chairman, CEO & MD, Lead Independent Director, ...) or null; category: independence/executive category "
     "(e.g. 'Independent, Non-Executive Director'). status: 'current' or 'ceased' ('appointed' during the year "
     "counts as current); null when only another company's report mentions the seat (own_report = false). "
     "roles, appointed_on, ceased_on and categories are lists. after_fy_end = true if they joined after "
     "March 31, 2024."),
    ("KMP_OF", "Person", "Company", "role: 'CEO' | 'CFO' | 'Company Secretary'; status, appointed_on, ceased_on; "
     "after_fy_end = true if they took up the role after March 31, 2024."),
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

# Relationship categories. "Connected" means ownership, people or money unless the question
# is about auditors (then services too). Names never connect two companies.
CATEGORIES = {
    "ownership": ("SUBSIDIARY_OF", "MERGED_INTO"),
    "people": ("DIRECTOR_OF", "KMP_OF"),
    "money": ("RELATED_PARTY_TXN", "GROUP_OF"),
    "services": ("AUDITED_BY",),
    "names": ("FORMERLY_NAMED",),
}
CONNECTION_TYPES = CATEGORIES["ownership"] + CATEGORIES["people"] + CATEGORIES["money"]
CONNECTION_PATTERN = "|".join(CONNECTION_TYPES)

RULES = f"""Rules:
- Directions are fixed; never reverse them: (Person)-[:DIRECTOR_OF]->(Company), (Person)-[:KMP_OF]->(Company),
  (subsidiary Company)-[:SUBSIDIARY_OF]->(parent Company), (Company)-[:AUDITED_BY]->(AuditFirm),
  (reporting Company)-[:RELATED_PARTY_TXN]->(party), (RelatedPartyGroup)-[:GROUP_OF]->(Company).
- Relationship categories: {'; '.join(f'{k}: {", ".join(v)}' for k, v in CATEGORIES.items())}.
- "Connected", "linked", "related to" (in general) means a path over ownership, people and money only:
  use [:{CONNECTION_PATTERN}*1..N]. Add AUDITED_BY only when the question is about auditors.
  FORMERLY_NAMED is a name link and never counts as a connection.
- "The board", "directors", "sits on the board": FY2024 directors from the company's own report:
  d.own_report = true AND d.status = 'current' AND coalesce(d.after_fy_end, false) = false.
  People with status 'ceased' are former directors: include them only when the question asks about former
  directors or changes during the year (then also report ceased_on / appointed_on).
- Directorships at companies outside the five pilot companies come only from another report
  (own_report = false, no status); they count as directorships but have no status.
- KMP roles (CEO/CFO/Company Secretary) follow the same status rule as directors, including
  coalesce(k.after_fy_end, false) = false for FY2024 holders.
- Use the entity uids given with the question (MATCH (c:Company {{uid: '...'}})) rather than matching names.
- Path convention: bind every matched pattern to a path variable (p = ..., p1 = ..., p2 = ...) and return it:
  RETURN p (or collect(p)[..10] AS paths when aggregating), plus the columns that answer the question.
  Answers show these paths and their sources, so never return only scalars.
- Read only: MATCH / OPTIONAL MATCH / WITH / WHERE / RETURN / ORDER BY / LIMIT / UNWIND / EXISTS {{ }}.
- If the question can't be answered from these nodes and relationships (it asks about strategy, ESG,
  financial results, dividends, employees or other prose), say so instead of writing Cypher."""

EXAMPLES = [
    ("Who is a director of more than one of the pilot companies?",
     "MATCH p = (person:Person)-[d:DIRECTOR_OF]->(c:Company) WHERE c.nse_symbol IS NOT NULL AND d.own_report "
     "AND d.status = 'current' AND coalesce(d.after_fy_end, false) = false "
     "WITH person, collect(c.nse_symbol) AS companies, collect(p) AS paths WHERE size(companies) > 1 "
     "RETURN person.name, person.din, companies, paths"),
    ("Who audits Tata Steel's financial statements?",
     "MATCH p = (c:Company {uid: 'L27100MH1907PLC000260'})-[a:AUDITED_BY {audit_type: 'statutory'}]->(f:AuditFirm) "
     "RETURN f.name, f.firm_registration_no, p"),
    ("Which companies are connected to both Tata Motors and TCS within two steps?",
     "MATCH (tm:Company {uid: 'L28920MH1945PLC004520'}) MATCH (tcs:Company {uid: 'L22210MH1995PLC084781'}) "
     f"MATCH p1 = (c:Company)-[:{CONNECTION_PATTERN}*1..2]-(tm) "
     f"MATCH p2 = (c)-[:{CONNECTION_PATTERN}*1..2]-(tcs) WHERE c <> tm AND c <> tcs "
     "WITH c, collect(p1)[0] AS p1, collect(p2)[0] AS p2 RETURN c.name, p1, p2"),
    ("How many subsidiaries does Infosys list?",
     "MATCH p = (s:Company)-[:SUBSIDIARY_OF]->(:Company {uid: 'L85110KA1981PLC013115'}) "
     "RETURN count(s) AS subsidiaries, collect(p)[..10] AS paths"),
    ("Who was TCS's CEO during FY2024?",
     "MATCH p = (person:Person)-[k:KMP_OF {role: 'CEO'}]->(:Company {uid: 'L22210MH1995PLC084781'}) "
     "RETURN person.name, k.status, k.appointed_on, k.ceased_on, p"),
    ("Which other listed companies does N Chandrasekaran sit on the board of?",
     "MATCH p = (:Person {uid: '00121863'})-[d:DIRECTOR_OF]->(c:Company) "
     "WHERE coalesce(d.status, 'current') = 'current' RETURN c.name, d.status, d.reported_by, p"),
    ("Which subsidiaries of Tata Motors are also related parties of TCS?",
     "MATCH p1 = (s:Company)-[:SUBSIDIARY_OF]->(:Company {uid: 'L28920MH1945PLC004520'}) "
     "MATCH p2 = (:Company {uid: 'L22210MH1995PLC084781'})-[t:RELATED_PARTY_TXN]->(s) "
     "RETURN DISTINCT s.name, collect(t.nature) AS natures, collect(p1)[0] AS p1, collect(p2) AS p2"),
    ("What did Tata Steel's related-party note say it bought from its subsidiaries?",
     "MATCH p = (:Company {uid: 'L27100MH1907PLC000260'})-[t:RELATED_PARTY_TXN]->(g:RelatedPartyGroup {name: 'Subsidiaries'}) "
     "WHERE toLower(t.nature) CONTAINS 'purchase' RETURN t.nature, t.amount_inr_crore, t.amount_as_printed, p"),
]


def describe_schema() -> str:
    """The schema, categories and rules as compact text for an LLM prompt."""
    lines = ["Graph of FY2023-24 annual-report facts for five Indian listed companies (pilot).", "", "Nodes:"]
    for label in LABELS:
        lines.append(f"- {label} {{uid, {', '.join(NODE_PROPS[label])}}}: {NODE_NOTES[label]}")
    lines += ["", "Relationships (every one also has " + ", ".join(COMMON_REL_PROPS) + "; source_doc, page, "
              "evidence and reported_by are parallel lists, one entry per source):"]
    for rtype, a, b, note in RELATIONSHIPS:
        props = ", ".join(REL_PROPS[rtype])
        lines.append(f"- ({a})-[:{rtype}{' {' + props + '}' if props else ''}]->({b}): {note}")
    lines += ["", RULES]
    return "\n".join(lines)


def describe_examples() -> str:
    return "\n\n".join(f"Q: {q}\nCypher: {c}" for q, c in EXAMPLES)
