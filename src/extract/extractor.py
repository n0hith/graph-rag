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

import csv
import datetime
import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from src.ingest.companies import Company
from src.llm.client import LLMClient, StructuredOutputError
from src.extract.amounts import NIL_REASON, STRUCK_OFF_REASON, apply_checks
from src.extract.cleanup import clean_facts
from src.extract.dates import fix_impossible_dates, report_date
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
from src.extract.tables import (
    CHANGE_DATE_RE,
    parse_date,
    parse_din_certificate,
    parse_directors_table,
    parse_subsidiaries_table,
)

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
    notes: list[str] = field(default_factory=list)  # DIN conflicts, dates found in text, FY2024 removals
    explained_removals: dict = field(default_factory=dict)  # (fact_type, section_type) -> count
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
    turn survivors into `Fact`s. Shared by every LLM-sourced fact type. Each group after
    the first is shown the page before it as context only (a table running over a page
    break has its heading there); a quote found only on that page is dropped, since that
    page is extracted in its own group."""
    facts: list[Fact] = []
    dropped: list[DroppedFact] = []
    calls = 0
    start = 0
    for group in _group_pages(pages, section_type):
        context = pages[start - 1] if start else None
        start += len(group)
        calls += 1
        prompt = prompt_fn(group, context)
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
                reason = ("quoted from the context page only" if context and _find_page(item.evidence, [context])
                          else "evidence not found in source text")
                dropped.append(DroppedFact(fact_type, section_type, reason, item.evidence, data))
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
    merged_into: dict[int, Fact] = {}
    merges, ambiguous = [], []
    # Same DIN under two spellings (e.g. a DIN filled from the certificate): one person.
    first_with_din: dict[str, Fact] = {}
    for f in directors:
        din = f.data.get("din")
        if not din:
            continue
        if din in first_with_din:
            target = first_with_din[din]
            merged_into[id(f)] = target
            merges.append(f"{f.data['person_name']!r} (p.{f.page}) -> {target.data['person_name']!r} (same DIN {din})")
        else:
            first_with_din[din] = f
    by_name: dict[str, dict[str, Fact]] = {}
    for f in first_with_din.values():
        by_name.setdefault(_norm_person(f.data["person_name"]), {})[f.data["din"]] = f

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

    return _fold(facts, merged_into), merges, ambiguous


def _fold(facts: list[Fact], merged_into: dict[int, Fact]) -> list[Fact]:
    """Drop the director copies keyed (by `id`) in `merged_into`, re-pointing each copy's
    other_directorship facts (linked by person_name + din) at the director it merged into."""
    if not merged_into:
        return facts
    repoint = {(f.data["person_name"], f.data.get("din")): target
               for f in facts if (target := merged_into.get(id(f))) is not None}
    kept = []
    for f in facts:
        if id(f) in merged_into:
            continue
        target = repoint.get((f.data.get("person_name"), f.data.get("din"))) if f.fact_type == "other_directorship" else None
        if target is not None:
            f = _with(f, person_name=target.data["person_name"], din=target.data.get("din"))
        kept.append(f)
    return _dedupe(kept)


def _with(f: Fact, **changes) -> Fact:
    """A copy of `f` with some `data` fields changed (Fact is frozen)."""
    return Fact(f.fact_type, f.method, f.company, f.nse_symbol, f.section_type, f.page, f.fy, {**f.data, **changes}, f.evidence)


def load_merge_overrides(path: Path) -> list[dict]:
    """data/overrides/merges.csv: hand-confirmed merges the automatic rules won't make
    (columns nse_symbol, fact_type, from_name, to_din, note). Missing file -> none."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return [row for row in csv.DictReader(fh) if row.get("nse_symbol")]


def _apply_merge_overrides(facts: list[Fact], overrides: list[dict], symbol: str) -> tuple[list[Fact], list[str]]:
    """Merge each override's `from_name` director into the director with `to_din`."""
    merged_into: dict[int, Fact] = {}
    log = []
    directors = [f for f in facts if f.fact_type == "director"]
    for o in overrides:
        if o["nse_symbol"] != symbol or o.get("fact_type", "director") != "director":
            continue
        target = next((f for f in directors if f.data.get("din") == o["to_din"]), None)
        copies = [f for f in directors if f is not target and _norm_person(f.data["person_name"]) == _norm_person(o["from_name"])]
        if target is None or not copies:
            log.append(f"override {o['from_name']!r} -> DIN {o['to_din']}: nothing to merge "
                       f"({'no director with that DIN' if target is None else 'no such name'})")
            continue
        for c in copies:
            merged_into[id(c)] = target
            log.append(f"override: {c.data['person_name']!r} (p.{c.page}, DIN {c.data.get('din') or 'none'}) -> "
                       f"{target.data['person_name']!r} (DIN {o['to_din']}) [{o.get('note', '')}]")
    return _fold(facts, merged_into), log


# ---------------------------------------------------------------- FY2024 board membership

# Pages that list the year's board: composition/attendance tables (board or committee) and
# the certificate of non-disqualification. A name found only elsewhere (e.g. a table of
# past general-meeting resolutions) isn't evidence of FY2024 board membership.
BOARD_PAGE_RE = re.compile(
    r"board meetings?\s+(?:held|attended)|attended\s+(?:the\s+)?last\s+agm|attendance\s+(?:at|of|record|details)"
    r"|meetings?\s+attended|number of (?:board )?meetings|disqualif",
    re.I,
)
FY_END = datetime.date(2024, 3, 31)


def _norm_text(text: str) -> str:
    """Page text for whole-word name lookups: punctuation and footnote markers become
    spaces, so "Uri Levine(1)" still contains " uri levine "."""
    return " " + " ".join(re.sub(r"[^\w\s-]", " ", _norm_person(" ".join(text.split()))).split()) + " "


def _director_certificate(pages: list[dict]) -> list[dict]:
    rows = []
    for p in pages:
        rows.extend({**r, "page": p["page"]} for r in parse_din_certificate(p["text"]))
    return rows


def _fill_dins_from_certificate(facts: list[Fact], pages: list[dict]) -> tuple[list[Fact], list[str]]:
    """A director without a DIN gets it from the certificate table when exactly one row there
    has the same normalized name (Infosys prints most DINs only there). The director's
    other_directorship facts get the DIN too, so they stay linked to it."""
    cert_by_name: dict[str, list[dict]] = {}
    for r in _director_certificate(pages):
        cert_by_name.setdefault(_norm_person(r["name"]), []).append(r)
    filled: dict[str, str] = {}  # person_name -> DIN
    notes, out = [], []
    for f in facts:
        if f.fact_type == "director" and not f.data.get("din"):
            matches = cert_by_name.get(_norm_person(f.data["person_name"]), [])
            if len({m["din"] for m in matches}) == 1:
                f = _with(f, din=matches[0]["din"], din_source=f"certificate p.{matches[0]['page']}")
                filled[f.data["person_name"]] = f.data["din"]
                notes.append(f"DIN filled from certificate: {f.data['person_name']} -> {f.data['din']} "
                             f"(p.{matches[0]['page']})")
        out.append(f)
    out = [_with(f, din=filled[f.data["person_name"]])
           if f.fact_type == "other_directorship" and not f.data.get("din") and f.data.get("person_name") in filled
           else f for f in out]
    return out, notes


def _change_date_in_text(director: Fact, pages: list[dict]) -> str | None:
    """For an LLM director fact marked appointed/ceased without a date: the date stated with
    a mention of the person (name or DIN), where the appointed/ceased wording sits right
    before the name or between the name and the date ("appointed Mr Bharat Puri (DIN: ...)
    ... commencing from May 15, 2024"). A date further along, past someone else's footnote
    ("(1) Retired ... effective April 19, 2023" after another name), doesn't count. Used only
    when every such mention agrees on the date."""
    keyword = re.compile(r"appoint" if director.data.get("status") == "appointed" else r"ceas|resign|retire|complet", re.I)
    needles = [re.escape(director.data["person_name"])] + ([re.escape(director.data["din"])] if director.data.get("din") else [])
    found = set()
    for p in pages:
        flat = " ".join(p["text"].split())
        for m in re.finditer("|".join(needles), flat):
            date = CHANGE_DATE_RE.search(flat, m.end(), m.end() + 300)
            if not date:
                continue
            between = flat[m.end(): date.start()]
            before = flat[max(0, m.start() - 100): m.start()]
            if keyword.search(between) or (keyword.search(before) and not re.search(r"\(\d\)", between)):
                found.add(date.group(1))
    return found.pop() if len(found) == 1 else None


def _finish_directors(facts: list[Fact], pages: list[dict]) -> tuple[list[Fact], list[str], list[DroppedFact]]:
    """Director clean-up that needs the whole governance section, after merging:

    - mark a DIN the certificate contradicts (`din_conflict`): TCS's certificate gives Al-Noor
      Ramji the DIN its own director table gives Don Callahan;
    - give an LLM director marked appointed/ceased the date the text states for it, and flag
      appointments after the year end (`after_fy_end`), so FY2024 board questions skip them;
    - drop anyone not named on a board/attendance/certificate page (or appointed after the year
      end): a name only in, say, a list of past AGM resolutions isn't an FY2024 director.
    """
    notes: list[str] = []
    dropped: list[DroppedFact] = []
    cert = _director_certificate(pages)
    cert_by_name: dict[str, list[dict]] = {}
    for r in cert:
        cert_by_name.setdefault(_norm_person(r["name"]), []).append(r)
    cert_by_din = {r["din"]: r for r in cert}
    names_by_din = {}
    for f in facts:
        if f.fact_type == "director" and f.data.get("din"):
            names_by_din[f.data["din"]] = _norm_person(f.data["person_name"])

    out = []
    for f in facts:
        if f.fact_type != "director":
            out.append(f)
            continue
        key = _norm_person(f.data["person_name"])
        matches = cert_by_name.get(key, [])
        din = f.data.get("din")
        conflict = {}
        for r in matches:
            if din and r["din"] != din:
                conflict = {"certificate_din": r["din"], "certificate_page": r["page"]}
        r = cert_by_din.get(din) if din else None
        if r and _norm_person(r["name"]) != key and _norm_person(r["name"]) in names_by_din.values():
            conflict = {"certificate_name_for_this_din": r["name"], "certificate_page": r["page"]}
        if conflict:
            f = _with(f, din_conflict=conflict)
            notes.append(f"DIN conflict: {f.data['person_name']} {din} vs certificate {conflict}")
        if f.data.get("status") == "appointed" and not f.data.get("appointed_on"):
            # The certificate prints each director's appointment date.
            row = next((r for r in matches if r.get("appointed_on")), None) or (
                cert_by_din.get(din) if din and cert_by_din.get(din, {}).get("appointed_on")
                and _norm_person(cert_by_din[din]["name"]) not in (set(names_by_din.values()) - {key}) else None)
            if row:
                f = _with(f, appointed_on=row["appointed_on"])
                notes.append(f"appointed_on from certificate: {f.data['person_name']} {row['appointed_on']} (p.{row['page']})")
        if f.method == "llm" and f.data.get("status") in ("appointed", "ceased"):
            field_name = "appointed_on" if f.data["status"] == "appointed" else "ceased_on"
            if not f.data.get(field_name):
                date = _change_date_in_text(f, pages)
                if date:
                    f = _with(f, **{field_name: date})
                    notes.append(f"{field_name} from text: {f.data['person_name']} {date}")
        appointed = parse_date(f.data.get("appointed_on"))
        f = _with(f, after_fy_end=bool(appointed and appointed > FY_END))
        out.append(f)

    board_text = [_norm_text(p["text"]) for p in pages if BOARD_PAGE_RE.search(" ".join(p["text"].split()))]
    kept = []
    removed_people = set()
    for f in out:
        if f.fact_type == "director" and not f.data["after_fy_end"]:
            name = " ".join(re.sub(r"[^\w\s-]", " ", _norm_person(f.data["person_name"])).split())
            on_board_page = any(f" {name} " in t for t in board_text) or (
                f.data.get("din") and (f.data["din"] in cert_by_din or any(f.data["din"] in t for t in board_text))
            )
            if not on_board_page:
                removed_people.add((f.data["person_name"], f.data.get("din")))
                dropped.append(DroppedFact("director", f.section_type, "not on an FY2024 board/attendance table or certificate",
                                           f.evidence, dict(f.data)))
                notes.append(f"not an FY2024 director (no board/attendance/certificate mention): "
                             f"{f.data['person_name']} {f.data.get('din') or ''} p.{f.page}")
                continue
        kept.append(f)
    kept = [f for f in kept if not (f.fact_type == "other_directorship"
                                   and (f.data.get("person_name"), f.data.get("din")) in removed_people)]
    return kept, notes, dropped


# Fields whose loss or change between runs must be flagged, and how a fact is recognised
# across runs (its identity without those fields).
KEY_FIELDS = {
    "director": ("din", "status", "appointed_on", "ceased_on"),
    "kmp": ("status", "appointed_on", "ceased_on"),
    "auditor": ("firm_registration_no",),
    "related_party": ("amount_inr_crore", "amount_as_printed"),
    "subsidiary": ("stake_pct",),
}


def _identity(f: Fact) -> tuple:
    d = f.data
    if f.fact_type == "director":
        return (f.fact_type, _norm_person(d.get("person_name", "")))
    if f.fact_type == "kmp":
        return (f.fact_type, _norm_person(d.get("person_name", "")), d.get("role"))
    if f.fact_type == "auditor":
        return (f.fact_type, _norm_ws(d.get("firm_name", "")).lower(), d.get("audit_type"))
    if f.fact_type == "related_party":
        return (f.fact_type, _norm_ws(d.get("party_name", "")).lower(), _norm_ws(d.get("nature", "")).lower())
    if f.fact_type == "subsidiary":
        return (f.fact_type, _norm_ws(d.get("subsidiary_name", "")).lower(), (d.get("country") or "").lower())
    return (f.fact_type,)


def field_changes(previous: list[Fact], new: list[Fact]) -> list[str]:
    """Key fields (DIN, FRN, amount, dates, status, stake) that were filled in the previous
    run and are now empty or different, for facts recognisable in both runs. A fact identity
    that appears more than once on either side (e.g. one party with two amounts) is skipped:
    there's no telling which old value corresponds to which new one."""
    def index(facts):
        seen: dict[tuple, list[Fact]] = {}
        for f in facts:
            if f.fact_type in KEY_FIELDS:
                seen.setdefault(_identity(f), []).append(f)
        return {k: v[0] for k, v in seen.items() if len(v) == 1}

    old, fresh = index(previous), index(new)
    flags = []
    for key, before in old.items():
        after = fresh.get(key)
        if after is None:
            continue
        for name in KEY_FIELDS[before.fact_type]:
            was, now = before.data.get(name), after.data.get(name)
            if was in (None, "") or was == now:
                continue
            label = " / ".join(str(k) for k in key[1:])
            change = "now empty" if now in (None, "") else f"now {now!r}"
            flags.append(f"{before.fact_type} {label}: {name} was {was!r}, {change}")
    return flags


def keep_previous_if_fewer(
    previous: list[Fact],
    new: list[Fact],
    accept_fewer: bool = False,
    explained: dict[tuple[str, str], int] | None = None,
) -> tuple[list[Fact], list[str]]:
    """Guard against silent regressions between runs, per (fact type, section): if the new
    run found fewer facts than the previous one did, keep the previous facts for that part
    and flag it. Both sides have their director copies merged first, so a merge that
    legitimately shrinks the director count isn't mistaken for a regression; `explained`
    counts facts the new run removed by a logged rule (FY2024 board rule, repeat block,
    override merges), which also don't count as missing. With `accept_fewer`, the new facts
    are kept anyway, but the drop is still flagged. Key-field changes are flagged too (see
    `field_changes`)."""
    previous, _, _ = _merge_directors(previous)

    def groups(facts: list[Fact]) -> dict[tuple[str, str], list[Fact]]:
        out: dict[tuple[str, str], list[Fact]] = {}
        for f in facts:
            out.setdefault((f.fact_type, f.section_type), []).append(f)
        return out

    old_groups, new_groups = groups(previous), groups(new)
    flags = field_changes(previous, new)
    kept = []
    for key in list(new_groups) + [k for k in old_groups if k not in new_groups]:
        old, fresh = old_groups.get(key, []), new_groups.get(key, [])
        if len(fresh) + (explained or {}).get(key, 0) < len(old):
            action = "kept the new facts anyway (--accept-fewer)" if accept_fewer else "kept the previous facts"
            flags.append(f"{key[0]} / {key[1]}: new run found {len(fresh)}, previous run {len(old)}; {action}")
            kept.extend(fresh if accept_fewer else old)
        else:
            kept.extend(fresh)
    return kept, flags


# Tata Motors' AOC-1 repeats some subsidiaries in a consolidated summary after the table.
REPEAT_BLOCK_RE = re.compile(r"Details of Direct Subsidiaries,? on consolidated basis", re.I)


def _drop_repeat_block(facts: list[Fact], pages: list[dict]) -> tuple[list[Fact], list[DroppedFact]]:
    """Drop subsidiary facts whose name occurs on its page only after a summary block
    heading that repeats rows already listed above it."""
    texts = {p["page"]: _norm_ws(p["text"]) for p in pages}
    kept, dropped = [], []
    for f in facts:
        text = texts.get(f.page, "")
        block = REPEAT_BLOCK_RE.search(text)
        at = text.find(_norm_ws(f.evidence))
        if block and at >= block.start():
            dropped.append(DroppedFact(f.fact_type, f.section_type, "in a summary block repeating rows listed above it",
                                       f.evidence, f.data))
        else:
            kept.append(f)
    return kept, dropped


def _check_amounts_on_page(facts: list[Fact], section: dict, raw_pdf_dir: Path
                           ) -> tuple[list[Fact], list[DroppedFact], list[str]]:
    """Related-party facts checked on the PDF page (see `src.extract.amounts.apply_checks`):
    passing amounts get `amount_as_printed`, a nature found under another printed heading is
    relabelled, nil rows and struck-off companies are dropped."""
    pdf_path = raw_pdf_dir / section["source_pdf"]
    if not pdf_path.exists():
        return facts, [], [f"related-party amounts not checked: {pdf_path.name} not found"]
    kept, removed, notes = apply_checks(facts, pdf_path, section["pages"])
    dropped = [DroppedFact(f.fact_type, f.section_type, reason, f.evidence, f.data) for f, reason in removed]
    return kept, dropped, notes


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


def extract_company(
    company: Company, sections_dir: Path, client: LLMClient, merge_overrides: list[dict] | None = None,
    raw_pdf_dir: Path | None = None, sections: set[str] | None = None,
) -> ExtractionResult:
    """Extract every fact type for one company. Section JSONs missing from `sections_dir`
    are skipped silently (nothing to extract). `merge_overrides` are hand-confirmed director
    merges (see `load_merge_overrides`). `raw_pdf_dir` holds the PDFs related-party amounts
    are checked against (default: `raw_pdfs` beside `sections_dir`). `sections`, if given,
    limits the run to those section types."""
    result = ExtractionResult()
    raw_pdf_dir = raw_pdf_dir or sections_dir.parent / "raw_pdfs"

    def load(section_type: str) -> dict | None:
        if sections is not None and section_type not in sections:
            return None
        return _load_section(sections_dir, company.nse_symbol, section_type)

    cg = load("corporate_governance")
    if cg:
        table_facts = []
        for i, page in enumerate(cg["pages"]):
            # TCS prints the director table's footnotes on the following page.
            footnote_text = page["text"] + "\n" + (cg["pages"][i + 1]["text"] if i + 1 < len(cg["pages"]) else "")
            for table in page["tables"]:
                for row in parse_directors_table(table, page["text"], footnote_text):
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

    aoc1 = load("subsidiaries_aoc1")
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
            facts, repeats = _drop_repeat_block(facts, aoc1["pages"])
            dropped.extend(repeats)
            result.facts.extend(facts)
            result.dropped.extend(dropped)
            result.calls_used += calls

    for section_type, audit_type in [("auditor_report", "statutory"), ("secretarial_audit", "secretarial")]:
        sec = load(section_type)
        if not sec:
            continue
        facts, dropped, calls = _extract_llm_facts(
            client, sec["pages"], lambda pages, context, t=audit_type: auditor_prompt(pages, t, context),
            (AuditorFactList, "auditors"), "auditor", section_type, company,
            f"extract.auditor.{audit_type}", extra_data={"audit_type": audit_type},
        )
        result.facts.extend(facts)
        result.dropped.extend(dropped)
        result.calls_used += calls

    rpt = load("related_party")
    amount_notes: list[str] = []
    if rpt:
        facts, dropped, calls = _extract_llm_facts(
            client, rpt["pages"], related_party_prompt, (RelatedPartyFactList, "related_party_transactions"),
            "related_party", "related_party", company, "extract.related_party",
        )
        facts, removed, amount_notes = _check_amounts_on_page(_dedupe(facts), rpt, raw_pdf_dir)
        dropped.extend(removed)
        result.facts.extend(facts)
        result.dropped.extend(dropped)
        result.calls_used += calls

    facts = _dedupe(result.facts)
    cg_pages = cg["pages"] if cg else []
    facts, filled = _fill_dins_from_certificate(facts, cg_pages)
    facts, result.merges, result.ambiguous = _merge_directors(facts)
    others_before = sum(f.fact_type == "other_directorship" for f in facts)
    facts, override_log = _apply_merge_overrides(facts, merge_overrides or [], company.nse_symbol)
    facts, notes, not_fy = _finish_directors(facts, cg_pages)
    any_section = next((sec for sec in [cg, aoc1, rpt] if sec), None)
    pdf_path = raw_pdf_dir / any_section["source_pdf"] if any_section else None
    published_on = report_date(pdf_path) if pdf_path and pdf_path.exists() else None
    facts, date_notes = fix_impossible_dates(facts, published_on, company.nse_symbol, merge_overrides or [])
    report_pages = None
    if pdf_path and pdf_path.exists():
        import pymupdf

        with pymupdf.open(pdf_path) as doc:
            report_pages = {i: " ".join(page.get_text().split()) for i, page in enumerate(doc, 1)}
    facts, cleanup_notes, _ = clean_facts(facts, cg_pages, report_pages)
    notes = notes + date_notes + [f"cleanup: {n}" for n in cleanup_notes]
    result.facts = facts
    # Removals by a logged rule the previous run didn't apply, so the regression guard
    # doesn't mistake them for facts the new run missed.
    same_din = sum("(same DIN" in m for m in result.merges)
    explained = Counter({("director", "corporate_governance"): same_din + len(override_log) + len(not_fy)})
    explained[("other_directorship", "corporate_governance")] = others_before - sum(
        f.fact_type == "other_directorship" for f in facts)
    explained[("subsidiary", "subsidiaries_aoc1")] = sum(
        d.reason.startswith("in a summary block") for d in result.dropped)
    explained[("related_party", "related_party")] = sum(
        d.reason in (NIL_REASON, STRUCK_OFF_REASON) for d in result.dropped)
    result.explained_removals = dict(explained)
    result.merges = filled + result.merges + override_log
    result.notes = notes + amount_notes
    result.dropped.extend(not_fy)
    return result
