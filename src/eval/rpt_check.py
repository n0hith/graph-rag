"""Check saved related-party facts' amounts against the PDF pages (no LLM calls), and
record `amount_as_printed` on the facts that pass. The check itself is
`src.extract.amounts`; extraction runs it on new facts too."""

from __future__ import annotations

import json
from pathlib import Path

from src.extract.amounts import AmountCheck, check_amounts, with_checked_amount
from src.extract.extractor import load_facts, save_facts
from src.ingest.companies import Company


def check_related_party(extracted_dir: Path, sections_dir: Path, raw_pdf_dir: Path, companies: list[Company],
                        apply: bool = True) -> list[AmountCheck]:
    """Check every company's related-party amounts; with `apply`, write `amount_as_printed`
    onto facts that pass (and move a fact to the page its row is actually on)."""
    results: list[AmountCheck] = []
    for c in companies:
        f_path = extracted_dir / f"{c.nse_symbol}.jsonl"
        s_path = sections_dir / c.nse_symbol / "related_party.json"
        if not f_path.exists() or not s_path.exists():
            continue
        section = json.loads(s_path.read_text(encoding="utf-8"))
        pdf_path = raw_pdf_dir / section["source_pdf"]
        facts = load_facts(f_path)
        updated = list(facts)
        for i, status, page, cell, basis, detail in check_amounts(facts, pdf_path, [p["page"] for p in section["pages"]]):
            f = facts[i]
            results.append(AmountCheck(c.nse_symbol, i, f.data.get("party_name", ""), f.data.get("nature", ""),
                                       f.data.get("amount_inr_crore"), f.page, status, page,
                                       cell.printed if cell else None, basis, detail))
            updated[i] = with_checked_amount(f, page, cell)
        if apply:
            save_facts(f_path, updated)
            run_path = extracted_dir / f"{c.nse_symbol}.run.json"
            if run_path.exists():
                run = json.loads(run_path.read_text(encoding="utf-8"))
                run["notes"] = [n for n in run.get("notes", []) if not n.startswith("amount not verified")] + [
                    f"amount not verified on the page: {r.party_name} / {r.nature} = {r.amount} (p.{r.cited_page}): {r.detail}"
                    for r in results if r.symbol == c.nse_symbol and r.status == "fail"]
                run_path.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    return results
