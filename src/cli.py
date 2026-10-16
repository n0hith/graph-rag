"""Command-line interface. Run with: python -m src.cli --help"""

from __future__ import annotations

import time

import typer
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


def _not_built(phase: int) -> None:
    typer.echo(f"Not built yet: this command arrives in Phase {phase}.")
    raise typer.Exit(code=1)


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
def extract() -> None:
    """Extract facts from sections with table parsing and the LLM."""
    _not_built(3)


@app.command()
def resolve() -> None:
    """Merge duplicate people and companies."""
    _not_built(4)


@app.command()
def load() -> None:
    """Load resolved facts into Neo4j."""
    _not_built(5)


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


@app.command()
def ask(question: str, mode: str = typer.Option("graph", help="graph, baseline or both")) -> None:
    """Answer a question."""
    if mode not in ("baseline", "graph", "both"):
        typer.secho(f"Unknown mode {mode!r}: use graph, baseline or both.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if mode in ("graph", "both"):
        _not_built(6)

    from src.qa.baseline_index import BaselineIndex
    from src.qa.baseline_rag import answer_baseline
    from src.qa.embeddings import SentenceTransformerEmbedder

    settings = get_settings()
    index = BaselineIndex(settings.vector_store_dir)
    if index.count() == 0:
        typer.secho("The baseline index is empty. Run `baseline-index` first.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    embedder = SentenceTransformerEmbedder(settings.embedding_model)
    client = build_client(settings, purpose="qa")
    try:
        result = answer_baseline(question, index, embedder, client, settings.baseline_top_k)
    except (DailyLimitReached, APIError, LLMError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho("\nAnswer:", bold=True)
    typer.echo(result.answer)
    if result.sources:
        typer.secho("\nSources:", bold=True)
        for s in result.sources:
            typer.echo(f"  {s.company} ({s.nse_symbol}), {s.page_label}")
    typer.echo(f"\n{client.tracker.summary()}")


@app.command("eval")
def run_eval() -> None:
    """Run the evaluation set against both systems."""
    _not_built(7)


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
