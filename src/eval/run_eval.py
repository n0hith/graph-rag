"""Phase 7: run both systems once on every verified test question (src/eval/scoring_rules.md).

Each (question, system) answer is appended to data/eval/answers.jsonl as soon as it exists and is
final: a later run skips it. A call that fails for an infrastructure reason (quota, overload,
network, Neo4j down) before an answer exists is not recorded, so the next run retries it; the LLM
cache replays any calls that already succeeded, so a retried question costs only the missing calls.

The fallback model is switched off for the run, so every answer comes from GEMINI_QA_MODEL: when
its daily quota runs out the run stops, to resume after the reset, instead of switching models.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import httpx
from google.genai.errors import APIError
from neo4j.exceptions import ServiceUnavailable, SessionExpired

from src.llm.client import LLMClient, ModelUnavailableError
from src.llm.rate_limiter import DailyLimitReached
from src.qa.answer import QAResult, answer_question

SYSTEMS = ("graph", "baseline")
INFRA_ERRORS = (ModelUnavailableError, APIError, httpx.TransportError, ServiceUnavailable, SessionExpired)


def load_questions(path: Path) -> list[dict]:
    questions = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [q for q in questions if q.get("verified") is True]


def load_answers(path: Path) -> dict[tuple[str, str], dict]:
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {(r["id"], r["system"]): r for r in rows}


def _record(q: dict, system: str, result: QAResult, model: str, commit: str) -> dict:
    return {
        "id": q["id"], "system": system, "question": q["question"], "answer": result.answer,
        "route": result.route, "cypher": result.cypher, "paths": result.paths, "sources": result.sources,
        "notes": result.notes, "model": model, "commit": commit,
        "answered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def run(questions: list[dict], answers_path: Path, client: LLMClient, driver,
        baseline: Callable[[str], tuple[str, list[str]]], commit: str,
        progress: Callable[[str], None] = print) -> dict:
    """Answer every missing (question, system) pair. Returns counts of what happened."""
    done = load_answers(answers_path)
    counts = {"already_done": 0, "answered": 0, "infra_failed": 0, "stopped_on_quota": False}
    answers_path.parent.mkdir(parents=True, exist_ok=True)
    for q in questions:
        for system in SYSTEMS:
            if (q["id"], system) in done:
                counts["already_done"] += 1
                continue
            try:
                if system == "graph":
                    result = answer_question(q["question"], client, driver, baseline)
                else:
                    answer, sources = baseline(q["question"])
                    result = QAResult(q["question"], answer, "baseline", sources=sources)
            except DailyLimitReached as exc:
                progress(f"{q['id']} {system}: daily quota used up ({exc}); stopping, resume after the reset")
                counts["stopped_on_quota"] = True
                return counts
            except INFRA_ERRORS as exc:
                progress(f"{q['id']} {system}: infrastructure failure, will retry next run: "
                         f"{type(exc).__name__}: {' '.join(str(exc).split())[:200]}")
                counts["infra_failed"] += 1
                continue
            row = _record(q, system, result, client.default_model, commit)
            with answers_path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            done[(q["id"], system)] = row
            counts["answered"] += 1
            progress(f"{q['id']} {system}: answered (route {result.route})")
    return counts
