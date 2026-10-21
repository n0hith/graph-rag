"""Resolve DIN conflicts using what the pilot reports print.

`extract` marks a director's DIN as conflicting (`din_conflict`) when the company's own
certificate of non-disqualification disagrees with its director table: TCS's certificate
gives Al-Noor Ramji the DIN its director table gives Don Callahan. This step gathers every
DIN printed next to that person's name, in the same report's governance section and in the
other pilot reports' extracted director facts, and records the outcome on the fact as
`din_resolution`. Only DINs printed in these reports are used; both DINs stay on record.
Re-run it after `extract`, which rewrites the facts files.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from src.extract.extractor import _norm_person, load_facts, save_facts
from src.ingest.companies import Company

NAME_DIN_RE = r"{name}\W{{0,12}}(?:\([^)]*\)\W{{0,6}})?(?:DIN\s*(?:No\.?)?\s*[:\-]?\s*)?\(?(\d{{8}})"


@dataclass
class DinFinding:
    company: str
    person_name: str
    din: str
    conflict: dict
    same_report: Counter = field(default_factory=Counter)  # DIN -> mentions outside the certificate
    other_reports: list[tuple[str, str, int | None]] = field(default_factory=list)  # (symbol, DIN, page)
    resolved_din: str | None = None
    basis: str = ""


def _mentions(text: str, name: str) -> list[str]:
    """DINs printed right after `name` ("Al-Noor Ramji (DIN 00230865)", "Al-Noor Ramji DIN: 00230865")."""
    flat = " ".join(text.split())
    pattern = NAME_DIN_RE.format(name=re.escape(name))
    return re.findall(pattern, flat, re.I)


def check_dins(extracted_dir: Path, sections_dir: Path, companies: list[Company], apply: bool = False) -> list[DinFinding]:
    facts = {c.nse_symbol: load_facts(extracted_dir / f"{c.nse_symbol}.jsonl")
             for c in companies if (extracted_dir / f"{c.nse_symbol}.jsonl").exists()}
    findings = []
    for symbol, company_facts in facts.items():
        cg_path = sections_dir / symbol / "corporate_governance.json"
        pages = json.loads(cg_path.read_text(encoding="utf-8"))["pages"] if cg_path.exists() else []
        changed = False
        for i, f in enumerate(company_facts):
            if f.fact_type != "director" or not f.data.get("din_conflict"):
                continue
            name = f.data["person_name"]
            finding = DinFinding(symbol, name, f.data["din"], f.data["din_conflict"])
            cert_page = f.data["din_conflict"].get("certificate_page")
            for p in pages:
                if p["page"] != cert_page:
                    finding.same_report.update(_mentions(p["text"], name))
            for other, other_facts in facts.items():
                if other == symbol:
                    continue
                for g in other_facts:
                    if g.fact_type == "director" and g.data.get("din") and _norm_person(g.data["person_name"]) == _norm_person(name):
                        finding.other_reports.append((other, g.data["din"], g.page))

            votes = set(finding.same_report) | {d for _, d, _ in finding.other_reports}
            if len(votes) == 1:
                finding.resolved_din = votes.pop()
                finding.basis = (f"{sum(finding.same_report.values())} mention(s) elsewhere in {symbol}'s report"
                                 + (f"; {', '.join(f'{s} p.{p}' for s, _, p in finding.other_reports)}"
                                    if finding.other_reports else "; no other pilot report lists this person"))
            elif votes:
                finding.basis = f"sources disagree: {sorted(votes)}"
            else:
                finding.basis = "no DIN printed for this name outside the certificate"
            findings.append(finding)

            if apply:
                resolution = {"din": finding.resolved_din, "basis": finding.basis}
                data = {**f.data, "din_resolution": resolution}
                if finding.resolved_din and finding.resolved_din != f.data["din"]:
                    data["din_conflict"] = {**f.data["din_conflict"], "table_din": f.data["din"]}
                    data["din"] = finding.resolved_din
                company_facts[i] = type(f)(f.fact_type, f.method, f.company, f.nse_symbol, f.section_type,
                                           f.page, f.fy, data, f.evidence)
                changed = True
        if apply and changed:
            save_facts(extracted_dir / f"{symbol}.jsonl", company_facts)
    return findings
