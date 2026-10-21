"""Pydantic models for the facts extracted from a report's sections.

Each fact type mirrors one relationship in the graph schema (PROJECT_SPEC.md). Every
fact carries an `evidence` field: a short, exact quote the extractor must find in the
source text before the fact is trusted (see `extractor._find_page`). Facts produced by
table parsing instead of the LLM don't need that check — their `evidence` is just the
raw cell text they came from, not an LLM claim that could be hallucinated.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ListedDirectorship(BaseModel):
    """A directorship this report says one of its directors holds in another listed company
    (-> `(Person)-[:DIRECTOR_OF {category, reported_by}]->(Company)`, reported by this
    company, not by the other one)."""

    company_name: str
    category: str | None = None
    note: str | None = None


class DirectorFact(BaseModel):
    """One Board of Directors member (-> `(Person)-[:DIRECTOR_OF]->(Company)`)."""

    person_name: str
    din: str | None = None
    role: str
    is_independent: bool
    is_executive: bool
    status: Literal["current", "ceased", "appointed"] = "current"
    other_listed_directorships: list[ListedDirectorship] = []
    evidence: str


class DirectorFactList(BaseModel):
    directors: list[DirectorFact]


class KmpFact(BaseModel):
    """A Key Managerial Person (-> `(Person)-[:KMP_OF]->(Company)`)."""

    person_name: str
    role: Literal["CEO", "CFO", "Company Secretary"]
    status: Literal["current", "ceased", "appointed"] = "current"
    appointed_on: str | None = None
    ceased_on: str | None = None
    evidence: str


class KmpFactList(BaseModel):
    kmp: list[KmpFact]


class SubsidiaryFact(BaseModel):
    """One subsidiary from Form AOC-1 (-> `(Company)-[:SUBSIDIARY_OF]->(Company)`)."""

    subsidiary_name: str
    # Two subsidiaries can share a name (Infosys has "Infosys Consulting S.R.L." in both
    # Romania and Argentina), so the country is part of what tells them apart.
    country: str | None = None
    cin: str | None = None
    stake_pct: float | None = None
    evidence: str


class SubsidiaryFactList(BaseModel):
    subsidiaries: list[SubsidiaryFact]


class AuditorFact(BaseModel):
    """One audit firm (-> `(Company)-[:AUDITED_BY]->(AuditFirm)`). `audit_type` is set
    by the caller (which section the fact came from), not asked of the model. A secretarial
    audit can be signed by an individual practising company secretary rather than a firm
    (Tata Consumer's is); `firm_name` then holds that person's name."""

    firm_name: str
    firm_registration_no: str | None = None
    evidence: str


class AuditorFactList(BaseModel):
    auditors: list[AuditorFact]


class RelatedPartyFact(BaseModel):
    """One related-party transaction (-> `(Company)-[:RELATED_PARTY_TXN]->(Company|Person)`)."""

    party_name: str
    nature: str
    amount_inr_crore: float | None = None
    evidence: str


class RelatedPartyFactList(BaseModel):
    related_party_transactions: list[RelatedPartyFact]
