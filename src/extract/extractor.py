"""Turn a company's sectionized report into facts.

For directors and subsidiaries, table parsing (`tables.py`) is tried first since those
sections usually have a clean table; the LLM only runs where no such table is found.
Auditors and related-party transactions always go through the LLM, since those facts
live in prose, not clean tables. Every LLM-produced fact's `evidence` quote must be found
verbatim in the section's own text before it's kept; a fact whose quote can't be found is
dropped (and logged) as a likely hallucination. Long sections are split into page groups
before each LLM call, and duplicate facts across groups are merged afterwards.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.ingest.companies import Company
from src.llm.client import LLMClient, StructuredOutputError
from src.extract.prompts import (
    auditor_prompt,
    director_prompt,
    kmp_prompt,
    related_party_prompt,
    subsidiary_prompt,
)
from src.extract.schema import (
    AuditorFactList,
    DirectorFactList,
    KmpFactList,
    RelatedPartyFactList,
    SubsidiaryFactList,
)
from src.extract.tables import parse_directors_table, parse_subsidiaries_table

logger = logging.getLogger(__name__)

# The pilot's whole dataset is one reporting year; see PROJECT_SPEC.md "Scope".
FY = "FY2023-24"
# Pages per LLM call. Keeps each call focused and keeps cost/latency predictable, per
# PROJECT_SPEC.md Phase 3: "split by page groups if needed, then merge duplicate facts".
GROUP_SIZE = 6
MAX_RETRIES = 2


@dataclass(frozen=True)
class Fact:
    """One extracted fact, ready for Phase 4 (entity resolution) and Phase 5 (loading)."""

    fact_type: str  # "director" | "kmp" | "subsidiary" | "auditor" | "related_party"
    method: str  # "table" | "llm"
    company: str
    nse_symbol: str
    section_type: str
    page: int | None
    fy: str
    data: dict
    evidence: str


@dataclass(frozen=True)
class DroppedFact:
    """An LLM-produced fact whose evidence quote didn't check out."""

    fact_type: str
    section_type: str
    reason: str
    evidence: str
    data: dict


@dataclass
class ExtractionResult:
    facts: list[Fact] = field(default_factory=list)
    dropped: list[DroppedFact] = field(default_factory=list)
    calls_used: int = 0


# An auditor's `firm_registration_no` is only kept when the evidence quote shows it under
# an FRN label; the model has put peer-review ("PR No.") numbers there otherwise.
FRN_LABEL_RE = re.compile(r"firm['’]?s?\s+registration\s+(?:no|number)|\bFRN\b", re.I)
NOT_AN_FRN_RE = re.compile(r"^\s*(?:PR|FCS|ACS|CP|UDIN|M(?:embership)?\.?\s*No)\b", re.I)


def _checked_frn(value: str | None, evidence: str) -> str | None:
    """`value` if the evidence quote labels it as a firm registration number, else None."""
    if not value or NOT_AN_FRN_RE.search(value):
        return None
    flat = _norm_ws(evidence)
    label = FRN_LABEL_RE.search(flat)
    if not label or _norm_ws(value) not in flat[label.end():]:
        return None
    return value


def _group_pages(pages: list[dict], size: int = GROUP_SIZE) -> list[list[dict]]:
    return [pages[i : i + size] for i in range(0, len(pages), size)]


CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _norm_ws(text: str) -> str:
    """Whitespace collapsed, and stray control characters dropped: some PDFs' text has them
    inside words (TCS's p.98 reads "\\x07Tata Consumer"), which no LLM quote would copy."""
    return " ".join(CONTROL_CHARS_RE.sub("", text).split())


def _find_page(evidence: str, pages: list[dict]) -> int | None:
    """Which page (if any) in `pages` contains `evidence`, ignoring whitespace differences."""
    needle = _norm_ws(evidence)
    if not needle:
        return None
    for page in pages:
        if needle in _norm_ws(page["text"]):
            return page["page"]
    return None


def _load_section(sections_dir: Path, symbol: str, section_type: str) -> dict | None:
    path = sections_dir / symbol / f"{section_type}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _call_structured(client: LLMClient, prompt: str, schema: type, step: str):
    """`generate_structured`, retrying up to MAX_RETRIES times with the validation error
    appended to the prompt, per PROJECT_SPEC.md Phase 3."""
    last_error: str | None = None
    for attempt in range(MAX_RETRIES + 1):
        full_prompt = prompt
        if attempt:
            full_prompt += (
                f"\n\nYour previous reply was invalid: {last_error}\n"
                "Return only valid JSON matching the required schema."
            )
        try:
            return client.generate_structured(full_prompt, schema, step=step)
        except StructuredOutputError as exc:
            last_error = str(exc)
            if attempt == MAX_RETRIES:
                logger.warning("%s: giving up after %d attempts (%s)", step, attempt + 1, last_error)
                raise


def estimate_calls(sections_dir: Path, symbol: str) -> dict[str, int]:
    """How many LLM calls `extract_company` would make for this company, without calling it."""
    estimate: dict[str, int] = {}

    cg = _load_section(sections_dir, symbol, "corporate_governance")
    if cg:
        has_director_table = any(
            len(parse_directors_table(t)) >= 2 for p in cg["pages"] for t in p["tables"]
        )
        estimate["directors"] = 0 if has_director_table else len(_group_pages(cg["pages"]))
        estimate["kmp"] = len(_group_pages(cg["pages"]))

    aoc1 = _load_section(sections_dir, symbol, "subsidiaries_aoc1")
    if aoc1:
        has_subsidiary_table = any(
            parse_subsidiaries_table(t) for p in aoc1["pages"] for t in p["tables"]
        )
        estimate["subsidiaries"] = 0 if has_subsidiary_table else len(_group_pages(aoc1["pages"]))

    for section_type, key in [("auditor_report", "auditor_statutory"), ("secretarial_audit", "auditor_secretarial")]:
        sec = _load_section(sections_dir, symbol, section_type)
        if sec:
            estimate[key] = len(_group_pages(sec["pages"]))

    rpt = _load_section(sections_dir, symbol, "related_party")
    if rpt:
        estimate["related_party"] = len(_group_pages(rpt["pages"]))

    return estimate


def _fact_key(fact_type: str, data: dict) -> tuple:
    if fact_type == "director":
        return (fact_type, (data.get("din") or data.get("person_name", "")).lower())
    if fact_type == "kmp":
        return (fact_type, data.get("person_name", "").lower(), data.get("role", ""))
    if fact_type == "other_directorship":
        return (fact_type, (data.get("din") or data.get("person_name", "")).lower(), data.get("company_name", "").lower())
    if fact_type == "subsidiary":
        return (fact_type, data.get("subsidiary_name", "").lower())
    if fact_type == "auditor":
        return (fact_type, data.get("firm_name", "").lower(), data.get("audit_type", ""))
    if fact_type == "related_party":
        return (fact_type, data.get("party_name", "").lower(), data.get("nature", "").lower(), data.get("amount_inr_crore"))
    return (fact_type, json.dumps(data, sort_keys=True))


def _dedupe(facts: list[Fact]) -> list[Fact]:
    seen: set[tuple] = set()
    kept = []
    for f in facts:
        key = _fact_key(f.fact_type, f.data)
        if key in seen:
            continue
        seen.add(key)
        kept.append(f)
    return kept


def _extract_llm_facts(
    client: LLMClient,
    pages: list[dict],
    prompt_fn,
    list_attr: str,
    fact_type: str,
    section_type: str,
    company: Company,
    step: str,
    extra_data: dict | None = None,
) -> tuple[list[Fact], list[DroppedFact], int]:
    """Run `prompt_fn` over `pages` in groups, validate each fact's evidence quote, and
    turn survivors into `Fact`s. Shared by every LLM-sourced fact type."""
    facts: list[Fact] = []
    dropped: list[DroppedFact] = []
    calls = 0
    for group in _group_pages(pages):
        calls += 1
        prompt = prompt_fn(group)
        try:
            result = _call_structured(client, prompt, list_attr[0], step)
        except StructuredOutputError:
            continue
        for item in getattr(result, list_attr[1]):
            data = item.model_dump(exclude={"evidence"})
            if extra_data:
                data.update(extra_data)
            if fact_type == "auditor":
                data["firm_registration_no"] = _checked_frn(data.get("firm_registration_no"), item.evidence)
            page = _find_page(item.evidence, group)
            if page is None:
                dropped.append(DroppedFact(fact_type, section_type, "evidence not found in source text", item.evidence, data))
                continue
            facts.append(Fact(fact_type, "llm", company.name, company.nse_symbol, section_type, page, FY, data, item.evidence))
    return facts, dropped, calls


def _directorship_facts(director: Fact, entries: list[dict], company: Company) -> list[Fact]:
    """One `other_directorship` fact per directorship in another listed company that this
    company's report lists for `director`. `reported_by` records whose report said so: the
    other company's own report is the authority on its board, this is only a cross-reference."""
    facts = []
    for entry in entries:
        entry = dict(entry)
        evidence = entry.pop("evidence", None) or entry["company_name"]
        data = {
            "person_name": director.data["person_name"],
            "din": director.data.get("din"),
            **entry,
            "reported_by": company.nse_symbol,
        }
        facts.append(Fact("other_directorship", director.method, company.name, company.nse_symbol,
                          director.section_type, director.page, FY, data, evidence))
    return facts


def _checked_directorships(director: Fact, pages: list[dict]) -> tuple[list[dict], list[DroppedFact]]:
    """The LLM's `other_listed_directorships` for `director`, keeping only companies whose
    name appears on the director's page or the one after (a table row can wrap onto it)."""
    nearby = [p for p in pages if director.page is not None and director.page <= p["page"] <= director.page + 1]
    kept, dropped = [], []
    for entry in director.data.pop("other_listed_directorships", []) or []:
        if _find_page(entry["company_name"], nearby) is None:
            dropped.append(DroppedFact("other_directorship", director.section_type,
                                       "company name not found near the director's evidence",
                                       entry["company_name"], {"person_name": director.data["person_name"], **entry}))
        else:
            kept.append(entry)
    return kept, dropped


def extract_company(company: Company, sections_dir: Path, client: LLMClient) -> ExtractionResult:
    """Extract every fact type for one company. Section JSONs missing from `sections_dir`
    are skipped silently (nothing to extract)."""
    result = ExtractionResult()

    cg = _load_section(sections_dir, company.nse_symbol, "corporate_governance")
    if cg:
        table_facts = []
        for page in cg["pages"]:
            for table in page["tables"]:
                for row in parse_directors_table(table, page["text"]):
                    evidence = row.pop("evidence")
                    others = row.pop("other_listed_directorships")
                    director = Fact("director", "table", company.name, company.nse_symbol, "corporate_governance", page["page"], FY, row, evidence)
                    table_facts.append(director)
                    table_facts.extend(_directorship_facts(director, others, company))
        if table_facts:
            result.facts.extend(table_facts)
        else:
            facts, dropped, calls = _extract_llm_facts(
                client, cg["pages"], director_prompt, (DirectorFactList, "directors"),
                "director", "corporate_governance", company, "extract.directors",
            )
            for director in facts:
                others, bad = _checked_directorships(director, cg["pages"])
                result.facts.append(director)
                result.facts.extend(_directorship_facts(director, others, company))
                dropped.extend(bad)
            result.dropped.extend(dropped)
            result.calls_used += calls

        facts, dropped, calls = _extract_llm_facts(
            client, cg["pages"], kmp_prompt, (KmpFactList, "kmp"),
            "kmp", "corporate_governance", company, "extract.kmp",
        )
        result.facts.extend(facts)
        result.dropped.extend(dropped)
        result.calls_used += calls

    aoc1 = _load_section(sections_dir, company.nse_symbol, "subsidiaries_aoc1")
    if aoc1:
        table_facts = []
        for page in aoc1["pages"]:
            for table in page["tables"]:
                for row in parse_subsidiaries_table(table):
                    evidence = row.pop("evidence")
                    table_facts.append(
                        Fact("subsidiary", "table", company.name, company.nse_symbol, "subsidiaries_aoc1", page["page"], FY, row, evidence)
                    )
        if table_facts:
            result.facts.extend(table_facts)
        else:
            facts, dropped, calls = _extract_llm_facts(
                client, aoc1["pages"], subsidiary_prompt, (SubsidiaryFactList, "subsidiaries"),
                "subsidiary", "subsidiaries_aoc1", company, "extract.subsidiaries",
            )
            result.facts.extend(facts)
            result.dropped.extend(dropped)
            result.calls_used += calls

    for section_type, audit_type in [("auditor_report", "statutory"), ("secretarial_audit", "secretarial")]:
        sec = _load_section(sections_dir, company.nse_symbol, section_type)
        if not sec:
            continue
        facts, dropped, calls = _extract_llm_facts(
            client, sec["pages"], lambda pages, t=audit_type: auditor_prompt(pages, t),
            (AuditorFactList, "auditors"), "auditor", section_type, company,
            f"extract.auditor.{audit_type}", extra_data={"audit_type": audit_type},
        )
        result.facts.extend(facts)
        result.dropped.extend(dropped)
        result.calls_used += calls

    rpt = _load_section(sections_dir, company.nse_symbol, "related_party")
    if rpt:
        facts, dropped, calls = _extract_llm_facts(
            client, rpt["pages"], related_party_prompt, (RelatedPartyFactList, "related_party_transactions"),
            "related_party", "related_party", company, "extract.related_party",
        )
        result.facts.extend(facts)
        result.dropped.extend(dropped)
        result.calls_used += calls

    result.facts = _dedupe(result.facts)
    return result
