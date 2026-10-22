"""Phase 4: entity resolution. Every person, company, audit firm and related-party group
mentioned in the five reports' facts becomes one entity, and every fact becomes a relation
between entities, keeping its source (document, page, evidence quote, FY).

People merge by DIN first (the TCS certificate's DIN conflict is resolved as recorded by
`check-dins`: the fact's `din`, both DINs kept on the person), then by hand-confirmed
merges (data/overrides/merges.csv), then by the same normalised name: always within one
report, and across reports only when the name has a full given name and the two sides
can't be told apart by DIN. Companies merge by CIN (the five reporting companies), then by
normalised name (legal form, punctuation, "(formerly ...)" and bracketed short names as
aliases, lookalike l/I), never across two different countries. Anything that only looks
alike is listed for review, not merged. Every merge decision is logged.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from src.extract.extractor import Fact, load_facts
from src.ingest.companies import Company
from src.resolve.normalize import (
    CompanyName,
    canonical_country,
    companies_may_match,
    company_name,
    fold_lookalikes,
    group_anchor,
    initials_only,
    is_group_label,
    person_key,
    person_tokens,
    persons_may_match,
)

logger = logging.getLogger(__name__)


@dataclass
class Mention:
    id: str
    kind: str  # person | company | firm | group
    name: str  # as printed (whitespace collapsed)
    key: str
    symbol: str  # whose report
    fact_type: str
    page: int | None
    din: str | None = None
    cin: str | None = None
    country: str | None = None
    aliases: list[str] = field(default_factory=list)  # short names: the same company
    former_names: list[str] = field(default_factory=list)  # may be another company's name today
    extra: dict = field(default_factory=dict)


@dataclass
class Uncertain:
    kind: str
    a_id: str
    a_name: str
    a_reports: str
    b_id: str
    b_name: str
    b_reports: str
    reason: str


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        self.parent[rb] = ra
        return True


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


def _display_person(name: str) -> str:
    """The printed name without a leading title ("Mr. N. Chandrasekaran" -> "N. Chandrasekaran")."""
    words = _clean(name).split()
    while words and person_tokens(words[0]) == [] and words[1:]:
        words = words[1:]
    return " ".join(words)


def _resolved_din(f: Fact) -> str | None:
    resolution = f.data.get("din_resolution") or {}
    return resolution.get("din") or f.data.get("din")


# ---------------------------------------------------------------- overrides


def load_overrides(path: Path) -> list[dict]:
    """data/overrides/merges.csv rows. Person rows (fact_type director/kmp/person) map
    `from_name` in that company's report to the person with `to_din`. Company rows
    (fact_type company) take `action`: merge (`from_name` is the same company as
    `to_name`), split (never merge the two), merged_into (record that `from_name` merged
    into `to_name`; they stay two companies)."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return [row for row in csv.DictReader(fh) if row.get("nse_symbol") or row.get("fact_type")]


@dataclass
class Resolution:
    entities: list[dict]
    relations: list[dict]
    log: list[dict]
    uncertain: list[Uncertain]
    mentions: list[Mention]


def resolve(extracted_dir: Path, companies: list[Company], overrides: list[dict]) -> Resolution:
    facts_by_symbol = {c.nse_symbol: load_facts(extracted_dir / f"{c.nse_symbol}.jsonl")
                       for c in companies if (extracted_dir / f"{c.nse_symbol}.jsonl").exists()}
    log: list[dict] = []
    uncertain: list[Uncertain] = []
    mentions: list[Mention] = []
    fact_mentions: dict[tuple[str, int], dict[str, str]] = {}  # (symbol, fact index) -> role -> mention id

    def add(m: Mention, symbol: str, index: int | None, role: str) -> Mention:
        mentions.append(m)
        if index is not None:
            fact_mentions.setdefault((symbol, index), {})[role] = m.id
        return m

    def company_mention(mid: str, printed: str, symbol: str, fact_type: str, page, country=None,
                        cin=None) -> Mention:
        cn: CompanyName = company_name(printed)
        return Mention(mid, "company", cn.display, cn.key, symbol, fact_type, page, cin=cin,
                       country=canonical_country(country) or cn.country, aliases=list(cn.short_names),
                       former_names=list(cn.former_names))

    # ---- mentions
    for c in companies:
        add(company_mention(f"{c.nse_symbol}:reporter", c.name, c.nse_symbol, "reporter", None, "India", c.cin),
            c.nse_symbol, None, "")
    for symbol, facts in facts_by_symbol.items():
        for i, f in enumerate(facts):
            d, mid = f.data, f"{symbol}:{i}"
            if f.fact_type == "director":
                add(Mention(mid, "person", _clean(d["person_name"]), person_key(d["person_name"]), symbol,
                            f.fact_type, f.page, din=_resolved_din(f)), symbol, i, "person")
            elif f.fact_type == "kmp":
                add(Mention(mid, "person", _clean(d["person_name"]), person_key(d["person_name"]), symbol,
                            f.fact_type, f.page), symbol, i, "person")
            elif f.fact_type == "other_directorship":
                add(Mention(mid + ":p", "person", _clean(d["person_name"]), person_key(d["person_name"]), symbol,
                            f.fact_type, f.page, din=d.get("din")), symbol, i, "person")
                add(company_mention(mid + ":c", d["company_name"], symbol, f.fact_type, f.page), symbol, i, "company")
            elif f.fact_type == "subsidiary":
                add(company_mention(mid, d["subsidiary_name"], symbol, f.fact_type, f.page, d.get("country"),
                                    d.get("cin")), symbol, i, "company")
            elif f.fact_type == "auditor":
                frn = "".join((d.get("firm_registration_no") or "").split()).upper() or None
                key = f"frn:{frn}" if frn else company_name(d["firm_name"]).key
                add(Mention(mid, "firm", _clean(d["firm_name"]), key, symbol, f.fact_type, f.page,
                            extra={"frn": frn}), symbol, i, "firm")
            elif f.fact_type == "related_party":
                party = _clean(d["party_name"])
                if is_group_label(party):
                    add(Mention(mid, "group", party, f"{symbol}:{fold_lookalikes(party)}", symbol, f.fact_type, f.page,
                                extra={"anchor": group_anchor(party)}), symbol, i, "party")
                    if group_anchor(party):
                        add(company_mention(mid + ":anchor", group_anchor(party), symbol, "group_anchor", f.page),
                            symbol, None, "")
                else:
                    add(company_mention(mid, party, symbol, f.fact_type, f.page), symbol, i, "party")

    by_id = {m.id: m for m in mentions}
    uf = UnionFind()
    for m in mentions:
        uf.find(m.id)

    def merge(a: Mention, b: Mention, rule: str) -> None:
        if uf.union(a.id, b.id):
            log.append({"kind": a.kind, "rule": rule, "a": a.name, "a_report": a.symbol, "a_page": a.page,
                        "b": b.name, "b_report": b.symbol, "b_page": b.page})

    def members(root: str) -> list[Mention]:
        return [m for m in mentions if uf.find(m.id) == root]

    # ---- people
    people = [m for m in mentions if m.kind == "person"]
    by_din: dict[str, list[Mention]] = defaultdict(list)
    for m in people:
        if m.din:
            by_din[m.din].append(m)
    for din, ms in by_din.items():
        for m in ms[1:]:
            merge(ms[0], m, f"same DIN {din}")
    for o in overrides:
        if (o.get("fact_type") or "director") not in ("director", "kmp", "person") or not o.get("to_din"):
            continue
        target = by_din.get(o["to_din"])
        if not target:
            log.append({"kind": "person", "rule": "override: no person with that DIN", "a": o["from_name"],
                        "a_report": o["nse_symbol"], "b": o["to_din"]})
            continue
        for m in people:
            if m.symbol == o["nse_symbol"] and m.key == person_key(o["from_name"]):
                merge(target[0], m, f"override merges.csv: {o['from_name']} = DIN {o['to_din']}")

    def dins(root: str) -> set[str]:
        return {m.din for m in members(root) if m.din}

    def name_merge(a: Mention, b: Mention, rule: str) -> None:
        ra, rb = uf.find(a.id), uf.find(b.id)
        if ra == rb:
            return
        da, db = dins(ra), dins(rb)
        if da and db and not (da & db):
            uncertain.append(Uncertain("person", ra, a.name, a.symbol, rb, b.name, b.symbol,
                                       f"same name, different DINs ({', '.join(sorted(da))} / {', '.join(sorted(db))})"))
            return
        merge(a, b, rule)

    by_key: dict[str, list[Mention]] = defaultdict(list)
    for m in people:
        by_key[m.key].append(m)
    for key, ms in by_key.items():
        for b in ms[1:]:
            a = next((x for x in ms if x.symbol == b.symbol and x is not b), None)
            if a is not None:
                name_merge(a, b, "same name, same report")
        reports = sorted({m.symbol for m in ms})
        if len(reports) > 1:
            if initials_only(ms[0].name):
                firsts = {r: next(m for m in ms if m.symbol == r) for r in reports}
                roots = {uf.find(m.id) for m in firsts.values()}
                if len(roots) > 1:
                    a, *rest = firsts.values()
                    for b in rest:
                        if uf.find(a.id) != uf.find(b.id) and not (dins(uf.find(a.id)) and dins(uf.find(b.id))):
                            uncertain.append(Uncertain("person", uf.find(a.id), a.name, a.symbol, uf.find(b.id),
                                                       b.name, b.symbol, "same initials-only name in two reports, "
                                                       "no shared DIN"))
            else:
                for b in ms[1:]:
                    name_merge(ms[0], b, "same full name, across reports")

    # ---- companies
    companies_m = [m for m in mentions if m.kind == "company"]
    company_keys: dict[str, list[Mention]] = defaultdict(list)
    for m in companies_m:
        company_keys[m.key].append(m)
    company_overrides = [o for o in overrides if o.get("fact_type") == "company"]
    splits = {frozenset((company_name(o["from_name"]).key, company_name(o["to_name"]).key))
              for o in company_overrides if o.get("action") == "split"}
    # Pairs the user has decided on (any action), so they leave the review list.
    decided = {frozenset((company_name(o["from_name"]).key, company_name(o["to_name"]).key)) for o in company_overrides}

    def countries(root: str) -> set[str]:
        return {m.country.lower() for m in members(root) if m.country}

    def company_merge(a: Mention, b: Mention, rule: str) -> None:
        ra, rb = uf.find(a.id), uf.find(b.id)
        if ra == rb:
            return
        if frozenset((a.key, b.key)) in splits:
            log.append({"kind": "company", "rule": "override split: not merged", "a": a.name, "b": b.name})
            return
        # Two rows of one report's subsidiary list are two companies, whatever else matches.
        same_list = ({m.symbol for m in members(ra) if m.fact_type == "subsidiary"}
                     & {m.symbol for m in members(rb) if m.fact_type == "subsidiary"})
        if same_list:
            log.append({"kind": "company", "rule": f"never merged: separate rows of {', '.join(sorted(same_list))}'s "
                        f"subsidiary list", "a": a.name, "a_report": a.symbol, "a_page": a.page, "b": b.name,
                        "b_report": b.symbol, "b_page": b.page, "would_have_been": rule})
            return
        ca, cb = countries(ra), countries(rb)
        if ca and cb and not (ca & cb):
            return  # same name, different countries: two companies (AOC-1 lists such pairs)
        merge(a, b, rule)

    for key, ms in company_keys.items():
        located = defaultdict(list)
        for m in ms:
            located[(m.country or "").lower()].append(m)
        countries_here = [c for c in located if c]
        for c in countries_here:
            for m in located[c][1:]:
                company_merge(located[c][0], m, "same name, same country")
        unplaced = located.get("", [])
        if len(countries_here) > 1 and unplaced:
            for m in unplaced:
                uncertain.append(Uncertain("company", m.id, m.name, m.symbol, located[countries_here[0]][0].id,
                                           f"{key} (in {', '.join(sorted(countries_here))})", "",
                                           "same name as subsidiaries in several countries; which one?"))
            continue
        anchor = located[countries_here[0]][0] if countries_here else unplaced[0]
        for m in unplaced:
            company_merge(anchor, m, "same name" + (" (country from the other mention)" if countries_here else ""))
    # A bracketed short name is the same company ("... Co. Limited (Infosys China)"). A former
    # name is not merged on: it can be another company's name today (TMF Business Services
    # Limited was "formerly known as Tata Motors Finance Limited", while a different company is
    # now called Tata Motors Finance Limited).
    for m in companies_m:
        for alias in m.aliases:
            for other in company_keys.get(company_name(alias).key, []):
                company_merge(m, other, f"short name of '{m.name}': '{alias}'")
    former_matches = []
    for m in companies_m:
        for former in m.former_names:
            for other in company_keys.get(company_name(former).key, []):
                if uf.find(other.id) != uf.find(m.id) and frozenset((m.key, other.key)) not in decided:
                    former_matches.append((m, other, former))
    # Hand-confirmed company merges; merged_into is recorded as a relation later.
    merged_into, formerly_named = [], []
    for o in company_overrides:
        froms = company_keys.get(company_name(o["from_name"]).key, [])
        tos = company_keys.get(company_name(o["to_name"]).key, [])
        if o.get("action", "merge") == "merge":
            if tos:
                target = tos[0]
                for m in froms:
                    company_merge(target, m, f"override merges.csv: {o['from_name']} = {o['to_name']}")
                target.aliases.append(o["from_name"])
                log.append({"kind": "company", "rule": "override alias recorded", "a": o["from_name"],
                            "b": target.name, "b_report": target.symbol})
        elif o.get("action") == "merged_into" and froms and tos:
            merged_into.append((froms[0], tos[0], o))
        elif o.get("action") == "formerly_named" and froms and tos:
            formerly_named.append((froms[0], tos[0], o))

    # ---- audit firms: FRN, else name
    firms = [m for m in mentions if m.kind == "firm"]
    for i, a in enumerate(firms):
        for b in firms[i + 1:]:
            if a.key == b.key or company_name(a.name).key == company_name(b.name).key:
                merge(a, b, "same FRN" if a.key == b.key and a.key.startswith("frn:") else "same name")
    # ---- groups: one per report and label
    groups = [m for m in mentions if m.kind == "group"]
    by_group_key = defaultdict(list)
    for m in groups:
        by_group_key[m.key].append(m)
    for ms in by_group_key.values():
        for m in ms[1:]:
            merge(ms[0], m, "same group label, same report")

    # ---- entities
    roots: dict[str, list[Mention]] = defaultdict(list)
    for m in mentions:
        roots[uf.find(m.id)].append(m)
    entity_id: dict[str, str] = {}
    entities = []
    counters = Counter()
    for root, ms in roots.items():
        kind = ms[0].kind
        counters[kind] += 1
        eid = f"{kind}:{counters[kind]:04d}"
        for m in ms:
            entity_id[m.id] = eid
        entities.append(_entity(eid, kind, ms))

    # ---- uncertain look-alikes between different entities (not merged)
    entity_by_id = {e["id"]: e for e in entities}
    uncertain = [u for u in uncertain]
    seen_pairs = set()
    for m, other, former in former_matches:
        a, b = entity_id[m.id], entity_id[other.id]
        if a != b and frozenset((a, b)) not in seen_pairs:
            seen_pairs.add(frozenset((a, b)))
            uncertain.append(Uncertain("company", a, m.name, "", b, other.name, "",
                                       f"'{m.name}' was formerly called '{former}', which is how this other mention is "
                                       "printed: renamed company, or a different company that now has the old name?"))
    for u in uncertain:
        u.a_id, u.b_id = entity_id.get(u.a_id, u.a_id), entity_id.get(u.b_id, u.b_id)
        seen_pairs.add(frozenset((u.a_id, u.b_id)))
    _suggest(entities, uncertain, seen_pairs, decided)

    relations = _relations(facts_by_symbol, companies, fact_mentions, entity_id, by_id, entity_by_id)
    for frm, to, o in merged_into:
        relations.append({"type": "MERGED_INTO", "from": entity_id[frm.id], "to": entity_id[to.id],
                          "note": o.get("note", ""), "sources": [_override_source(o)]})
    for frm, to, o in formerly_named:
        # A name link, not a company link: `from` was once called what `to` is called now.
        relations.append({"type": "FORMERLY_NAMED", "from": entity_id[frm.id], "to": entity_id[to.id],
                          "former_name": to.name, "note": o.get("note", ""), "sources": [_override_source(o)]})
    for u in uncertain:
        u.a_reports = ", ".join(entity_by_id[u.a_id]["reports"]) if u.a_id in entity_by_id else u.a_reports
        u.b_reports = ", ".join(entity_by_id[u.b_id]["reports"]) if u.b_id in entity_by_id else u.b_reports
    return Resolution(entities, relations, log, uncertain, mentions)


def _override_source(o: dict) -> dict:
    """The source a merges.csv note cites: its page ("p.307") and its quoted text."""
    note = o.get("note", "")
    page = re.search(r"\bp\.(\d+)", note)
    quote = re.search(r'"([^"]+)"', note)
    return {"source_doc": f"{o['nse_symbol']}.pdf", "page": int(page.group(1)) if page else None,
            "evidence": quote.group(1) if quote else note, "fy": "FY2023-24", "fact_type": "override",
            "reported_by": o["nse_symbol"]}


def _entity(eid: str, kind: str, ms: list[Mention]) -> dict:
    reports = sorted({m.symbol for m in ms if m.fact_type != "reporter"} | {m.symbol for m in ms if m.fact_type == "reporter"})
    names = Counter(m.name for m in ms)
    e = {"id": eid, "type": {"person": "Person", "company": "Company", "firm": "AuditFirm", "group": "RelatedPartyGroup"}[kind],
         "reports": sorted({m.symbol for m in ms}),
         "mentioned_in": sorted({m.symbol for m in ms if m.fact_type != "reporter"}),
         "aliases": sorted(set(names) | {a for m in ms for a in m.aliases}),
         "former_names": sorted({a for m in ms for a in m.former_names}),
         "mentions": len(ms)}
    if kind == "person":
        with_din = [m for m in ms if m.din]
        full = max((_display_person(m.name) for m in (with_din or ms)), key=lambda n: (not initials_only(n), len(n)))
        e.update(name=full, name_normalized=person_key(full), din=with_din[0].din if with_din else None,
                 dins=sorted({m.din for m in with_din}))
    elif kind == "company":
        reporter = next((m for m in ms if m.fact_type == "reporter"), None)
        e.update(name=reporter.name if reporter else names.most_common(1)[0][0],
                 name_normalized=ms[0].key, cin=next((m.cin for m in ms if m.cin), None),
                 nse_symbol=reporter.symbol if reporter else None,
                 countries=sorted({m.country for m in ms if m.country}),
                 roles=sorted({m.fact_type for m in ms}),
                 subsidiary_of=sorted({m.symbol for m in ms if m.fact_type == "subsidiary"}))
    elif kind == "firm":
        e.update(name=names.most_common(1)[0][0], firm_registration_no=next((m.extra["frn"] for m in ms if m.extra.get("frn")), None))
    else:
        e.update(name=ms[0].name, reported_by=ms[0].symbol, anchor=ms[0].extra.get("anchor"))
    return e


def _suggest(entities: list[dict], uncertain: list[Uncertain], seen: set, decided: set = frozenset()) -> None:
    """Pairs of different person or company entities whose names look alike (blocked by a
    shared word), excluding pairs a DIN or two different countries already tell apart, and
    pairs decided in merges.csv."""
    for kind, check in [("Person", persons_may_match), ("Company", None)]:
        es = [e for e in entities if e["type"] == kind]
        index = defaultdict(set)
        for n, e in enumerate(es):
            for alias in e["aliases"]:
                words = person_tokens(alias) if kind == "Person" else company_name(alias).core.split()
                for w in words:
                    if len(w) > 2:
                        index[fold_lookalikes(w)].add(n)
        pairs = set()
        for ns in index.values():
            if len(ns) < 60:
                pairs |= {(a, b) for a in ns for b in ns if a < b}
        for a, b in sorted(pairs):
            ea, eb = es[a], es[b]
            if frozenset((ea["id"], eb["id"])) in seen:
                continue
            if kind == "Person":
                if ea["dins"] and eb["dins"]:
                    continue
                reason = next((r for x in ea["aliases"] for y in eb["aliases"] if (r := persons_may_match(x, y))), None)
            else:
                if ea["countries"] and eb["countries"] and not set(ea["countries"]) & set(eb["countries"]):
                    continue
                if ea.get("cin") and eb.get("cin"):
                    continue
                if any(frozenset((company_name(x).key, company_name(y).key)) in decided
                       for x in ea["aliases"] for y in eb["aliases"]):
                    continue
                # Two rows of one report's subsidiary list: two companies by rule, nothing to ask.
                if set(ea.get("subsidiary_of", [])) & set(eb.get("subsidiary_of", [])):
                    continue
                reason = next((r for x in ea["aliases"] for y in eb["aliases"]
                               if (r := companies_may_match(company_name(x), company_name(y)))), None)
            if reason:
                seen.add(frozenset((ea["id"], eb["id"])))
                uncertain.append(Uncertain(kind.lower(), ea["id"], ea["name"], "", eb["id"], eb["name"], "", reason))


# ---------------------------------------------------------------- relations

STATUS_ORDER = ("current", "appointed", "ceased")


def combined_status(statuses: list[str], ceased_dates: list[str]) -> tuple[str, bool]:
    """Status of one person's seat or role from all its mentions: "appointed" and "current"
    both mean current; only "ceased" means they left. Mentions that disagree (one ceased, one
    current) keep "ceased" when a cessation date is stated, else "current"; the second value
    says whether they disagreed."""
    s = {x for x in statuses if x}
    left = "ceased" in s
    stayed = bool(s & {"current", "appointed"})
    if left and stayed:
        return ("ceased" if ceased_dates else "current"), True
    return ("ceased" if left else "current"), False


def _source(symbol: str, f: Fact) -> dict:
    return {"source_doc": f"{symbol}.pdf", "page": f.page, "evidence": f.evidence, "fy": f.fy, "fact_type": f.fact_type,
            "reported_by": symbol}


def _relations(facts_by_symbol, companies, fact_mentions, entity_id, by_id, entity_by_id) -> list[dict]:
    reporter = {c.nse_symbol: entity_id[f"{c.nse_symbol}:reporter"] for c in companies}
    seats: dict[tuple, dict] = {}
    roles: dict[tuple, dict] = {}
    out = []
    for symbol, facts in facts_by_symbol.items():
        for i, f in enumerate(facts):
            ids = {role: entity_id[mid] for role, mid in fact_mentions.get((symbol, i), {}).items()}
            d = f.data
            if f.fact_type in ("director", "other_directorship"):
                company = reporter[symbol] if f.fact_type == "director" else ids["company"]
                seat = seats.setdefault((ids["person"], company), {
                    "type": "DIRECTOR_OF", "from": ids["person"], "to": company, "statuses": [], "roles": set(),
                    "appointed_on": set(), "ceased_on": set(), "categories": set(), "sources": [],
                    "is_independent": None, "is_executive": None, "after_fy_end": False, "own_report": False})
                seat["sources"].append(_source(symbol, f))
                if f.fact_type == "director":
                    seat["own_report"] = True
                    seat["statuses"].append(d.get("status"))
                    seat["roles"].add(d.get("role"))
                    seat["is_independent"], seat["is_executive"] = d.get("is_independent"), d.get("is_executive")
                    seat["after_fy_end"] |= bool(d.get("after_fy_end"))
                    if d.get("appointed_on"):
                        seat["appointed_on"].add(d["appointed_on"])
                    if d.get("ceased_on"):
                        seat["ceased_on"].add(d["ceased_on"])
                    for k in ("din_conflict", "din_resolution"):
                        if d.get(k):
                            seat[k] = d[k]
                else:
                    seat["categories"].add(d.get("category"))
            elif f.fact_type == "kmp":
                role = roles.setdefault((ids["person"], reporter[symbol], d["role"]), {
                    "type": "KMP_OF", "from": ids["person"], "to": reporter[symbol], "role": d["role"], "statuses": [],
                    "appointed_on": set(), "ceased_on": set(), "sources": []})
                role["statuses"].append(d.get("status"))
                role["sources"].append(_source(symbol, f))
                if d.get("appointed_on"):
                    role["appointed_on"].add(d["appointed_on"])
                if d.get("ceased_on"):
                    role["ceased_on"].add(d["ceased_on"])
                if d.get("date_conflict"):
                    role["date_conflict"] = d["date_conflict"]
            elif f.fact_type == "subsidiary":
                out.append({"type": "SUBSIDIARY_OF", "from": ids["company"], "to": reporter[symbol],
                            "stake_pct": d.get("stake_pct"), "sources": [_source(symbol, f)]})
            elif f.fact_type == "auditor":
                out.append({"type": "AUDITED_BY", "from": reporter[symbol], "to": ids["firm"],
                            "audit_type": d.get("audit_type"), "firm_registration_no": d.get("firm_registration_no"),
                            "sources": [_source(symbol, f)]})
            elif f.fact_type == "related_party":
                out.append({"type": "RELATED_PARTY_TXN", "from": reporter[symbol], "to": ids["party"],
                            "nature": d.get("nature"), "amount_inr_crore": d.get("amount_inr_crore"),
                            "amount_as_printed": d.get("amount_as_printed"), "sources": [_source(symbol, f)]})
    for rel in list(seats.values()) + list(roles.values()):
        status, conflict = combined_status(rel.pop("statuses"), sorted(rel["ceased_on"]))
        if rel["type"] == "DIRECTOR_OF" and not rel["own_report"]:
            status = None  # only another company's report mentions this seat; no status stated
        rel["status"] = status
        rel["status_conflict"] = conflict
        for k in ("appointed_on", "ceased_on", "roles", "categories"):
            if k in rel:
                rel[k] = sorted(x for x in rel[k] if x)
        out.append(rel)
    for e in entity_by_id.values():  # groups point at the company they are about
        if e["type"] == "RelatedPartyGroup" and e.get("anchor"):
            anchor_key = company_name(e["anchor"]).key
            target = next((x["id"] for x in entity_by_id.values() if x["type"] == "Company"
                           and anchor_key in {company_name(a).key for a in x["aliases"]}), None)
            if target:
                # The group's label is the evidence: the first transaction row naming it.
                first = next(r for r in out if r["type"] == "RELATED_PARTY_TXN" and r["to"] == e["id"])
                out.append({"type": "GROUP_OF", "from": e["id"], "to": target, "sources": first["sources"][:1]})
    return out


# ---------------------------------------------------------------- output


def write_outputs(res: Resolution, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "entities.jsonl").open("w", encoding="utf-8") as fh:
        for e in res.entities:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    with (out_dir / "relations.jsonl").open("w", encoding="utf-8") as fh:
        for r in res.relations:
            fh.write(json.dumps(r, ensure_ascii=False, default=sorted) + "\n")
    with (out_dir / "merge_log.jsonl").open("w", encoding="utf-8") as fh:
        for row in res.log:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (out_dir / "uncertain.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[*asdict(res.uncertain[0]).keys(), "decision"] if res.uncertain else ["kind"])
        w.writeheader()
        for u in res.uncertain:
            w.writerow({**asdict(u), "decision": ""})


# ---------------------------------------------------------------- stable ids and relation keys

# What makes a relation one relation: its type, its two ends, and these properties.
RELATION_KEY = {
    "DIRECTOR_OF": (), "KMP_OF": ("role",), "SUBSIDIARY_OF": (), "AUDITED_BY": ("audit_type",),
    "RELATED_PARTY_TXN": ("nature", "amount_as_printed"), "GROUP_OF": (), "MERGED_INTO": (), "FORMERLY_NAMED": (),
}


def relation_key(r: dict) -> tuple:
    return (r["type"], r["from"], r["to"], *(r.get(k) for k in RELATION_KEY[r["type"]]))


def fold_relations(relations: list[dict]) -> list[dict]:
    """One relation per key, sources combined: the same fact can reach one pair of entities
    twice when two spellings of a party resolved to one company (Infosys p.253 prints
    "Infosys Turkey Bilgi Teknolojileri Limited Sirketi" with and without a line break)."""
    out: dict[tuple, dict] = {}
    for r in relations:
        key = relation_key(r)
        if key not in out:
            out[key] = {**r, "sources": list(r["sources"])}
            continue
        seen = {(s["source_doc"], s["page"], s["evidence"]) for s in out[key]["sources"]}
        out[key]["sources"] += [s for s in r["sources"] if (s["source_doc"], s["page"], s["evidence"]) not in seen]
    return list(out.values())


def apply_uids(res: Resolution, uid: dict[str, str]) -> Resolution:
    """The resolution with every run-local entity id replaced by its stable uid."""
    entities = [{**e, "id": uid[e["id"]]} for e in res.entities]
    relations = fold_relations([{**r, "from": uid[r["from"]], "to": uid[r["to"]]} for r in res.relations])
    uncertain = [Uncertain(u.kind, uid.get(u.a_id, u.a_id), u.a_name, u.a_reports, uid.get(u.b_id, u.b_id), u.b_name,
                           u.b_reports, u.reason) for u in res.uncertain]
    return Resolution(entities, relations, res.log, uncertain, res.mentions)
