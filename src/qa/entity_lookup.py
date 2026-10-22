"""Map the names in a question to graph nodes before any Cypher is written.

The QA model lists the names as written ("TaMo", "Chandrasekaran", "tata steel"); each is then
looked up: first in a fixed table of the five pilot companies' common names and tickers, then
in the `entity_names` full-text index (names and every alias). A name resolves when exactly one
node matches it exactly, or, failing that, exactly one node's name contains all its words
("Chandrasekaran" -> "N. Chandrasekaran"), or one fuzzy hit clearly outscores the rest. Several
equally good matches make it ambiguous: the answer then lists them instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import BaseModel

from src.llm.client import LLMClient
from src.resolve.normalize import company_name, fold_lookalikes, person_tokens

# Common names and tickers of the five pilot companies -> NSE symbol.
PILOT_ALIASES = {
    "TCS": ("tcs", "tata consultancy services", "tata consultancy", "tata consultancy services limited"),
    "TATAMOTORS": ("tata motors", "tamo", "tml", "tatamotors", "tata motors limited", "tata motors ltd"),
    "TATASTEEL": ("tata steel", "tatasteel", "tata steel limited", "tata steel ltd"),
    "TATACONSUM": ("tata consumer", "tata consumer products", "tcpl", "tataconsum", "tata consumer products limited"),
    "INFY": ("infosys", "infy", "infosys limited", "infosys ltd"),
}
FUZZY_MARGIN = 1.3  # a fuzzy hit must outscore the next by this factor
LUCENE_SPECIAL = re.compile(r'([+\-!(){}\[\]^"~*?:\\/&|])')


class Mentions(BaseModel):
    names: list[str]


MENTIONS_PROMPT = (
    "List the names of specific companies, people and audit firms mentioned in this question, exactly as "
    "written, including short forms and tickers (e.g. 'TaMo', 'TCS', 'Infy'). Leave out generic words such as "
    "'board', 'directors', 'subsidiaries', 'auditor', 'pilot companies'. Return an empty list if there are "
    "none.\n\nQuestion: {question}"
)


@dataclass
class Candidate:
    uid: str
    label: str
    name: str
    detail: str = ""  # DIN, NSE symbol, countries, reports: enough to tell candidates apart

    def describe(self) -> str:
        return f"{self.name} ({self.label}{', ' + self.detail if self.detail else ''})"


@dataclass
class EntityMatch:
    mention: str
    status: str  # resolved | ambiguous | not_found
    node: Candidate | None = None
    candidates: list[Candidate] = field(default_factory=list)
    how: str = ""


def extract_mentions(client: LLMClient, question: str) -> list[str]:
    result = client.generate_structured(MENTIONS_PROMPT.format(question=question), Mentions, temperature=0.0,
                                        step="qa.entities")
    seen, out = set(), []
    for name in result.names:
        name = " ".join(name.split())
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out


def _candidate(record) -> Candidate:
    node = record["node"]
    label = next(iter(node.labels))
    detail = ", ".join(x for x in [
        f"NSE {node.get('nse_symbol')}" if node.get("nse_symbol") else "",
        f"DIN {node.get('din')}" if node.get("din") else "",
        "/".join(node.get("countries") or []),
        "in " + ", ".join(node.get("reports") or []) if node.get("reports") else "",
    ] if x)
    return Candidate(node["uid"], label, node.get("name", ""), detail)


def _aliases(record) -> list[str]:
    node = record["node"]
    return [node.get("name", "")] + list(node.get("aliases") or [])


def _same_name(mention: str, alias: str) -> bool:
    if company_name(mention).key == company_name(alias).key:
        return True
    a, b = company_name(mention).core, company_name(alias).core
    return bool(a) and a == b


def _contains_words(mention: str, alias: str) -> bool:
    words = [fold_lookalikes(w) for w in person_tokens(mention)]
    have = {fold_lookalikes(w) for w in person_tokens(alias)}
    return bool(words) and all(w in have for w in words)


def is_acronym(mention: str) -> bool:
    return mention.isalpha() and mention.isupper() and 2 <= len(mention) <= 5


def initials(name: str) -> str:
    """Initials of a company name without its legal form: "Jaguar Land Rover Limited" -> "jlr"."""
    words = company_name(name).core.split()
    return "".join(w[0] for w in words if w not in {"and", "of", "the"})


def lucene_query(mention: str) -> str:
    words = [LUCENE_SPECIAL.sub(r"\\\1", w) for w in mention.split()]
    return " AND ".join(f"{w}~" if len(w) >= 5 else w for w in words)


def resolve_mention(driver, mention: str, database: str | None = None) -> EntityMatch:
    flat = " ".join(re.sub(r"[.,']", " ", mention.lower()).split())
    symbol = next((s for s, names in PILOT_ALIASES.items() if flat in names), None)
    if symbol:
        records = driver.execute_query("MATCH (node:Company {nse_symbol: $s}) RETURN node", s=symbol,
                                       database_=database).records
        if records:
            return EntityMatch(mention, "resolved", _candidate(records[0]), how=f"pilot company name ({symbol})")
    records = driver.execute_query(
        "CALL db.index.fulltext.queryNodes('entity_names', $q) YIELD node, score "
        "RETURN node, score ORDER BY score DESC LIMIT 15", q=lucene_query(mention), database_=database).records
    if is_acronym(mention):
        # "JLR": the companies whose initials spell it, and those with the acronym in their name.
        spelled = [r for r in driver.execute_query("MATCH (node:Company) RETURN node", database_=database).records
                   if any(initials(a) == mention.lower() for a in _aliases(r))]
        named = [r for r in records if any(_contains_words(mention, a) for a in _aliases(r))]
        hits = list({r["node"]["uid"]: r for r in spelled + named}.values())
        if len(hits) == 1:
            return EntityMatch(mention, "resolved", _candidate(hits[0]), how="acronym")
        if hits:
            return EntityMatch(mention, "ambiguous", candidates=[_candidate(r) for r in hits[:6]],
                               how=f"{len(hits)} companies fit the acronym")
    if not records:
        return EntityMatch(mention, "not_found", how="no node has this name")
    for test, how in [(_same_name, "same name"), (_contains_words, "name contains all its words")]:
        hits = [r for r in records if any(test(mention, a) for a in _aliases(r))]
        if len(hits) == 1:
            return EntityMatch(mention, "resolved", _candidate(hits[0]), how=how)
        if len(hits) > 1:
            return EntityMatch(mention, "ambiguous", candidates=[_candidate(r) for r in hits[:6]],
                               how=f"{len(hits)} nodes match by {how}")
    top, second = records[0]["score"], (records[1]["score"] if len(records) > 1 else 0.0)
    if top >= FUZZY_MARGIN * second:
        return EntityMatch(mention, "resolved", _candidate(records[0]), how=f"closest spelling (score {top:.2f})")
    return EntityMatch(mention, "ambiguous", candidates=[_candidate(r) for r in records[:5]],
                       how="several names are about equally close")


def lookup_entities(client: LLMClient, driver, question: str, database: str | None = None) -> list[EntityMatch]:
    return [resolve_mention(driver, m, database) for m in extract_mentions(client, question)]
