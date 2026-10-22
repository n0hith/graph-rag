"""Write reports/extraction_summary.md: the tracked record of an extraction run.

Raw facts (data/extracted/*.jsonl) stay gitignored; this file is what gets committed with
each run's results: fact counts, drops with examples, merges, director checks, DIN
conflicts, regressions, the completeness table and the cross-report directorship check.
"""

from __future__ import annotations

import datetime
import json
import subprocess
from collections import Counter
from pathlib import Path

from src.eval.completeness import check_company
from src.eval.directorship_check import check_directorships
from src.eval.rpt_check import check_related_party
from src.extract.amounts import NIL_REASON, STRUCK_OFF_REASON
from src.extract.extractor import load_facts
from src.ingest.companies import Company


def _git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _bullets(items: list[str], limit: int | None = None) -> list[str]:
    shown = items if limit is None else items[:limit]
    out = [f"- {i}" for i in shown]
    if limit is not None and len(items) > limit:
        out.append(f"- … {len(items) - limit} more (see data/extracted/<SYMBOL>.run.json)")
    return out


def write_summary(path: Path, extracted_dir: Path, sections_dir: Path, companies: list[Company],
                  known_gaps: list[str] = (), raw_pdf_dir: Path | None = None) -> Path:
    lines = [
        "# Extraction summary",
        "",
        f"Generated {datetime.date.today().isoformat()} from code at commit `{_git_head()}`. Raw facts are in "
        "`data/extracted/` (gitignored); this file is the tracked record.",
        "",
    ]
    runs = {}
    facts = {}
    for c in companies:
        f_path, r_path = extracted_dir / f"{c.nse_symbol}.jsonl", extracted_dir / f"{c.nse_symbol}.run.json"
        facts[c.nse_symbol] = load_facts(f_path) if f_path.exists() else []
        runs[c.nse_symbol] = json.loads(r_path.read_text(encoding="utf-8")) if r_path.exists() else {}

    # ---- counts
    types = sorted({f.fact_type for fs in facts.values() for f in fs})
    lines += ["## Facts per company", "", "| Company | " + " | ".join(types) + " | total | LLM calls (last run) |",
              "|---|" + "---|" * (len(types) + 2)]
    for c in companies:
        fs = facts[c.nse_symbol]
        by = Counter((f.fact_type, f.method) for f in fs)
        cells = []
        for t in types:
            table, llm = by.get((t, "table"), 0), by.get((t, "llm"), 0)
            cells.append(" + ".join(x for x in [f"{table} table" if table else "", f"{llm} LLM" if llm else ""] if x) or "0")
        lines.append(f"| {c.nse_symbol} | " + " | ".join(cells) + f" | {len(fs)} | {runs[c.nse_symbol].get('calls_used', '?')} |")
    lines.append("")

    # ---- completeness
    lines += ["## Completeness (counted independently from the section text)", "",
              "Subsidiaries: numbered AOC-1 Part A rows vs extracted, with each extracted name located in its row. "
              "Directors: the certificate of non-disqualification (board on March 31) vs extracted; every extracted "
              "director not on it must have ceased during the year or joined after it.", "",
              "| Company | AOC-1 rows | Subsidiaries extracted | Rows missing | Extras | Certificate | Directors extracted "
              "| On certificate | Ceased in FY | After FY end | Unexplained | Certificate not extracted | No DIN |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    details = []
    for c in companies:
        subs, dirs = check_company(sections_dir, extracted_dir, c.nse_symbol)
        s = subs or type("x", (), {"rows": "–", "extracted": "–", "missing": [], "extra": []})()
        lines.append(
            f"| {c.nse_symbol} | {s.rows} | {s.extracted} | {len(s.missing)} | {len(s.extra)} | {dirs.certificate} "
            f"| {dirs.extracted} | {dirs.on_certificate} | {len(dirs.ceased_in_year)} | {len(dirs.after_fy_end)} "
            f"| {len(dirs.unexplained)} | {len(dirs.missing)} | {len(dirs.without_din)} |")
        items = ([f"AOC-1 row {r} not extracted: {t[:70]}" for r, t in s.missing]
                 + [f"extra subsidiary: {e}" for e in s.extra]
                 + [f"ceased in FY: {x}" for x in dirs.ceased_in_year]
                 + [f"appointed after FY end: {x}" for x in dirs.after_fy_end]
                 + [f"UNEXPLAINED director: {x}" for x in dirs.unexplained]
                 + [f"certificate director not extracted: {x}" for x in dirs.missing]
                 + [f"director without DIN: {x}" for x in dirs.without_din])
        if items:
            details += [f"**{c.nse_symbol}**", ""] + _bullets(items) + [""]
    lines += [""] + details

    # ---- DIN conflicts
    conflicts = [(c.nse_symbol, f) for c in companies for f in facts[c.nse_symbol]
                 if f.fact_type == "director" and f.data.get("din_conflict")]
    lines += ["## DIN conflicts", ""]
    if not conflicts:
        lines.append("None.")
    for symbol, f in conflicts:
        res = f.data.get("din_resolution") or {}
        lines.append(f"- {symbol}: **{f.data['person_name']}** DIN {f.data['din']}; conflict {f.data['din_conflict']}; "
                     f"resolution: {res.get('din') or 'unresolved'} ({res.get('basis', 'run check-dins')})")
    lines.append("")

    # ---- related-party amounts on the page
    if raw_pdf_dir is not None:
        amount_checks = check_related_party(extracted_dir, sections_dir, raw_pdf_dir, companies, apply=False)
        by = Counter((r.symbol, r.status) for r in amount_checks)
        bases = Counter((r.symbol, r.basis.split(";")[0]) for r in amount_checks if r.status == "pass")
        removed = Counter((c.nse_symbol, d["reason"]) for c in companies for d in runs[c.nse_symbol].get("dropped", [])
                          if d["fact_type"] == "related_party")
        lines += ["## Related-party amounts checked on the page (no LLM)", "",
                  "Each amount must be the FY2024 figure on its party's row (matrix tables: the nature's row, under the "
                  "party's column), and in list tables the row must sit under the fact's nature heading (carried over a "
                  "column or page break). Passing facts carry `amount_as_printed`. Amounts are compared exactly, in crore "
                  "as printed. A fact whose amount sits under exactly one other printed heading is relabelled to it "
                  "(`nature_as_extracted` keeps the old nature). Rows whose FY2024 cell is a dash (nil) are not stored as "
                  "transactions, nor are the companies in Tata Motors' 'Transactions with struck off companies' table "
                  "(external vendors and customers).", "",
                  "| Company | Related-party facts | Pass | Relabelled | Fail | No amount | Nil rows removed "
                  "| Struck-off removed |", "|---|---|---|---|---|---|---|---|"]
        for c in companies:
            n = sum(r.symbol == c.nse_symbol for r in amount_checks)
            relabelled = sum(f.fact_type == "related_party" and "nature_as_extracted" in f.data for f in facts[c.nse_symbol])
            lines.append(f"| {c.nse_symbol} | {n} | {by[(c.nse_symbol, 'pass')]} | {relabelled} | {by[(c.nse_symbol, 'fail')]} "
                         f"| {by[(c.nse_symbol, 'no_amount')]} | {removed[(c.nse_symbol, NIL_REASON)]} "
                         f"| {removed[(c.nse_symbol, STRUCK_OFF_REASON)]} |")
        lines += ["", "How each pass was decided:", ""]
        lines += _bullets([f"{symbol}: {basis}: {n}" for (symbol, basis), n in sorted(bases.items())])
        relabels = [f"{c.nse_symbol} p.{f.page}: {f.data['party_name']} = {f.data.get('amount_as_printed')}: "
                    f"'{f.data['nature_as_extracted']}' -> '{f.data['nature']}'"
                    for c in companies for f in facts[c.nse_symbol] if "nature_as_extracted" in f.data]
        lines += ["", f"Relabelled ({len(relabels)}):", ""] + (_bullets(relabels) if relabels else ["None."])
        fails = [f"{r.symbol} p.{r.cited_page}: {r.party_name} / {r.nature} = {r.amount}: {r.detail}"
                 for r in amount_checks if r.status in ("fail", "relabel", "nil", "no_amount")]
        lines += ["", f"Not passing ({len(fails)}):", ""] + (_bullets(fails) if fails else ["None."]) + [""]

    # ---- impossible dates
    conflicts = [(c.nse_symbol, f) for c in companies for f in facts[c.nse_symbol] if f.data.get("date_conflict")]
    lines += ["## Dates later than the report itself", "",
              "A date after the report's own date (its PDF's last-saved date) cannot be right; the same person's other "
              "mention is used and the printed date kept as `date_conflict`.", ""]
    lines += _bullets([f"{symbol}: {f.fact_type} {f.data.get('person_name')} (p.{f.page}): {d['field']} printed "
                       f"'{d['as_printed']}', {d['reason']}; now '{d['other_mention']}' as on p."
                       f"{', p.'.join(map(str, d['other_pages']))}"
                       for symbol, f in conflicts for d in [f.data["date_conflict"]]]) or ["None."]
    lines.append("")

    # ---- cross-report directorships
    checks = check_directorships(extracted_dir, companies)
    status = Counter(ch.status for ch in checks)
    lines += ["## Cross-report directorships (check-directorships)", "",
              f"{len(checks)} claims that a director sits on another pilot company's board: "
              + ", ".join(f"{n} {s}" for s, n in sorted(status.items())), ""]
    for ch in sorted(checks, key=lambda ch: (ch.status == "match", ch.reported_by, ch.target, ch.person_name)):
        lines.append(f"- [{ch.status}] {ch.reported_by} says {ch.person_name} (DIN {ch.din or '?'}) is on {ch.target}'s "
                     f"board ({ch.category or 'no category'}). {ch.detail}")
    lines.append("")

    # ---- per-company run details
    lines += ["## Run details per company", ""]
    for c in companies:
        run = runs[c.nse_symbol]
        if not run:
            continue
        dropped = run.get("dropped", [])
        reasons = Counter(d["reason"] for d in dropped)
        lines += [f"### {c.nse_symbol}", "",
                  f"Dropped: {len(dropped)}" + (" (" + "; ".join(f"{n}× {r}" for r, n in reasons.items()) + ")" if dropped else "")]
        lines += _bullets([f"[{d['fact_type']}] {d['reason']}: {json.dumps(d['evidence'][:90], ensure_ascii=False)}"
                           for d in dropped], 5)
        for title, key in [("Merges", "merges"), ("Possible matches not merged", "ambiguous"),
                           ("Director and amount checks", "notes"),
                           ("Regressions / key-field changes vs previous run", "regressions")]:
            if run.get(key):
                lines += ["", f"{title}:"] + _bullets(run[key], 12)
        if run.get("partial_runs"):
            lines += ["", "Partial re-runs since the last full run:"] + _bullets([
                f"{r['date']}: {', '.join(r['sections'])}: {r['calls_used']} LLM calls, {r['facts']} facts"
                + (f"; regressions: {'; '.join(r['regressions'])}" if r["regressions"] else "; no regressions")
                for r in run["partial_runs"]])
        lines.append("")

    if known_gaps:
        lines += ["## Known gaps", ""] + _bullets(list(known_gaps)) + [""]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
