"""Name normalisation for entity resolution: people and companies.

Both kinds fold the lookalike letters lowercase "l" and capital "I" (Tata Steel's PDF prints
"Neelachal Ispat" as "Neelachal lspat"), so keys are only for comparing, never for display.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

PERSON_TITLES = {"mr", "mrs", "ms", "miss", "dr", "prof", "shri", "smt", "sri", "late"}
PUNCT_RE = re.compile(r"[.,'’`‘\"()\-–/&:;]")


def fold_lookalikes(text: str) -> str:
    """Lowercase, then fold "i" into "l": capital I and lowercase l look the same in some
    PDFs' fonts, so "lspat" and "Ispat" must compare equal."""
    return text.lower().replace("i", "l")


# ---------------------------------------------------------------- people


def person_tokens(name: str) -> list[str]:
    """Lowercased name tokens without titles or punctuation: "Mr. N. Chandrasekaran" ->
    ["n", "chandrasekaran"]."""
    tokens = PUNCT_RE.sub(" ", " ".join(name.split()).lower()).split()
    while tokens and tokens[0] in PERSON_TITLES:
        tokens = tokens[1:]
    return tokens


def person_key(name: str) -> str:
    return fold_lookalikes(" ".join(person_tokens(name)))


def initials_only(name: str) -> bool:
    """Whether every given name is an initial ("N Chandrasekaran", "O P Bhatt"): such a name
    alone is too weak to join two reports' mentions."""
    tokens = person_tokens(name)
    return len(tokens) < 2 or all(len(t) == 1 for t in tokens[:-1])


def persons_may_match(a: str, b: str) -> str | None:
    """Why two different person names might be one person (for the review list), or None:
    same surname with compatible initials ("Om Prakash Bhatt" / "O P Bhatt"), the same
    letters spaced differently ("Krishna Kumar" / "Krishnakumar"), or a close spelling."""
    ta, tb = [fold_lookalikes(t) for t in person_tokens(a)], [fold_lookalikes(t) for t in person_tokens(b)]
    if not ta or not tb or ta == tb:
        return None
    if "".join(ta) == "".join(tb):
        return "same letters, spaced differently"
    if "".join(ta[1:]) == "".join(tb[1:]) and ta[0][0] == tb[0][0] and len(ta) > 1 and len(tb) > 1:
        return "same surname, given name abbreviated"
    if ta[-1] == tb[-1] and len(ta) == len(tb) and all(x[0] == y[0] and (x == y or len(x) == 1 or len(y) == 1)
                                                      for x, y in zip(ta[:-1], tb[:-1])):
        return "same surname, compatible initials"
    if "".join(ta[1:]).replace(" ", "") == "".join(tb[1:]) or "".join(ta)[1:] == "".join(tb[1:]):
        return "same surname letters, initial differs in spacing"
    ratio = SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
    if ratio >= 0.88:
        return f"similar spelling ({ratio:.2f})"
    return None


# ---------------------------------------------------------------- companies

FOOTNOTE_RE = re.compile(r"(?:\s*(?:\(\d+\)|\*+|\^+|#+|@+|\$+|[¹²³⁴⁵⁶⁷⁸⁹⁰]+))+\s*$")
# One level of nested brackets inside: "(formerly Global Enterprise International (Malaysia) Sdn. Bhd.)".
FORMERLY_RE = re.compile(r"\(\s*(?:formerly|earlier|previously)\s+(?:known\s+as\s+)?((?:[^()]|\([^()]*\))+)\)", re.I)
TRAILING_BRACKET_RE = re.compile(r"\(([^()]+)\)\s*$")
STATUS_NOTE_RE = re.compile(r"\s*\((?:dormant|under liquidation|liquidated|in liquidation)\)\s*$", re.I)

# Country spellings in the reports, folded to one name each.
COUNTRY_ALIASES = {
    "uk": "UK", "u k": "UK", "united kingdom": "UK", "england": "UK", "us": "US", "usa": "US", "u s a": "US",
    "u s": "US", "united states": "US", "united states of america": "US", "the netherlands": "Netherlands",
    "netherlands": "Netherlands", "holland": "Netherlands", "itlay": "Italy", "columbia": "Colombia",
    "budapest": "Hungary", "dubai": "UAE", "uae": "UAE", "united arab emirates": "UAE",
    "gb": "UK", "great britain": "UK", "capellen g d de luxembourg": "Luxembourg", "czech republic": "Czech Republic", "korea": "South Korea",
}
COUNTRIES = {
    "argentina", "australia", "austria", "bahamas", "belgium", "brazil", "bulgaria", "canada", "chile", "china",
    "colombia", "czech republic", "denmark", "ecuador", "finland", "france", "germany", "guatemala", "hungary",
    "india", "indonesia", "ireland", "israel", "italy", "japan", "luxembourg", "malaysia", "mexico", "morocco",
    "netherlands", "nigeria", "norway", "philippines", "poland", "portugal", "qatar", "romania", "russia",
    "saudi arabia", "serbia", "singapore", "slovakia", "south africa", "south korea", "spain", "sweden",
    "switzerland", "taiwan", "thailand", "turkey", "uruguay", "vietnam", "uk", "us", "uae", "sri lanka",
    "kenya", "uganda", "bangladesh", "new zealand", "egypt", "ghana", "zambia", "zimbabwe", "tanzania",
}


def canonical_country(text: str | None) -> str | None:
    """'U.K.' / 'UK ' -> 'UK', 'U.S.A.' -> 'US', 'The \\nNetherlands' -> 'Netherlands'."""
    if not text:
        return None
    flat = " ".join(re.sub(r"[.()]", " ", text).split()).lower()
    if not flat:
        return None
    if flat in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[flat]
    return flat.title() if flat in COUNTRIES else " ".join(text.split())


def is_country(text: str) -> bool:
    flat = " ".join(re.sub(r"[.()]", " ", text).split()).lower()
    return flat in COUNTRIES or flat in COUNTRY_ALIASES
# Legal-form words and their canonical spelling in a key.
LEGAL_FORMS = {
    "limited": "ltd", "ltd": "ltd", "private": "pvt", "pvt": "pvt", "company": "co", "co": "co",
    "corporation": "corp", "corp": "corp", "incorporated": "inc", "inc": "inc", "llc": "llc", "llp": "llp",
    "plc": "plc", "pte": "pte", "gmbh": "gmbh", "ag": "ag", "bv": "bv", "nv": "nv", "ab": "ab", "oy": "oy",
    "sa": "sa", "spa": "spa", "sarl": "sarl", "srl": "srl", "sro": "sro", "kft": "kft", "sdn": "sdn",
    "bhd": "bhd", "pty": "pty", "kk": "kk", "as": "as", "sas": "sas", "ltda": "ltda", "kg": "kg",
    "spzoo": "spzoo", "sl": "sl", "sa de cv": "sadecv",
}
# Dotted forms joined before tokenising ("S.a.r.l" -> "sarl", "B.V." -> "bv").
DOTTED_FORMS = re.compile(r"\b((?:[a-z]\.){1,4}[a-z]?)\.?(?=\s|$|,|\))", re.I)


@dataclass
class CompanyName:
    """A company name as printed, split into what identifies it."""

    printed: str
    display: str  # without footnote markers, line breaks and former-name brackets
    key: str  # normalised display name (exact matches merge)
    core: str  # key without legal-form words (only for suggesting matches)
    short_names: list[str] = field(default_factory=list)  # "(Infosys China)": the same company
    former_names: list[str] = field(default_factory=list)  # "(formerly X)": X may now be another company's name
    country: str | None = None  # a country printed with the name: "(Argentina)", "... Inc. USA"

    @property
    def aliases(self) -> list[str]:
        return self.short_names + self.former_names


SPZOO_RE = re.compile(r"\bsp\.?\s*z\.?\s*o\.?\s*o\.?(?=\W|$)", re.I)
AS_RE = re.compile(r"\ba/s\b", re.I)


def _company_key(name: str) -> tuple[str, str]:
    text = " ".join(name.split()).lower().replace("&", " and ")
    text = AS_RE.sub(" as ", SPZOO_RE.sub(" spzoo ", text))
    text = DOTTED_FORMS.sub(lambda m: m.group(1).replace(".", ""), text)
    tokens = PUNCT_RE.sub(" ", text).split()
    if tokens and tokens[0] == "the":
        tokens = tokens[1:]
    key = [LEGAL_FORMS.get(t, t) for t in tokens]
    core = [t for t, raw in zip(key, tokens) if raw not in LEGAL_FORMS]
    return fold_lookalikes(" ".join(key)), fold_lookalikes(" ".join(core))


# Zero-width, so every legal-form word is tried as the start of the tail ("Pte. Limited Singapore").
LEGAL_TAIL_RE = re.compile(r"(?=\b(?:limited|ltd|inc|llc|plc|pte|gmbh|ag|bv|b\.v|corp|corporation|co)\.?,?\s+(.+)$)", re.I)


def company_name(printed: str) -> CompanyName:
    """Split a printed company name: footnote markers dropped ("Sirketi(1)", "Singapore**"),
    "(formerly known as X)" kept as a former name, a trailing bracketed short name of two or
    more words kept as a short name ("... Co. Limited (Infosys China)"), and a country printed
    as a trailing bracket ("S.R.L. (Argentina)") or after the legal form ("Pte. Limited
    Singapore", "Inc. USA") taken out as the country. "(Dormant)" and similar notes are
    dropped. A country that is part of the name ("Tata Consultancy Services Belgium") stays."""
    text = FOOTNOTE_RE.sub("", " ".join(printed.split()))
    former = [FOOTNOTE_RE.sub("", m.group(1)).strip() for m in FORMERLY_RE.finditer(text)]
    text = FOOTNOTE_RE.sub("", FORMERLY_RE.sub("", text).strip())
    text = STATUS_NOTE_RE.sub("", text)
    short, country = [], None
    trailing = TRAILING_BRACKET_RE.search(text)
    if trailing and is_country(trailing.group(1)):
        country = canonical_country(trailing.group(1))
        text = text[: trailing.start()].strip()
    elif trailing and len(trailing.group(1).split()) >= 2:
        short.append(FOOTNOTE_RE.sub("", trailing.group(1)).strip())
        text = text[: trailing.start()].strip()
    tail = next((m for m in LEGAL_TAIL_RE.finditer(text) if is_country(m.group(1))), None)
    if tail:
        country = country or canonical_country(tail.group(1))
        text = text[: tail.start(1)].strip()
    text = text.rstrip(" ,")
    key, core = _company_key(text)
    return CompanyName(printed, text, key, core, short, former, country)


def company_key(name: str) -> str:
    return company_name(name).key


def companies_may_match(a: CompanyName, b: CompanyName) -> str | None:
    """Why two different company names might be one company (for the review list), or
    None: the same name apart from legal form, one name's words contained in the other's,
    or a close spelling."""
    if a.key == b.key:
        return None
    if a.core and a.core == b.core:
        return "same name apart from the legal form"
    ta, tb = set(a.key.split()), set(b.key.split())
    differ = ta ^ tb
    # "InMotion Ventures 2" / "3", "Tata Steel International (Nigeria)" / "(India)": siblings.
    countries = {fold_lookalikes(c) for c in COUNTRIES | set(COUNTRY_ALIASES)}
    if any(any(ch.isdigit() for ch in w) or w in countries for w in differ):
        return None
    ratio = SequenceMatcher(None, a.key, b.key).ratio()
    if ratio >= 0.93:
        return f"similar spelling ({ratio:.2f})"
    return None


# Related-party "parties" that are categories of parties, not one company or person.
GROUP_RE = re.compile(
    r"^(?:subsidiaries|associates|joint ventures?|promoters?|other related parties|key managerial personnel"
    r"|whole-time directors|relatives)\b|\bsubsidiaries of\b|\bjoint ventures? of\b|\bits subsidiaries\b"
    r"|\bassociates\s*/", re.I)
GROUP_ANCHOR_RE = re.compile(r"(?:of|ventures of)\s+(.+?)(?:\s+and their subsidiaries)?$|^(.+?),\s+its subsidiaries", re.I)


def is_group_label(name: str) -> bool:
    return bool(GROUP_RE.search(" ".join(name.split())))


def group_anchor(name: str) -> str | None:
    """The company a group label is about: "Subsidiaries of Tata Sons Private Limited" ->
    "Tata Sons Private Limited"; "Subsidiaries of the Company" -> None (the reporter)."""
    m = GROUP_ANCHOR_RE.search(" ".join(name.split()))
    if not m:
        return None
    anchor = (m.group(1) or m.group(2) or "").strip()
    return None if anchor.lower() in {"the company", "promoter", "the promoter"} else anchor
