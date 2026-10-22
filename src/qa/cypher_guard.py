"""Safety and validation for generated Cypher (PROJECT_SPEC.md Phase 6).

Every query is checked for write operations (after string literals and comments are removed,
so a company called "Merge Ltd" doesn't trip it), procedure calls are limited to read-only
ones, a LIMIT is added when the query has none at the end, and the query is EXPLAINed before it
runs. Both EXPLAIN and the run happen in a read-only session with a timeout, so even a write
that slipped past the checks would be refused by the database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from neo4j import READ_ACCESS, unit_of_work

WRITE_RE = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|LOAD\s+CSV|ALTER|GRANT|DENY|REVOKE|RENAME"
    r"|START|STOP|TERMINATE|ENABLE|DEALLOCATE|REALLOCATE|USE)\b", re.I)
CALL_RE = re.compile(r"\bCALL\s+([A-Za-z_][\w.]*)", re.I)
READ_PROCEDURES = {"db.index.fulltext.querynodes", "db.index.fulltext.queryrelationships", "db.labels",
                   "db.relationshiptypes", "db.propertykeys", "db.schema.visualization"}
LITERAL_RE = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`[^`]*`|//[^\n]*|/\*.*?\*/", re.S)
LIMIT_AT_END_RE = re.compile(r"\bLIMIT\s+(?:\d+|\$\w+)\s*;?\s*$", re.I)
DEFAULT_LIMIT = 100
TIMEOUT_SECONDS = 15.0


class CypherRejected(ValueError):
    """The query would write, or calls a procedure that isn't known to be read-only."""


@dataclass
class GuardedQuery:
    cypher: str  # as it will run (LIMIT added if needed)
    limit_added: bool


def _code_only(cypher: str) -> str:
    return LITERAL_RE.sub(" ", cypher)


def check_read_only(cypher: str) -> None:
    code = _code_only(cypher)
    write = WRITE_RE.search(code)
    if write:
        raise CypherRejected(f"write operation not allowed: {write.group(1).upper()}")
    for proc in CALL_RE.findall(code):
        if proc.lower() not in READ_PROCEDURES:
            raise CypherRejected(f"procedure not allowed: {proc}")


def ensure_limit(cypher: str, limit: int = DEFAULT_LIMIT) -> GuardedQuery:
    text = cypher.strip().rstrip(";").strip()
    if LIMIT_AT_END_RE.search(text):
        return GuardedQuery(text, False)
    return GuardedQuery(f"{text}\nLIMIT {limit}", True)


def guard(cypher: str, limit: int = DEFAULT_LIMIT) -> GuardedQuery:
    """Refuse writes, add a LIMIT if missing. Raises CypherRejected."""
    if not cypher or not cypher.strip():
        raise CypherRejected("empty query")
    check_read_only(cypher)
    return ensure_limit(cypher, limit)


class ReadOnlyRunner:
    """EXPLAIN and run queries in read-only transactions with a timeout."""

    def __init__(self, driver, database: str | None = None, timeout: float = TIMEOUT_SECONDS) -> None:
        self.driver = driver
        self.database = database
        self.timeout = timeout

    def _read(self, text: str, fetch: bool):
        @unit_of_work(timeout=self.timeout)
        def work(tx):
            result = tx.run(text)
            return list(result) if fetch else result.consume()

        with self.driver.session(database=self.database, default_access_mode=READ_ACCESS) as session:
            return session.execute_read(work)

    def explain(self, cypher: str) -> None:
        """Raises the database's error (syntax, unknown function, ...) without running the query."""
        self._read("EXPLAIN " + cypher, fetch=False)

    def run(self, cypher: str) -> list:
        return self._read(cypher, fetch=True)
