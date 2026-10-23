"""Phase 7 scoring (src/eval/scoring_rules.md), written and committed before any answer was read.

1. Item extraction (LLM, blind): for every answer outside `text_only`, the QA model lists the items
   the answer gives as its answer, seeing only the question and the answer (no gold, no system
   name), in a shuffled order, at temperature 0. The prompt is EXTRACT_SYSTEM below.
2. Matching (no LLM): each answer item is compared with the gold items in src/eval/scoring_key.jsonl.
   The key restates each gold answer as required parts: everything outside brackets in the gold
   item is required, bracketed text is context; descriptive words are required only where the
   question asks for them or two gold items would otherwise look the same.
   - "n:" a name. Matches after folding case, punctuation, titles (Mr/Ms/Dr), legal forms
     (Ltd/Limited, Pvt/Private, Co), the l/I lookalike and spacing ("T.V." = "T V"), through every
     alias the resolved entities record (names, aliases, NSE symbol), or a close spelling: every
     word similar at 0.9 or more, initials exact. "A | B" means either spelling.
   - "v:" a number, amount or percentage: same value whatever the format ("₹2,40,893 crore" =
     "2,40,893" = "Rs 2.40893 lakh crore"; "55.39%" = "55.39 percent"; words like "twenty-three").
   - "d:" a date, in any format (day first for numeric dates, as in the reports).
   - "w:" a word or phrase that must appear.  "none": the item says there is none.
   An answer item matches a gold item when it contains all of its parts, so a value counts only
   when given with its entity. Lists: precision = answer items matching some gold item / answer
   items; recall = gold items matched / gold items; F1. Numbers: right only when the answer gives
   the gold value and no different value. None/unanswerable: right only when the answer gives no
   items (says there are none, or that the reports don't say).
3. Text-only answers are graded by the LLM judge (JUDGE_SYSTEM, the rubric in the rules), blind and
   shuffled, and every grade is exported for the user's hand check before anything is final.
"""

from __future__ import annotations

import csv
import json
import random
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, Field

from src.llm.client import LLMClient, StructuredOutputError
from src.resolve.normalize import COUNTRY_ALIASES, DOTTED_FORMS, LEGAL_FORMS, PERSON_TITLES, PUNCT_RE, fold_lookalikes

SHUFFLE_SEED = 20241023
SIMILARITY = 0.9

EXTRACT_SYSTEM = (
    "You split an answer to a question about company annual reports into the separate items it gives as its "
    "answer. You do not judge whether the answer is right, and you never add anything that is not in the answer."
)
EXTRACT_PROMPT = """Question: {question}

Answer: {answer}

List the items this answer gives as its answer to the question.
- One item per entity (company, person, firm, committee, country), per number, and per date or other fact the
  question asks for.
- Copy the wording from the answer. Keep with each entity the values, dates, roles or categories the answer gives
  for it (e.g. "Tata Motors: Rs 298.51 crore", "X appointed June 1, 2023", "Y (associate)").
- When the answer gives one value or category for several entities, write one item per entity, each with it.
- Leave out what the answer mentions only as context or as a step towards the answer (such as the company it
  identified along the way), and leave out sources, page numbers and caveats.
- If, for one entity, the answer says there is none, keep an item saying so (e.g. "Company X: none").
- If the answer as a whole says there are none, or that the reports do not give the answer, return no items
  and set says_none to true."""

JUDGE_SYSTEM = (
    "You grade an answer to a question about company annual reports against the gold answer. Grades: 1 = states "
    "the gold answer's key fact(s) correctly and nothing that contradicts them; 0.5 = some key facts correct, "
    "some missing; 0 = wrong, contradicts the gold answer, or says the reports don't contain it. Formatting and "
    "units may differ (\"Rs 2,40,893 crore\" = \"2,40,893 crore\"); a rounded or approximate value is wrong. "
    "Reply with the grade and a one-line reason."
)
JUDGE_PROMPT = "Question: {question}\n\nGold answer: {gold}\n\nAnswer to grade: {answer}"


class AnswerItems(BaseModel):
    items: list[str] = Field(description="The items the answer gives as its answer, in its own wording")
    says_none: bool = Field(description="True if the answer says there are none or the reports don't say")


class JudgeGrade(BaseModel):
    grade: Literal["1", "0.5", "0"]
    reason: str = Field(description="One line")


# ---------------------------------------------------------------- names


def norm_tokens(text: str) -> list[str]:
    """Words for comparing names: lowercase, "&" as "and", dotted initials joined, punctuation,
    titles, legal forms and "the" dropped, l/I folded."""
    text = " ".join(text.split()).replace("&", " and ").replace("’", "'")
    text = re.sub(r"'s\b", "", text)
    text = DOTTED_FORMS.sub(lambda m: m.group(1).replace(".", ""), text)
    tokens = PUNCT_RE.sub(" ", text.lower()).split()
    tokens = [t for t in tokens if t not in LEGAL_FORMS and t not in PERSON_TITLES and t != "the" and t != "m/s"]
    while tokens and tokens[-1] == "and":
        tokens.pop()
    while tokens and tokens[0] == "and":
        tokens.pop(0)
    return [fold_lookalikes(t) for t in tokens]


def _tokens_close(a: list[str], b: list[str]) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x == y:
            continue
        if len(x) <= 2 or len(y) <= 2 or SequenceMatcher(None, x, y).ratio() < SIMILARITY:
            return False
    return True


def name_in(name_tokens: list[str], text_tokens: list[str]) -> bool:
    """Whether a name occurs in a text: the same words, the same letters spaced differently, or
    every word a close spelling."""
    n = len(name_tokens)
    if not n:
        return False
    joined = "".join(name_tokens)
    for size in range(1, n + 5):  # initials may be split: "A. G. S." = "A.G.S."
        for i in range(len(text_tokens) - size + 1):
            window = text_tokens[i:i + size]
            if "".join(window) == joined or (size == n and _tokens_close(name_tokens, window)):
                return True
    return False


@dataclass
class AliasIndex:
    """Every spelling of each resolved entity, looked up by any one of them."""

    spellings: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_entities(cls, path: Path) -> "AliasIndex":
        index = cls()
        if not path.exists():
            return index
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            names = [e["name"], *e.get("aliases", [])] + ([e["nse_symbol"]] if e.get("nse_symbol") else [])
            for name in names:
                index.spellings.setdefault(" ".join(norm_tokens(name)), []).extend(names)
        for spelling, country in COUNTRY_ALIASES.items():
            group = [s for s, c in COUNTRY_ALIASES.items() if c == country] + [country]
            index.spellings.setdefault(" ".join(norm_tokens(spelling)), []).extend(group)
        return index

    def variants(self, name: str) -> list[list[str]]:
        names = [n.strip() for n in name.split("|")]
        out = []
        for n in names:
            out.append(norm_tokens(n))
            out += [norm_tokens(s) for s in self.spellings.get(" ".join(norm_tokens(n)), [])]
        unique = []
        for tokens in out:
            if tokens and tokens not in unique:
                unique.append(tokens)
        return unique


# ---------------------------------------------------------------- dates and numbers

MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                          "september", "october", "november", "december"])}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9
_MON = r"(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)\.?"
_ORD = r"(?:st|nd|rd|th)?"
DATE_PATTERNS = [
    (re.compile(rf"\b{_MON}\s+(\d{{1,2}}){_ORD},?\s+(\d{{4}})\b", re.I), ("m", "d", "y")),
    (re.compile(rf"\b(\d{{1,2}}){_ORD}(?:\s+of)?[\s-]+{_MON},?[\s-]+(\d{{4}})\b", re.I), ("d", "m", "y")),
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), ("y", "m", "d")),
    (re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b"), ("d", "m", "y")),
]


def find_dates(text: str) -> tuple[set[tuple[int, int, int]], str]:
    """The dates in a text as (year, month, day), and the text with them blanked out."""
    found = set()
    for pattern, order in DATE_PATTERNS:
        def take(m: re.Match) -> str:
            parts = dict(zip(order, m.groups()))
            month = parts["m"]
            month = MONTHS.get(month.lower().rstrip(".")) if not month.isdigit() else int(month)
            try:
                y, mo, d = int(parts["y"]), int(month), int(parts["d"])
            except (TypeError, ValueError):
                return m.group(0)
            if 1 <= mo <= 12 and 1 <= d <= 31:
                found.add((y, mo, d))
                return " "
            return m.group(0)
        text = pattern.sub(take, text)
    return found, text


NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen".split())}
NUMBER_WORDS.update({w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())})
NUMBER_WORD_RE = re.compile(r"\b(?:(?:" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))
                            + r"|hundred|thousand|and)[\s-]*)+\b", re.I)


def _words_to_number(words: str) -> int | None:
    total, current, seen = 0, 0, False
    for w in re.split(r"[\s-]+", words.lower().strip()):
        if w in NUMBER_WORDS:
            current += NUMBER_WORDS[w]
            seen = True
        elif w == "hundred":
            current = max(current, 1) * 100
        elif w == "thousand":
            total += max(current, 1) * 1000
            current = 0
    return total + current if seen else None


UNIT_TO_CRORE = {"lakh crore": 1e5, "lakh crores": 1e5, "crore": 1.0, "crores": 1.0, "cr": 1.0, "million": 0.1,
                 "mn": 0.1, "billion": 100.0, "bn": 100.0, "lakh": 0.01, "lakhs": 0.01}
NUMBER_RE = re.compile(
    r"(₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*(%|percent|per cent)?\s*"
    r"(lakh crores?|crores?|cr\b\.?|million|mn\b|billion|bn\b|lakhs?)?", re.I)


@dataclass(frozen=True)
class Value:
    kind: str  # amount (in crore) | percent | plain
    raw: float  # the number as printed
    crore: float | None = None


def find_values(text: str) -> list[Value]:
    """Numbers, amounts and percentages in a text (dates and bare years left out)."""
    _, text = find_dates(text)
    text = re.sub(r"\b(?:fy|fiscal|financial year)\s*'?\d{2,4}(?:-\d{2,4})?\b", " ", text, flags=re.I)
    text = NUMBER_WORD_RE.sub(lambda m: f" {_words_to_number(m.group(0))} " if _words_to_number(m.group(0)) is not None
                              else m.group(0), text)
    values = []
    for m in NUMBER_RE.finditer(text):
        currency, digits, percent, unit = m.groups()
        start = m.start(2)
        if start > 0 and text[start - 1].isalpha():
            continue  # part of a word or code ("FY24", "L22210")
        raw = float(digits.replace(",", ""))
        if percent:
            values.append(Value("percent", raw))
        elif unit:
            values.append(Value("amount", raw, raw * UNIT_TO_CRORE[unit.lower().rstrip(".").strip()]))
        elif currency:
            values.append(Value("amount", raw, raw))
        elif not (1990 <= raw <= 2035 and raw == int(raw) and "," not in digits):
            values.append(Value("plain", raw))
    return values


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b))


def value_matches(gold: Value, found: Value) -> bool:
    if gold.kind == "amount" and found.kind == "amount":
        return _same(gold.crore, found.crore) or _same(gold.raw, found.raw)
    return _same(gold.raw, found.raw)


def parse_gold_value(text: str) -> Value:
    values = find_values(text)
    if len(values) != 1:
        raise ValueError(f"gold value {text!r} must hold exactly one number")
    return values[0]


# ---------------------------------------------------------------- matching

NONE_RE = re.compile(r"\b(none|no|not|nil|vacant|without|n/?a)\b", re.I)


def part_in(part: str, item: str, aliases: AliasIndex) -> bool:
    kind, _, text = part.partition(":")
    if part == "none":
        return NONE_RE.search(item) is not None
    if kind == "n":
        tokens = norm_tokens(item)
        return any(name_in(v, tokens) for v in aliases.variants(text))
    if kind == "w":
        word, tokens = norm_tokens(text), norm_tokens(item)
        return name_in(word, tokens)
    if kind == "d":
        gold, _ = find_dates(text)
        found, _ = find_dates(item)
        return bool(gold) and gold <= found
    if kind == "v":
        gold = parse_gold_value(text)
        return any(value_matches(gold, v) for v in find_values(item))
    raise ValueError(f"unknown part {part!r}")


@dataclass
class Score:
    score: float  # F1 for lists, 1/0 for numbers and none
    correct: bool  # completely right
    precision: float | None = None
    recall: float | None = None
    matched_gold: list[int] = field(default_factory=list)
    extra_items: list[str] = field(default_factory=list)
    detail: str = ""


def score_list(gold_items: list[list[str]], items: list[str], aliases: AliasIndex) -> Score:
    hits = [[all(part_in(p, a, aliases) for p in g) for a in items] for g in gold_items]
    found = [i for i, row in enumerate(hits) if any(row)]
    good_items = [j for j in range(len(items)) if any(row[j] for row in hits)]
    recall = len(found) / len(gold_items)
    precision = len(good_items) / len(items) if items else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    extras = [items[j] for j in range(len(items)) if j not in good_items]
    return Score(f1, f1 == 1.0, precision, recall, found, extras,
                 f"{len(found)}/{len(gold_items)} gold found, {len(extras)} extra")


def score_number(gold_text: str, items: list[str]) -> Score:
    gold = parse_gold_value(gold_text)
    values = [v for item in items for v in find_values(item)]
    right = [v for v in values if value_matches(gold, v)]
    other = [v for v in values if not value_matches(gold, v)]
    correct = bool(right) and not other
    detail = "no value given" if not values else ("gold value" if correct else
                                                    "different value given" if not right else "gold and other values")
    return Score(float(correct), correct, detail=detail)


def score_none(items: list[str], says_none: bool) -> Score:
    correct = not items
    return Score(float(correct), correct, extra_items=list(items),
                 detail="says none / not stated" if correct else "gives an answer")


def score_answer(key: dict, extraction: AnswerItems, aliases: AliasIndex) -> Score:
    if key["type"] == "list":
        return score_list(key["items"], extraction.items, aliases)
    if key["type"] == "number":
        return score_number(key["value"], extraction.items)
    return score_none(extraction.items, extraction.says_none)


# ---------------------------------------------------------------- LLM steps (blind, shuffled)


def blind_order(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Shuffle (question id, system) pairs with a fixed seed, so the order hides the system."""
    out = sorted(pairs)
    random.Random(SHUFFLE_SEED).shuffle(out)
    return out


def _structured(client: LLMClient, prompt: str, schema: type[BaseModel], system: str, step: str):
    """Invalid replies are never cached, so they are asked again (up to twice more), as in extraction."""
    for attempt in range(3):
        try:
            return client.generate_structured(prompt, schema, system=system, temperature=0.0, step=step)
        except StructuredOutputError:
            if attempt == 2:
                raise


def extract_items(client: LLMClient, question: str, answer: str) -> AnswerItems:
    return _structured(client, EXTRACT_PROMPT.format(question=question, answer=" ".join(answer.split())),
                       AnswerItems, EXTRACT_SYSTEM, "eval.extract")


def judge(client: LLMClient, question: str, gold: str, answer: str) -> JudgeGrade:
    return _structured(client, JUDGE_PROMPT.format(question=question, gold=gold, answer=" ".join(answer.split())),
                       JudgeGrade, JUDGE_SYSTEM, "eval.judge")


def gold_text(q: dict) -> str:
    g = q["gold_answer"]
    return "; ".join(map(str, g)) if isinstance(g, list) else str(g)


def run_llm_steps(questions: dict[str, dict], answers: dict[tuple[str, str], dict], out_path: Path,
                  step: str, call: Callable[[dict, dict], BaseModel], wanted: Callable[[dict, dict], bool],
                  on_error: Callable[[str, str, Exception], bool]) -> dict[tuple[str, str], dict]:
    """Run one LLM step (extraction or judge) over the answers it applies to, blind and shuffled; results are
    appended to out_path as they arrive and reused on the next run. `on_error` returns False to stop."""
    done = {}
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[(r["id"], r["system"])] = r
    out_path.parent.mkdir(parents=True, exist_ok=True)
    for qid, system in blind_order(list(answers)):
        q, a = questions[qid], answers[(qid, system)]
        if (qid, system) in done or not wanted(q, a):
            continue
        try:
            result = call(q, a)
        except Exception as exc:  # noqa: BLE001 - the caller decides which errors are retried
            if on_error(qid, step, exc):
                continue
            break
        row = {"id": qid, "system": system, **result.model_dump()}
        with out_path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        done[(qid, system)] = row
    return done


# ---------------------------------------------------------------- failure reasons

REASONS = ("wrong query", "missing fact (not in the graph)", "extraction error", "entity not found",
           "asked for clarification", "fell back to the baseline", "retrieval miss (baseline)", "invented answer",
           "partial list", "wrong value")


def _pages(sources: list[str]) -> set[tuple[str, int]]:
    out = set()
    for s in sources:
        m = re.match(r"(\S+\.pdf) pp?\.(\d+)(?:-(\d+))?", s)
        if m:
            start, end = int(m.group(2)), int(m.group(3) or m.group(2))
            out |= {(m.group(1), p) for p in range(start, end + 1)}
    return out


def provisional_reason(q: dict, key: dict, answer: dict, score: Score) -> str:
    """A first reason from the fixed set, read off the route, notes and score. Reasons that need the
    graph checked (wrong query / missing fact / extraction error) are marked for diagnosis."""
    if answer["route"] == "clarify":
        return "asked for clarification"
    if key["type"] == "none":
        return "invented answer"
    notes = " ".join(answer.get("notes") or [])
    gold_pages = {(p["doc"], p["page"]) for p in q["pages"]}
    if answer["route"] == "baseline":
        missed = not (gold_pages & _pages(answer.get("sources") or []))
        prefix = "fell back to the baseline; " if answer["system"] == "graph" else ""
        if missed:
            return prefix + "retrieval miss (baseline)"
        return prefix + ("partial list" if key["type"] == "list" and (score.recall or 0) > 0 else "wrong value")
    if "is not in the graph" in notes:
        return "entity not found"
    if key["type"] == "list" and 0 < (score.recall or 0) < 1:
        return "partial list"
    if key["type"] == "number" or (key["type"] == "list" and score.recall == 1):
        return "wrong value"
    return "to diagnose: wrong query / missing fact (not in the graph) / extraction error"


# ---------------------------------------------------------------- exports


def write_judge_handcheck(path: Path, map_path: Path, questions: dict, answers: dict, grades: dict) -> int:
    """Every judge grade, shuffled and without the system name, for the user's hand check; the row -> system
    map is kept separately."""
    rows, mapping = [], {}
    for n, (qid, system) in enumerate(blind_order([k for k in grades]), 1):
        q, g = questions[qid], grades[(qid, system)]
        rows.append({"row": n, "id": qid, "question": q["question"], "gold": gold_text(q),
                     "pages": "; ".join(f"{p['doc']} p.{p['page']}" for p in q["pages"]),
                     "answer": " ".join(answers[(qid, system)]["answer"].split()),
                     "judge_grade": g["grade"], "judge_reason": g["reason"], "your_grade": "", "your_note": ""})
        mapping[n] = {"id": qid, "system": system}
    _write_csv(path, rows)
    map_path.write_text(json.dumps(mapping, indent=1), encoding="utf-8")
    return len(rows)


def write_extraction_check(path: Path, questions: dict, answers: dict, extractions: dict, scores: dict) -> int:
    rows = []
    for n, (qid, system) in enumerate(blind_order([k for k in extractions]), 1):
        q, e, s = questions[qid], extractions[(qid, system)], scores[(qid, system)]
        rows.append({"row": n, "id": qid, "question": q["question"], "gold": gold_text(q),
                     "answer": " ".join(answers[(qid, system)]["answer"].split()),
                     "extracted_items": " || ".join(e["items"]), "says_none": e["says_none"],
                     "score": round(s.score, 3), "detail": s.detail, "extraction_ok?": "", "your_note": ""})
    _write_csv(path, rows)
    return len(rows)


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["row"])
        writer.writeheader()
        writer.writerows(rows)
