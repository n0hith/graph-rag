"""Command-line interface. Run with: python -m src.cli --help"""

from __future__ import annotations

import time

import typer
from pathlib import Path
from google.genai.errors import APIError
from pydantic import BaseModel, Field

from src.config import get_settings, setup_logging
from src.ingest.companies import Company, load_companies, select_companies
from src.llm.client import LLMClient, LLMError, build_client
from src.llm.rate_limiter import DailyLimitReached

app = typer.Typer(help="Graph RAG over Indian company annual reports.", no_args_is_help=True)


@app.callback()
def main(log_level: str = typer.Option(None, help="Override LOG_LEVEL (DEBUG, INFO, WARNING).")) -> None:
    """Set up logging before any command runs."""
    setup_logging(log_level or get_settings().log_level)


# ---------------------------------------------------------------- pipeline steps


def _companies(symbols: list[str] | None) -> list[Company]:
    settings = get_settings()
    try:
        return select_companies(load_companies(settings.companies_csv), symbols)
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1)


@app.command()
def download(
    company: list[str] = typer.Option(None, "--company", "-c", help="NSE symbol; repeat for several. Default: all."),
    force: bool = typer.Option(False, help="Download again even if the file is already there."),
) -> None:
    """Download annual report PDFs listed in data/companies.csv."""
    from src.ingest.download import Status, download_all

    settings = get_settings()
    results = download_all(_companies(company), settings.raw_pdf_dir, settings.checksum_file, force=force)
    colors = {Status.DOWNLOADED: typer.colors.GREEN, Status.SKIPPED: None}
    for r in results:
        size = f"{r.size / 1e6:.1f} MB" if r.size else ""
        line = f"{r.company.nse_symbol:<11} {r.status.value:<20} {size:>9}  {r.message}"
        typer.secho(line.rstrip(), fg=colors.get(r.status, typer.colors.RED))
    bad = [r for r in results if r.status not in colors]
    if bad:
        raise typer.Exit(code=1)


@app.command()
def sectionize(
    company: list[str] = typer.Option(None, "--company", "-c", help="NSE symbol; repeat for several. Default: all."),
    force: bool = typer.Option(False, help="Redo companies that were already sectionized."),
) -> None:
    """Find the relevant sections (directors, subsidiaries, auditors, ...) in each PDF."""
    from src.ingest.sectionize import SECTION_TYPES, sectionize_company

    settings = get_settings()
    problems = 0
    for c in _companies(company):
        pdf = settings.raw_pdf_dir / c.pdf_name
        if not pdf.exists():
            typer.secho(f"{c.nse_symbol}: {pdf.name} not downloaded yet (run `download`)", fg=typer.colors.RED)
            problems += 1
            continue
        r = sectionize_company(c, pdf, settings.sections_dir, force=force)
        found = len(r.detection.sections)
        note = " (already done, skipped)" if r.skipped else ""
        typer.secho(f"\n{c.nse_symbol}: {found}/{len(SECTION_TYPES)} sections, {r.page_count} pages{note}", bold=True)
        if r.cin.cin == c.cin:
            typer.echo(f"  CIN {r.cin.cin} found {r.cin.count}x, matches companies.csv")
        else:
            typer.secho(f"  CIN mismatch: report has {r.cin.cin} ({r.cin.count}x), companies.csv has {c.cin or 'nothing'}",
                        fg=typer.colors.YELLOW)
            problems += 1
        for kind in SECTION_TYPES:
            s = r.detection.sections.get(kind)
            if s:
                typer.echo(f"  found    {kind:<21} pages {s.page_start}-{s.page_end}")
            else:
                typer.secho(f"  MISSING  {kind:<21} {r.detection.missing.get(kind, '')}", fg=typer.colors.RED)
                problems += 1
        for sub in r.detection.subsidiary_secretarial:
            typer.echo(f"  found    secretarial_audit (subsidiary: {sub.subsidiary_name}) pages {sub.page_start}-{sub.page_end}")
    typer.echo(f"\nSections saved under {settings.sections_dir}")
    if problems:
        raise typer.Exit(code=1)


@app.command()
def extract(
    company: list[str] = typer.Option(None, "--company", "-c", help="NSE symbol; repeat for several. Default: all."),
    sample_size: int = typer.Option(20, help="How many facts to export to CSV for hand-checking (0: don't export)."),
    accept_fewer: bool = typer.Option(
        False, help="Keep a re-run's results even where it found fewer facts than the previous run."
    ),
    section: list[str] = typer.Option(
        None, "--section", help="Only re-run this section type (e.g. related_party); repeat for several. "
                                "Other sections keep their saved facts."
    ),
) -> None:
    """Extract facts from sectionized reports, with table parsing tried before the LLM.

    Where a re-run finds fewer facts of a type in a section than the saved previous run,
    the previous facts are kept and the drop is flagged (unless --accept-fewer)."""
    import datetime
    import json
    from collections import Counter

    from dataclasses import asdict

    from src.extract.extractor import (
        ExtractionResult,
        estimate_calls,
        extract_company,
        keep_previous_if_fewer,
        load_facts,
        load_merge_overrides,
        save_facts,
    )
    from src.eval.sample_facts import export_sample
    from src.llm.client import UsageTracker

    settings = get_settings()
    companies = _companies(company)

    only = set(section) if section else None
    section_keys = {"directors": "corporate_governance", "kmp": "corporate_governance",
                    "subsidiaries": "subsidiaries_aoc1", "auditor_statutory": "auditor_report",
                    "auditor_secretarial": "secretarial_audit", "related_party": "related_party"}
    estimates = {c.nse_symbol: {k: v for k, v in estimate_calls(settings.sections_dir, c.nse_symbol).items()
                                if only is None or section_keys[k] in only}
                 for c in companies}
    typer.secho("Estimated Gemini calls:", bold=True)
    total_estimate = 0
    for symbol, breakdown in estimates.items():
        subtotal = sum(breakdown.values())
        total_estimate += subtotal
        typer.echo(f"  {symbol:<11} {subtotal:<4} ({', '.join(f'{k}={v}' for k, v in breakdown.items())})")
    typer.echo(f"  total: {total_estimate}\n")

    tracker = UsageTracker()
    try:
        client = build_client(settings, purpose="extraction", tracker=tracker)
    except LLMError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    out_dir = settings.data_dir / "extracted"
    out_dir.mkdir(parents=True, exist_ok=True)
    combined = ExtractionResult()
    regressions: list[str] = []
    overrides = load_merge_overrides(settings.data_dir / "overrides" / "merges.csv")
    try:
        for c in companies:
            result = extract_company(c, settings.sections_dir, client, overrides, settings.raw_pdf_dir, only)
            path = out_dir / f"{c.nse_symbol}.jsonl"
            previous = load_facts(path) if path.exists() else []
            untouched = [f for f in previous if only is not None and f.section_type not in only]
            previous = [f for f in previous if only is None or f.section_type in only]
            facts, flags = keep_previous_if_fewer(previous, result.facts, accept_fewer, result.explained_removals)
            regressions.extend(f"{c.nse_symbol}: {flag}" for flag in flags)
            save_facts(path, untouched + facts)
            run_path = out_dir / f"{c.nse_symbol}.run.json"
            run = {
                "calls_used": result.calls_used,
                "dropped": [asdict(d) for d in result.dropped],
                "merges": result.merges,
                "ambiguous": result.ambiguous,
                "notes": result.notes,
                "explained_removals": [[*k, v] for k, v in result.explained_removals.items() if v],
                "regressions": flags,
            }
            if only is not None and run_path.exists():
                # A partial re-run: keep the last full run's record for the other sections.
                last = json.loads(run_path.read_text(encoding="utf-8"))
                mine = lambda text: any(name in text for name in only)
                run = {
                    **last,
                    "dropped": [d for d in last.get("dropped", []) if d["section_type"] not in only] + run["dropped"],
                    "notes": [n for n in last.get("notes", []) if not n.startswith(("amount not verified", "related-party amounts"))]
                             + result.notes,
                    "regressions": [r for r in last.get("regressions", []) if not mine(r)] + flags,
                    "partial_runs": last.get("partial_runs", []) + [{
                        "date": datetime.date.today().isoformat(), "sections": sorted(only),
                        "calls_used": result.calls_used, "facts": len(result.facts), "regressions": flags}],
                }
            run_path.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
            facts = untouched + facts
            combined.facts.extend(facts)
            combined.dropped.extend(result.dropped)
            combined.calls_used += result.calls_used
            combined.merges.extend(f"{c.nse_symbol}: {m}" for m in result.merges)
            combined.ambiguous.extend(f"{c.nse_symbol}: {a}" for a in result.ambiguous)
            combined.notes.extend(f"{c.nse_symbol}: {n}" for n in result.notes)
    except (DailyLimitReached, APIError, LLMError) as exc:
        # Companies not reached keep their previous facts file untouched.
        typer.secho(f"\nStopped early: {exc}", fg=typer.colors.YELLOW)

    by_type_method = Counter((f.fact_type, f.method) for f in combined.facts)
    typer.secho("\nFacts extracted:", bold=True)
    for (fact_type, method), n in sorted(by_type_method.items()):
        typer.echo(f"  {fact_type:<15} {method:<6} {n}")
    typer.echo(f"  total: {len(combined.facts)}")

    typer.secho(f"\nDropped (evidence check or a rule; all reasons in <SYMBOL>.run.json): {len(combined.dropped)}", bold=True)
    for d in combined.dropped[:10]:
        typer.echo(f"  [{d.fact_type}/{d.section_type}] {d.reason}: {d.evidence[:100]!r}")

    typer.secho(f"\nDirector copies merged: {len(combined.merges)}", bold=True)
    for m in combined.merges:
        typer.echo(f"  {m}")
    if combined.ambiguous:
        typer.secho(f"\nPossible matches NOT merged: {len(combined.ambiguous)}", bold=True)
        for a in combined.ambiguous:
            typer.echo(f"  {a}")
    if combined.notes:
        typer.secho(f"\nDirector checks: {len(combined.notes)}", bold=True)
        for n in combined.notes:
            typer.echo(f"  {n}")
    if regressions:
        typer.secho(f"\nFewer facts or changed key fields vs the previous run: {len(regressions)}", bold=True, fg=typer.colors.YELLOW)
        for r in regressions:
            typer.secho(f"  {r}", fg=typer.colors.YELLOW)

    typer.echo(f"\nActual Gemini calls used: {combined.calls_used} (estimated {total_estimate})")
    typer.echo(client.tracker.summary())
    typer.echo(f"\nFacts saved under {out_dir}")

    if combined.facts and sample_size:
        sample_path = export_sample(combined.facts, out_dir / "sample_for_review.csv", sample_size)
        typer.secho(f"Sample of {min(sample_size, len(combined.facts))} facts for hand-checking: {sample_path}", bold=True)


@app.command("check-directorships")
def check_directorships_cmd() -> None:
    """Check each report's claims about directorships at other pilot companies against
    those companies' own extracted director lists."""
    from collections import Counter

    from src.eval.directorship_check import check_directorships

    settings = get_settings()
    checks = check_directorships(settings.data_dir / "extracted", _companies(None))
    counts = Counter(c.status for c in checks)
    typer.secho(f"{len(checks)} cross-company directorship claims: "
                + ", ".join(f"{n} {s}" for s, n in sorted(counts.items())), bold=True)
    for c in sorted(checks, key=lambda c: (c.status == "match", c.reported_by, c.target, c.person_name)):
        colour = typer.colors.GREEN if c.status == "match" else typer.colors.YELLOW
        typer.secho(f"  [{c.status}] {c.reported_by} says {c.person_name} (DIN {c.din or '?'}) is on "
                    f"{c.target}'s board ({c.category or 'no category'})", fg=colour)
        if c.detail:
            typer.echo(f"      {c.detail}")


@app.command("sample-facts")
def sample_facts_cmd(
    size: int = typer.Option(50, help="How many facts to sample."),
    seed: int = typer.Option(42, help="Random seed, so the same sample can be drawn again."),
) -> None:
    """Export a hand-check sample spread across companies and fact types, weighted towards
    LLM facts and related-party amounts (data/extracted/sample_for_review.csv)."""
    from collections import Counter

    from src.eval.sample_facts import export_stratified_sample
    from src.extract.extractor import load_facts

    settings = get_settings()
    out_dir = settings.data_dir / "extracted"
    facts = [f for c in _companies(None) if (out_dir / f"{c.nse_symbol}.jsonl").exists()
             for f in load_facts(out_dir / f"{c.nse_symbol}.jsonl")]
    must_include = [
        # New since the hand-check: TCS's p.299 table (Tata Sons group), and Infosys amounts.
        (lambda f: f.nse_symbol == "TCS" and f.fact_type == "related_party" and f.page == 299, 4),
        (lambda f: f.nse_symbol == "INFY" and f.fact_type == "related_party", 5),
    ]
    path = out_dir / "sample_for_review.csv"
    sample = export_stratified_sample(facts, path, size, must_include, seed)
    typer.secho(f"{len(sample)} facts written to {path}", bold=True)
    for (symbol, fact_type, method), n in sorted(Counter((f.nse_symbol, f.fact_type, f.method) for f in sample).items()):
        typer.echo(f"  {symbol:<11} {fact_type:<19} {method:<6} {n}")


@app.command()
def report(
    gap: list[str] = typer.Option(None, "--gap", help="A known gap to list in the summary; repeat for several."),
) -> None:
    """Write reports/extraction_summary.md (tracked) from the latest extraction results."""
    from src.eval.summary import write_summary

    settings = get_settings()
    path = write_summary(settings.data_dir.parent / "reports" / "extraction_summary.md",
                         settings.data_dir / "extracted", settings.sections_dir, _companies(None), gap or [],
                         settings.raw_pdf_dir)
    typer.echo(f"Wrote {path}")


@app.command("check-rpt-amounts")
def check_rpt_amounts_cmd(
    apply: bool = typer.Option(True, help="Write amount_as_printed onto the facts that pass."),
) -> None:
    """Check each saved related-party amount on the PDF page (no LLM calls): the party's row,
    the FY2024 column, under its nature heading. Applying it also relabels a nature found
    under another printed heading and removes nil rows and struck-off companies."""
    from collections import Counter

    from src.eval.rpt_check import check_related_party

    settings = get_settings()
    results = check_related_party(settings.data_dir / "extracted", settings.sections_dir, settings.raw_pdf_dir,
                                  _companies(None), apply)
    counts = Counter((r.symbol, r.status) for r in results)
    typer.secho("Related-party amounts checked on the page:", bold=True)
    for symbol in dict.fromkeys(r.symbol for r in results):
        moved = sum(r.symbol == symbol and r.status != "nil" and r.page not in (None, r.cited_page) for r in results)
        typer.echo(f"  {symbol:<11} pass {counts[(symbol, 'pass')]:<4} relabel {counts[(symbol, 'relabel')]:<3} "
                   f"nil {counts[(symbol, 'nil')]:<3} fail {counts[(symbol, 'fail')]:<3} "
                   f"no amount {counts[(symbol, 'no_amount')]:<3} (page corrected: {moved})")
    for r in results:
        if r.status in ("fail", "relabel", "no_amount"):
            typer.secho(f"  [{r.status}] {r.symbol} p.{r.cited_page} {r.party_name} / {r.nature} = {r.amount}: "
                        f"{r.detail or r.basis}", fg=typer.colors.YELLOW)
    if apply:
        typer.echo("Applied: nil rows and struck-off companies removed (reasons in <SYMBOL>.run.json), "
                   "relabelled natures keep nature_as_extracted.")


@app.command("clean-facts")
def clean_facts_cmd(apply: bool = typer.Option(True, help="Save the cleaned facts.")) -> None:
    """Clean saved facts without LLM calls: names (line breaks, footnote markers), other-directorship
    pages, KMP appointed after the year end, director roles."""
    from src.eval.rpt_check import clean_saved_facts

    settings = get_settings()
    results = clean_saved_facts(settings.data_dir / "extracted", settings.sections_dir, _companies(None), apply)
    for symbol, (notes, counts) in results.items():
        typer.secho(f"{symbol}: names cleaned: {counts['footnote']} with footnote markers, "
                    f"{counts['line_break']} with line breaks; {len(notes)} other change(s)", bold=True)
        for n in notes:
            typer.echo(f"  {n}")


@app.command("check-dates")
def check_dates_cmd(
    apply: bool = typer.Option(True, help="Replace impossible dates and record date_conflict on the fact."),
) -> None:
    """Find appointment/cessation dates later than the report's own date (its PDF's) and take
    the same person's other mention instead (no LLM calls)."""
    from src.eval.rpt_check import check_dates

    settings = get_settings()
    notes = check_dates(settings.data_dir / "extracted", settings.raw_pdf_dir, _companies(None),
                        settings.data_dir / "overrides" / "merges.csv", apply)
    typer.secho(f"{sum(map(len, notes.values()))} impossible date(s)", bold=True)
    for symbol, items in notes.items():
        for n in items:
            typer.echo(f"  {symbol}: {n}")


@app.command("check-dins")
def check_dins_cmd(
    apply: bool = typer.Option(True, help="Record each resolution on the director fact (din_resolution)."),
) -> None:
    """Resolve DINs a company's certificate contradicts, using what the pilot reports print."""
    from src.eval.din_check import check_dins

    settings = get_settings()
    findings = check_dins(settings.data_dir / "extracted", settings.sections_dir, _companies(None), apply)
    typer.secho(f"{len(findings)} director(s) with a DIN conflict", bold=True)
    for f in findings:
        typer.echo(f"  {f.company}: {f.person_name} table DIN {f.din}, conflict {f.conflict}")
        typer.echo(f"      same report elsewhere: {dict(f.same_report) or 'none'}")
        typer.echo(f"      other pilot reports: {f.other_reports or 'none'}")
        typer.echo(f"      -> {f.resolved_din or 'unresolved'} ({f.basis})")


@app.command()
def resolve() -> None:
    """Merge duplicate people and companies across the five reports' facts (no LLM calls).
    Writes data/resolved/ (entities, relations, merge log, uncertain.csv) and
    reports/resolution_summary.md."""
    from collections import Counter

    from src.resolve.ids import Registry, assign_uids
    from src.resolve.merge_entities import apply_uids, load_overrides, resolve as run_resolve, write_outputs
    from src.resolve.report import write_resolution_summary

    settings = get_settings()
    res = run_resolve(settings.data_dir / "extracted", _companies(None),
                      load_overrides(settings.data_dir / "overrides" / "merges.csv"))
    registry_path = settings.data_dir / "resolved" / "id_registry.csv"
    registry = Registry.load(registry_path)
    before = set(registry.rows)
    uids, id_notes = assign_uids(res.entities, registry)
    res = apply_uids(res, uids)
    registry.save(registry_path)
    write_outputs(res, settings.data_dir / "resolved")
    path = write_resolution_summary(settings.data_dir.parent / "reports" / "resolution_summary.md", res)
    mentions, entities = Counter(m.kind for m in res.mentions), Counter(e["type"] for e in res.entities)
    multi = Counter(e["type"] for e in res.entities if len(e["reports"]) > 1)
    typer.secho("Entities (mentions -> entities, in more than one report):", bold=True)
    for kind, label in [("person", "Person"), ("company", "Company"), ("firm", "AuditFirm"), ("group", "RelatedPartyGroup")]:
        typer.echo(f"  {label:<18} {mentions[kind]:>4} -> {entities[label]:<4} ({multi[label]} in more than one report)")
    typer.echo(f"Relations: {dict(Counter(r['type'] for r in res.relations))}")
    typer.echo(f"Stable ids: {len(set(uids.values()))} in use, {len(set(registry.rows) - before)} new this run "
               f"(registry: {registry_path})")
    for n in id_notes:
        typer.echo(f"  {n}")
    typer.secho(f"Uncertain matches for review (not merged): {len(res.uncertain)}", bold=True, fg=typer.colors.YELLOW)
    typer.echo(f"Wrote {settings.data_dir / 'resolved'} and {path}")


@app.command()
def load(
    sanity: bool = typer.Option(True, help="Run the sanity queries after loading."),
) -> None:
    """Load data/resolved/ into Neo4j (constraints first, then MERGE, so re-running changes
    nothing), print node/relationship counts and run the sanity queries."""
    from neo4j import GraphDatabase
    from neo4j.exceptions import ServiceUnavailable

    from src.graph.load_neo4j import graph_counts, load_graph, load_resolved, run_sanity_queries

    settings = get_settings()
    entities, relations = load_resolved(settings.data_dir / "resolved")
    auth = (settings.neo4j_user, settings.neo4j_password.get_secret_value())
    try:
        with GraphDatabase.driver(settings.neo4j_uri, auth=auth, notifications_min_severity="WARNING") as driver:
            result = load_graph(driver, entities, relations)
            nodes, rels = graph_counts(driver)
            sanity_results = run_sanity_queries(driver) if sanity else {}
    except ServiceUnavailable:
        typer.secho(f"Cannot reach Neo4j at {settings.neo4j_uri}. Is it running? (docker compose up -d)",
                    fg=typer.colors.RED)
        raise typer.Exit(code=1)
    typer.secho(f"Loaded {len(entities)} entities and {len(relations)} relations "
                f"(removed as no longer in the data: {result['pruned_nodes']} nodes, "
                f"{result['pruned_relationships']} relationships).", bold=True)
    typer.secho("Nodes:", bold=True)
    for label, n in nodes.items():
        typer.echo(f"  {label:<18} {n}")
    typer.secho("Relationships:", bold=True)
    for rtype, n in rels.items():
        typer.echo(f"  {rtype:<18} {n}")
    for name, rows in sanity_results.items():
        typer.secho(f"\n{name}: {len(rows)}", bold=True)
        for row in rows:
            typer.echo("  " + "; ".join(f"{k}={v}" for k, v in row.items()))


@app.command("baseline-index")
def baseline_index(
    company: list[str] = typer.Option(None, "--company", "-c", help="NSE symbol; repeat for several. Default: all."),
    force: bool = typer.Option(False, help="Re-chunk and re-embed companies that are already indexed."),
) -> None:
    """Chunk, embed and index report text for the plain RAG baseline."""
    from src.qa.baseline_index import build_index
    from src.qa.embeddings import SentenceTransformerEmbedder
    from src.qa.tokenizer import HFTokenizer

    settings = get_settings()
    typer.echo(f"Loading embedding model {settings.embedding_model} (first run downloads it)...")
    embedder = SentenceTransformerEmbedder(settings.embedding_model)
    tokenizer = HFTokenizer(settings.embedding_model)
    stats = build_index(
        _companies(company),
        settings.raw_pdf_dir,
        settings.vector_store_dir,
        embedder,
        tokenizer,
        settings.baseline_chunk_tokens,
        settings.baseline_chunk_overlap_tokens,
        settings.embedding_model,
        force=force,
    )
    total = 0
    for s in stats:
        note = " (already indexed, skipped)" if s.skipped else ""
        typer.echo(f"{s.nse_symbol:<11} {s.chunk_count} chunks{note}")
        total += s.chunk_count
    typer.secho(f"\n{total} chunks stored in {settings.vector_store_dir}", bold=True)


def _baseline_answerer(settings, client):
    """`question -> (answer, sources)` with the baseline RAG; the embedding model loads on first use."""
    from src.qa.baseline_index import BaselineIndex
    from src.qa.baseline_rag import answer_baseline
    from src.qa.embeddings import SentenceTransformerEmbedder

    state = {}

    def answer(question: str) -> tuple[str, list[str]]:
        if "index" not in state:
            state["index"] = BaselineIndex(settings.vector_store_dir)
            state["embedder"] = SentenceTransformerEmbedder(settings.embedding_model)
        result = answer_baseline(question, state["index"], state["embedder"], client, settings.baseline_top_k)
        return result.answer, [f"{s.nse_symbol}.pdf {s.page_label}" for s in result.sources]

    return answer


def _print_result(result) -> None:
    typer.secho("\nAnswer:", bold=True)
    typer.echo(result.answer)
    typer.secho(f"\nRoute: {result.route}", bold=True)
    if result.cypher:
        typer.secho("\nCypher:", bold=True)
        typer.echo(result.cypher)
    if result.paths:
        typer.secho(f"\nPaths ({len(result.paths)}):", bold=True)
        for path in result.paths[:15]:
            typer.echo(f"  {path}")
        if len(result.paths) > 15:
            typer.echo(f"  ... {len(result.paths) - 15} more")
    if result.sources:
        typer.secho("\nSources:", bold=True)
        typer.echo("  " + "; ".join(result.sources))
    if result.notes:
        typer.secho("\nNotes:", bold=True)
        for n in result.notes:
            typer.echo(f"  {n}")


@app.command()
def ask(question: str, mode: str = typer.Option("graph", help="graph (falls back to baseline), baseline or both")) -> None:
    """Answer a question: graph first (with fallback to the baseline), the baseline alone, or both."""
    from neo4j import GraphDatabase

    from src.qa.answer import QAResult, answer_question

    if mode not in ("baseline", "graph", "both"):
        typer.secho(f"Unknown mode {mode!r}: use graph, baseline or both.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    settings = get_settings()
    client = build_client(settings, purpose="qa")
    baseline = _baseline_answerer(settings, client)
    try:
        if mode in ("graph", "both"):
            auth = (settings.neo4j_user, settings.neo4j_password.get_secret_value())
            with GraphDatabase.driver(settings.neo4j_uri, auth=auth, notifications_min_severity="WARNING") as driver:
                result = answer_question(question, client, driver, baseline)
            if mode == "both":
                typer.secho("=== Graph ===", bold=True)
            _print_result(result)
        if mode in ("baseline", "both"):
            if mode == "both":
                typer.secho("\n=== Baseline ===", bold=True)
            answer, sources = baseline(question)
            _print_result(QAResult(question, answer, "baseline", sources=sources))
    except (DailyLimitReached, APIError, LLMError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1)
    typer.echo(f"\n{client.tracker.summary()}")


@app.command("dev-run")
def dev_run(only: list[str] = typer.Option(None, "--only", help="Question id(s) to run, e.g. dev05.")) -> None:
    """Run the Phase 6 practice questions (src/qa/dev_questions.jsonl; never reused in Phase 7) and write
    reports/dev_questions_run.md."""
    from neo4j import GraphDatabase

    from src.eval.summary import _git_head
    from src.qa.answer import answer_question
    from src.qa.dev_run import load_dev_questions, score, write_report

    settings = get_settings()
    questions = load_dev_questions(Path(__file__).parent / "qa" / "dev_questions.jsonl")
    if only:
        questions = [q for q in questions if q["id"] in only]
    client = build_client(settings, purpose="qa")
    baseline = _baseline_answerer(settings, client)
    outcomes = []
    auth = (settings.neo4j_user, settings.neo4j_password.get_secret_value())
    with GraphDatabase.driver(settings.neo4j_uri, auth=auth, notifications_min_severity="WARNING") as driver:
        for q in questions:
            try:
                result = answer_question(q["question"], client, driver, baseline)
            except (DailyLimitReached, APIError, LLMError) as exc:
                typer.secho(f"Stopped at {q['id']}: {exc}", fg=typer.colors.RED)
                break
            outcome = score(q, result)
            outcomes.append(outcome)
            colour = typer.colors.GREEN if outcome.passed else typer.colors.YELLOW
            typer.secho(f"{q['id']} [{result.route}] {'ok' if outcome.passed else 'FAIL: ' + '; '.join(outcome.problems)}",
                        fg=colour)
    path = write_report(settings.data_dir.parent / "reports" / "dev_questions_run.md", outcomes,
                        client.tracker.summary(), _git_head())
    typer.secho(f"{sum(o.passed for o in outcomes)} of {len(outcomes)} passed. Wrote {path}", bold=True)
    typer.echo(client.tracker.summary())


@app.command("eval")
def run_eval() -> None:
    """Phase 7: answer every verified test question with both systems once (resumable; answers are
    written to data/eval/answers.jsonl and not printed)."""
    from neo4j import GraphDatabase

    from src.eval.run_eval import SYSTEMS, load_questions, run
    from src.eval.summary import _git_head

    settings = get_settings()
    questions = load_questions(Path(__file__).parent / "eval" / "questions.jsonl")
    answers_path = settings.data_dir / "eval" / "answers.jsonl"
    client = build_client(settings, purpose="qa")
    client.fallback_model = None  # every answer from GEMINI_QA_MODEL; stop on quota instead of switching
    baseline = _baseline_answerer(settings, client)
    auth = (settings.neo4j_user, settings.neo4j_password.get_secret_value())
    with GraphDatabase.driver(settings.neo4j_uri, auth=auth, notifications_min_severity="WARNING") as driver:
        driver.verify_connectivity()
        counts = run(questions, answers_path, client, driver, baseline, _git_head(), typer.echo)
    total = len(questions) * len(SYSTEMS)
    finished = counts["already_done"] + counts["answered"]
    typer.secho(f"{finished} of {total} answers done ({counts['answered']} new this run, "
                f"{counts['infra_failed']} infrastructure failures to retry)"
                + (". Stopped: daily quota used up." if counts["stopped_on_quota"] else "."), bold=True)
    typer.echo(client.tracker.summary())


# ---------------------------------------------------------------- setup checks


class _CompanyCheck(BaseModel):
    """Tiny schema used only to test structured output."""

    company_name: str = Field(description="Full legal name of the company")
    headquarters_city: str
    parent_group: str | None = Field(description="Business group it belongs to, if any")


@app.command("check-llm")
def check_llm() -> None:
    """Phase 0 check: one text call, one structured call, then the same structured call again (cache)."""
    settings = get_settings()
    try:
        client = build_client(settings, purpose="extraction")
    except LLMError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.echo(
        f"Provider: {settings.llm_provider}, model: {client.default_model}, "
        f"fallback: {client.fallback_model or 'none'}"
    )
    try:
        start = time.perf_counter()
        text = client.generate_text(
            "In one sentence, what is a knowledge graph?", step="check.text"
        )
        _report("1. Plain text call", start, client)
        typer.echo(f"   -> {text.strip()}")

        prompt = "Give basic facts about Tata Consultancy Services."
        start = time.perf_counter()
        first = client.generate_structured(prompt, _CompanyCheck, step="check.structured")
        _report("2. Structured call", start, client)
        typer.echo(f"   -> {first.model_dump()}")

        start = time.perf_counter()
        second = client.generate_structured(prompt, _CompanyCheck, step="check.structured")
        _report("3. Same structured call again", start, client)
    except DailyLimitReached as exc:
        typer.secho(str(exc), fg=typer.colors.YELLOW)
        raise typer.Exit(code=2)
    except (APIError, LLMError) as exc:
        typer.secho(f"LLM call failed: {exc}", fg=typer.colors.RED)
        typer.echo(client.tracker.summary())
        raise typer.Exit(code=1)

    if client.last_call_cached and second == first:
        typer.secho("Cache works: the repeat call was served from disk.", fg=typer.colors.GREEN)
    else:
        typer.secho("Cache problem: the repeat call went to the API.", fg=typer.colors.RED)
    typer.echo(client.tracker.summary())


def _report(label: str, start: float, client: LLMClient) -> None:
    source = "from cache" if client.last_call_cached else "from API"
    typer.echo(f"{label}: {time.perf_counter() - start:.2f}s ({source}, model {client.last_model})")


@app.command("check-neo4j")
def check_neo4j() -> None:
    """Phase 0 check: connect to Neo4j and run a trivial query."""
    from neo4j import GraphDatabase
    from neo4j.exceptions import AuthError, ServiceUnavailable

    settings = get_settings()
    auth = (settings.neo4j_user, settings.neo4j_password.get_secret_value())
    try:
        with GraphDatabase.driver(settings.neo4j_uri, auth=auth) as driver:
            driver.verify_connectivity()
            info = driver.get_server_info()
            records, _, _ = driver.execute_query("RETURN 1 AS ok")
    except ServiceUnavailable:
        typer.secho(
            f"Cannot reach Neo4j at {settings.neo4j_uri}. Is it running? (docker compose up -d)",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)
    except AuthError:
        typer.secho("Neo4j rejected the username/password in .env.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    typer.secho(
        f"Neo4j OK: {info.agent} at {settings.neo4j_uri}, test query returned {records[0]['ok']}.",
        fg=typer.colors.GREEN,
    )


if __name__ == "__main__":
    app()
