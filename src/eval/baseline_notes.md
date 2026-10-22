# Baseline RAG test notes

Manual spot-checks of the Phase 2 plain RAG baseline (`ask --mode baseline`), run against
all 5 pilot companies' indexed reports. Not a scored evaluation — early candidates for
`eval/questions.jsonl` (Phase 7). Gold answers there must still be verified against the PDFs
by hand, not copied from these runs.

## 1. "Who are the independent directors of TCS?"

**Answer:** TCS has 5 independent directors out of a total of 9 directors [Tata Consultancy
Services Limited, p.95, p.94]. However, the provided excerpts do not specify the names of
these independent directors.

**Sources:** TCS pp.94-95, p.95, pp.117-119, pp.64-65 (plus two chunks from other companies
that scored into the top-k but weren't used in the answer)

**Note:** Retrieval found the *count* of independent directors but not the page listing their
names — a real baseline limitation. Candidate category: `1hop` (if the gold answer is just the
count) or a harder retrieval case (if the gold answer is the name list). Good test of whether
hybrid/keyword search (see README "To do before Phase 7") fixes this.

## 2. "Who is the statutory auditor of Tata Steel?"

**Answer:** The provided excerpts do not explicitly state the name of the statutory auditor of
Tata Steel Limited for the consolidated financial statements for the year ended March 31, 2024.
Excerpt 1 starts the "INDEPENDENT AUDITORS REPORT" but does not show the signatory firm
[p.419]. Excerpt 2 mentions "the Report of the Auditors" but does not name them [p.557].
Excerpt 4 mentions Messrs Shome & Banerjee as Cost Auditors, which is a different role [p.570].

**Sources:** Tata Steel pp.418-419, pp.556-557, pp.438-439, pp.569-570, pp.260-261, p.270

**Note:** Correctly distinguished the cost auditor from the statutory auditor instead of
guessing — the "don't guess" instruction in the prompt held up. The actual auditor name is on
the signature page of the auditor's report, which didn't make the top-6 retrieved chunks.
Candidate category: `1hop`, expected to need better retrieval or more chunks to pass.

## 3. "Which directors sit on the boards of both Tata Motors and Tata Steel?"

**Answer:** Not obtained — hit Gemini's real daily quota for `gemini-3.8-flash` before
answering (see `GEMINI_MODEL_LIMITS` in `.env`; this was Google's actual free-tier cap for that
model, not our own configured limit, which was far from used up). Left unanswered deliberately,
per the user's instruction, for the eval set rather than re-run.

**Note:** This is also the kind of question the plain baseline is *expected* to struggle with
regardless of quota — it needs cross-document reasoning (comparing two separate reports' director
lists), which plain top-k chunk retrieval over one index can't really do. Good `2hop` candidate:
this is exactly the gap the graph phases (5-6) are meant to close, and the baseline's failure
mode here should be "can't connect the two documents," not "ran out of quota" — rerun once a
quota resets so the recorded failure reason is the real one, not quota exhaustion.

## Phase 7 step 1: stronger baseline, before vs after (2026-10-22)

Same three questions, same answer model as the graph route (gemini-3.5-flash-lite), both at temperature 0, so
only retrieval differs. Before = the Phase 2 baseline (embeddings only, top 6, no company filter). After =
hybrid search (top 40 by embeddings and top 40 by BM25, combined by reciprocal rank fusion, each method's top 4
always kept), top 12, and a company filter when the question names pilot companies (an equal share each when
it names several). The answers recorded above came from gemini-3.8-flash, the QA model at the time, so they are
not the comparison.

| Question | Before | After |
|---|---|---|
| Who are the independent directors of TCS? | correct (all five, from the p.117 certificate) | correct (all five, pp.117-119) |
| Who is the statutory auditor of Tata Steel? | wrong: says the excerpts don't name the firm (saw only its FRN and partner) | correct: Price Waterhouse & Co Chartered Accountants LLP (pp.426, 299) |
| Which directors sit on the boards of both Tata Motors and Tata Steel? | wrong: found nothing on Tata Motors (all six chunks were Tata Steel's) | correct for the year end: N Chandrasekaran (O P Bhatt left Tata Steel's board on June 9, 2023) |

A first version of the hybrid search lost question 1: fusion alone ranked the certificate chunk (a strong
embedding hit with no keyword hit) below chunks both methods ranked moderately, and named Don Callahan, who
ceased in January 2024. Keeping each method's top hits fixed it. With two companies named, the first
version still filled all 12 slots from Tata Steel; the equal share fixed that.

**Who are the independent directors of TCS?**

- Before: Based on the provided excerpts, the independent directors of Tata Consultancy Services Limited (TCS) are: * O P Bhatt [Tata Consultancy Services Limited, p. 117] * Dr. Pradeep Kumar Khosla [Tata Consultancy Services Limited, p. 117] * Hanne Sorensen [Tata Consultancy Services Limited, p. 117] * Keki Mistry [Tata Consultancy Services Limited, p. 117] * Al-Noor Ramji [Tata Consultancy Services Limited, p. 117]
  - Sources: TCS p.95, TATACONSUM p.291, TCS pp.94-95, TCS pp.117-119, TATAMOTORS pp.516-517, TCS pp.64-65
- After (filter: TCS): Based on the provided excerpts, the independent directors of Tata Consultancy Services Limited are: * O P Bhatt [Tata Consultancy Services Limited, pp. 117-119] * Dr. Pradeep Kumar Khosla [Tata Consultancy Services Limited, pp. 117-119] * Hanne Sorensen [Tata Consultancy Services Limited, pp. 117-119] * Keki Mistry [Tata Consultancy Services Limited, pp. 117-119] * Al-Noor Ramji [Tata Consultancy Services Limited, pp. 117-119]
  - Sources: TCS p.95, TCS pp.94-95, TCS pp.117-119, TCS pp.64-65, TCS p.59, TCS pp.108-109, TCS pp.96-97, TCS pp.114-116, TCS p.109, TCS p.99, TCS pp.1-3, TCS pp.93-94

**Who is the statutory auditor of Tata Steel?**

- Before: Based on the provided excerpts, the excerpts do not state who the statutory auditor of Tata Steel is. (The reports mention "Independent Auditor's Report" by a firm with Firm Registration Number 304026E/E-300009 and partner Subramanian Vivek, and Cost Auditors Messrs Shome & Banerjee, but do not explicitly name the statutory auditor entity) [Tata Steel Limited, pp. 418-419, 569-570].
  - Sources: TATASTEEL pp.418-419, TATASTEEL pp.556-557, TATASTEEL pp.438-439, TATASTEEL pp.569-570, TATASTEEL pp.260-261, TATASTEEL p.270
- After (filter: TATASTEEL): Based on the provided excerpts, the statutory auditor for Tata Steel's consolidated and standalone financial statements is **Price Waterhouse & Co Chartered Accountants LLP** [Tata Steel Limited, pp. 426, 299].
  - Sources: TATASTEEL pp.418-419, TATASTEEL pp.556-557, TATASTEEL pp.438-439, TATASTEEL pp.569-570, TATASTEEL p.100, TATASTEEL pp.426-427, TATASTEEL p.121, TATASTEEL pp.299-300, TATASTEEL pp.286-289, TATASTEEL pp.1-3, TATASTEEL pp.429-430

**Which directors sit on the boards of both Tata Motors and Tata Steel?**

- Before: The provided report excerpts do not contain information about the boards of Tata Motors, so I cannot answer this question.
  - Sources: TATASTEEL pp.438-439, TATASTEEL pp.418-419, TATASTEEL pp.10-12, TATASTEEL p.174, TATASTEEL p.100, TATASTEEL pp.556-557
- After (filter: TATAMOTORS, TATASTEEL): Based on the provided excerpts, N Chandrasekaran is a director on the boards of both Tata Motors Limited and Tata Steel Limited [Tata Motors Limited, p. 404, p. 502; Tata Steel Limited, pp. 418-419].
  - Sources: TATAMOTORS pp.404-405, TATASTEEL pp.438-439, TATAMOTORS p.502, TATASTEEL pp.418-419, TATAMOTORS p.528, TATASTEEL p.60, TATAMOTORS pp.106-107, TATASTEEL pp.60-61, TATAMOTORS pp.263-264, TATASTEEL p.242, TATAMOTORS p.248, TATASTEEL p.100
