# Graph RAG over Indian Company Annual Reports

A question-answering system that turns five companies' annual reports into a
knowledge graph, so it can answer questions whose answer is spread across
several documents — the kind plain RAG struggles with. On a 95-question test
set, every answer checked against the source PDFs, it beats a strong
hybrid-search RAG baseline on multi-step questions, and this README is upfront
about where it doesn't.

## The problem

Normal RAG finds the paragraphs most similar to your question and hands them to
an LLM. That works for "Who is TCS's auditor?" but breaks on "Which directors
sit on the boards of both Tata Motors and Tata Steel?" — no single paragraph
holds the answer. You have to collect facts from two 500-page reports and
compare them.

## The approach

Read the reports once, pull out the important facts (directors, subsidiaries,
auditors, related-party transactions), and store them as a knowledge graph of
companies, people, and the relationships between them. A question is then
answered by turning it into a graph query, which can walk those relationships
directly. Every fact keeps a link to the exact report page it came from.

## Data

FY2023-24 annual reports of five Nifty 50 companies: TCS, Tata Motors, Tata
Steel, Tata Consumer Products, and Infosys. Infosys is deliberately the
"outsider" — it shares no directors with the Tata companies, which lets the
system be tested on questions that should correctly return no answer.

The final graph has 549 entities (476 companies, 54 people, 6 audit firms, 13
related-party groups) and 1,016 relationships. 6 people and 18 companies appear
in more than one report — these shared entities are what make cross-company
questions possible.

## How it works

1. **Download & sectionize** — fetch the reports, locate the relevant sections.
2. **Baseline RAG** — a hybrid (keyword + embedding) search system, built as a
   fair competitor to beat.
3. **Fact extraction** — an LLM pulls out facts, each with an exact supporting
   quote; facts whose quote isn't on the page are dropped as likely
   hallucinations. Rule-based checks then verify amounts, dates and director
   IDs against the PDF pages.
4. **Entity resolution** — merge duplicate people and companies across reports
   using director/company registration IDs (DIN/CIN) and name matching.
5. **Graph loading** — into Neo4j, with stable IDs so re-runs don't duplicate.
6. **Graph question answering** — question → Cypher query (read-only, with
   safety checks), falling back to the baseline when the graph can't answer.
7. **Evaluation** — 95 verified questions, both systems compared.

## Results

On the 80 questions outside the free-text category:

| Category | n | Graph | Baseline | Winner |
|---|---|---|---|---|
| 1-hop (simple lookup) | 16 | 0.98 | 0.92 | Graph |
| 2-hop | 20 | 0.88 | 0.75 | Graph |
| 3-hop | 15 | 0.62 | 0.37 | Graph |
| Aggregation / counting | 20 | 0.54 | 0.58 | Baseline |
| None / unanswerable | 9 | 0.67 | 0.89 | Baseline |
| **Overall** | **80** | **0.74** | **0.68** | **Graph** |

(Mean score per question: F1 for list answers, 1 or 0 otherwise.)

Free-text questions (15) are a tie at 0.87 each — both systems route these
through the baseline. Those answers were graded by an LLM judge, and all 30
grades were checked by hand (93% agreement).

The questions were written from the PDFs, not the graph, and every gold answer
was checked against the cited pages. Full results, every answer and the failure
list are in [`reports/eval_results.md`](reports/eval_results.md).

**What this shows:** the graph's advantage grows as questions require more
steps, which is exactly the gap it was built to close. The baseline is better
at knowing when to say "no answer", and neither system got any of the four
"how many" questions right.

## Honest limitations

- **Counting is the weak spot.** On all four "how many" questions the graph
  fell back to the baseline, which got them wrong. Three of them ask how many
  subsidiaries are incorporated in a given country. The graph stores country
  for TCS, Tata Motors and Infosys subsidiaries, but the schema description the
  query model sees doesn't mention it, so the model decided the graph couldn't
  answer. That's the clearest next improvement; measuring it fairly needs new
  questions, not this test set.
- **"No answer" questions:** the graph got 6 of 9 right, the baseline 8 of 9.
  Of the graph's three misses, one asked for clarification on an ambiguous name,
  one came from the baseline after falling back, and one was a graph answer
  that should have been "none".
- **Subsidiary auditors aren't extracted.** Found during test-set
  verification: the governance report's material-subsidiaries table names them,
  but extraction doesn't read that table yet. Deliberately not fixed before
  evaluation, to avoid tuning to the test set.
- Tables printed sideways or without borders rely on the LLM reading page text
  rather than table parsing.

## Tech stack

Python, Google Gemini (extraction & querying), Neo4j (knowledge graph),
ChromaDB + sentence-transformers + BM25 (baseline RAG), Streamlit (demo).
~260 tests.

## Running it

Requires Python 3.11, Docker (for Neo4j) and a Gemini API key. The annual
reports aren't in the repo: `download` fetches them from the URLs in
`data/companies.csv` and checks them against `data/pdf_checksums.json`.

```
pip install -r requirements.txt
copy .env.example .env            # then add GEMINI_API_KEY and NEO4J_PASSWORD
docker compose up -d

python -m src.cli download
python -m src.cli sectionize
python -m src.cli baseline-index
python -m src.cli extract
python -m src.cli check-dins
python -m src.cli check-rpt-amounts
python -m src.cli check-dates
python -m src.cli clean-facts
python -m src.cli resolve
python -m src.cli load

python -m src.cli ask "Who is the statutory auditor of Tata Steel?"
python -m src.cli ask --mode both "Which directors sit on the boards of both Tata Motors and Tata Steel?"
streamlit run src/demo/app.py
```

`python -m src.cli eval` and `eval-score` re-run the evaluation. Setup details
(API rate limits, resuming after a quota stop), every command, and the notes
from each phase are in [`docs/technical-notes.md`](docs/technical-notes.md).
