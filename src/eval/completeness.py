"""Completeness of extracted subsidiaries and directors, counted independently from the
section text (none of the extraction code's own parsing or prompts is involved).

- Subsidiaries: Form AOC-1 Part A numbers its rows. A row is a line holding exactly the
  next serial number (or the number followed by the name), before any "Part B". Each
  extracted subsidiary's name is then located in the text, on its own page, to find which
  row it came from: rows with no extracted name are missing, names outside any row (or a
  second name in one row) are extras.
- Directors: the certificate of non-disqualification lists the board on March 31 with
  DINs. Every certificate director should be extracted; every other extracted director
  should be explained by having ceased during the year or joined after it.
"""

from __future__ import annotations

import bisect
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.extract.extractor import _norm_person, load_facts
from src.extract.tables import parse_din_certificate

PART_B_RE = re.compile(r"part\s*[-–]?\s*[\"'‘“]?\s*b\b", re.I)


@dataclass
class SubsidiaryCheck:
    rows: int
    extracted: int
    missing: list[tuple[int, str]] = field(default_factory=list)  # (row number, start of row text)
    extra: list[str] = field(default_factory=list)


@dataclass
class DirectorCheck:
    certificate: int
    extracted: int
    on_certificate: int = 0
    ceased_in_year: list[str] = field(default_factory=list)
    after_fy_end: list[str] = field(default_factory=list)
    unexplained: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)  # certificate directors not extracted
    without_din: list[str] = field(default_factory=list)


def _flat(line: str) -> str:
    return " ".join(line.split())


def check_subsidiaries(section: dict, facts: list) -> SubsidiaryCheck:
    lines, line_page = [], []
    for p in section["pages"]:
        for line in p["text"].split("\n"):
            lines.append(line)
            line_page.append(p["page"])
    rows, row_idx, expected = [], [], 1
    end = len(lines)
    for i, line in enumerate(lines):
        if PART_B_RE.search(line):
            end = i
            break
        same_line = re.fullmatch(rf"{expected}\.?\s+([A-Za-z0-9].*)", line)
        on_next = re.fullmatch(rf"{expected}\.?", line) and i + 1 < len(lines) and re.search(r"[A-Za-z]{2}", lines[i + 1])
        if same_line or on_next:
            rows.append((expected, _flat(same_line.group(1) if same_line else lines[i + 1])))
            row_idx.append(i)
            expected += 1

    flat_lines = [_flat(line) for line in lines]
    offsets, pos = [], 0
    for fl in flat_lines:
        offsets.append(pos)
        pos += len(fl) + 1
    flat = " ".join(flat_lines)
    row_starts = [offsets[i] for i in row_idx]
    part_a_end = offsets[end] if end < len(lines) else len(flat)
    page_span = {}
    for i, page in enumerate(line_page):
        lo, hi = page_span.get(page, (offsets[i], offsets[i]))
        page_span[page] = (min(lo, offsets[i]), max(hi, offsets[i] + len(flat_lines[i])))

    subs = [f for f in facts if f.fact_type == "subsidiary"]
    claimed: dict[int, list[str]] = {}
    extra = []
    for f in subs:
        name = _flat(f.data["subsidiary_name"])
        lo, hi = page_span.get(f.page, (0, len(flat)))
        hits = [m.start() for m in re.finditer(re.escape(name), flat[lo:hi])]
        rows_hit = [bisect.bisect_right(row_starts, lo + h) for h in hits if lo + h < part_a_end]
        rows_hit = [r for r in rows_hit if r > 0]
        if not rows_hit:
            extra.append(f"{name} (p.{f.page}): {'not found verbatim' if not hits else 'outside the numbered rows'}")
            continue
        row = next((r for r in rows_hit if r not in claimed), rows_hit[0])
        claimed.setdefault(row, []).append(name)
    for row, names in claimed.items():
        extra.extend(f"{n}: second name in row {row}" for n in names[1:])
    missing = [rows[r - 1] for r in range(1, len(rows) + 1) if r not in claimed]
    # A name not found verbatim (different quote marks, a footnote marker) may still be
    # the one missing row; pair them up only when the counts say so, for the report.
    return SubsidiaryCheck(len(rows), len(subs), missing, extra)


def check_directors(section: dict, facts: list) -> DirectorCheck:
    cert = []
    for p in section["pages"]:
        cert.extend(parse_din_certificate(p["text"]))
    directors = [f.data for f in facts if f.fact_type == "director"]
    cert_names = {_norm_person(r["name"]): r for r in cert}
    cert_dins = {r["din"]: r for r in cert}
    extracted_names = {_norm_person(d["person_name"]) for d in directors}

    check = DirectorCheck(len(cert), len(directors))
    matched = set()
    for d in directors:
        name, din = _norm_person(d["person_name"]), d.get("din")
        row = cert_names.get(name)
        if row is None and din in cert_dins and _norm_person(cert_dins[din]["name"]) not in extracted_names:
            row = cert_dins[din]  # the certificate spells the name differently (full legal name)
        label = f"{d['person_name']} ({din or 'no DIN'})"
        if not din:
            check.without_din.append(label)
        if row is not None and d.get("status") != "ceased":
            check.on_certificate += 1
            matched.add(row["din"])
        elif d.get("status") == "ceased":
            check.ceased_in_year.append(f"{label}, ceased {d.get('ceased_on') or '(date not stated)'}")
        elif d.get("after_fy_end"):
            check.after_fy_end.append(f"{label}, appointed {d.get('appointed_on')}")
        else:
            check.unexplained.append(f"{label}, status {d.get('status')}")
    check.missing = [f"{r['name']} ({r['din']})" for r in cert if r["din"] not in matched]
    return check


def check_company(sections_dir: Path, extracted_dir: Path, symbol: str) -> tuple[SubsidiaryCheck | None, DirectorCheck | None]:
    facts = load_facts(extracted_dir / f"{symbol}.jsonl")

    def section(kind):
        path = sections_dir / symbol / f"{kind}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    aoc1, cg = section("subsidiaries_aoc1"), section("corporate_governance")
    return (check_subsidiaries(aoc1, facts) if aoc1 else None, check_directors(cg, facts) if cg else None)
