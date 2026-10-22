"""Dates no report can contain: a director's or KMP's appointment or cessation dated after
the report itself was produced.

The report's date is its PDF's last-modified date (falling back to its creation date): the
file cannot record an event after it was last saved. Where a fact carries such a date and
another mention of the same person gives the same field a possible date, that date is used
and the conflict is kept on the fact as `date_conflict`; with no other mention, the date is
left as printed and only flagged. (Tata Consumer p.295 prints "upto October 31, 2024" for
L Krishnakumar in a report saved on May 21, 2024; pp.289 and 317 say October 31, 2023.)
"""

from __future__ import annotations

import datetime
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from src.extract.tables import parse_date

if TYPE_CHECKING:
    from src.extract.extractor import Fact

DATE_FIELDS = ("appointed_on", "ceased_on")


def report_date(pdf_path: Path) -> datetime.date | None:
    """The PDF's last-modified date, else its creation date ("D:20240521224206+05'30'")."""
    import pymupdf

    with pymupdf.open(pdf_path) as doc:
        meta = doc.metadata or {}
    for key in ("modDate", "creationDate"):
        value = (meta.get(key) or "").removeprefix("D:")
        try:
            return datetime.date(int(value[0:4]), int(value[4:6]), int(value[6:8]))
        except ValueError:
            continue
    return None


def _person_key(f: Fact, din_by_name: dict[str, str]) -> str | None:
    from src.extract.extractor import _norm_person

    name = f.data.get("person_name")
    if not name:
        return None
    din = f.data.get("din") or din_by_name.get(_norm_person(name))
    return f"din:{din}" if din else f"name:{_norm_person(name)}"


def fix_impossible_dates(facts: list[Fact], published_on: datetime.date | None, symbol: str,
                         merge_overrides: list[dict] = ()) -> tuple[list[Fact], list[str]]:
    """Replace each date later than `published_on` with the same person's other mention of
    that field (people are matched by DIN, by a hand-confirmed merge, or by name), keeping
    `date_conflict` on the fact. Returns (facts, notes)."""
    from src.extract.extractor import Fact, _norm_person

    if published_on is None:
        return facts, []
    din_by_name = {_norm_person(o["from_name"]): o["to_din"] for o in merge_overrides
                   if o.get("nse_symbol") == symbol and o.get("to_din")}
    din_by_name.update({_norm_person(f.data["person_name"]): f.data["din"]
                        for f in facts if f.fact_type == "director" and f.data.get("din")})

    def possible(value) -> bool:
        d = parse_date(value) if isinstance(value, str) else None
        return d is not None and d <= published_on

    out, notes = list(facts), []
    for i, f in enumerate(facts):
        for field in DATE_FIELDS:
            value = f.data.get(field)
            date = parse_date(value) if isinstance(value, str) else None
            if date is None or date <= published_on:
                continue
            key = _person_key(f, din_by_name)
            others = Counter(g.data[field] for g in facts
                             if g is not f and _person_key(g, din_by_name) == key and possible(g.data.get(field)))
            where = f"{f.fact_type} {f.data.get('person_name')} {field} '{value}' (p.{f.page})"
            if not others:
                notes.append(f"date after the report's date ({published_on.isoformat()}), no other mention, "
                             f"left as printed: {where}")
                continue
            chosen = others.most_common(1)[0][0]
            pages = sorted({g.page for g in facts if _person_key(g, din_by_name) == key and g.data.get(field) == chosen})
            conflict = {"field": field, "as_printed": value, "page": f.page,
                        "reason": f"after the report's date ({published_on.isoformat()}, PDF last saved)",
                        "other_mention": chosen, "other_pages": pages}
            data = {**out[i].data, field: chosen, "date_conflict": conflict}
            out[i] = Fact(**{**out[i].__dict__, "data": data})
            notes.append(f"date after the report's date ({published_on.isoformat()}): {where} -> '{chosen}' "
                         f"(as on p.{', p.'.join(map(str, pages))})")
    return out, notes
