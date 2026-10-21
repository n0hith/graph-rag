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
        "only if the text says they joined partway through the year; otherwise 'current'. "
        "If the report lists the director's directorships in other listed entities (often "
        "a table column like 'Directorship in other listed entity (Category of "
        "Directorship)'), put each one in `other_listed_directorships`: `company_name` "
        "spelled exactly as in the excerpt, `category` as stated for it (expand an "
        "abbreviation like 'NINED' or '(I)' only if the report's own key explains it), and "
        "`note` for any remark on it such as 'Debt Listed' or a cessation date. Leave the "
        "list empty if none are listed for them.\n\n"
        f"Report excerpt:\n{_paged_text(pages)}"
    )


def kmp_prompt(pages: list[dict]) -> str:
    return (
        f"{COMMON_RULES}\n\n"
        "From this Corporate Governance Report excerpt, identify the Chief Executive "
        "Officer (CEO), Chief Financial Officer (CFO), and Company Secretary, if named. "
        "`role` must be exactly one of 'CEO', 'CFO', or 'Company Secretary' — map titles "
        "like 'CEO & Managing Director' or 'Chief Executive Officer and MD' to 'CEO'. "
        "Skip anyone whose role here isn't one of these three. Set `status` to 'ceased' "
        "only if the text marks them as having resigned, ceased, or an erstwhile/outgoing "
        "holder of that role; 'appointed' only if the text says they took up the role "
        "partway through the year; otherwise 'current'. Fill `appointed_on` or `ceased_on` "
        "only when the report states an actual date for that change; leave them null "
        "otherwise — never guess a date.\n\n"
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
        "signed it (usually near the end, after 'For <Firm Name>'). Fill "
        "`firm_registration_no` only with the firm's registration number, i.e. a value "
        "labelled 'Firm Registration No.', 'Firm's Registration No.' or 'FRN'. Never put a "
        "peer review certificate number ('PR No.'), FCS/ACS/membership number, CP number or "
        "UDIN there; if no firm registration number is stated, leave it null.\n\n"
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
