"""Reading the list of companies from data/companies.csv."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Company:
    """One row of companies.csv."""

    name: str
    nse_symbol: str
    cin: str
    report_url: str

    @property
    def pdf_name(self) -> str:
        """File name of the downloaded report in data/raw_pdfs/."""
        return f"{self.nse_symbol}.pdf"


def load_companies(path: Path) -> list[Company]:
    """Read companies.csv. Rows without an NSE symbol are skipped."""
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    companies = []
    for row in rows:
        symbol = (row.get("nse_symbol") or "").strip()
        if not symbol:
            continue
        companies.append(
            Company(
                name=(row.get("name") or "").strip(),
                nse_symbol=symbol,
                cin=(row.get("cin") or "").strip().upper(),
                report_url=(row.get("report_url") or "").strip(),
            )
        )
    return companies


def select_companies(companies: list[Company], symbols: list[str] | None) -> list[Company]:
    """Keep only the given NSE symbols (case-insensitive); all companies when `symbols` is empty."""
    if not symbols:
        return companies
    wanted = {s.strip().upper() for s in symbols}
    unknown = wanted - {c.nse_symbol.upper() for c in companies}
    if unknown:
        raise ValueError(f"Not in companies.csv: {', '.join(sorted(unknown))}")
    return [c for c in companies if c.nse_symbol.upper() in wanted]
