# Phase 7 scoring rules (agreed before any evaluation run)

Written 2026-10-22 and committed before the test set is run by either system. These rules will
not change after seeing results.

## What is scored

- Only questions in `src/eval/questions.jsonl` with `verified: true` count. Where the user
  corrected a gold answer during verification, the corrected answer is the gold.
- Two systems: the graph route (`ask --mode graph`, which may fall back to the baseline by its
  own rules) and the baseline (`ask --mode baseline`).

## How each answer type is scored

**Lists** (`answer_type: entity_list`)
- Per question: precision, recall and F1 between the entities in the answer and the gold list.
- Name matching handles aliases and spellings: case, punctuation, titles (Mr/Ms/Dr), legal forms
  (Ltd/Limited, Pvt/Private), the l/I lookalike, every alias the resolved entities record, and
  close spellings (similarity 0.9 or more). Each gold item can be matched once.
- A gold item that carries a value ("Tata Motors: ₹298.51 crore", "Japan 66%") counts as found
  only if the answer gives that value for that entity (number rules below).
- Reported per category: average F1, and the share of questions answered completely correctly
  (F1 = 1, i.e. every gold item found and nothing extra).

**Numbers and counts** (`answer_type: number`)
- A number is correct if it equals the gold value. It may be stated at a different precision
  (e.g. rounded to the nearest crore) or with different formatting or units: "₹2,40,893 crore",
  "2,40,893", "240,893 crore" and "Rs 2.40893 lakh crore" are the same; "129" and "one hundred
  twenty-nine" are the same; "55.39%" and "55.39 percent" are the same. An approximate value
  ("about ₹1,100 crore") or a different value is wrong.
- *Note, 2026-10-23 (after the results):* this rule used to end "A rounded or approximate value
  is wrong". That wording was too strict and contradicted the rule's own "formatting and units
  may differ" clause; this corrects it. It was applied in the text-only hand check to t078
  (hand-check rows 7 and 21): "₹140,987 crore" for the gold "₹1,40,987.43 crore", graded 1
  instead of the judge's 0.5. It does not change the result: both systems gave that answer, and
  text-only is a tie either way. The automatic scorer (`src/eval/score.py`) was not changed.
  None of the 64 automatically scored failures gives a value within 1% of a gold value, so no
  automatic score would change under either wording.

**Dates and short factual text outside `text_only`** (`answer_type: text` in other categories)
- Split into the key facts the gold states (each date, number, name); scored as a list of those
  facts by the rules above. Dates match whatever the format ("June 1, 2023", "01/06/2023").

**None and unanswerable** (`answer_type: none` / `unanswerable`)
- Correct only if the system says there are none, or that the reports don't say. Mentioning
  related context is fine (e.g. that the previous Company Secretary resigned).
- Any invented answer (naming an entity, a value or a date as the answer) is wrong.

**Text-only** (`category: text_only`)
- Graded by an LLM judge with the fixed rubric below, and reported separately from the other
  categories. The user hand-checks ALL of the judge's grades (15 questions x 2 systems = 30);
  where the user disagrees, the user's grade counts, and the judge's agreement rate is reported.
- Judge: the configured `GEMINI_QA_MODEL` at temperature 0, with the prompt below, fixed in code
  before the run. (It is the same model that writes both systems' answers, which is why every
  grade is checked by hand.)
- Rubric: **1** = states the gold answer's key fact(s) correctly and nothing that contradicts
  them; **0.5** = some key facts correct, some missing; **0** = wrong, contradicts the gold, or
  says the reports don't contain it. The judge returns the grade and a one-line reason.

## Clarification questions

- Answering "which one do you mean?" counts as wrong, unless the question is genuinely ambiguous
  (marked `ambiguous: true` during verification). The current draft has no such question.

## Fair comparison

- The grader does not see which system gave an answer: answers are shuffled and stripped of the
  system name, route, Cypher and sources before grading (automatic scoring and the LLM judge).
- Each system runs once, at temperature 0, on every verified question. No re-runs and no prompt
  or code changes after seeing results. If a call fails for an infrastructure reason (quota,
  network) before any answer is produced, that call is retried; an answer, once produced, is final.

## Report

- Results by category for both systems: questions scored; for lists, average F1 and the share
  completely correct; for numbers, accuracy; for none/unanswerable, accuracy; text-only judge
  scores separately (after the user's hand check of every grade), with the judge's agreement rate.
- Overall results, and which system wins each category.
- A failure list: every question a system got less than fully right, with the reason, from a
  fixed set: wrong query, missing fact (not in the graph), extraction error, entity not found,
  asked for clarification, fell back to the baseline, retrieval miss (baseline), invented answer,
  partial list, wrong value.
