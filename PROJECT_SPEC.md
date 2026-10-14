# Project: Graph RAG over Indian Company Annual Reports

## Who I am and how I want you to work
I'm a third-year CSE student building this as a serious resume project for SWE/ML internships. I want it to be deep, well-engineered, and honestly evaluated, not a demo that only works on cherry-picked questions.

Working rules:
- Build ONE phase at a time. At the end of each phase, STOP and give me a short progress report in plain, simple language: what works, what doesn't, what's next. Avoid heavy jargon and walls of numbers.
- Always write complete files, never partial snippets or "rest stays the same".
- When you create or change files, show where they sit in the project structure.
- Never invent data: no made-up URLs, company IDs, or answers. If you need something from me (like report URLs), ask.
- Never hardcode answers to make tests pass.
- If something in this spec is unclear or a better approach exists, ask me before building.

## The goal
Normal vector RAG fails on multi-step questions whose answer is spread across several documents, e.g.:
- "Which people are directors of both Company A and Company B?"
- "Which audit firm audits both Tata Steel and Infosys, if any?"
- "How many Nifty 50 companies does Deloitte (or its Indian affiliates) audit?"

This project:
1. Extracts facts (companies, people, auditors, and their relationships) from annual reports into a knowledge graph.
2. Answers questions by turning them into graph queries, showing the path it followed and citing source pages.
3. Proves, with a proper test set, where this beats a plain RAG baseline and where it doesn't.

## Scope
- Data: FY2023-24 annual reports of Nifty 50 companies (PDFs).
- Pilot with 5 companies first: TCS, Tata Motors, Tata Steel, Tata Consumer Products, Infosys (Infosys is the deliberate outsider, to test that the system returns empty answers instead of inventing links). No banks in the pilot. Only scale to all 50 after the pipeline works end to end on 5.
- I will provide report URLs in `data/companies.csv`. Create the file with headers and an example row, then ask me to fill it in.

## Tech stack
- Python 3.11, with a virtual environment and `requirements.txt` using pinned versions
- PDF parsing: PyMuPDF (text), pdfplumber (tables)
- Schemas and validation: Pydantic v2
- LLM: Google Gemini via the official `google-genai` Python SDK (`from google import genai`). Do NOT use the older deprecated `google-generativeai` package.
  - Before writing the client, check Google's current Gemini API docs for the SDK usage and current model names. Do not rely on memory for model names.
  - Two configurable models in `.env`:
    - `GEMINI_EXTRACTION_MODEL`: a fast, cheap "Flash"-class model for bulk fact extraction
    - `GEMINI_QA_MODEL`: a stronger model for question → Cypher and answer writing
  - Wrap everything in a provider-agnostic client in `src/llm/client.py` with methods like `generate_text(...)` and `generate_structured(prompt, pydantic_model)`, so the provider can be swapped later. Ollama is deferred (not installed); the interface stays provider-agnostic so it can be added later.
  - Rate limiting and resilience:
    - Configurable requests-per-minute limit (`GEMINI_RPM` in `.env`), enforced client-side
    - Configurable requests-per-day limit (`GEMINI_RPD`). When reached, stop cleanly with a clear message; the next run resumes where it stopped
    - Exponential backoff with jitter on rate-limit (429) and server (5xx) errors, with a max retry count
    - Long jobs must be resumable: if extraction stops halfway, re-running continues from where it stopped
  - Cache every LLM call on disk, keyed by a hash of model + prompt + schema, so re-runs cost nothing
  - Track and log approximate token usage per pipeline step, and print a short summary at the end of each run
- Embeddings: sentence-transformers `BAAI/bge-small-en-v1.5` (local, free)
- Vector store for the baseline: ChromaDB (local, persistent)
- Graph database: Neo4j 5 Community via `docker-compose.yml`, official `neo4j` Python driver
- Fuzzy name matching: rapidfuzz
- CLI: typer, with commands `download`, `sectionize`, `extract`, `resolve`, `load`, `baseline-index`, `ask`, `eval`
- Demo: Streamlit, with a graph view using `streamlit-agraph` or pyvis
- Tests: pytest
- Config: `.env` + `src/config.py`; never commit secrets. Provide `.env.example` with: `GEMINI_API_KEY`, `GEMINI_EXTRACTION_MODEL`, `GEMINI_QA_MODEL`, `GEMINI_RPM`, `GEMINI_RPD`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `LLM_PROVIDER` (default `gemini`)

## Project structure
```
graph-rag-filings/
├── data/
│   ├── companies.csv          # name, nse_symbol, cin, report_url (I fill this)
│   ├── raw_pdfs/
│   ├── sections/              # extracted sections as JSON with page numbers
│   ├── extracted/             # raw LLM-extracted facts (JSONL)
│   ├── resolved/              # cleaned, merged facts ready for loading
│   ├── overrides/             # manual merge/fix files I can edit
│   └── cache/                 # LLM response cache
├── src/
│   ├── config.py
│   ├── llm/
│   │   ├── client.py          # provider-agnostic interface
│   │   ├── gemini_provider.py
│   │   ├── ollama_provider.py
│   │   ├── rate_limiter.py
│   │   └── cache.py
│   ├── ingest/
│   │   ├── download.py
│   │   └── sectionize.py
│   ├── extract/
│   │   ├── schema.py
│   │   ├── prompts.py
│   │   └── extractor.py
│   ├── resolve/
│   │   └── merge_entities.py
│   ├── graph/
│   │   ├── load_neo4j.py
│   │   └── schema_info.py     # graph schema text given to the LLM
│   ├── qa/
│   │   ├── baseline_rag.py
│   │   ├── text_to_cypher.py
│   │   ├── cypher_guard.py    # safety + validation for generated queries
│   │   └── answer.py          # router: graph first, fallback to baseline
│   ├── eval/
│   │   ├── questions.jsonl
│   │   ├── sample_facts.py    # exports facts for hand-checking
│   │   └── run_eval.py
│   └── cli.py
├── app/demo.py
├── tests/
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── PROJECT_SPEC.md
└── README.md
```

## Graph schema
Nodes:
- `Company {cin (unique), name, nse_symbol}`
  - Subsidiaries may lack a CIN (foreign subsidiaries). Use a generated stable id plus normalized name for those.
- `Person {din (unique when present), name, name_normalized}`
- `AuditFirm {name, firm_registration_no}`

Relationships (EVERY relationship must carry `source_doc`, `page`, `evidence` (short exact quote), `fy`):
- `(Person)-[:DIRECTOR_OF {role, is_independent, is_executive, status: current|ceased|appointed, appointed_on, ceased_on}]->(Company)` (dates only when the report states them)
- `(Person)-[:KMP_OF {role}]->(Company)` for CEO, CFO, Company Secretary
- `(Company)-[:SUBSIDIARY_OF {stake_pct}]->(Company)`
- `(Company)-[:ASSOCIATE_OF | JV_OF {stake_pct}]->(Company)`
- `(Company)-[:AUDITED_BY {audit_type: statutory|secretarial}]->(AuditFirm)`
- `(Company)-[:RELATED_PARTY_TXN {nature, amount_inr_crore}]->(Company|Person)`

## Decisions made before Phase 0
- Auditors are recorded only where the report names them. Subsidiary auditors are usually not named in the parent's report, so a question like "Which subsidiaries of Tata Steel are audited by the same firm that audits Infosys?" stays in the test set, marked as unanswerable from this data.
- `ollama_provider.py` is not created until Ollama is actually needed.
- One git commit at the end of each phase.

## Phases

### Phase 0: Setup
Repo skeleton, requirements, docker-compose for Neo4j, `.env.example`, config, LLM client (Gemini provider with rate limiting, retries, and caching), CLI skeleton, empty `companies.csv` with headers. README with setup steps, including how to get a Gemini API key from Google AI Studio. Confirm Neo4j starts, and confirm the Gemini client works with: one plain text call, one structured-output call using a small Pydantic model, and a second identical call that is served from the cache.

### Phase 1: Download and sectionize
- Download PDFs from `companies.csv` politely (retries, timeouts, skip already-downloaded files).
- Find relevant sections using heading keywords and page-range logic: Board of Directors / Corporate Governance Report (director names, DINs, categories), Form AOC-1 / list of subsidiaries, Independent Auditor's Report, Secretarial Audit Report, Related Party Transactions note.
- Save each section as JSON: company, section_type, page_start, page_end, text per page, and tables where detected.
- Print a summary per company: which sections were found and which were missing.

### Phase 2: Plain RAG baseline (build this BEFORE the graph)
- Chunk full report text (about 500 tokens, small overlap, keep page numbers), embed, store in ChromaDB.
- `ask --mode baseline "question"` retrieves top-k chunks and answers with page citations, using `GEMINI_QA_MODEL`.
- This is the system the graph version must beat, so make it reasonable, not deliberately weak.

### Phase 3: Fact extraction
- Pydantic models for each fact type in `schema.py`.
- Section-specific prompts in `prompts.py` (directors prompt differs from subsidiaries prompt).
- Use Gemini's structured output (JSON response with a schema derived from the Pydantic model) via `generate_structured`, with `GEMINI_EXTRACTION_MODEL`. Still validate every response with Pydantic. On invalid output, retry up to 2 times with the error message included.
- Each fact must include an `evidence` quote. Check the quote actually appears in the source text (allowing for whitespace differences). Drop facts that fail and log them, since these are likely hallucinations.
- Where a section has a clean table (directors with DINs, subsidiary lists), try table parsing first and only use the LLM when table parsing fails. Record which method produced each fact. This also saves API calls.
- Keep long sections within sensible input sizes: split by page groups if needed, then merge duplicate facts afterwards.
- `sample_facts.py`: export a random sample of 50 facts to CSV with a blank "correct?" column so I can hand-check accuracy. Then a script reads my labels and reports accuracy per fact type.

### Phase 4: Entity resolution
- Persons: merge by DIN first. Without DIN, normalize names (remove Mr/Ms/Dr/Shri/Smt, punctuation, handle initials like "N." vs "Natarajan") and fuzzy-match within strict thresholds.
- Companies: merge by CIN first, else normalized-name matching (handle "Ltd" vs "Limited", "Pvt", brackets, "(formerly ...)").
- Write every merge decision to a log file. Support `data/overrides/merges.csv` (force-merge / force-split) that I can edit.
- Report: number of entities before and after merging, plus uncertain matches for me to review.

### Phase 5: Load into Neo4j
- Uniqueness constraints and indexes first.
- Idempotent loading with MERGE so re-running doesn't duplicate anything.
- After loading, print simple counts and run 3 sanity queries.

### Phase 6: Graph question answering
- `schema_info.py` produces a compact text description of the graph schema, plus 8-10 example question → Cypher pairs covering 1-hop, 2-hop, 3-hop, and counting questions.
- `text_to_cypher.py`: question → Cypher using that schema and the examples, with `GEMINI_QA_MODEL`.
- `cypher_guard.py`:
  - Reject any write operation (CREATE, MERGE, DELETE, SET, REMOVE, DROP, LOAD CSV, CALL dbms/apoc write procedures).
  - Run `EXPLAIN` first to catch syntax errors. On error, retry generation up to 2 times with the error message.
  - Force a LIMIT if none is present. Add a query timeout.
  - Run the queries with a read-only session.
- `answer.py` router: try the graph first. If the query fails, returns nothing, or the question is clearly about prose (e.g. "what does the company say about its ESG strategy?"), fall back to the baseline. Always return: the answer, which route was used, the Cypher (if any), the graph path(s), and source citations (doc + page).
- Handle entity names in questions: map "Tata Motors" / "TaMo" / "TATAMOTORS" to the right node with a fuzzy lookup step before generating Cypher.

### Phase 7: Evaluation
- `questions.jsonl` fields: id, question, category (`1hop`, `2hop`, `3hop`, `aggregation`, `text_only`), gold_answer (list of entities, a number, or a short text), verified (true/false), notes.
- Help me write about 100 questions. You may draft candidates using templates over the graph, but gold answers MUST be verified by me against the PDFs, not copied from the graph (otherwise the test is biased toward the graph). Only verified questions count in the final scores.
- Include `text_only` questions where the baseline SHOULD win, so the evaluation is honest.
- Scoring: exact match for numbers; precision/recall/F1 over entity sets for list answers; optional LLM-as-judge for text answers, reported separately.
- Run both systems on every question. Output a results table by category, a simple bar chart, and a file of failures with their reason (wrong query, missing fact, extraction error, entity not found).
- Respect the rate limit during evaluation and use the cache so re-running the eval is cheap.
- Summarize the results in plain language in the README.

### Phase 8: Demo app
Streamlit app: question box, toggle for Graph / Baseline / Both side by side, answer, sources with page numbers, the generated Cypher in an expandable box, and an interactive graph view highlighting the answer path. Include 5 example questions as clickable buttons.

## Quality bar
- Type hints and docstrings on public functions.
- Logging instead of prints inside the pipeline (CLI summaries can print).
- pytest tests for: name normalization, entity merging, cypher_guard (it must block write queries), the evidence-quote check, section detection on a small fixture, the rate limiter, and the LLM cache. Tests must not call the real Gemini API; mock it.
- Every pipeline step can be re-run safely and skips work already done.
- README: problem statement, architecture diagram (Mermaid), setup, how to run each step, evaluation results, known limitations.

## Start
Begin with Phase 0. Before writing any code, list any questions you have about this spec.
