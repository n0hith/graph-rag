"""Run the practice questions (src/qa/dev_questions.jsonl) and score them.

These questions are for building and tuning Phase 6 only; they must not be reused in the
Phase 7 test set. A question passes when it took the expected route, its answer contains every
`must_contain` term and none of the `must_not_contain` terms (numbers compared without
thousands separators, so "6,01,546" and "601,546" both match 601546).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from src.qa.answer import QAResult


@dataclass
class DevOutcome:
    question: dict
    result: QAResult
    passed: bool
    problems: list[str]


def load_dev_questions(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("’", "'").replace("‘", "'").split())


def contains(answer: str, term: str) -> bool:
    if re.fullmatch(r"[\d,.]+", term):
        digits = term.replace(",", "")
        return re.search(rf"(?<![\d.]){re.escape(digits)}(?![\d])", answer.replace(",", "")) is not None
    return _norm(term) in _norm(answer)


def score(question: dict, result: QAResult) -> DevOutcome:
    problems = []
    if result.route != question["expected_route"]:
        problems.append(f"route {result.route}, expected {question['expected_route']}")
    missing = [t for t in question["must_contain"] if not contains(result.answer, t)]
    if missing:
        problems.append("missing: " + ", ".join(missing))
    wrong = [t for t in question["must_not_contain"] if contains(result.answer, t)]
    if wrong:
        problems.append("should not include: " + ", ".join(wrong))
    return DevOutcome(question, result, not problems, problems)


def write_report(path: Path, outcomes: list[DevOutcome], usage: str, commit: str) -> Path:
    passed = sum(o.passed for o in outcomes)
    lines = ["# Practice questions run (Phase 6 development set)", "",
             f"Code at commit `{commit}`. {passed} of {len(outcomes)} passed. These questions are for building and "
             "tuning only and must not be reused in the Phase 7 test set.", "",
             "| id | category | question | route | correct | what went wrong |", "|---|---|---|---|---|---|"]
    for o in outcomes:
        q = o.question
        lines.append(f"| {q['id']} | {q['category']} | {q['question']} | {o.result.route} | "
                     f"{'yes' if o.passed else 'no'} | {'; '.join(o.problems)} |")
    lines += ["", "## Answers", ""]
    for o in outcomes:
        r = o.result
        lines += [f"### {o.question['id']}: {o.question['question']}", "",
                  f"- Route: {r.route}" + (" (passed)" if o.passed else f" (failed: {'; '.join(o.problems)})"),
                  f"- Answer: {' '.join(r.answer.split())}"]
        if r.cypher:
            lines.append(f"- Cypher: `{' '.join(r.cypher.split())}`")
        if r.paths:
            lines.append(f"- Paths ({len(r.paths)}): " + "; ".join(r.paths[:5]) + (" ..." if len(r.paths) > 5 else ""))
        if r.sources:
            lines.append("- Sources: " + "; ".join(r.sources[:8]))
        if r.notes:
            lines.append("- Notes: " + "; ".join(r.notes))
        lines.append("")
    lines += ["## LLM usage", "", "```", usage, "```", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
