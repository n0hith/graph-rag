"""Which of the five pilot companies a question names, from their common names and tickers.

Used by the baseline to search only those companies' reports, and by the graph route's entity
lookup as its first step. Plain text matching on whole words, so the baseline doesn't depend on
the graph."""

from __future__ import annotations

import re

# Common names and tickers of the five pilot companies -> NSE symbol.
PILOT_ALIASES = {
    "TCS": ("tcs", "tata consultancy services", "tata consultancy", "tata consultancy services limited"),
    "TATAMOTORS": ("tata motors", "tamo", "tml", "tatamotors", "tata motors limited", "tata motors ltd"),
    "TATASTEEL": ("tata steel", "tatasteel", "tata steel limited", "tata steel ltd"),
    "TATACONSUM": ("tata consumer", "tata consumer products", "tcpl", "tataconsum", "tata consumer products limited"),
    "INFY": ("infosys", "infy", "infosys limited", "infosys ltd"),
}


def _flat(text: str) -> str:
    return " " + " ".join(re.sub(r"[^\w\s]", " ", text.lower().replace("'s", "")).split()) + " "


def companies_named(question: str) -> list[str]:
    """NSE symbols of the pilot companies the question names, in order of first mention."""
    text = _flat(question)
    found = []
    for symbol, names in PILOT_ALIASES.items():
        positions = [text.find(f" {n} ") for n in names if f" {n} " in text]
        if positions:
            found.append((min(positions), symbol))
    return [symbol for _, symbol in sorted(found)]
