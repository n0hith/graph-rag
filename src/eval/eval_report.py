"""Phase 7 results report (reports/eval_results.md) from the scored answers.

Per question, the score is F1 for lists and 1 or 0 for numbers and none/unanswerable; "fully
correct" means F1 = 1 or right. A category's winner is the system with the higher mean score (a tie
if equal). Text-only grades are the judge's and stay provisional until the user's hand check.
"""

from __future__ import annotations

from pathlib import Path

from src.eval.score import Score, gold_text

CATEGORIES = ("1hop", "2hop", "3hop", "aggregation", "none_or_unanswerable")
SYSTEMS = ("graph", "baseline")


def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _fmt(x: float | None, pct: bool = False) -> str:
    if x is None:
        return "-"
    return _pct(x) if pct else f"{x:.2f}"


def _rows_for(scored: list[dict], category: str | None, system: str, answer_type: str | None = None) -> list[dict]:
    return [r for r in scored if (category is None or r["category"] == category) and r["system"] == system
            and (answer_type is None or r["key_type"] == answer_type)]


def summary_table(scored: list[dict]) -> list[str]:
    lines = ["| Category | Questions | Graph: mean score | Graph: fully correct | Baseline: mean score | "
             "Baseline: fully correct | Winner |", "|---|---|---|---|---|---|---|"]
    for cat in (*CATEGORIES, None):
        means, fulls = {}, {}
        for s in SYSTEMS:
            rows = _rows_for(scored, cat, s)
            means[s] = _mean([r["score"] for r in rows])
            fulls[s] = _mean([float(r["correct"]) for r in rows])
        n = len(_rows_for(scored, cat, "graph"))
        g, b = means["graph"], means["baseline"]
        winner = "-" if g is None else ("tie" if abs(g - b) < 1e-9 else ("graph" if g > b else "baseline"))
        label = cat or "**All except text-only**"
        lines.append(f"| {label} | {n} | {_fmt(g)} | {_fmt(fulls['graph'], True)} | {_fmt(b)} | "
                     f"{_fmt(fulls['baseline'], True)} | {winner} |")
    return lines


def by_type_table(scored: list[dict]) -> list[str]:
    lines = ["| Category | System | Lists: n | Lists: average F1 | Lists: fully correct | Numbers: n | "
             "Numbers: exact match | None/unanswerable: n | None/unanswerable: accuracy |",
             "|---|---|---|---|---|---|---|---|---|"]
    for cat in CATEGORIES:
        for s in SYSTEMS:
            lists = _rows_for(scored, cat, s, "list")
            nums = _rows_for(scored, cat, s, "number")
            nones = _rows_for(scored, cat, s, "none")
            if not (lists or nums or nones):
                continue
            lines.append(f"| {cat} | {s} | {len(lists)} | {_fmt(_mean([r['score'] for r in lists]))} | "
                         f"{_fmt(_mean([float(r['correct']) for r in lists]), True)} | {len(nums)} | "
                         f"{_fmt(_mean([float(r['correct']) for r in nums]), True)} | {len(nones)} | "
                         f"{_fmt(_mean([float(r['correct']) for r in nones]), True)} |")
    return lines


def text_only_table(grades: list[dict]) -> list[str]:
    lines = ["| System | Questions | Mean judge grade | Grade 1 | Grade 0.5 | Grade 0 |", "|---|---|---|---|---|---|"]
    for s in SYSTEMS:
        gs = [float(g["grade"]) for g in grades if g["system"] == s]
        lines.append(f"| {s} | {len(gs)} | {_fmt(_mean(gs))} | {gs.count(1.0)} | {gs.count(0.5)} | {gs.count(0.0)} |")
    return lines


def _cell(text: str, limit: int | None = None) -> str:
    text = " ".join(str(text).split()).replace("|", "\\|")
    return text if limit is None or len(text) <= limit else text[: limit - 3] + "..."


def write_report(path: Path, questions: dict, answers: dict, scored: list[dict], grades: list[dict],
                 header: list[str]) -> Path:
    lines = ["# Phase 7 evaluation results", "", *header, "",
             "## Results by category (automatic scoring)", "",
             "Per question: F1 for lists, 1 or 0 for numbers and none/unanswerable. Fully correct: F1 = 1 or "
             "right. Winner: higher mean score.", "", *summary_table(scored), "",
             "### By answer type", "", *by_type_table(scored), "",
             "## Text-only (LLM judge, provisional)", "",
             "The judge's grades, before the user's hand check of all of them; the user's grade replaces the judge's "
             "where they disagree, and the agreement rate is added then. Hand-check file: "
             "`exports/judge_handcheck.csv`.", "", *text_only_table(grades), "",
             "## Failure list", "",
             "Every question a system got less than fully right (text-only excluded until the hand check). Reasons "
             "come from the fixed set in the scoring rules.", "",
             "| id | category | system | route | score | reason | what was wrong |", "|---|---|---|---|---|---|---|"]
    for r in sorted((r for r in scored if not r["correct"]), key=lambda r: (r["id"], r["system"])):
        lines.append(f"| {r['id']} | {r['category']} | {r['system']} | {r['route']} | {r['score']:.2f} | "
                     f"{r['reason']} | {_cell(r['what'], 220)} |")
    lines += ["", "## Answers", ""]
    for qid in sorted(questions):
        q = questions[qid]
        lines += [f"### {qid} ({q['category']}): {q['question']}", "", f"- Gold: {_cell(gold_text(q))}"]
        for s in SYSTEMS:
            a = answers.get((qid, s))
            if a is None:
                continue
            row = next((r for r in scored if r["id"] == qid and r["system"] == s), None)
            grade = next((g for g in grades if g["id"] == qid and g["system"] == s), None)
            mark = (f"score {row['score']:.2f}" if row else f"judge {grade['grade']} (provisional)" if grade else "")
            lines.append(f"- {s} [{a['route']}; {mark}]: {_cell(a['answer'])}")
            if a.get("cypher"):
                lines.append(f"  - Cypher: `{_cell(a['cypher'])}`")
            if row and row.get("items") is not None:
                lines.append(f"  - Items extracted: {_cell(' || '.join(row['items']) or '(none)')}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def describe(key: dict, score: Score) -> str:
    """What was wrong, for the failure list: missing gold items and extra items."""
    if key["type"] == "list":
        missing = [" + ".join(p.split(":", 1)[-1] for p in g) for i, g in enumerate(key["items"])
                   if i not in score.matched_gold]
        parts = []
        if missing:
            parts.append("missing: " + "; ".join(missing))
        if score.extra_items:
            parts.append("extra: " + "; ".join(score.extra_items))
        return " / ".join(parts) or score.detail
    if key["type"] == "none":
        return "gave: " + "; ".join(score.extra_items)
    return f"{score.detail} (gold {key['value']})"
