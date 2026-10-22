# Phase 7 test set: plan (fixed before drafting)

Written and committed on 2026-10-22, before any test question was drafted. The mix below is
fixed: it will not change after seeing which system does better.

## Mix (95 questions)

| Category | Count | What it tests |
|---|---|---|
| `1hop` | 15 | One fact from one report (an auditor, a KMP, a director's category, a subsidiary's stake, a related-party amount). |
| `2hop` | 20 | Two linked facts, within one report or across two (at least 8 involve two companies). |
| `3hop` | 15 | Three linked facts (at least 8 involve two or more companies). |
| `aggregation` | 20 | Counting or complete lists that need a whole table or list, not one row (e.g. "how many TCS subsidiaries are incorporated in the USA?", "list every independent director of Tata Motors"). |
| `text_only` | 15 | Facts that live in prose or financial statements, not in the graph (results, headcount, board meetings, CSR). The baseline should win these. |
| `none_or_unanswerable` | 10 | 5 whose correct answer is "none" (e.g. Infosys directors on another pilot company's board) and 5 the reports can't answer (e.g. who audits a subsidiary). |

Each of `1hop`, `aggregation` and `text_only` spreads across all five companies (3 or 4 per company).
Two-company questions are included on purpose even where the strengthened baseline may now answer
them: the test should show where each system wins, not favour one.

## Rules

- Drafted from the PDFs (page text read directly), not from the graph or the extracted facts.
- Each question has a proposed gold answer, the PDF page(s) to check it, and `verified: false`.
  Only questions the user verifies against the PDFs count in the scores.
- None may repeat or reword a practice question: the 16 in `src/qa/dev_questions.jsonl` or the
  3 in `src/eval/baseline_notes.md` (used to tune the baseline). Excluded topics, as asked
  there: Tata Steel's statutory auditor; TCS's independent directors; directors shared by Tata
  Motors and Tata Steel, or by Tata Motors and TCS; which pilot companies share a statutory
  auditor; Tata Motors subsidiaries that are TCS related parties; the board seat of Tata Motors'
  CFO; auditors of pilot companies with a Tata Steel director; companies connected to both Tata
  Motors and TCS; Tata Steel's subsidiary count; which company has the most subsidiaries;
  Infosys's board size; TCS's headcount; Tata Steel's dividend; TCS's CEO; Tata Consumer's
  director list; N Chandrasekaran's DIN; "Krishnakumar" at Tata Consumer.
- "FY2024" means the year ended March 31, 2024. "The board" means directors at March 31, 2024
  unless the question says otherwise.
- No evaluation is run until the user has verified the gold answers and the scoring rules are
  agreed in writing.
