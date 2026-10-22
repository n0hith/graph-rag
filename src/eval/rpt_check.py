"""Apply the page checks to saved facts (no LLM calls): related-party amounts
(`src.extract.amounts`: `amount_as_printed`, relabelled natures, nil rows and struck-off
companies removed) and impossible dates (`src.extract.dates`). Extraction runs the same
checks on new facts."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from src.extract.amounts import AmountCheck, apply_checks, check_amounts
from src.extract.cleanup import clean_facts
from src.extract.dates import fix_impossible_dates, report_date
from src.extract.extractor import DroppedFact, load_facts, load_merge_overrides, save_facts
from src.ingest.companies import Company

AMOUNT_NOTE_PREFIXES = ("amount not verified", "nature relabelled", "related party with no amount")
DATE_NOTE_PREFIX = "date after the report's date"


def _update_run(run_path: Path, note_prefixes: tuple[str, ...], notes: list[str],
                dropped: list[DroppedFact] = ()) -> None:
    """Replace this check's notes in a company's run record and add what it removed."""
    if not run_path.exists():
        return
    run = json.loads(run_path.read_text(encoding="utf-8"))
    run["notes"] = [n for n in run.get("notes", []) if not n.startswith(note_prefixes)] + notes
    run["dropped"] = run.get("dropped", []) + [asdict(d) for d in dropped]
    run_path.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")


def check_related_party(extracted_dir: Path, sections_dir: Path, raw_pdf_dir: Path, companies: list[Company],
                        apply: bool = True) -> list[AmountCheck]:
    """Check every company's related-party amounts. With `apply`, act on the results (see
    `apply_checks`) and save; the returned checks are those of the facts before that."""
    results: list[AmountCheck] = []
    for c in companies:
        f_path = extracted_dir / f"{c.nse_symbol}.jsonl"
        s_path = sections_dir / c.nse_symbol / "related_party.json"
        if not f_path.exists() or not s_path.exists():
            continue
        section = json.loads(s_path.read_text(encoding="utf-8"))
        pdf_path = raw_pdf_dir / section["source_pdf"]
        facts = load_facts(f_path)
        for i, status, page, cell, basis, detail in check_amounts(facts, pdf_path, [p["page"] for p in section["pages"]]):
            f = facts[i]
            results.append(AmountCheck(c.nse_symbol, i, f.data.get("party_name", ""), f.data.get("nature", ""),
                                       f.data.get("amount_inr_crore"), f.page, status, page,
                                       cell.printed if cell else None, basis, detail))
        if apply:
            kept, removed, notes = apply_checks(facts, pdf_path, section["pages"])
            save_facts(f_path, kept)
            _update_run(extracted_dir / f"{c.nse_symbol}.run.json", AMOUNT_NOTE_PREFIXES, notes,
                        [DroppedFact(f.fact_type, f.section_type, reason, f.evidence, f.data) for f, reason in removed])
    return results


def check_dates(extracted_dir: Path, raw_pdf_dir: Path, companies: list[Company], overrides_path: Path,
                apply: bool = True) -> dict[str, list[str]]:
    """Fix dates later than each report's own date (see `fix_impossible_dates`). Returns the
    notes per company."""
    overrides = load_merge_overrides(overrides_path)
    out = {}
    for c in companies:
        f_path = extracted_dir / f"{c.nse_symbol}.jsonl"
        pdf_path = raw_pdf_dir / f"{c.nse_symbol}.pdf"
        if not f_path.exists() or not pdf_path.exists():
            continue
        facts, notes = fix_impossible_dates(load_facts(f_path), report_date(pdf_path), c.nse_symbol, overrides)
        out[c.nse_symbol] = notes
        if apply:
            save_facts(f_path, facts)
            _update_run(extracted_dir / f"{c.nse_symbol}.run.json", (DATE_NOTE_PREFIX,), notes)
    return out


def clean_saved_facts(extracted_dir: Path, sections_dir: Path, companies: list[Company],
                      apply: bool = True) -> dict[str, tuple[list[str], dict]]:
    """Names, directorship pages, KMP after the year end, director roles (src/extract/cleanup.py).
    Returns the notes and name counts per company."""
    out = {}
    for c in companies:
        f_path = extracted_dir / f"{c.nse_symbol}.jsonl"
        s_path = sections_dir / c.nse_symbol / "corporate_governance.json"
        if not f_path.exists():
            continue
        pages = json.loads(s_path.read_text(encoding="utf-8"))["pages"] if s_path.exists() else []
        facts, notes, counts = clean_facts(load_facts(f_path), pages)
        out[c.nse_symbol] = (notes, counts)
        if apply:
            save_facts(f_path, facts)
            _update_run(extracted_dir / f"{c.nse_symbol}.run.json", ("cleanup:",), [f"cleanup: {n}" for n in notes])
    return out
