"""Prompts for LLM-based fact extraction. One builder per fact type, since directors,
subsidiaries, auditors and related-party transactions each need different instructions."""

from __future__ import annotations

COMMON_RULES = (
    "Only extract facts that are explicitly stated in the excerpt below. Never infer, "
    "guess, or use outside knowledge. For every item, the `evidence` field must be a "
    "short, exact quote copied verbatim from the excerpt (same spelling, spacing and "
    "punctuation) that supports it. If nothing relevant appears in this excerpt, return "
    "an empty list rather than guessing."
)


def _paged_text(pages: list[dict]) -> str:
    """Join a page group's text with `[PAGE N]` markers, so the model can tell pages apart."""
    return "\n\n".join(f"[PAGE {p['page']}]\n{p['text']}" for p in pages)


def director_prompt(pages: list[dict]) -> str:
    return (
        f"{COMMON_RULES}\n\n"
        "From this Corporate Governance Report excerpt, list every Board of Directors "
        "member mentioned (current or outgoing). For `role` use their board title (e.g. "
        "'Chairman', 'Managing Director & CEO', 'Independent Director'). Set "
        "`is_independent` and `is_executive` from the category stated for them (e.g. "
        "'Non-Independent, Executive'). Set `status` to 'ceased' only if the text marks "
        "them as having resigned, ceased, or an erstwhile/outgoing member; 'appointed' "
        "only if the text says they joined partway through the year; otherwise 'current'.\n\n"
        f"Report excerpt:\n{_paged_text(pages)}"
    )


def kmp_prompt(pages: list[dict]) -> str:
    return (
        f"{COMMON_RULES}\n\n"
        "From this Corporate Governance Report excerpt, identify the Chief Executive "
        "Officer (CEO), Chief Financial Officer (CFO), and Company Secretary, if named. "
        "`role` must be exactly one of 'CEO', 'CFO', or 'Company Secretary' — map titles "
        "like 'CEO & Managing Director' or 'Chief Executive Officer and MD' to 'CEO'. "
        "Skip anyone whose role here isn't one of these three.\n\n"
        f"Report excerpt:\n{_paged_text(pages)}"
    )


def subsidiary_prompt(pages: list[dict]) -> str:
    return (
        f"{COMMON_RULES}\n\n"
        "From this Form AOC-1 excerpt (salient features of subsidiaries' financial "
        "statements), list every subsidiary named, with its CIN if stated and its "
        "parent's percentage shareholding (`stake_pct`) if stated. Do not include "
        "associates or joint ventures listed under a separate 'Part B'.\n\n"
        f"Report excerpt:\n{_paged_text(pages)}"
    )


def auditor_prompt(pages: list[dict], audit_type: str) -> str:
    kind = "statutory (financial statements)" if audit_type == "statutory" else "secretarial"
    return (
        f"{COMMON_RULES}\n\n"
        f"This excerpt is the company's {kind} audit report. Identify the audit firm that "
        "signed it (usually near the end, after 'For <Firm Name>'), and its registration "
        "number if stated (a firm registration number, FCS number, or similar identifier "
        "near the signature block).\n\n"
        f"Report excerpt:\n{_paged_text(pages)}"
    )


def related_party_prompt(pages: list[dict]) -> str:
    return (
        f"{COMMON_RULES}\n\n"
        "From this related-party transactions note, list each distinct related party "
        "(company or person) and the nature of the transaction(s) with them (e.g. "
        "'sale of goods', 'remuneration', 'rent paid'). Give the amount in INR crore if "
        "stated (convert if given in lakh or another unit, stating the converted crore "
        "figure). If a party has several kinds of transactions, list each as a separate item.\n\n"
        f"Report excerpt:\n{_paged_text(pages)}"
    )
