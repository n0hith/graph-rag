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
