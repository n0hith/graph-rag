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
# Dense tables (a page of AOC-1 lists ~40 subsidiaries; Tata Steel's related-party table has
# dozens of cells) came out unstable at 6 pages per call: one re-run returned a single
# subsidiary for Tata Motors, another skipped Tata Steel's whole table. Fewer pages per call.
GROUP_SIZE_BY_SECTION = {"subsidiaries_aoc1": 2, "related_party": 2}
MAX_RETRIES = 2
# Extraction should give the same answer every time it's asked; Gemini's default isn't 0.
TEMPERATURE = 0.0


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


FACT_FIELDS = ("fact_type", "method", "company", "nse_symbol", "section_type", "page", "fy", "data", "evidence")


def save_facts(path: Path, facts: list[Fact]) -> None:
    """One JSON object per line, in `FACT_FIELDS` order."""
    with path.open("w", encoding="utf-8") as fh:
        for f in facts:
            fh.write(json.dumps({k: getattr(f, k) for k in FACT_FIELDS}, ensure_ascii=False) + "\n")


def load_facts(path: Path) -> list[Fact]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Fact(**{k: row[k] for k in FACT_FIELDS}) for row in map(json.loads, filter(str.strip, lines))]


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
    merges: list[str] = field(default_factory=list)  # director copies merged, one line each
    ambiguous: list[str] = field(default_factory=list)  # possible same-person pairs left unmerged


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


def _group_pages(pages: list[dict], section_type: str = "") -> list[list[dict]]:
    size = GROUP_SIZE_BY_SECTION.get(section_type, GROUP_SIZE)
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
            return client.generate_structured(full_prompt, schema, temperature=TEMPERATURE, step=step)
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
        estimate["subsidiaries"] = 0 if has_subsidiary_table else len(_group_pages(aoc1["pages"], "subsidiaries_aoc1"))

    for section_type, key in [("auditor_report", "auditor_statutory"), ("secretarial_audit", "auditor_secretarial")]:
        sec = _load_section(sections_dir, symbol, section_type)
        if sec:
            estimate[key] = len(_group_pages(sec["pages"]))

    rpt = _load_section(sections_dir, symbol, "related_party")
    if rpt:
        estimate["related_party"] = len(_group_pages(rpt["pages"], "related_party"))

    return estimate


def _fact_key(fact_type: str, data: dict) -> tuple:
    if fact_type == "director":
        return (fact_type, (data.get("din") or data.get("person_name", "")).lower())
    if fact_type == "kmp":
        return (fact_type, data.get("person_name", "").lower(), data.get("role", ""))
    if fact_type == "other_directorship":
        return (fact_type, (data.get("din") or data.get("person_name", "")).lower(), data.get("company_name", "").lower())
    if fact_type == "subsidiary":
        return (fact_type, data.get("subsidiary_name", "").lower(), (data.get("country") or "").lower())
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
    for group in _group_pages(pages, section_type):
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


PERSON_TITLE_RE = re.compile(r"^(?:mr|mrs|ms|dr|prof|shri|smt)\b\s*")


def _norm_person(name: str) -> str:
    """Case, titles and punctuation ignored: "Mr. L. Krishnakumar" == "L Krishnakumar"."""
    name = " ".join(re.sub(r"[.,'’`]", " ", name.lower()).split())
    return PERSON_TITLE_RE.sub("", name)


def _initials_match(a: str, b: str) -> bool:
    """Same surname, and the given names agree on their initials: "om prakash bhatt" vs
    "o p bhatt". Too loose to merge on, but worth listing as a possible match."""
    ta, tb = a.split(), b.split()
    if len(ta) < 2 or len(tb) < 2 or ta[-1] != tb[-1]:
        return False
    return [t[0] for t in ta[:-1]] == [t[0] for t in tb[:-1]]


def _merge_directors(facts: list[Fact]) -> tuple[list[Fact], list[str], list[str]]:
    """Fold director facts without a DIN into the one same-name director that has a DIN.

    The LLM sees a director on several pages (board table, attendance table, a certificate
    listing DINs) and only some of them print the DIN, so the same person can come out once
    with a DIN and once without, which DIN-or-name dedup can't catch. A copy is merged only
    when its normalized name matches exactly one DIN; several DINs for one name, or a name
    that only matches on initials ("Om Prakash Bhatt" / "O P Bhatt"), are listed instead.
    The dropped copy's `other_directorship` facts are re-pointed at the kept director."""
    directors = [f for f in facts if f.fact_type == "director"]
    by_name: dict[str, dict[str, Fact]] = {}
    for f in directors:
        if f.data.get("din"):
            by_name.setdefault(_norm_person(f.data["person_name"]), {})[f.data["din"]] = f

    merged_into: dict[int, Fact] = {}
    merges, ambiguous = [], []
    first_without_din: dict[str, Fact] = {}
    for f in directors:
        if f.data.get("din"):
            continue
        key = _norm_person(f.data["person_name"])
        targets = by_name.get(key, {})
        if len(targets) == 1:
            target = next(iter(targets.values()))
        elif len(targets) > 1:
            ambiguous.append(f"{f.data['person_name']!r} (p.{f.page}, no DIN) matches several DINs: "
                             f"{', '.join(sorted(targets))}; not merged")
            continue
        elif key in first_without_din:
            target = first_without_din[key]
        else:
            first_without_din[key] = f
            for other_key, dins in by_name.items():
                if _initials_match(key, other_key):
                    t = next(iter(dins.values()))
                    ambiguous.append(f"{f.data['person_name']!r} (p.{f.page}, no DIN) may be "
                                     f"{t.data['person_name']!r} (DIN {t.data['din']}); not merged")
            continue
        merged_into[id(f)] = target
        merges.append(f"{f.data['person_name']!r} (p.{f.page}, no DIN) -> {target.data['person_name']!r} "
                      f"(DIN {target.data.get('din') or 'none'}, p.{target.page})")

    if not merged_into:
        return facts, merges, ambiguous
    # A director's other_directorship facts point at it by (person_name, din).
    repoint = {(f.data["person_name"], None): merged_into[id(f)] for f in directors if id(f) in merged_into}
    kept = []
    for f in facts:
        if id(f) in merged_into:
            continue
        target = repoint.get((f.data.get("person_name"), f.data.get("din"))) if f.fact_type == "other_directorship" else None
        if target is not None:
            f = Fact(f.fact_type, f.method, f.company, f.nse_symbol, f.section_type, f.page, f.fy,
                     {**f.data, "person_name": target.data["person_name"], "din": target.data.get("din")}, f.evidence)
        kept.append(f)
    return _dedupe(kept), merges, ambiguous


def keep_previous_if_fewer(
    previous: list[Fact], new: list[Fact], accept_fewer: bool = False
) -> tuple[list[Fact], list[str]]:
    """Guard against silent regressions between runs, per (fact type, section): if the new
    run found fewer facts than the previous one did, keep the previous facts for that part
    and flag it. Both sides have their director copies merged first, so a merge that
    legitimately shrinks the director count isn't mistaken for a regression. With
    `accept_fewer`, the new facts are kept anyway, but the drop is still flagged."""
    previous, _, _ = _merge_directors(previous)

    def groups(facts: list[Fact]) -> dict[tuple[str, str], list[Fact]]:
        out: dict[tuple[str, str], list[Fact]] = {}
        for f in facts:
            out.setdefault((f.fact_type, f.section_type), []).append(f)
        return out

    old_groups, new_groups = groups(previous), groups(new)
    kept, flags = [], []
    for key in list(new_groups) + [k for k in old_groups if k not in new_groups]:
        old, fresh = old_groups.get(key, []), new_groups.get(key, [])
        if len(fresh) < len(old):
            action = "kept the new facts anyway (--accept-fewer)" if accept_fewer else "kept the previous facts"
            flags.append(f"{key[0]} / {key[1]}: new run found {len(fresh)}, previous run {len(old)}; {action}")
            kept.extend(fresh if accept_fewer else old)
        else:
            kept.extend(fresh)
    return kept, flags


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

    result.facts, result.merges, result.ambiguous = _merge_directors(_dedupe(result.facts))
    return result
