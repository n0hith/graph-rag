# Phase 7 evaluation results

Answers produced at code commit(s) `fcc5dd9` with `gemini-3.5-flash-lite` (fallback model off), temperature 0, one run per system; scored at commit `1e25cc0` by `eval-score` (src/eval/score.py, src/eval/scoring_key.jsonl). 95 verified questions x 2 systems.

## Results by category (automatic scoring)

Per question: F1 for lists, 1 or 0 for numbers and none/unanswerable. Fully correct: F1 = 1 or right. Winner: higher mean score.

| Category | Questions | Graph: mean score | Graph: fully correct | Baseline: mean score | Baseline: fully correct | Winner |
|---|---|---|---|---|---|---|
| 1hop | 16 | 0.98 | 94% | 0.92 | 88% | graph |
| 2hop | 20 | 0.88 | 80% | 0.75 | 60% | graph |
| 3hop | 15 | 0.62 | 53% | 0.37 | 20% | graph |
| aggregation | 20 | 0.54 | 35% | 0.58 | 35% | baseline |
| none_or_unanswerable | 9 | 0.67 | 67% | 0.89 | 89% | baseline |
| **All except text-only** | 80 | 0.74 | 65% | 0.68 | 55% | graph |

Item extraction was spot-checked by the user (24 of the 159 extractions in `exports/extraction_check.csv`): every one listed exactly what the answer claims, with values attached and "none" marked correctly; no extraction errors found.

### By answer type

| Category | System | Lists: n | Lists: average F1 | Lists: fully correct | Numbers: n | Numbers: exact match | None/unanswerable: n | None/unanswerable: accuracy |
|---|---|---|---|---|---|---|---|---|
| 1hop | graph | 13 | 0.97 | 92% | 3 | 100% | 0 | - |
| 1hop | baseline | 13 | 0.97 | 92% | 3 | 67% | 0 | - |
| 2hop | graph | 19 | 0.87 | 79% | 1 | 100% | 0 | - |
| 2hop | baseline | 19 | 0.74 | 58% | 1 | 100% | 0 | - |
| 3hop | graph | 15 | 0.62 | 53% | 0 | - | 0 | - |
| 3hop | baseline | 15 | 0.37 | 20% | 0 | - | 0 | - |
| aggregation | graph | 16 | 0.67 | 44% | 4 | 0% | 0 | - |
| aggregation | baseline | 16 | 0.72 | 44% | 4 | 0% | 0 | - |
| none_or_unanswerable | graph | 0 | - | - | 0 | - | 9 | 67% |
| none_or_unanswerable | baseline | 0 | - | - | 0 | - | 9 | 89% |

## Text-only (LLM judge, hand-checked)

The judge graded all 30 answers; the user hand-checked every grade, and the user's grade counts where they disagree (src/eval/judge_handcheck.jsonl).

| System | Questions | Mean grade (final) | Grade 1 | Grade 0.5 | Grade 0 | Mean judge grade | Winner |
|---|---|---|---|---|---|---|---|
| graph | 15 | 0.87 | 13 | 0 | 2 | 0.83 | tie |
| baseline | 15 | 0.87 | 13 | 0 | 2 | 0.83 | tie |

Judge agreement with the user's hand check: 28/30 = 93%.

Grades the user changed:

- t078 (baseline, hand-check row 7): judge 0.5 -> user 1; same number rounded to the nearest crore (gold 1,40,987.43 crore); user's call that whole-crore rounding of a figure stated in crore is acceptable for text-only, departing from the numbers rule's 'a rounded value is wrong'
- t078 (graph, hand-check row 21): judge 0.5 -> user 1; same number rounded to the nearest crore (gold 1,40,987.43 crore); user's call that whole-crore rounding of a figure stated in crore is acceptable for text-only, departing from the numbers rule's 'a rounded value is wrong'

## Failure list

Every question a system got less than fully right. Reasons come from the fixed set in the scoring rules.

| id | category | system | route | score | reason | what was wrong |
|---|---|---|---|---|---|---|
| t003 | 1hop | baseline | baseline | 0.00 | retrieval miss (baseline) | no value given (gold 51%) |
| t012 | 1hop | baseline | baseline | 0.67 | retrieval miss (baseline) | extra: Mr. Ashish Goenka: Group Chief Financial Officer of Tata Consumer Products |
| t012 | 1hop | graph | graph | 0.67 | wrong value | extra: Ashish Goenka (current status, appointed on December 18, 2023) |
| t016 | 2hop | baseline | baseline | 0.00 | retrieval miss (baseline) | missing: N Chandrasekaran |
| t018 | 2hop | baseline | baseline | 0.00 | retrieval miss (baseline) | missing: N Chandrasekaran |
| t019 | 2hop | baseline | baseline | 0.00 | retrieval miss (baseline) | missing: Bharat Puri; May 15, 2024 |
| t021 | 2hop | baseline | baseline | 0.50 | partial list | extra: MMJB & Associates LLP; Dr. Asim Kumar Chattopadhyay |
| t023 | 2hop | baseline | baseline | 0.86 | partial list | missing: Tata Motors Limited |
| t027 | 2hop | graph | graph | 0.00 | wrong query (both Thailand subsidiaries are in the graph (97.21%, 55.39%); the query's LIMIT 1 returned one row, so the answer step said the premise of two did not hold) | missing: Tata Technologies (Thailand) Limited; 55.39% |
| t030 | 2hop | baseline | baseline | 0.50 | partial list | missing: Tata Consumer Products Limited + ₹228.62 crore / extra: Tata Consumer Products Limited: the provided report excerpts do not state the exact monetary amount of the dividend paid specifically to Tata Sons Priva... |
| t030 | 2hop | graph | baseline | 0.50 | fell back to the baseline; partial list | missing: Tata Consumer Products Limited + ₹228.62 crore / extra: Tata Consumer Products Limited: the provided report excerpts do not state the exact monetary amount of the dividend paid specifically to Tata Sons Priva... |
| t033 | 2hop | baseline | baseline | 0.67 | partial list | missing: Germany |
| t033 | 2hop | graph | baseline | 0.67 | fell back to the baseline; partial list | missing: Germany |
| t035 | 2hop | baseline | baseline | 0.44 | retrieval miss (baseline) | missing: Corporate Social Responsibility & Sustainability Committee / extra: Audit Committee: Deepak Kapoor (Chairperson); Audit Committee: Ms. Farida Khambata; Audit Committee: Ms. Bharti Gupta Ramola; Audit Committe... |
| t035 | 2hop | graph | baseline | 0.44 | fell back to the baseline; retrieval miss (baseline) | missing: Corporate Social Responsibility & Sustainability Committee / extra: Audit Committee: Deepak Kapoor (Chairperson); Audit Committee: Ms. Farida Khambata; Audit Committee: Ms. Bharti Gupta Ramola; Audit Committe... |
| t036 | 3hop | baseline | baseline | 0.50 | partial list | missing: P B Balaji / extra: Chief Financial Officer for Tata Motors Limited: none |
| t037 | 3hop | baseline | baseline | 0.00 | wrong value | missing: Pradeep Manohar Gaitonde; Maloy Kumar Gupta |
| t037 | 3hop | graph | baseline | 0.00 | fell back to the baseline; wrong value | missing: Pradeep Manohar Gaitonde; Maloy Kumar Gupta |
| t038 | 3hop | baseline | baseline | 0.67 | retrieval miss (baseline) | missing: Tata Consultancy Services Limited |
| t039 | 3hop | baseline | baseline | 0.00 | wrong value | missing: N Chandrasekaran |
| t040 | 3hop | baseline | baseline | 0.67 | retrieval miss (baseline) | missing: Tata Steel Limited + Parvatheesam Kanchinadham; Tata Consumer Products Limited + none |
| t040 | 3hop | graph | graph | 0.86 | partial list | missing: Tata Consumer Products Limited + none |
| t041 | 3hop | baseline | baseline | 0.50 | partial list | missing: Sanjiv V. Pilgaonkar / extra: Tata Consumer Products Limited: The provided excerpts do not contain the name of the audit partner who signed Tata Consumer Products Limited's statutory auditor's report |
| t041 | 3hop | graph | baseline | 0.50 | fell back to the baseline; partial list | missing: Sanjiv V. Pilgaonkar / extra: Tata Consumer Products Limited: The provided excerpts do not contain the name of the audit partner who signed Tata Consumer Products Limited's statutory auditor's report |
| t044 | 3hop | baseline | baseline | 0.25 | retrieval miss (baseline) | missing: Tata Consultancy Services Limited + Parikh & Associates; Tata Motors Limited + Parikh & Associates; Tata Consumer Products Limited + Dr. Asim Kumar Chattopadhyay / extra: Tata Motors Limited: The provided exc... |
| t045 | 3hop | baseline | baseline | 0.00 | wrong value | missing: The Tata Power Company Limited; The Indian Hotels Company Limited; Tata Chemicals Limited |
| t046 | 3hop | baseline | baseline | 0.00 | retrieval miss (baseline) | missing: EdgeVerve Systems Limited + ₹1,089 crore; Infosys BPM Limited + ₹1,887 crore |
| t046 | 3hop | graph | baseline | 0.00 | fell back to the baseline; retrieval miss (baseline) | missing: EdgeVerve Systems Limited + ₹1,089 crore; Infosys BPM Limited + ₹1,887 crore |
| t047 | 3hop | baseline | baseline | 0.00 | retrieval miss (baseline) | missing: N Chandrasekaran |
| t048 | 3hop | baseline | baseline | 0.00 | wrong value | missing: Pradeep Manohar Gaitonde; Amit Somani / extra: Parikh & Associates, Practising Company Secretaries; P. N. Parikh |
| t048 | 3hop | graph | baseline | 0.00 | fell back to the baseline; wrong value | missing: Pradeep Manohar Gaitonde; Amit Somani / extra: Parikh & Associates, Practising Company Secretaries; P. N. Parikh |
| t049 | 3hop | baseline | baseline | 0.00 | retrieval miss (baseline) | missing: Noel Naval Tata |
| t049 | 3hop | graph | baseline | 0.00 | fell back to the baseline; retrieval miss (baseline) | missing: Noel Naval Tata |
| t050 | 3hop | graph | graph | 0.00 | wrong query (the query matched category CONTAINS 'independent', which also matches 'Non-Independent', so it returned N. Chandrasekaran with O P Bhatt and the answer step declined to choose) | missing: O P Bhatt |
| t051 | aggregation | baseline | baseline | 0.40 | partial list | extra: Technopolis Knowledge Park Limited; TCC Construction Private Limited; TCL Employee Welfare Trust; THDC Management Services Limited; TP Luminaire Private Limited; TPL Services Private Limited; TPL-CIL Constructi... |
| t051 | aggregation | graph | baseline | 0.40 | fell back to the baseline; partial list | extra: Technopolis Knowledge Park Limited; TCC Construction Private Limited; TCL Employee Welfare Trust; THDC Management Services Limited; TP Luminaire Private Limited; TPL Services Private Limited; TPL-CIL Constructi... |
| t053 | aggregation | baseline | baseline | 0.00 | wrong value | no value given (gold 3) |
| t053 | aggregation | graph | baseline | 0.00 | fell back to the baseline; wrong value | no value given (gold 3) |
| t054 | aggregation | graph | graph | 0.00 | wrong query (the query did not leave out RelatedPartyGroup nodes, so the aggregate 'Subsidiaries of the Company' (26,298 crore) outranked TCS Netherlands BV (4,009 crore)) | missing: Tata Consultancy Services Netherlands BV / extra: Subsidiaries of the Company: INR 26,298.0 crore |
| t055 | aggregation | baseline | baseline | 0.00 | wrong value | different value given (gold 23) |
| t055 | aggregation | graph | baseline | 0.00 | fell back to the baseline; wrong value | different value given (gold 23) |
| t056 | aggregation | baseline | baseline | 0.73 | retrieval miss (baseline) | missing: O P Bhatt; K V Chowdary / extra: Mr. Om Prakash Bhatt |
| t057 | aggregation | baseline | baseline | 0.37 | retrieval miss (baseline) | missing: Nita Co. Ltd; Fiat India Automobiles Private Ltd / extra: Freight Tiger Commerce Solutions Private Limited (referred to as Freight Commerce Solutions Private Limited in financial transaction tables) (associat... |
| t057 | aggregation | graph | baseline | 0.37 | fell back to the baseline; retrieval miss (baseline) | missing: Nita Co. Ltd; Fiat India Automobiles Private Ltd / extra: Freight Tiger Commerce Solutions Private Limited (referred to as Freight Commerce Solutions Private Limited in financial transaction tables) (associat... |
| t058 | aggregation | baseline | baseline | 0.00 | wrong value | no value given (gold 10) |
| t058 | aggregation | graph | baseline | 0.00 | fell back to the baseline; wrong value | no value given (gold 10) |
| t060 | aggregation | baseline | baseline | 0.86 | retrieval miss (baseline) | missing: 10 |
| t060 | aggregation | graph | graph | 0.13 | partial list | missing: 2 + executive; 3 + non-executive + non-independent; 5 + independent / extra: Koushik Chatterjee: executive director; T. V. Narendran: executive director; Shekhar C. Mande: independent director; V. K. Sharma: ... |
| t061 | aggregation | baseline | baseline | 0.00 | retrieval miss (baseline) | missing: Dr. Shekhar C. Mande + June 1, 2023; O P Bhatt + June 9, 2023; T V Narendran + September 19, 2023 / extra: Mr. O P Bhatt retired from the Board after serving for a decade; Dr. Shekhar Mande joined the Board a... |
| t061 | aggregation | graph | graph | 0.80 | partial list | missing: T V Narendran + September 19, 2023 |
| t063 | aggregation | baseline | baseline | 0.80 | partial list | extra: Mr. N. Chandrasekaran: Retired by rotation and was re-appointed as a Non-Executive (Non-Independent) Director at the 60th Annual General Meeting held on June 6, 2023 |
| t063 | aggregation | graph | graph | 0.67 | partial list | missing: Ajit Krishnakumar + November 1, 2023 |
| t065 | aggregation | baseline | baseline | 0.00 | wrong value | missing: Tata Sons Private Limited + ₹228.62 crore; Tata Investment Corporation Limited + ₹37.41 crore |
| t065 | aggregation | graph | graph | 0.00 | wrong value (the query and rows were right (Tata Sons 228.62 crore, Tata Investment Corporation 37.41 crore, nature 'Dividend Paid'); the answer step misread 'Dividend Paid' as not receiving dividends (no closer reason in the fixed set)) | missing: Tata Sons Private Limited + ₹228.62 crore; Tata Investment Corporation Limited + ₹37.41 crore |
| t067 | aggregation | baseline | baseline | 0.00 | wrong value | different value given (gold 10) |
| t067 | aggregation | graph | baseline | 0.00 | fell back to the baseline; wrong value | different value given (gold 10) |
| t068 | aggregation | baseline | baseline | 0.75 | partial list | missing: Infosys Green Forum; Skava Systems Pvt. Ltd. |
| t068 | aggregation | graph | baseline | 0.75 | fell back to the baseline; partial list | missing: Infosys Green Forum; Skava Systems Pvt. Ltd. |
| t069 | aggregation | baseline | baseline | 0.67 | retrieval miss (baseline) | missing: Infosys BPM Limited |
| t069 | aggregation | graph | baseline | 0.67 | fell back to the baseline; retrieval miss (baseline) | missing: Infosys BPM Limited |
| t081 | text_only | baseline | baseline | 0.00 | wrong value | grade 0: The answer failed to state the correct number of board meetings from the report. |
| t081 | text_only | graph | baseline | 0.00 | fell back to the baseline; wrong value | grade 0: The answer failed to state the correct number of board meetings from the report. |
| t085 | text_only | baseline | baseline | 0.00 | wrong value | grade 0: The answer states an incorrect total CSR spend instead of the gold answer of ₹577 crore. |
| t085 | text_only | graph | baseline | 0.00 | fell back to the baseline; wrong value | grade 0: The answer states an incorrect total CSR spend instead of the gold answer of ₹577 crore. |
| t086 | none_or_unanswerable | graph | clarify | 0.00 | asked for clarification | gave: |
| t089 | none_or_unanswerable | baseline | baseline | 0.00 | invented answer | gave: Tata Steel UK Limited (TSUK); Tata International West Asia DMCC (TIWA); Tata Steel Downstream Products Limited; Tata Motors Limited |
| t089 | none_or_unanswerable | graph | baseline | 0.00 | invented answer | gave: Tata Steel UK Limited (TSUK); Tata International West Asia DMCC (TIWA); Tata Steel Downstream Products Limited; Tata Motors Limited |
| t095 | none_or_unanswerable | graph | graph | 0.00 | invented answer | gave: Neelabja Chakrabarty: Company Secretary of Tata Consumer Products Limited, with a ceased status on February 07, 2024 |

## Answers

### t001 (1hop): Which firm carried out TCS's secretarial audit for FY2024?

- Gold: Parikh & Associates
- graph [graph; score 1.00]: Parikh & Associates carried out Tata Consultancy Services Limited's secretarial audit for FY2024.
  - Cypher: `MATCH p = (c:Company {uid: 'L22210MH1995PLC084781'})-[a:AUDITED_BY {audit_type: 'secretarial'}]->(f:AuditFirm) RETURN f.name, f.firm_registration_no, p LIMIT 100`
  - Items extracted: Parikh & Associates
- baseline [baseline; score 1.00]: Parikh & Associates carried out TCS's secretarial audit for FY2024 [Tata Consultancy Services Limited, pp.68-69].
  - Items extracted: Parikh & Associates

### t002 (1hop): Who is TCS's Company Secretary?

- Gold: Pradeep Manohar Gaitonde
- graph [graph; score 1.00]: TCS's Company Secretary is Pradeep Manohar Gaitonde.
  - Cypher: `MATCH p = (person:Person)-[k:KMP_OF {role: 'Company Secretary'}]->(:Company {uid: 'L22210MH1995PLC084781'}) WHERE k.status = 'current' AND coalesce(k.after_fy_end, false) = false RETURN person.name, k.appointed_on, p LIMIT 100`
  - Items extracted: Pradeep Manohar Gaitonde
- baseline [baseline; score 1.00]: TCS's Company Secretary is Pradeep Manohar Gaitonde [Tata Consultancy Services Limited, p. 5, p. 8].
  - Items extracted: TCS's Company Secretary: Pradeep Manohar Gaitonde

### t003 (1hop): What percentage of C-Edge Technologies Limited does TCS hold?

- Gold: 51%
- graph [graph; score 1.00]: Tata Consultancy Services Limited holds 51.0% of C-Edge Technologies Limited.
  - Cypher: `MATCH p = (c:Company {uid: 'C-000059'})-[s:SUBSIDIARY_OF]->(:Company {uid: 'L22210MH1995PLC084781'}) RETURN c.name, s.stake_pct, p LIMIT 100`
  - Items extracted: C-Edge Technologies Limited: 51.0% held by Tata Consultancy Services Limited
- baseline [baseline; score 0.00]: Based on the provided excerpts, C-Edge Technologies Limited is listed as an unquoted subsidiary with an investment of ₹5 crore as of March 31, 2024, and March 31, 2023 [Tata Consultancy Services Limited, p. 261]. However, the exact percentage of equity held or voting power in C-Edge Technologies Limited is not mentioned in the excerpts.
  - Items extracted: (none)

### t004 (1hop): Who is Tata Motors' Chief Financial Officer?

- Gold: P B Balaji
- graph [graph; score 1.00]: Tata Motors' current Chief Financial Officer is P. B. Balaji.
  - Cypher: `MATCH p = (person:Person)-[k:KMP_OF {role: 'CFO'}]->(:Company {uid: 'L28920MH1945PLC004520'}) WHERE k.status = 'current' AND coalesce(k.after_fy_end, false) = false RETURN person.name, k.status, k.appointed_on, k.ceased_on, p LIMIT 100`
  - Items extracted: Tata Motors' current Chief Financial Officer: P. B. Balaji
- baseline [baseline; score 1.00]: Tata Motors' Group Chief Financial Officer is P B Balaji [Tata Motors Limited, pp. 385–386].
  - Items extracted: Tata Motors' Group Chief Financial Officer: P B Balaji

### t005 (1hop): Which audit firm and which partner signed Tata Motors' standalone auditor's report for FY2024?

- Gold: B S R & Co. LLP; Shiraz Vastani
- graph [baseline; score 1.00]: The standalone auditor's report for Tata Motors Limited for FY2024 was signed by the audit firm **B S R & Co. LLP** (Chartered Accountants) and partner **Shiraz Vastani** [Tata Motors Limited, pp. 385–386].
  - Items extracted: audit firm: B S R & Co. LLP \|\| partner: Shiraz Vastani
- baseline [baseline; score 1.00]: The standalone auditor's report for Tata Motors Limited for FY2024 was signed by the audit firm **B S R & Co. LLP** (Chartered Accountants) and partner **Shiraz Vastani** [Tata Motors Limited, pp. 385–386].
  - Items extracted: audit firm: B S R & Co. LLP \|\| partner: Shiraz Vastani

### t006 (1hop): What is Tata Motors' shareholding in Tata Technologies Limited according to its Form AOC-1?

- Gold: 55.39%
- graph [graph; score 1.00]: Tata Motors' shareholding in Tata Technologies Limited is 55.39%.
  - Cypher: `MATCH p = (s:Company {uid: 'C-000076'})-[rel:SUBSIDIARY_OF]->(c:Company {uid: 'L28920MH1945PLC004520'}) RETURN s.name, rel.stake_pct, p LIMIT 100`
  - Items extracted: Tata Motors' shareholding in Tata Technologies Limited: 55.39%
- baseline [baseline; score 1.00]: According to Form AOC-1, Tata Motors' shareholding in Tata Technologies Ltd is 55.39% [Tata Motors Limited, p. 476].
  - Items extracted: Tata Motors' shareholding in Tata Technologies Ltd: 55.39%

### t007 (1hop): Who is Tata Steel's Company Secretary?

- Gold: Parvatheesam Kanchinadham
- graph [graph; score 1.00]: Tata Steel's Company Secretary is Parvatheesam Kanchinadham.
  - Cypher: `MATCH p = (person:Person)-[k:KMP_OF {role: 'Company Secretary'}]->(:Company {uid: 'L27100MH1907PLC000260'}) WHERE k.status = 'current' AND coalesce(k.after_fy_end, false) = false RETURN person.name, k.appointed_on, p LIMIT 100`
  - Items extracted: Tata Steel's Company Secretary: Parvatheesam Kanchinadham
- baseline [baseline; score 1.00]: Tata Steel's Company Secretary is Parvatheesam Kanchinadham [Tata Steel Limited, pp. 438-439].
  - Items extracted: Tata Steel's Company Secretary: Parvatheesam Kanchinadham

### t008 (1hop): Who is the Vice-Chairman of Tata Steel's board?

- Gold: Noel Naval Tata
- graph [graph; score 1.00]: Noel Naval Tata is the Vice-Chairman of Tata Steel's board.
  - Cypher: `MATCH p = (person:Person)-[d:DIRECTOR_OF]->(c:Company {uid: 'L27100MH1907PLC000260'}) WHERE d.own_report AND d.status = 'current' AND coalesce(d.after_fy_end, false) = false AND toLower(d.title) CONTAINS 'vice-chairman' RETURN person.name, person.din, d.title, d.category, p LIMIT 100`
  - Items extracted: Noel Naval Tata: Vice-Chairman of Tata Steel's board
- baseline [baseline; score 1.00]: The Vice-Chairman of Tata Steel's board is Mr. Noel Naval Tata [Tata Steel Limited, p. 5, 10, 418].
  - Items extracted: Mr. Noel Naval Tata

### t009 (1hop): When did Dr. Shekhar C. Mande join Tata Steel's board?

- Gold: June 1, 2023
- graph [graph; score 1.00]: Dr. Shekhar C. Mande joined Tata Steel's board on June 1, 2023.
  - Cypher: `MATCH p = (person:Person {uid: '10083454'})-[d:DIRECTOR_OF]->(c:Company {uid: 'L27100MH1907PLC000260'}) RETURN person.name, d.appointed_on, d.title, d.category, p LIMIT 100`
  - Items extracted: Dr. Shekhar C. Mande joined Tata Steel's board on June 1, 2023
- baseline [baseline; score 1.00]: Dr. Shekhar C. Mande was appointed as an Additional Director of Tata Steel with effect from June 1, 2023 [Tata Steel Limited, p. 176].
  - Items extracted: Dr. Shekhar C. Mande: appointed as an Additional Director of Tata Steel with effect from June 1, 2023

### t010 (1hop): Which audit firm and which partner signed Tata Consumer Products' statutory auditor's report for FY2024?

- Gold: Deloitte Haskins & Sells LLP; Sanjiv V. Pilgaonkar
- graph [baseline; score 1.00]: The statutory auditor's report for FY2024 was signed by the audit firm **Deloitte Haskins & Sells LLP** and partner **Sanjiv V. Pilgaonkar** [Tata Consumer Products Limited, pp. 374-375].
  - Items extracted: Deloitte Haskins & Sells LLP \|\| Sanjiv V. Pilgaonkar
- baseline [baseline; score 1.00]: The statutory auditor's report for FY2024 was signed by the audit firm **Deloitte Haskins & Sells LLP** and partner **Sanjiv V. Pilgaonkar** [Tata Consumer Products Limited, pp. 374-375].
  - Items extracted: Deloitte Haskins & Sells LLP \|\| Sanjiv V. Pilgaonkar

### t011 (1hop): Who carried out Tata Consumer Products' secretarial audit for FY2024?

- Gold: Dr. Asim Kumar Chattopadhyay
- graph [graph; score 1.00]: Dr. Asim Kumar Chattopadhyay carried out Tata Consumer Products' secretarial audit for FY2024.
  - Cypher: `MATCH p = (c:Company {uid: 'L15491WB1962PLC031425'})-[a:AUDITED_BY {audit_type: 'secretarial'}]->(f:AuditFirm) RETURN f.name, f.firm_registration_no, p LIMIT 100`
  - Items extracted: Dr. Asim Kumar Chattopadhyay: Tata Consumer Products' secretarial audit for FY2024
- baseline [baseline; score 1.00]: Dr. Asim Kumar Chattopadhyay, a Practising Company Secretary, carried out Tata Consumer Products' secretarial audit for FY2024 [Tata Consumer Products Limited, pp. 248-250, 235-236].
  - Items extracted: Dr. Asim Kumar Chattopadhyay, a Practising Company Secretary

### t012 (1hop): Who is Tata Consumer Products' Chief Financial Officer?

- Gold: Sivakumar Sivasankaran
- graph [graph; score 0.67]: Tata Consumer Products' key managerial personnel are Sivakumar Sivasankaran (current status, appointment and cessation dates not provided) and Ashish Goenka (current status, appointed on December 18, 2023).
  - Cypher: `MATCH p = (person:Person)-[k:KMP_OF {role: 'CFO'}]->(:Company {uid: 'L15491WB1962PLC031425'}) WHERE k.status = 'current' AND coalesce(k.after_fy_end, false) = false RETURN person.name, k.status, k.appointed_on, k.ceased_on, p LIMIT 100`
  - Items extracted: Sivakumar Sivasankaran (current status, appointment and cessation dates not provided) \|\| Ashish Goenka (current status, appointed on December 18, 2023)
- baseline [baseline; score 0.67]: Based on the provided report excerpts, Mr. Ashish Goenka serves as the Group Chief Financial Officer of Tata Consumer Products [Tata Consumer Products Limited, p. 29]. Additionally, Sivakumar Sivasankaran is listed as the Chief Financial Officer [Tata Consumer Products Limited, pp. 250, 386]. (Note: Mr. L. Krishnakumar retired from the position of Executive Director & Group CFO effective October 31, 2023) [Tata Consumer Products Limited, p. 250].
  - Items extracted: Mr. Ashish Goenka: Group Chief Financial Officer of Tata Consumer Products \|\| Sivakumar Sivasankaran: Chief Financial Officer

### t013 (1hop): Who carried out Infosys's secretarial audit for fiscal 2024?

- Gold: Makarand M. Joshi & Co.
- graph [graph; score 1.00]: Makarand M. Joshi & Co. carried out Infosys's secretarial audit for fiscal 2024.
  - Cypher: `MATCH p = (c:Company {uid: 'L85110KA1981PLC013115'})-[a:AUDITED_BY {audit_type: 'secretarial'}]->(f:AuditFirm) RETURN f.name, f.firm_registration_no, p LIMIT 100`
  - Items extracted: Makarand M. Joshi & Co.
- baseline [baseline; score 1.00]: Based on the provided excerpts, the secretarial audit for Infosys for fiscal 2024 was conducted by Makarand M. Joshi & Co., Company Secretaries [Infosys Limited, p. 8, 56].
  - Items extracted: Makarand M. Joshi & Co., Company Secretaries

### t014 (1hop): Who is Infosys's Company Secretary?

- Gold: A.G.S. Manikantha
- graph [graph; score 1.00]: Infosys's Company Secretary is A.G.S. Manikantha (also listed as Manikantha A.G.S.), with a current status and no appointment date provided.
  - Cypher: `MATCH p = (person:Person)-[k:KMP_OF {role: 'Company Secretary'}]->(:Company {uid: 'L85110KA1981PLC013115'}) WHERE k.status = 'current' AND coalesce(k.after_fy_end, false) = false RETURN person.name, k.status, k.appointed_on, p LIMIT 100`
  - Items extracted: A.G.S. Manikantha (also listed as Manikantha A.G.S.): Company Secretary
- baseline [baseline; score 1.00]: Infosys's Company Secretary is A.G.S. Manikantha [Infosys Limited, pp. 1, 67, 202, 252, 281, 345].
  - Items extracted: A.G.S. Manikantha

### t015 (1hop): How much dividend income did Infosys receive from EdgeVerve in fiscal 2024?

- Gold: ₹1,089 crore
- graph [baseline; score 1.00]: In fiscal 2024, Infosys received ₹1,089 crore of dividend income from EdgeVerve [Infosys Limited, pp. 256-257].
  - Items extracted: Infosys received ₹1,089 crore of dividend income from EdgeVerve in fiscal 2024
- baseline [baseline; score 1.00]: In fiscal 2024, Infosys received ₹1,089 crore of dividend income from EdgeVerve [Infosys Limited, pp. 256-257].
  - Items extracted: Infosys received ₹1,089 crore of dividend income from EdgeVerve in fiscal 2024

### t016 (2hop): Which directors were on the boards of both TCS and Tata Steel on March 31, 2024?

- Gold: N Chandrasekaran
- graph [graph; score 1.00]: N. Chandrasekaran was on the boards of both TCS and Tata Steel on March 31, 2024.
  - Cypher: `MATCH p1 = (person:Person)-[d1:DIRECTOR_OF]->(:Company {uid: 'L22210MH1995PLC084781'}) MATCH p2 = (person)-[d2:DIRECTOR_OF]->(:Company {uid: 'L27100MH1907PLC000260'}) WHERE d1.own_report AND d1.status = 'current' AND coalesce(d1.after_fy_end, false) = false AND d2.own_report AND d2.status = 'current' AND coalesce(d2.after_fy_end, false) = false RETURN person.name, person.din, p1, p2 LIMIT 100`
  - Items extracted: N. Chandrasekaran
- baseline [baseline; score 0.00]: Based on the provided excerpts, there is no mention of any directors serving on the boards of both Tata Consultancy Services Limited (TCS) and Tata Steel Limited on March 31, 2024. Therefore, the excerpts do not contain the answer.
  - Items extracted: (none)

### t017 (2hop): Tata Consumer Products lists TCS among its related parties. Who is TCS's Chief Financial Officer?

- Gold: Samir Seksaria
- graph [graph; score 1.00]: Samir Seksaria is the Chief Financial Officer (current status).
  - Cypher: `MATCH p = (person:Person)-[k:KMP_OF {role: 'CFO'}]->(:Company {uid: 'L22210MH1995PLC084781'}) WHERE k.status = 'current' AND coalesce(k.after_fy_end, false) = false RETURN person.name, person.din, k.status, p LIMIT 100`
  - Items extracted: Samir Seksaria: Chief Financial Officer (current status)
- baseline [baseline; score 1.00]: The provided excerpts do not state that Tata Consumer Products lists TCS among its related parties. However, the excerpts state that the Chief Financial Officer (CFO) of Tata Consultancy Services Limited (TCS) is Samir Seksaria [Tata Consultancy Services Limited, p. 105].
  - Items extracted: Samir Seksaria (Chief Financial Officer)

### t018 (2hop): Which directors were on the boards of both Tata Consumer Products and TCS on March 31, 2024?

- Gold: N Chandrasekaran
- graph [graph; score 1.00]: N. Chandrasekaran was on the boards of both Tata Consumer Products and TCS on March 31, 2024.
  - Cypher: `MATCH p1 = (person:Person)-[d1:DIRECTOR_OF]->(c1:Company {uid: 'L15491WB1962PLC031425'}) MATCH p2 = (person)-[d2:DIRECTOR_OF]->(c2:Company {uid: 'L22210MH1995PLC084781'}) WHERE d1.own_report AND d1.status = 'current' AND coalesce(d1.after_fy_end, false) = false AND d2.own_report AND d2.status = 'current' AND coalesce(d2.after_fy_end, false) = false RETURN person.name, person.din, collect(p1) AS paths1, collect(p2) AS paths2 LIMIT 100`
  - Items extracted: N. Chandrasekaran was on the boards of both Tata Consumer Products and TCS on March 31, 2024
- baseline [baseline; score 0.00]: The provided excerpts do not contain information regarding directors serving on the boards of both Tata Consumer Products and TCS.
  - Items extracted: (none)

### t019 (2hop): Which Tata Consumer Products director joined Tata Motors' board after the financial year ended, and on what date?

- Gold: Bharat Puri; May 15, 2024
- graph [graph; score 1.00]: Bharat Puri joined Tata Motors' board on May 15, 2024.
  - Cypher: `MATCH p1 = (person:Person)-[d1:DIRECTOR_OF]->(:Company {uid: 'L15491WB1962PLC031425'}) WHERE d1.own_report AND d1.status = 'current' AND coalesce(d1.after_fy_end, false) = false MATCH p2 = (person)-[d2:DIRECTOR_OF]->(:Company {uid: 'L28920MH1945PLC004520'}) WHERE d2.after_fy_end = true RETURN person.name, d2.appointed_on, d2.reported_by, p1, p2 LIMIT 100`
  - Items extracted: Bharat Puri joined Tata Motors' board on May 15, 2024
- baseline [baseline; score 0.00]: Based on the provided excerpts, the excerpts do not mention any Tata Consumer Products director joining Tata Motors' board after the financial year ended. However, P.B. Balaji serves as the Group CFO of Tata Motors Limited and is on the board of Tata Consumer Products Ltd. [Tata Consumer Products Limited, p. 538].
  - Items extracted: (none)

### t020 (2hop): Which audit partner signed the statutory auditor's reports of both Tata Consumer Products and Infosys?

- Gold: Sanjiv V. Pilgaonkar
- graph [baseline; score 1.00]: Sanjiv V. Pilgaonkar signed the statutory auditor's reports for both Tata Consumer Products Limited and Infosys Limited [Tata Consumer Products Limited, pp. 374-375; Infosys Limited, pp. 268-269].
  - Items extracted: Tata Consumer Products Limited: Sanjiv V. Pilgaonkar \|\| Infosys Limited: Sanjiv V. Pilgaonkar
- baseline [baseline; score 1.00]: Sanjiv V. Pilgaonkar signed the statutory auditor's reports for both Tata Consumer Products Limited and Infosys Limited [Tata Consumer Products Limited, pp. 374-375; Infosys Limited, pp. 268-269].
  - Items extracted: Tata Consumer Products Limited: Sanjiv V. Pilgaonkar \|\| Infosys Limited: Sanjiv V. Pilgaonkar

### t021 (2hop): Who is the secretarial auditor of the company whose Vice-Chairman is Noel Naval Tata?

- Gold: Parikh & Associates
- graph [graph; score 1.00]: The secretarial auditor of the company whose Vice-Chairman is Noel Naval Tata (Tata Steel Limited) is Parikh & Associates.
  - Cypher: `MATCH p1 = (person:Person {uid: '00024713'})-[d:DIRECTOR_OF]->(c:Company) WHERE d.title CONTAINS 'Vice-Chairman' AND d.own_report AND d.status = 'current' AND coalesce(d.after_fy_end, false) = false MATCH p2 = (c)-[a:AUDITED_BY {audit_type: 'secretarial'}]->(f:AuditFirm) RETURN c.name, f.name, f.firm_registration_no, p1, p2 LIMIT 100`
  - Items extracted: Parikh & Associates
- baseline [baseline; score 0.50]: Based on the provided excerpts, Noel Naval Tata is the Vice-Chairman of Tata Steel Limited [Tata Steel Limited, pp. 418-419, 316-317]. The secretarial audit for Tata Steel Limited's subsidiary/related filings (such as for Tata Passenger Electric Mobility Limited / Tata Motors Limited or Tata Consumer Products Limited in the excerpts) is conducted by firms like MMJB & Associates LLP [Tata Motors Limited, pp. 166-168] and Parikh & Associates [Tata Motors Limited, pp. 161-162], and Parikh & Associates also certified the director disqualification status for Tata Steel Limited [Tata Steel Limited, p. 260]. However, the provided excerpts do not explicitly name the primary secretarial auditor of Tata Steel Limited itself. *(Note: Dr. Asim Kumar Chattopadhyay is listed as the Practising Company Secretary for Tata Consumer Products Limited [Tata Consumer Products Limited, pp. 248-250].)*
  - Items extracted: MMJB & Associates LLP \|\| Parikh & Associates \|\| Dr. Asim Kumar Chattopadhyay

### t022 (2hop): Saurabh Agrawal, a Tata Steel director, chairs Tata AIG General Insurance Company. How much did Tata Consumer Products pay Tata AIG under 'Other Expenses (Net)' in FY2024?

- Gold: ₹41.74 crore
- graph [graph; score 1.00]: Tata Consumer Products paid 41.74 crore INR to Tata AIG General Insurance Company under 'Other Expenses (Net)' in FY2024.
  - Cypher: `MATCH p = (:Company {uid: 'L15491WB1962PLC031425'})-[t:RELATED_PARTY_TXN]->(:Company {uid: 'C-000180'}) WHERE toLower(t.nature) CONTAINS 'other expenses' RETURN t.nature, t.amount_inr_crore, t.amount_as_printed, p LIMIT 100`
  - Items extracted: Tata Consumer Products: 41.74 crore INR
- baseline [baseline; score 1.00]: In FY2024, Tata Consumer Products paid Rs. 41.74 crores to Tata AIG General Insurance Limited under 'Other Expenses (Net)' [Tata Consumer Products Limited, pp. 424-425].
  - Items extracted: Tata Consumer Products paid Rs. 41.74 crores to Tata AIG General Insurance Limited under 'Other Expenses (Net)' in FY2024

### t023 (2hop): Which of the five pilot companies name N Chandrasekaran as their Chairman in their own reports?

- Gold: Tata Consultancy Services; Tata Motors; Tata Steel; Tata Consumer Products
- graph [graph; score 1.00]: Tata Motors Limited, Tata Consumer Products Limited, Tata Steel Limited, and Tata Consultancy Services Limited.
  - Cypher: `MATCH p = (person:Person {uid: '00121863'})-[d:DIRECTOR_OF]->(c:Company) WHERE d.own_report AND d.status = 'current' AND coalesce(d.after_fy_end, false) = false AND toLower(d.title) CONTAINS 'chair' RETURN c.name, d.title, d.category, p LIMIT 100`
  - Items extracted: Tata Motors Limited \|\| Tata Consumer Products Limited \|\| Tata Steel Limited \|\| Tata Consultancy Services Limited
- baseline [baseline; score 0.86]: Based on the provided report excerpts, the following companies name N Chandrasekaran as their Chairman in their reports: * **Tata Consultancy Services Limited** [Tata Consultancy Services Limited, pp. 5-7, 51-52] * **Tata Consumer Products Limited** [Tata Consumer Products Limited, pp. 23-24] * **Tata Steel Limited** [Tata Steel Limited, p. 230, 268-270] *(Note: The provided excerpts do not contain reports from the other pilot companies to verify their chairperson status.)*
  - Items extracted: Tata Consultancy Services Limited \|\| Tata Consumer Products Limited \|\| Tata Steel Limited

### t024 (2hop): Who is the Chief Financial Officer of the company where Hanne Sorensen and Keki Mistry are both independent directors?

- Gold: Samir Seksaria
- graph [graph; score 1.00]: The Chief Financial Officer of Tata Consultancy Services Limited is Samir Seksaria.
  - Cypher: `MATCH p1 = (h:Person {uid: '08035439'})-[d1:DIRECTOR_OF]->(c:Company) WHERE d1.own_report AND d1.status = 'current' AND coalesce(d1.after_fy_end, false) = false MATCH p2 = (k:Person {uid: '00008886'})-[d2:DIRECTOR_OF]->(c) WHERE d2.own_report AND d2.status = 'current' AND coalesce(d2.after_fy_end, false) = false MATCH p3 = (cfo:Person)-[kmp:KMP_OF {role: 'CFO'}]->(c) WHERE kmp.status = 'current' AND coalesce(kmp.after_fy_end, false) = false RETURN c.name, cfo.name, p1, p2, p3 LIMIT 100`
  - Items extracted: Samir Seksaria, Chief Financial Officer of Tata Consultancy Services Limited
- baseline [baseline; score 1.00]: Based on the provided reports, Hanne Sorensen and Keki Mistry are independent directors at Tata Consultancy Services Limited [Tata Consultancy Services Limited, p. 58, 98]. The Chief Financial Officer of Tata Consultancy Services Limited is Samir Seksaria [Tata Consultancy Services Limited, p. 5, 60].
  - Items extracted: Samir Seksaria: Chief Financial Officer of Tata Consultancy Services Limited

### t025 (2hop): Who is the Company Secretary of the company whose standalone auditor's report was signed by Shiraz Vastani?

- Gold: Maloy Kumar Gupta
- graph [baseline; score 1.00]: The Company Secretary of Tata Motors Limited (whose standalone auditor's report was signed by Shiraz Vastani) is Maloy Kumar Gupta [Tata Motors Limited, pp. 385–386].
  - Items extracted: Maloy Kumar Gupta
- baseline [baseline; score 1.00]: The Company Secretary of Tata Motors Limited (whose standalone auditor's report was signed by Shiraz Vastani) is Maloy Kumar Gupta [Tata Motors Limited, pp. 385–386].
  - Items extracted: Maloy Kumar Gupta

### t026 (2hop): In which country is the TCS subsidiary that TCS holds 66% of incorporated?

- Gold: Japan
- graph [baseline; score 1.00]: The TCS subsidiary in which TCS holds a 66% share is incorporated in Japan [Tata Consultancy Services Limited, pp. 306-307].
  - Items extracted: Japan
- baseline [baseline; score 1.00]: The TCS subsidiary in which TCS holds a 66% share is incorporated in Japan [Tata Consultancy Services Limited, pp. 306-307].
  - Items extracted: Japan

### t027 (2hop): According to its Form AOC-1, Tata Motors has two subsidiaries in Thailand. Which one does it hold the smaller stake in, and what is that stake?

- Gold: Tata Technologies (Thailand) Limited; 55.39%
- graph [graph; score 0.00]: Based on the query results, Tata Motors has only one subsidiary listed in Thailand (Tata Technologies (Thailand) Limited with a 55.39% stake), so the rows do not contain information to answer which of two subsidiaries it holds the smaller stake in.
  - Cypher: `MATCH p = (s:Company)-[rel:SUBSIDIARY_OF]->(:Company {uid: 'L28920MH1945PLC004520'}) WHERE 'Thailand' IN s.countries RETURN s.name, rel.stake_pct, p ORDER BY rel.stake_pct ASC LIMIT 1`
  - Items extracted: (none)
- baseline [baseline; score 1.00]: According to Form AOC-1, Tata Motors holds the smaller stake in **Tata Technologies (Thailand) Limited**, where its shareholding is **55.39%** (compared to 97.21% in Tata Motors (Thailand) Limited) [Tata Motors Limited, pp. 477, 479, 491].
  - Items extracted: Tata Technologies (Thailand) Limited: 55.39%

### t028 (2hop): Which company has both Noel Naval Tata and Saurabh Agrawal as directors, according to Tata Steel's board table (other than Tata Steel)?

- Gold: Voltas Limited
- graph [baseline; score 1.00]: Based on the provided excerpts, Voltas Limited has both Noel Naval Tata (as Non-Executive, Non-Independent Chairman) and Saurabh Agrawal (as a Non-Executive, Non-Independent Director) on its board [Tata Steel Limited, pp. 230-231].
  - Cypher: `MATCH p1 = (:Person {uid: '00024713'})-[d1:DIRECTOR_OF]->(c:Company), p2 = (:Person {uid: '02144558'})-[d2:DIRECTOR_OF]->(c) WHERE c.uid <> 'L27100MH1907PLC000260' AND d1.reported_by = 'L27100MH1907PLC000260' AND d2.reported_by = 'L27100MH1907PLC000260' RETURN c.name, c.nse_symbol, collect(p1)[0] AS p1, collect(p2)[0] AS p2 LIMIT 100`
  - Items extracted: Voltas Limited
- baseline [baseline; score 1.00]: Based on the provided excerpts, Voltas Limited has both Noel Naval Tata (as Non-Executive, Non-Independent Chairman) and Saurabh Agrawal (as a Non-Executive, Non-Independent Director) on its board [Tata Steel Limited, pp. 230-231].
  - Items extracted: Voltas Limited

### t029 (2hop): According to Tata Consumer Products' report, in which other listed company is its director P. B. Balaji a director?

- Gold: Tata Technologies Limited
- graph [graph; score 1.00]: P. B. Balaji is a director in Tata Technologies Limited.
  - Cypher: `MATCH p = (:Person {uid: '02762983'})-[d:DIRECTOR_OF]->(c:Company) WHERE c.uid <> 'L15491WB1962PLC031425' RETURN c.name, c.nse_symbol, d.own_report, p LIMIT 100`
  - Items extracted: Tata Technologies Limited
- baseline [baseline; score 1.00]: According to Tata Consumer Products' report, P. B. Balaji is a director in Tata Technologies Limited [Tata Consumer Products Limited, p. 538].
  - Items extracted: Tata Technologies Limited

### t030 (2hop): Both Tata Motors and Tata Consumer Products report paying a dividend to Tata Sons Private Limited in FY2024. How much did each pay?

- Gold: Tata Motors: ₹298.51 crore; Tata Consumer Products: ₹228.62 crore
- graph [baseline; score 0.50]: Based on the provided excerpts: * **Tata Motors Limited** paid a dividend of ₹298.51 crores to Tata Sons Private Limited (Promoter Company) in FY2024 [Tata Motors Limited, pp. 464–465]. * **Tata Consumer Products Limited** had 270,557,128 shares held by Tata Sons Private Limited representing a 28.39% holding [Tata Consumer Products Limited, pp. 410–411, 482–483], but the provided report excerpts do not state the exact monetary amount of the dividend paid specifically to Tata Sons Private Limited.
  - Items extracted: Tata Motors Limited paid a dividend of ₹298.51 crores to Tata Sons Private Limited (Promoter Company) in FY2024 \|\| Tata Consumer Products Limited: the provided report excerpts do not state the exact monetary amount of the dividend paid specifically to Tata Sons Private Limited
- baseline [baseline; score 0.50]: Based on the provided excerpts: * **Tata Motors Limited** paid a dividend of ₹298.51 crores to Tata Sons Private Limited (Promoter Company) in FY2024 [Tata Motors Limited, pp. 464–465]. * **Tata Consumer Products Limited** had 270,557,128 shares held by Tata Sons Private Limited representing a 28.39% holding [Tata Consumer Products Limited, pp. 410–411, 482–483], but the provided report excerpts do not state the exact monetary amount of the dividend paid specifically to Tata Sons Private Limited.
  - Items extracted: Tata Motors Limited paid a dividend of ₹298.51 crores to Tata Sons Private Limited (Promoter Company) in FY2024 \|\| Tata Consumer Products Limited: the provided report excerpts do not state the exact monetary amount of the dividend paid specifically to Tata Sons Private Limited

### t031 (2hop): To which subsidiary had Tata Consumer Products given a guarantee still outstanding at March 31, 2024, and how much equity did it invest in that subsidiary during FY2024?

- Gold: Tata Coffee Vietnam Company Limited; ₹196.34 crore guarantee; ₹25.45 crore equity
- graph [baseline; score 1.00]: Based on the provided report excerpts, Tata Consumer Products gave a corporate guarantee to lending banks that was outstanding at March 31, 2024, on behalf of its overseas wholly owned subsidiary, **Tata Coffee Vietnam Company Limited** (amounting to Rs. 196.34 Crores) [Tata Consumer Products Limited, pp. 420-421, 425-426]. During FY2024, the amount of investment made by the company in **Tata Coffee Vietnam Company Limited** was **Rs. 25.45 Crores** [Tata Consumer Products Limited, pp. 425-426].
  - Items extracted: Tata Coffee Vietnam Company Limited: corporate guarantee to lending banks outstanding at March 31, 2024 amounting to Rs. 196.34 Crores \|\| Tata Coffee Vietnam Company Limited: amount of investment made by the company during FY2024 was Rs. 25.45 Crores
- baseline [baseline; score 1.00]: Based on the provided report excerpts, Tata Consumer Products gave a corporate guarantee to lending banks that was outstanding at March 31, 2024, on behalf of its overseas wholly owned subsidiary, **Tata Coffee Vietnam Company Limited** (amounting to Rs. 196.34 Crores) [Tata Consumer Products Limited, pp. 420-421, 425-426]. During FY2024, the amount of investment made by the company in **Tata Coffee Vietnam Company Limited** was **Rs. 25.45 Crores** [Tata Consumer Products Limited, pp. 425-426].
  - Items extracted: Tata Coffee Vietnam Company Limited: corporate guarantee to lending banks outstanding at March 31, 2024 amounting to Rs. 196.34 Crores \|\| Tata Coffee Vietnam Company Limited: amount of investment made by the company during FY2024 was Rs. 25.45 Crores

### t032 (2hop): Which TCS subsidiary merged into another TCS subsidiary during FY2024, into which one, and when?

- Gold: Saudi Desert Rose Holding B.V.; Tata Consultancy Services Netherlands BV; August 29, 2023
- graph [graph; score 1.00]: Saudi Desert Rose Holding B.V. merged into Tata Consultancy Services Netherlands BV with effect from August 29, 2023.
  - Cypher: `MATCH p1 = (s1:Company)-[:SUBSIDIARY_OF]->(:Company {uid: 'L22210MH1995PLC084781'}) MATCH p2 = (s1)-[m:MERGED_INTO]->(s2:Company) RETURN s1.name AS merged_company, s2.name AS surviving_company, m.note AS merger_note, [p1, p2] AS paths LIMIT 100`
  - Items extracted: Saudi Desert Rose Holding B.V. merged into Tata Consultancy Services Netherlands BV with effect from August 29, 2023
- baseline [baseline; score 1.00]: During FY2024, Saudi Desert Rose Holding B.V. merged into Tata Consultancy Services Netherlands BV with effect from August 29, 2023 [Tata Consultancy Services Limited, pp. 57-58, 240].
  - Items extracted: Saudi Desert Rose Holding B.V. merged into Tata Consultancy Services Netherlands BV \|\| effective date: August 29, 2023

### t033 (2hop): TCS Technology Solutions AG was renamed during the year. What is its new name, and in which country is it incorporated?

- Gold: TCS Technology Solution GmbH; Germany
- graph [baseline; score 0.67]: Based on the provided reports, TCS Technology Solutions AG was renamed to TCS Technology Solutions GmbH [Tata Consultancy Services Limited, pp. 57-58, 235-237]. However, the provided excerpts do not mention the country in which it is incorporated.
  - Items extracted: TCS Technology Solutions AG new name: TCS Technology Solutions GmbH
- baseline [baseline; score 0.67]: Based on the provided reports, TCS Technology Solutions AG was renamed to TCS Technology Solutions GmbH [Tata Consultancy Services Limited, pp. 57-58, 235-237]. However, the provided excerpts do not mention the country in which it is incorporated.
  - Items extracted: TCS Technology Solutions AG new name: TCS Technology Solutions GmbH

### t034 (2hop): According to Tata Motors' Form AOC-1, what was Jaguar Land Rover Limited previously called, and what is Tata Motors' shareholding in it?

- Gold: Jaguar Cars Limited; 100%
- graph [graph; score 1.00]: Jaguar Land Rover Limited was previously called Jaguar Cars Limited, and Tata Motors' shareholding in it is 100.0%.
  - Cypher: `MATCH p1 = (s:Company {uid: 'C-000068'})-[sub:SUBSIDIARY_OF]->(tm:Company {uid: 'L28920MH1945PLC004520'}) MATCH p2 = (s)-[f:FORMERLY_NAMED]->(fn:Company) RETURN s.name, f.former_name, f.note, sub.stake_pct, p1, p2 LIMIT 100`
  - Items extracted: Jaguar Land Rover Limited was previously called Jaguar Cars Limited \|\| Tata Motors' shareholding in Jaguar Land Rover Limited is 100.0%
- baseline [baseline; score 1.00]: According to Tata Motors' report excerpts, Jaguar Land Rover Limited was previously called Jaguar Cars Limited [Tata Motors Limited, p. 477]. Tata Motors' effective holding/shareholding in it is 100.00% [Tata Motors Limited, pp. 292, 477].
  - Items extracted: Jaguar Land Rover Limited was previously called Jaguar Cars Limited \|\| Tata Motors' effective holding/shareholding in Jaguar Land Rover Limited is 100.00%

### t035 (2hop): Which Tata Steel committee does Deepak Kapoor chair, and which executive directors sit on it?

- Gold: Corporate Social Responsibility & Sustainability Committee; T V Narendran; Koushik Chatterjee
- graph [baseline; score 0.44]: Based on the provided excerpts, Deepak Kapoor chairs the Audit Committee of Tata Steel Limited [Tata Steel Limited, pp. 234-235]. The executive directors who sit on this committee as invitees are Mr. T. V. Narendran and Mr. Koushik Chatterjee [Tata Steel Limited, pp. 234-235, 237 (implicitly noted through executive attendees/members context - wait, let me check exact wording)]. Actually, the members of the Audit Committee are Mr. Deepak Kapoor (Chairperson), Ms. Farida Khambata, Ms. Bharti Gupta Ramola, and Mr. Saurabh Agrawal [Tata Steel Limited, p. 177]. The executive directors (Mr. T.V. Narendran and Mr. Koushik Chatterjee) attend the Audit Committee meetings as **invitees** rather than members [Tata Steel Limited, p. 234].
  - Items extracted: Audit Committee: Deepak Kapoor (Chairperson) \|\| Audit Committee: Ms. Farida Khambata \|\| Audit Committee: Ms. Bharti Gupta Ramola \|\| Audit Committee: Mr. Saurabh Agrawal \|\| Audit Committee invitees: Mr. T. V. Narendran \|\| Audit Committee invitees: Mr. Koushik Chatterjee
- baseline [baseline; score 0.44]: Based on the provided excerpts, Deepak Kapoor chairs the Audit Committee of Tata Steel Limited [Tata Steel Limited, pp. 234-235]. The executive directors who sit on this committee as invitees are Mr. T. V. Narendran and Mr. Koushik Chatterjee [Tata Steel Limited, pp. 234-235, 237 (implicitly noted through executive attendees/members context - wait, let me check exact wording)]. Actually, the members of the Audit Committee are Mr. Deepak Kapoor (Chairperson), Ms. Farida Khambata, Ms. Bharti Gupta Ramola, and Mr. Saurabh Agrawal [Tata Steel Limited, p. 177]. The executive directors (Mr. T.V. Narendran and Mr. Koushik Chatterjee) attend the Audit Committee meetings as **invitees** rather than members [Tata Steel Limited, p. 234].
  - Items extracted: Audit Committee: Deepak Kapoor (Chairperson) \|\| Audit Committee: Ms. Farida Khambata \|\| Audit Committee: Ms. Bharti Gupta Ramola \|\| Audit Committee: Mr. Saurabh Agrawal \|\| Audit Committee invitees: Mr. T. V. Narendran \|\| Audit Committee invitees: Mr. Koushik Chatterjee

### t036 (3hop): Hanne Sorensen sits on the boards of two pilot companies. Who are the Chief Financial Officers of those companies?

- Gold: Samir Seksaria (TCS); P B Balaji (Tata Motors)
- graph [graph; score 1.00]: The Chief Financial Officers are Samir Seksaria (for Tata Consultancy Services Limited) and P. B. Balaji (for Tata Motors Limited).
  - Cypher: `MATCH (person:Person {uid: '08035439'})-[d:DIRECTOR_OF]->(c:Company) WHERE d.own_report AND d.status = 'current' AND coalesce(d.after_fy_end, false) = false MATCH p = (k:Person)-[kmp:KMP_OF {role: 'CFO'}]->(c) WHERE kmp.status = 'current' AND coalesce(kmp.after_fy_end, false) = false RETURN c.name, k.name, kmp.role, p LIMIT 100`
  - Items extracted: Samir Seksaria (for Tata Consultancy Services Limited) \|\| P. B. Balaji (for Tata Motors Limited)
- baseline [baseline; score 0.50]: Based on the provided excerpts, Hanne Sorensen sits on the boards of Tata Consultancy Services Limited and Tata Motors Limited [Tata Consultancy Services Limited, pp. 5, 58, 98-99; Tata Motors Limited, pp. 257-258, 263-264]. The Chief Financial Officer of Tata Consultancy Services Limited is Samir Seksaria [Tata Consultancy Services Limited, pp. 5]. The excerpts do not contain the name of the Chief Financial Officer for Tata Motors Limited.
  - Items extracted: Chief Financial Officer of Tata Consultancy Services Limited: Samir Seksaria \|\| Chief Financial Officer for Tata Motors Limited: none

### t037 (3hop): Who are the Company Secretaries of the pilot companies on whose boards Al-Noor Ramji sits?

- Gold: Pradeep Manohar Gaitonde (TCS); Maloy Kumar Gupta (Tata Motors)
- graph [baseline; score 0.00]: Based on the provided excerpts, the excerpts do not contain the names of the Company Secretaries for the companies on whose boards Al-Noor Ramji sits.
  - Items extracted: (none)
- baseline [baseline; score 0.00]: Based on the provided excerpts, the excerpts do not contain the names of the Company Secretaries for the companies on whose boards Al-Noor Ramji sits.
  - Items extracted: (none)

### t038 (3hop): Which other pilot companies use the same secretarial auditor as the company whose CEO & MD is T V Narendran?

- Gold: Tata Consultancy Services; Tata Motors
- graph [graph; score 1.00]: Tata Consultancy Services Limited and Tata Motors Limited.
  - Cypher: `MATCH p1 = (:Person {uid: '03083605'})-[k:KMP_OF]->(c1:Company) WHERE k.role = 'CEO & MD' OR k.role = 'CEO' MATCH p2 = (c1)-[a1:AUDITED_BY {audit_type: 'secretarial'}]->(f:AuditFirm)<-[a2:AUDITED_BY {audit_type: 'secretarial'}]-(c2:Company) WHERE c1 <> c2 AND c2.nse_symbol IS NOT NULL RETURN c2.name, f.name, [p1, p2] AS paths LIMIT 100`
  - Items extracted: Tata Consultancy Services Limited \|\| Tata Motors Limited
- baseline [baseline; score 0.67]: Based on the provided excerpts, the company whose CEO & MD is T.V. Narendran is Tata Steel Limited [Tata Steel Limited, p. 170, 418]. Tata Steel Limited appointed **Parikh & Associates** as its Secretarial Auditor for FY2023-24 [Tata Steel Limited, p. 181]. According to the report excerpts, **Parikh & Associates** also conducted the Secretarial Audit for **Tata Motors Passenger Vehicles Limited** (formerly TML Business Analytics Services Limited) [Tata Motors Limited, pp. 161–162].
  - Items extracted: Tata Motors Passenger Vehicles Limited

### t039 (3hop): Which directors of Tata Steel also sit on the board of a pilot company whose statutory auditor is Deloitte Haskins & Sells LLP?

- Gold: N Chandrasekaran (via Tata Consumer Products)
- graph [graph; score 1.00]: N. Chandrasekaran
  - Cypher: `MATCH p1 = (person:Person)-[d1:DIRECTOR_OF]->(ts:Company {uid: 'L27100MH1907PLC000260'}) WHERE d1.own_report AND d1.status = 'current' AND coalesce(d1.after_fy_end, false) = false MATCH p2 = (person)-[d2:DIRECTOR_OF]->(c:Company) WHERE c.uid <> ts.uid AND c.nse_symbol IS NOT NULL AND coalesce(d2.status, 'current') = 'current' MATCH p3 = (c)-[:AUDITED_BY {audit_type: 'statutory'}]->(f:AuditFirm {uid: 'F-000004'}) RETURN person.name, person.din, c.name AS company, collect(p1)[0] AS p1, collect(p2)[0] AS p2, collect(p3)[0] AS p3 LIMIT 100`
  - Items extracted: N. Chandrasekaran
- baseline [baseline; score 0.00]: The provided excerpts do not contain information about a pilot company whose statutory auditor is Deloitte Haskins & Sells LLP or which directors sit on such a board.
  - Items extracted: (none)

### t040 (3hop): For each pilot company that N Chandrasekaran chairs, who was its Company Secretary at March 31, 2024?

- Gold: TCS: Pradeep Manohar Gaitonde; Tata Motors: Maloy Kumar Gupta; Tata Steel: Parvatheesam Kanchinadham; Tata Consumer Products: none named (Neelabja Chakrabarty resigned February 7, 2024)
- graph [graph; score 0.86]: For the companies where N. Chandrasekaran is a director, the Company Secretaries at March 31, 2024, were: * Tata Motors Limited: Maloy Kumar Gupta * Tata Steel Limited: Parvatheesam Kanchinadham * Tata Consultancy Services Limited: Pradeep Manohar Gaitonde
  - Cypher: `MATCH p1 = (person:Person {uid: '00121863'})-[d:DIRECTOR_OF]->(c:Company) WHERE d.own_report AND d.status = 'current' AND coalesce(d.after_fy_end, false) = false AND toLower(coalesce(d.title, '')) CONTAINS 'chair' MATCH p2 = (kmp:Person)-[k:KMP_OF {role: 'Company Secretary'}]->(c) WHERE k.status = 'current' AND coalesce(k.after_fy_end, false) = false RETURN c.name, kmp.name, p1, p2 LIMIT 100`
  - Items extracted: Tata Motors Limited: Maloy Kumar Gupta \|\| Tata Steel Limited: Parvatheesam Kanchinadham \|\| Tata Consultancy Services Limited: Pradeep Manohar Gaitonde
- baseline [baseline; score 0.67]: Based on the provided excerpts, N Chandrasekaran serves as Chairman of the board of Tata Sons (the holding company/promoter) [Tata Consumer Products Limited, p. 23; Tata Consultancy Services Limited, p. 51] and is also identified as Chairman of Tata Consultancy Services Limited [Tata Consultancy Services Limited, p. 51], Tata Consumer Products Limited [Tata Consumer Products Limited, p. 526], and Tata Motors Limited [Tata Motors Limited, p. 402]. The Company Secretaries for these operating companies as of March 31, 2024, are: * **Tata Consultancy Services Limited:** Pradeep Manohar Gaitonde [Tata Consultancy Services Limited, p. 58] * **Tata Motors Limited:** Maloy Kumar Gupta [Tata Motors Limited, p. 402] * **Tata Consumer Products Limited:** The provided excerpts do not name the Company Secretary as of March 31, 2024 (Neelabja Chakrabarty is mentioned in relation to percentage increases in remuneration [Tata Consumer Products Limited, p. 250], but the excerpts do not state if she held the position of Company Secretary as of March 31, 2024). * **Tata Sons Private Limited:** The provided excerpts do not contain this information.
  - Items extracted: Tata Consultancy Services Limited: Pradeep Manohar Gaitonde \|\| Tata Motors Limited: Maloy Kumar Gupta

### t041 (3hop): P B Balaji is a director of one pilot company and KMP of another. Which audit partners signed those two companies' statutory auditor's reports?

- Gold: Sanjiv V. Pilgaonkar (Tata Consumer Products, Deloitte); Shiraz Vastani (Tata Motors, B S R & Co. LLP)
- graph [baseline; score 0.50]: Based on the provided excerpts, P B Balaji is Group Chief Financial Officer and KMP of Tata Motors Limited [Tata Motors Limited, p. 516] and a director of Tata Consumer Products Limited [Tata Consumer Products Limited, p. 538-539]. The statutory auditor's reports for these companies were signed by the following partners: - **Tata Motors Limited**: Shiraz Vastani, Partner (representing B S R & Co. LLP) [Tata Motors Limited, p. 280, 384]. - **Tata Consumer Products Limited**: The provided excerpts do not contain the name of the audit partner who signed Tata Consumer Products Limited's statutory auditor's report.
  - Items extracted: Tata Motors Limited: Shiraz Vastani, Partner (representing B S R & Co. LLP) \|\| Tata Consumer Products Limited: The provided excerpts do not contain the name of the audit partner who signed Tata Consumer Products Limited's statutory auditor's report
- baseline [baseline; score 0.50]: Based on the provided excerpts, P B Balaji is Group Chief Financial Officer and KMP of Tata Motors Limited [Tata Motors Limited, p. 516] and a director of Tata Consumer Products Limited [Tata Consumer Products Limited, p. 538-539]. The statutory auditor's reports for these companies were signed by the following partners: - **Tata Motors Limited**: Shiraz Vastani, Partner (representing B S R & Co. LLP) [Tata Motors Limited, p. 280, 384]. - **Tata Consumer Products Limited**: The provided excerpts do not contain the name of the audit partner who signed Tata Consumer Products Limited's statutory auditor's report.
  - Items extracted: Tata Motors Limited: Shiraz Vastani, Partner (representing B S R & Co. LLP) \|\| Tata Consumer Products Limited: The provided excerpts do not contain the name of the audit partner who signed Tata Consumer Products Limited's statutory auditor's report

### t042 (3hop): Which of TCS's German subsidiaries does TCS's related-party note name individually, and for what?

- Gold: Tata Consultancy Services Deutschland GmbH: revenue from operations ₹3,593 crore
- graph [baseline; score 1.00]: Based on the provided excerpts, Tata Consultancy Services' German subsidiary named individually in the related-party note is **Tata Consultancy Services Deutschland GmbH**, for "Revenue from operations" (with amounts of ₹3,593 crore for the year ended March 31, 2024, and ₹3,221 crore for the year ended March 31, 2023) [Tata Consultancy Services Limited, pp. 301-302].
  - Items extracted: Tata ConsultancyServices Deutschland GmbH: Revenue from operations (₹3,593 crore for the year ended March 31, 2024, and ₹3,221 crore for the year ended March 31, 2023)
- baseline [baseline; score 1.00]: Based on the provided excerpts, Tata Consultancy Services' German subsidiary named individually in the related-party note is **Tata Consultancy Services Deutschland GmbH**, for "Revenue from operations" (with amounts of ₹3,593 crore for the year ended March 31, 2024, and ₹3,221 crore for the year ended March 31, 2023) [Tata Consultancy Services Limited, pp. 301-302].
  - Items extracted: Tata ConsultancyServices Deutschland GmbH: Revenue from operations (₹3,593 crore for the year ended March 31, 2024, and ₹3,221 crore for the year ended March 31, 2023)

### t043 (3hop): Bharat Puri joined another pilot company's board after the year ended. Which audit partner signed that company's standalone auditor's report?

- Gold: Shiraz Vastani (B S R & Co. LLP)
- graph [baseline; score 1.00]: Based on the provided excerpts, Bharat Puri was appointed as an Additional Director of Tata Motors Limited with effect from May 15, 2024 [Tata Motors Limited, p. 480-481]. The standalone auditor's report for Tata Motors Limited was signed by audit partner **Shiraz Vastani** (Membership No.: 103334) [Tata Motors Limited, p. 385-386].
  - Items extracted: Shiraz Vastani
- baseline [baseline; score 1.00]: Based on the provided excerpts, Bharat Puri was appointed as an Additional Director of Tata Motors Limited with effect from May 15, 2024 [Tata Motors Limited, p. 480-481]. The standalone auditor's report for Tata Motors Limited was signed by audit partner **Shiraz Vastani** (Membership No.: 103334) [Tata Motors Limited, p. 385-386].
  - Items extracted: Shiraz Vastani

### t044 (3hop): Which secretarial auditor does each pilot company chaired by N Chandrasekaran use?

- Gold: TCS: Parikh & Associates; Tata Motors: Parikh & Associates; Tata Steel: Parikh & Associates; Tata Consumer Products: Dr. Asim Kumar Chattopadhyay
- graph [graph; score 1.00]: The secretarial auditor used by each company is: - Tata Motors Limited: Parikh & Associates - Tata Consumer Products Limited: DR. ASIM KUMAR CHATTOPADHYAY - Tata Steel Limited: Parikh & Associates - Tata Consultancy Services Limited: Parikh & Associates
  - Cypher: `MATCH p1 = (person:Person {uid: '00121863'})-[d:DIRECTOR_OF]->(c:Company) WHERE d.own_report AND d.status = 'current' AND coalesce(d.after_fy_end, false) = false AND toLower(coalesce(d.title, '')) CONTAINS 'chair' MATCH p2 = (c)-[a:AUDITED_BY {audit_type: 'secretarial'}]->(f:AuditFirm) RETURN c.name, f.name, f.firm_registration_no, collect(p1)[0] AS p1, collect(p2)[0] AS p2 LIMIT 100`
  - Items extracted: Tata Motors Limited: Parikh & Associates \|\| Tata Consumer Products Limited: DR. ASIM KUMAR CHATTOPADHYAY \|\| Tata Steel Limited: Parikh & Associates \|\| Tata Consultancy Services Limited: Parikh & Associates
- baseline [baseline; score 0.25]: Based on the provided report excerpts, the specific secretarial auditors used by each company are as follows: * **Tata Steel Limited:** Parikh & Associates [Tata Steel Limited, p. 181]. * **Tata Motors Limited:** The provided excerpts do not name the secretarial auditor for Tata Motors Limited itself (though Parikh & Associates is mentioned as the secretarial auditor for its subsidiary, Tata Motors Passenger Vehicles Limited) [Tata Motors Limited, pp. 161–162]. * **Tata Consultancy Services Limited** and **Tata Consumer Products Limited:** The provided excerpts do not contain information regarding the secretarial auditors for these companies.
  - Items extracted: Tata Steel Limited: Parikh & Associates \|\| Tata Motors Limited: The provided excerpts do not name the secretarial auditor for Tata Motors Limited itself \|\| Tata Consultancy Services Limited: information regarding the secretarial auditors for these companies is not contained \|\| Tata Consumer Products Limited: information regarding the secretarial auditors for these companies is not contained

### t045 (3hop): Which companies outside the five pilot companies are linked to both Tata Steel and Tata Consumer Products through the directorships their reports list?

- Gold: The Tata Power Company Limited; The Indian Hotels Company Limited; Tata Chemicals Limited
- graph [graph; score 1.00]: The companies are The Tata Power Company Limited, The Indian Hotels Company Limited, and Tata Chemicals Limited.
  - Cypher: `MATCH (ts:Company {uid: 'L27100MH1907PLC000260'}) MATCH (tcp:Company {uid: 'L15491WB1962PLC031425'}) MATCH p1 = (person:Person)-[:DIRECTOR_OF]->(ts) MATCH p2 = (person)-[:DIRECTOR_OF]->(tcp) MATCH p3 = (person)-[:DIRECTOR_OF]->(c:Company) WHERE c.nse_symbol IS NULL AND c <> ts AND c <> tcp WITH c, person, collect(p1)[0] AS p1, collect(p2)[0] AS p2, collect(p3)[0] AS p3 RETURN c.name, person.name, p1, p2, p3 LIMIT 100`
  - Items extracted: The Tata Power Company Limited \|\| The Indian Hotels Company Limited \|\| Tata Chemicals Limited
- baseline [baseline; score 0.00]: Based on the provided excerpts, the reports do not contain the answer to which companies outside the five pilot companies are linked to both Tata Steel and Tata Consumer Products through their listed directorships [Tata Steel Limited, pp. 438-439, 152, 230, 191-192, 9, 79-80; Tata Consumer Products Limited, pp. 6-10, 285-286, 290-291, 144-146, 426-427, 312-313].
  - Items extracted: (none)

### t046 (3hop): Which of Infosys's Indian subsidiaries paid Infosys a dividend in fiscal 2024, and how much?

- Gold: EdgeVerve Systems Limited: ₹1,089 crore; Infosys BPM Limited: ₹1,887 crore
- graph [baseline; score 0.00]: The provided excerpts do not contain information about which specific Indian subsidiaries paid Infosys a dividend or the individual amounts paid by them in fiscal 2024 (they only state that Infosys received a total of ₹2,976 crore of dividend from its subsidiaries in fiscal 2024) [Infosys Limited, p. 99].
  - Items extracted: (none)
- baseline [baseline; score 0.00]: The provided excerpts do not contain information about which specific Indian subsidiaries paid Infosys a dividend or the individual amounts paid by them in fiscal 2024 (they only state that Infosys received a total of ₹2,976 crore of dividend from its subsidiaries in fiscal 2024) [Infosys Limited, p. 99].
  - Items extracted: (none)

### t047 (3hop): Which director of Tata Consumer Products also sits on the board of the company Tata Consumer paid ₹15.90 crore of 'Other Expenses (Net)' to?

- Gold: N Chandrasekaran
- graph [graph; score 1.00]: N. Chandrasekaran
  - Cypher: `MATCH p1 = (:Company {uid: 'L15491WB1962PLC031425'})-[t:RELATED_PARTY_TXN]->(c:Company) WHERE t.amount_inr_crore = 15.90 AND toLower(t.nature) CONTAINS 'other expenses' MATCH p2 = (person:Person)-[d:DIRECTOR_OF]->(c) WHERE d.own_report AND d.status = 'current' AND coalesce(d.after_fy_end, false) = false MATCH p3 = (person)-[d2:DIRECTOR_OF]->(:Company {uid: 'L15491WB1962PLC031425'}) WHERE d2.own_report AND d2.status = 'current' AND coalesce(d2.after_fy_end, false) = false RETURN person.name, person.din, c.name, t.nature, t.amount_inr_crore, p1, p2, p3 LIMIT 100`
  - Items extracted: N. Chandrasekaran
- baseline [baseline; score 0.00]: Based on the provided excerpts, the reports do not contain information about the amount of 'Other Expenses (Net)' paid to any company, so this cannot be answered.
  - Items extracted: (none)

### t048 (3hop): Al-Noor Ramji joined a pilot company's board in October 2023. Who is that company's Company Secretary, and who signed its statutory auditor's report?

- Gold: Pradeep Manohar Gaitonde; Amit Somani (B S R & Co. LLP)
- graph [baseline; score 0.00]: Based on the provided excerpts, Al-Noor Ramji was appointed as an Independent Director of Tata Consultancy Services Limited for a term of five years from October 12, 2023 [Tata Consultancy Services Limited, p. 58]. Regarding Tata Consultancy Services Limited: * The excerpts do not name the Company Secretary who signed the secretarial records, but the Certificate of Non-Disqualification of Directors was issued by **Parikh & Associates, Practising Company Secretaries** (signed by **P. N. Parikh**) [Tata Consultancy Services Limited, pp. 116–117]. * The provided excerpts do not contain the name of the person who signed the statutory auditor's report for Tata Consultancy Services Limited.
  - Items extracted: Parikh & Associates, Practising Company Secretaries \|\| P. N. Parikh
- baseline [baseline; score 0.00]: Based on the provided excerpts, Al-Noor Ramji was appointed as an Independent Director of Tata Consultancy Services Limited for a term of five years from October 12, 2023 [Tata Consultancy Services Limited, p. 58]. Regarding Tata Consultancy Services Limited: * The excerpts do not name the Company Secretary who signed the secretarial records, but the Certificate of Non-Disqualification of Directors was issued by **Parikh & Associates, Practising Company Secretaries** (signed by **P. N. Parikh**) [Tata Consultancy Services Limited, pp. 116–117]. * The provided excerpts do not contain the name of the person who signed the statutory auditor's report for Tata Consultancy Services Limited.
  - Items extracted: Parikh & Associates, Practising Company Secretaries \|\| P. N. Parikh

### t049 (3hop): Which Tata Steel director chairs a company that Tata Consumer Products paid a dividend to in FY2024?

- Gold: Noel Naval Tata (Tata Investment Corporation Limited)
- graph [baseline; score 0.00]: The provided excerpts do not contain information to answer this question.
  - Items extracted: (none)
- baseline [baseline; score 0.00]: The provided excerpts do not contain information to answer this question.
  - Items extracted: (none)

### t050 (3hop): Which person is a director of both TCS and Tata Motors and was also an independent director of Tata Steel during part of FY2024?

- Gold: O P Bhatt
- graph [graph; score 0.00]: Based on the query results, the rows do not specify who was an independent director of Tata Steel during part of FY2024 or their status and dates, so the question cannot be answered using only the provided data.
  - Cypher: `MATCH p1 = (person:Person)-[d1:DIRECTOR_OF]->(:Company {uid: 'L22210MH1995PLC084781'}) MATCH p2 = (person)-[d2:DIRECTOR_OF]->(:Company {uid: 'L28920MH1945PLC004520'}) MATCH p3 = (person)-[d3:DIRECTOR_OF]->(:Company {uid: 'L27100MH1907PLC000260'}) WHERE d1.own_report AND d1.status = 'current' AND coalesce(d1.after_fy_end, false) = false AND d2.own_report AND d2.status = 'current' AND coalesce(d2.after_fy_end, false) = false AND d3.own_report AND (d3.status = 'current' OR d3.status = 'ceased') AND toLower(coalesce(d3.category, '')) CONTAINS 'independent' RETURN person.name, person.din, collect(p1) AS p1, collect(p2) AS p2, collect(p3) AS p3 LIMIT 100`
  - Items extracted: (none)
- baseline [baseline; score 1.00]: Based on the provided reports, O. P. Bhatt served as a director on the boards of TCS and Tata Motors, and also served as an Independent Director of Tata Steel until June 9, 2023 [Tata Consultancy Services Limited, p. 98; Tata Motors Limited, p. 248; Tata Steel Limited, p. 233].
  - Items extracted: O. P. Bhatt: director on the boards of TCS \|\| O. P. Bhatt: director on the boards of Tata Motors \|\| O. P. Bhatt: Independent Director of Tata Steel until June 9, 2023

### t051 (aggregation): Which TCS subsidiaries are incorporated in India?

- Gold: APTOnline Limited; C-Edge Technologies Limited; MP Online Limited; TCS e-Serve International Limited; MahaOnline Limited; TCS Foundation
- graph [baseline; score 0.40]: Based on the provided report excerpts, the TCS subsidiaries incorporated in India mentioned in the reports are: * APTOnline Limited [Tata Consultancy Services Limited, p. 306] * C-Edge Technologies Limited [Tata Consultancy Services Limited, p. 306] * MP Online Limited [Tata Consultancy Services Limited, p. 306] * TCS e-Serve International Limited [Tata Consultancy Services Limited, p. 306] * MahaOnline Limited [Tata Consultancy Services Limited, pp. 306, 308] * TCS Foundation [Tata Consultancy Services Limited, p. 308] * Technopolis Knowledge Park Limited [Tata Consultancy Services Limited, p. 55] * TCC Construction Private Limited [Tata Consultancy Services Limited, p. 55] * TCL Employee Welfare Trust [Tata Consultancy Services Limited, p. 55] * THDC Management Services Limited [Tata Consultancy Services Limited, p. 55] * TP Luminaire Private Limited [Tata Consultancy Services Limited, p. 55] * TPL Services Private Limited [Tata Consultancy Services Limited, p. 55] * TPL-CIL Construction LLP [Tata Consultancy Services Limited, p. 55] * TQ Cert Services Private Limited [Tata Consultancy Services Limited, p. 55] * TRIL Bengaluru Consultants Private Limited [Tata Consultancy Services Limited, p. 55] * TRIL Bengaluru Real Estate Five Limited [Tata Consultancy Services Limited, p. 55] * TRIL Bengaluru Real Estate One Private Limited [Tata Consultancy Services Limited, p. 55] * TRIL Bengaluru Real Estate Six Limited [Tata Consultancy Services Limited, p. 55] * TRIL IT4 Private Limited [Tata Consultancy Services Limited, p. 55] * TRIL Real Estate Balewadi Limited [Tata Consultancy Services Limited, p. 55] * TRIL Roads Private Limited [Tata Consultancy Services Limited, p. 55] * TRIL Urban Transport Private Limited [Tata Consultancy Services Limited, p. 55] * Uchit Expressways Private Limited [Tata Consultancy Services Limited, p. 55] * Ujjwal Pune Limited [Tata Consultancy Services Limited, p. 55]
  - Items extracted: APTOnline Limited \|\| C-Edge Technologies Limited \|\| MP Online Limited \|\| TCS e-Serve International Limited \|\| MahaOnline Limited \|\| TCS Foundation \|\| Technopolis Knowledge Park Limited \|\| TCC Construction Private Limited \|\| TCL Employee Welfare Trust \|\| THDC Management Services Limited \|\| TP Luminaire Private Limited \|\| TPL Services Private Limited \|\| TPL-CIL Construction LLP \|\| TQ Cert Services Private Limited \|\| TRIL Bengaluru Consultants Private Limited \|\| TRIL Bengaluru Real Estate Five Limited \|\| TRIL Bengaluru Real Estate One Private Limited \|\| TRIL Bengaluru Real Estate Six Limited \|\| TRIL IT4 Private Limited \|\| TRIL Real Estate Balewadi Limited \|\| TRIL Roads Private Limited \|\| TRIL Urban Transport Private Limited \|\| Uchit Expressways Private Limited \|\| Ujjwal Pune Limited
- baseline [baseline; score 0.40]: Based on the provided report excerpts, the TCS subsidiaries incorporated in India mentioned in the reports are: * APTOnline Limited [Tata Consultancy Services Limited, p. 306] * C-Edge Technologies Limited [Tata Consultancy Services Limited, p. 306] * MP Online Limited [Tata Consultancy Services Limited, p. 306] * TCS e-Serve International Limited [Tata Consultancy Services Limited, p. 306] * MahaOnline Limited [Tata Consultancy Services Limited, pp. 306, 308] * TCS Foundation [Tata Consultancy Services Limited, p. 308] * Technopolis Knowledge Park Limited [Tata Consultancy Services Limited, p. 55] * TCC Construction Private Limited [Tata Consultancy Services Limited, p. 55] * TCL Employee Welfare Trust [Tata Consultancy Services Limited, p. 55] * THDC Management Services Limited [Tata Consultancy Services Limited, p. 55] * TP Luminaire Private Limited [Tata Consultancy Services Limited, p. 55] * TPL Services Private Limited [Tata Consultancy Services Limited, p. 55] * TPL-CIL Construction LLP [Tata Consultancy Services Limited, p. 55] * TQ Cert Services Private Limited [Tata Consultancy Services Limited, p. 55] * TRIL Bengaluru Consultants Private Limited [Tata Consultancy Services Limited, p. 55] * TRIL Bengaluru Real Estate Five Limited [Tata Consultancy Services Limited, p. 55] * TRIL Bengaluru Real Estate One Private Limited [Tata Consultancy Services Limited, p. 55] * TRIL Bengaluru Real Estate Six Limited [Tata Consultancy Services Limited, p. 55] * TRIL IT4 Private Limited [Tata Consultancy Services Limited, p. 55] * TRIL Real Estate Balewadi Limited [Tata Consultancy Services Limited, p. 55] * TRIL Roads Private Limited [Tata Consultancy Services Limited, p. 55] * TRIL Urban Transport Private Limited [Tata Consultancy Services Limited, p. 55] * Uchit Expressways Private Limited [Tata Consultancy Services Limited, p. 55] * Ujjwal Pune Limited [Tata Consultancy Services Limited, p. 55]
  - Items extracted: APTOnline Limited \|\| C-Edge Technologies Limited \|\| MP Online Limited \|\| TCS e-Serve International Limited \|\| MahaOnline Limited \|\| TCS Foundation \|\| Technopolis Knowledge Park Limited \|\| TCC Construction Private Limited \|\| TCL Employee Welfare Trust \|\| THDC Management Services Limited \|\| TP Luminaire Private Limited \|\| TPL Services Private Limited \|\| TPL-CIL Construction LLP \|\| TQ Cert Services Private Limited \|\| TRIL Bengaluru Consultants Private Limited \|\| TRIL Bengaluru Real Estate Five Limited \|\| TRIL Bengaluru Real Estate One Private Limited \|\| TRIL Bengaluru Real Estate Six Limited \|\| TRIL IT4 Private Limited \|\| TRIL Real Estate Balewadi Limited \|\| TRIL Roads Private Limited \|\| TRIL Urban Transport Private Limited \|\| Uchit Expressways Private Limited \|\| Ujjwal Pune Limited

### t052 (aggregation): List every TCS subsidiary that TCS holds less than 100% of, with the shareholding. Leave out any subsidiary that merged into another company during the year.

- Gold: Tata Consultancy Services Japan, Ltd. 66%; APTOnline Limited 89%; C-Edge Technologies Limited 51%; MP Online Limited 89%; MahaOnline Limited 74%
- graph [graph; score 1.00]: - APTOnline Limited: 89.0% - C-Edge Technologies Limited: 51.0% - Tata Consultancy Services Japan, Ltd.: 66.0% - MahaOnline Limited: 74.0% - MP Online Limited: 89.0%
  - Cypher: `MATCH p = (s:Company)-[r:SUBSIDIARY_OF]->(:Company {uid: 'L22210MH1995PLC084781'}) WHERE r.stake_pct IS NOT NULL AND r.stake_pct < 100 AND NOT (s)-[:MERGED_INTO]->() RETURN s.name, r.stake_pct, p LIMIT 100`
  - Items extracted: APTOnline Limited: 89.0% \|\| C-Edge Technologies Limited: 51.0% \|\| Tata Consultancy Services Japan, Ltd.: 66.0% \|\| MahaOnline Limited: 74.0% \|\| MP Online Limited: 89.0%
- baseline [baseline; score 1.00]: Based on the provided excerpts, the TCS subsidiaries in which TCS holds less than 100% (excluding the one that merged) are: * **Tata Consultancy Services Japan, Ltd.:** 66% [Tata Consultancy Services Limited, p. 306] * **APTOnline Limited:** 89% [Tata Consultancy Services Limited, p. 306] * **C-Edge Technologies Limited:** 51% [Tata Consultancy Services Limited, p. 306] * **MP Online Limited:** 89% [Tata Consultancy Services Limited, p. 306] * **MahaOnline Limited:** 74% [Tata Consultancy Services Limited, p. 307]
  - Items extracted: Tata Consultancy Services Japan, Ltd.: 66% \|\| APTOnline Limited: 89% \|\| C-Edge Technologies Limited: 51% \|\| MP Online Limited: 89% \|\| MahaOnline Limited: 74%

### t053 (aggregation): How many TCS subsidiaries are incorporated in Germany?

- Gold: 3
- graph [baseline; score 0.00]: Based on the provided reports, there are 2 subsidiaries incorporated in Germany: 1. TCS Business Services GmbH [Tata Consultancy Services Limited, p. 306] 2. TCS Technology Solutions GmbH [Tata Consultancy Services Limited, p. 306]
  - Items extracted: TCS Business Services GmbH \|\| TCS Technology Solutions GmbH
- baseline [baseline; score 0.00]: Based on the provided reports, there are 2 subsidiaries incorporated in Germany: 1. TCS Business Services GmbH [Tata Consultancy Services Limited, p. 306] 2. TCS Technology Solutions GmbH [Tata Consultancy Services Limited, p. 306]
  - Items extracted: TCS Business Services GmbH \|\| TCS Technology Solutions GmbH

### t054 (aggregation): Among the related parties TCS names individually for 'Revenue from operations', which brought the most FY2024 revenue?

- Gold: Tata Consultancy Services Netherlands BV (₹4,009 crore)
- graph [graph; score 0.00]: Subsidiaries of the Company brought the most FY2024 revenue with INR 26,298.0 crore.
  - Cypher: `MATCH p = (:Company {uid: 'L22210MH1995PLC084781'})-[t:RELATED_PARTY_TXN]->(party) WHERE toLower(t.nature) CONTAINS 'revenue from operations' OR toLower(t.nature) CONTAINS 'sale' RETURN party.name, t.nature, t.amount_inr_crore, p ORDER BY t.amount_inr_crore DESC LIMIT 1`
  - Items extracted: Subsidiaries of the Company: INR 26,298.0 crore
- baseline [baseline; score 1.00]: Based on the material related party transactions listed in the report, the related party that brought the most FY2024 revenue among those named individually is **Tata Consultancy Services Netherlands BV** with ₹4,009 crore [Tata Consultancy Services Limited, pp. 301-302].
  - Items extracted: Tata Consultancy Services Netherlands BV: ₹4,009 crore

### t055 (aggregation): How many of the subsidiaries in Tata Motors' Form AOC-1 are incorporated in the UK?

- Gold: 23
- graph [baseline; score 0.00]: Based on the provided excerpts, the Form AOC-1 lists the following subsidiaries incorporated in the UK: 1. Tata Motors Design Tech Centre plc (formerly known as Tata Motors European Technical Centre PLC) [Tata Motors Limited, p.291] 2. INCAT International Plc. [Tata Motors Limited, p.291] 3. Tata Technologies Europe Limited [Tata Motors Limited, p.291] 4. Tata Technologies Nordics AB *(Note: listed with country UK in the excerpt)* [Tata Motors Limited, p.291] 5. Jaguar Land Rover Automotive Plc [Tata Motors Limited, p.291] 6. Jaguar Land Rover Limited [Tata Motors Limited, p.291] 7. JLR Nominee Company Limited [Tata Motors Limited, p.291] 8. The Daimler Motor Company Limited [Tata Motors Limited, p.291] 9. Daimler Transport Vehicles Limited [Tata Motors Limited, p.291] 10. S.S. Cars Limited [Tata Motors Limited, p.291] 11. The Lanchester Motor Company Limited [Tata Motors Limited, p.291] 12. Jaguar Land Rover Holdings Limited [Tata Motors Limited, p.291] 13. InMotion Ventures 3 Limited [Tata Motors Limited, p.292] 14. Jaguar Land Rover Ventures Limited [Tata Motors Limited, p.292] 15. Bowler Motors Limited [Tata Motors Limited, p.292] Counting these entries from the provided excerpts, there are 15 subsidiaries incorporated in the UK [Tata Motors Limited, pp. 291–292].
  - Items extracted: Tata Motors Design Tech Centre plc (formerly known as Tata Motors European Technical Centre PLC) \|\| INCAT International Plc. \|\| Tata Technologies Europe Limited \|\| Tata Technologies Nordics AB \|\| Jaguar Land Rover Automotive Plc \|\| Jaguar Land Rover Limited \|\| JLR Nominee Company Limited \|\| The Daimler Motor Company Limited \|\| Daimler Transport Vehicles Limited \|\| S.S. Cars Limited \|\| The Lanchester Motor Company Limited \|\| Jaguar Land Rover Holdings Limited \|\| InMotion Ventures 3 Limited \|\| Jaguar Land Rover Ventures Limited \|\| Bowler Motors Limited
- baseline [baseline; score 0.00]: Based on the provided excerpts, the Form AOC-1 lists the following subsidiaries incorporated in the UK: 1. Tata Motors Design Tech Centre plc (formerly known as Tata Motors European Technical Centre PLC) [Tata Motors Limited, p.291] 2. INCAT International Plc. [Tata Motors Limited, p.291] 3. Tata Technologies Europe Limited [Tata Motors Limited, p.291] 4. Tata Technologies Nordics AB *(Note: listed with country UK in the excerpt)* [Tata Motors Limited, p.291] 5. Jaguar Land Rover Automotive Plc [Tata Motors Limited, p.291] 6. Jaguar Land Rover Limited [Tata Motors Limited, p.291] 7. JLR Nominee Company Limited [Tata Motors Limited, p.291] 8. The Daimler Motor Company Limited [Tata Motors Limited, p.291] 9. Daimler Transport Vehicles Limited [Tata Motors Limited, p.291] 10. S.S. Cars Limited [Tata Motors Limited, p.291] 11. The Lanchester Motor Company Limited [Tata Motors Limited, p.291] 12. Jaguar Land Rover Holdings Limited [Tata Motors Limited, p.291] 13. InMotion Ventures 3 Limited [Tata Motors Limited, p.292] 14. Jaguar Land Rover Ventures Limited [Tata Motors Limited, p.292] 15. Bowler Motors Limited [Tata Motors Limited, p.292] Counting these entries from the provided excerpts, there are 15 subsidiaries incorporated in the UK [Tata Motors Limited, pp. 291–292].
  - Items extracted: Tata Motors Design Tech Centre plc (formerly known as Tata Motors European Technical Centre PLC) \|\| INCAT International Plc. \|\| Tata Technologies Europe Limited \|\| Tata Technologies Nordics AB \|\| Jaguar Land Rover Automotive Plc \|\| Jaguar Land Rover Limited \|\| JLR Nominee Company Limited \|\| The Daimler Motor Company Limited \|\| Daimler Transport Vehicles Limited \|\| S.S. Cars Limited \|\| The Lanchester Motor Company Limited \|\| Jaguar Land Rover Holdings Limited \|\| InMotion Ventures 3 Limited \|\| Jaguar Land Rover Ventures Limited \|\| Bowler Motors Limited

### t056 (aggregation): List all independent directors of Tata Motors as at March 31, 2024.

- Gold: O P Bhatt; Hanne Sorensen; Vedika Bhandarkar; K V Chowdary; Al-Noor Ramji; Usha Sangwan
- graph [graph; score 1.00]: The independent directors of Tata Motors as at March 31, 2024, are: - Usha Sangwan - O P Bhatt - Al-Noor Ramji - K V Chowdary - Hanne Sorensen - Vedika Bhandarkar
  - Cypher: `MATCH p = (person:Person)-[d:DIRECTOR_OF]->(c:Company {uid: 'L28920MH1945PLC004520'}) WHERE d.own_report AND d.status = 'current' AND coalesce(d.after_fy_end, false) = false AND toLower(d.category) CONTAINS 'independent' RETURN person.name, person.din, d.title, d.category, p LIMIT 100`
  - Items extracted: Usha Sangwan \|\| O P Bhatt \|\| Al-Noor Ramji \|\| K V Chowdary \|\| Hanne Sorensen \|\| Vedika Bhandarkar
- baseline [baseline; score 0.73]: Based on the provided excerpts, the exact list of all independent directors as of March 31, 2024, is not fully enumerated in a single list. However, the excerpts mention the following individuals who served as Independent Directors: * **Mrs. Usha Sangwan** [Tata Motors Limited, p. 247, 516-517] * **Mr. Al-Noor Ramji** [Tata Motors Limited, p. 247] * **Mr. Om Prakash Bhatt** [Tata Motors Limited, p. 247] * **Ms. Hanne Sorensen** [Tata Motors Limited, p. 247] * **Ms. Vedika Bhandarkar** [Tata Motors Limited, p. 516-517] *(Note: Mr. Bharat Puri was appointed as an Additional and Independent Director with effect from May 15, 2024, which is after March 31, 2024) [Tata Motors Limited, p. 480-481].*
  - Items extracted: Mrs. Usha Sangwan \|\| Mr. Al-Noor Ramji \|\| Mr. Om Prakash Bhatt \|\| Ms. Hanne Sorensen \|\| Ms. Vedika Bhandarkar

### t057 (aggregation): Which companies does Tata Motors list as its associates and joint ventures?

- Gold: Associates: Automobile Corporation of Goa Limited, Nita Co. Ltd, Tata AutoComp Systems Ltd, Tata Hitachi Construction Machinery Company Private Ltd; Joint venture: Fiat India Automobiles Private Ltd
- graph [baseline; score 0.37]: Based on the provided excerpts, Tata Motors lists the following associates and joint ventures: **Associates:** * Freight Tiger Commerce Solutions Private Limited (referred to as Freight Commerce Solutions Private Limited in financial transaction tables) [Tata Motors Limited, pp. 139-140, 377-378] * Automobile Corporation of Goa Limited [Tata Motors Limited, pp. 377-378] * Tata Hitachi Construction Machinery Company Private Limited [Tata Motors Limited, pp. 377-378] * Tata AutoComp Systems Limited [Tata Motors Limited, pp. 376-377] * TACO Prestolite Electric Private Limited [Tata Motors Limited, pp. 376-377] * TM Automotive Seating Systems Private Limited [Tata Motors Limited, pp. 376-377] **Joint Ventures:** * Chery Jaguar Land Rover Automotive Company Limited [Tata Motors Limited, pp. 479-480, 376-377] * Loginomic Tech Solutions Private Limited (“TruckEasy”) [Tata Motors Limited, pp. 479-480] * Jaguar Land Rover Switzerland AG [Tata Motors Limited, pp. 479-480] * Inchcape JLR Europe Limited [Tata Motors Limited, pp. 479-480] * Billia JLR Import AB [Tata Motors Limited, pp. 479-480] *(Note: The excerpts also mention Fiat India Automobiles Private Limited and Tata Cummins Private Ltd under "Joint Operations" [Tata Motors Limited, pp. 479-480], and state that the Company had 11 associate companies, 5 joint ventures, and 2 joint operations during FY24 [Tata Motors Limited, pp. 139-140]).*
  - Items extracted: Freight Tiger Commerce Solutions Private Limited (referred to as Freight Commerce Solutions Private Limited in financial transaction tables) (associate) \|\| Automobile Corporation of Goa Limited (associate) \|\| Tata Hitachi Construction Machinery Company Private Limited (associate) \|\| Tata AutoComp Systems Limited (associate) \|\| TACO Prestolite Electric Private Limited (associate) \|\| TM Automotive Seating Systems Private Limited (associate) \|\| Chery Jaguar Land Rover Automotive Company Limited (joint venture) \|\| Loginomic Tech Solutions Private Limited (“TruckEasy”) (joint venture) \|\| Jaguar Land Rover Switzerland AG (joint venture) \|\| Inchcape JLR Europe Limited (joint venture) \|\| Billia JLR Import AB (joint venture)
- baseline [baseline; score 0.37]: Based on the provided excerpts, Tata Motors lists the following associates and joint ventures: **Associates:** * Freight Tiger Commerce Solutions Private Limited (referred to as Freight Commerce Solutions Private Limited in financial transaction tables) [Tata Motors Limited, pp. 139-140, 377-378] * Automobile Corporation of Goa Limited [Tata Motors Limited, pp. 377-378] * Tata Hitachi Construction Machinery Company Private Limited [Tata Motors Limited, pp. 377-378] * Tata AutoComp Systems Limited [Tata Motors Limited, pp. 376-377] * TACO Prestolite Electric Private Limited [Tata Motors Limited, pp. 376-377] * TM Automotive Seating Systems Private Limited [Tata Motors Limited, pp. 376-377] **Joint Ventures:** * Chery Jaguar Land Rover Automotive Company Limited [Tata Motors Limited, pp. 479-480, 376-377] * Loginomic Tech Solutions Private Limited (“TruckEasy”) [Tata Motors Limited, pp. 479-480] * Jaguar Land Rover Switzerland AG [Tata Motors Limited, pp. 479-480] * Inchcape JLR Europe Limited [Tata Motors Limited, pp. 479-480] * Billia JLR Import AB [Tata Motors Limited, pp. 479-480] *(Note: The excerpts also mention Fiat India Automobiles Private Limited and Tata Cummins Private Ltd under "Joint Operations" [Tata Motors Limited, pp. 479-480], and state that the Company had 11 associate companies, 5 joint ventures, and 2 joint operations during FY24 [Tata Motors Limited, pp. 139-140]).*
  - Items extracted: Freight Tiger Commerce Solutions Private Limited (referred to as Freight Commerce Solutions Private Limited in financial transaction tables) (associate) \|\| Automobile Corporation of Goa Limited (associate) \|\| Tata Hitachi Construction Machinery Company Private Limited (associate) \|\| Tata AutoComp Systems Limited (associate) \|\| TACO Prestolite Electric Private Limited (associate) \|\| TM Automotive Seating Systems Private Limited (associate) \|\| Chery Jaguar Land Rover Automotive Company Limited (joint venture) \|\| Loginomic Tech Solutions Private Limited (“TruckEasy”) (joint venture) \|\| Jaguar Land Rover Switzerland AG (joint venture) \|\| Inchcape JLR Europe Limited (joint venture) \|\| Billia JLR Import AB (joint venture)

### t058 (aggregation): How many struck-off companies are listed in note 45 of Tata Motors' standalone financial statements for FY2024?

- Gold: 10
- graph [baseline; score 0.00]: Based on note 45 of Tata Motors' standalone financial statements for the year ended March 31, 2024, there are 10 struck-off companies listed [Tata Motors Limited, p. 466]: 1. Balasanka Cars Pvt. Ltd. 2. Chart D&S India Pvt. Ltd. 3. Cautela Techno Solutions Pvt. Ltd. 4. Farman Steels India Pvt. Ltd. 5. Highway Auto Tech Pvt. Ltd. 6. Honeycomb Relationship Management Pvt. Ltd. 7. Rudrapratap Forms Pvt. Ltd. 8. Taxi Films Pvt. Ltd. 9. Verific Investigation Consultants and Services Pvt. Ltd. 10. BM Carriers Pvt. Ltd.
  - Items extracted: Balasanka Cars Pvt. Ltd. \|\| Chart D&S India Pvt. Ltd. \|\| Cautela Techno Solutions Pvt. Ltd. \|\| Farman Steels India Pvt. Ltd. \|\| Highway Auto Tech Pvt. Ltd. \|\| Honeycomb Relationship Management Pvt. Ltd. \|\| Rudrapratap Forms Pvt. Ltd. \|\| Taxi Films Pvt. Ltd. \|\| Verific Investigation Consultants and Services Pvt. Ltd. \|\| BM Carriers Pvt. Ltd.
- baseline [baseline; score 0.00]: Based on note 45 of Tata Motors' standalone financial statements for the year ended March 31, 2024, there are 10 struck-off companies listed [Tata Motors Limited, p. 466]: 1. Balasanka Cars Pvt. Ltd. 2. Chart D&S India Pvt. Ltd. 3. Cautela Techno Solutions Pvt. Ltd. 4. Farman Steels India Pvt. Ltd. 5. Highway Auto Tech Pvt. Ltd. 6. Honeycomb Relationship Management Pvt. Ltd. 7. Rudrapratap Forms Pvt. Ltd. 8. Taxi Films Pvt. Ltd. 9. Verific Investigation Consultants and Services Pvt. Ltd. 10. BM Carriers Pvt. Ltd.
  - Items extracted: Balasanka Cars Pvt. Ltd. \|\| Chart D&S India Pvt. Ltd. \|\| Cautela Techno Solutions Pvt. Ltd. \|\| Farman Steels India Pvt. Ltd. \|\| Highway Auto Tech Pvt. Ltd. \|\| Honeycomb Relationship Management Pvt. Ltd. \|\| Rudrapratap Forms Pvt. Ltd. \|\| Taxi Films Pvt. Ltd. \|\| Verific Investigation Consultants and Services Pvt. Ltd. \|\| BM Carriers Pvt. Ltd.

### t059 (aggregation): List all independent directors of Tata Steel as at March 31, 2024.

- Gold: Deepak Kapoor; Farida Khambata; V. K. Sharma; Bharti Gupta Ramola; Dr. Shekhar C. Mande
- graph [graph; score 1.00]: The independent directors of Tata Steel as at March 31, 2024, are: - Shekhar C. Mande - V. K. Sharma - Farida Khambata - Bharti Gupta Ramola - Deepak Kapoor
  - Cypher: `MATCH p = (person:Person)-[d:DIRECTOR_OF]->(c:Company {uid: 'L27100MH1907PLC000260'}) WHERE d.own_report AND d.status = 'current' AND coalesce(d.after_fy_end, false) = false AND toLower(d.category) CONTAINS 'independent' RETURN person.name, person.din, d.title, d.category, p LIMIT 100`
  - Items extracted: Shekhar C. Mande \|\| V. K. Sharma \|\| Farida Khambata \|\| Bharti Gupta Ramola \|\| Deepak Kapoor
- baseline [baseline; score 1.00]: Based on the provided excerpts, the independent directors of Tata Steel as at March 31, 2024, are: * Deepak Kapoor [Tata Steel Limited, pp. 10-12, 234] * Farida Khambata [Tata Steel Limited, pp. 10-12, 234] * V. K. Sharma [Tata Steel Limited, pp. 10-12, 234] * Bharti Gupta Ramola [Tata Steel Limited, pp. 10-12, 234] * Dr. Shekhar C. Mande [Tata Steel Limited, pp. 10-12, 234]
  - Items extracted: Deepak Kapoor \|\| Farida Khambata \|\| V. K. Sharma \|\| Bharti Gupta Ramola \|\| Dr. Shekhar C. Mande

### t060 (aggregation): How many directors were on Tata Steel's board at March 31, 2024, and how many were executive, non-executive non-independent and independent?

- Gold: 10: 2 executive, 3 non-executive non-independent, 5 independent (2 of them women)
- graph [graph; score 0.13]: There were 10 directors on Tata Steel's board at March 31, 2024: 2 executive directors (Koushik Chatterjee and T. V. Narendran), 5 independent directors (Shekhar C. Mande, V. K. Sharma, Farida Khambata, Bharti Gupta Ramola, and Deepak Kapoor), and 3 non-executive non-independent directors (Noel Naval Tata, Saurabh Agrawal, and N. Chandrasekaran).
  - Cypher: `MATCH p = (person:Person)-[d:DIRECTOR_OF]->(c:Company {uid: 'L27100MH1907PLC000260'}) WHERE d.own_report AND d.status = 'current' AND coalesce(d.after_fy_end, false) = false RETURN count(person) AS total_directors, d.category, count(d.category) AS category_count, collect(p) AS paths LIMIT 100`
  - Items extracted: Tata Steel's board: 10 directors at March 31, 2024 \|\| Koushik Chatterjee: executive director \|\| T. V. Narendran: executive director \|\| Shekhar C. Mande: independent director \|\| V. K. Sharma: independent director \|\| Farida Khambata: independent director \|\| Bharti Gupta Ramola: independent director \|\| Deepak Kapoor: independent director \|\| Noel Naval Tata: non-executive non-independent director \|\| Saurabh Agrawal: non-executive non-independent director \|\| N. Chandrasekaran: non-executive non-independent director
- baseline [baseline; score 0.86]: Based on the provided excerpts, the exact total number of directors on Tata Steel's board at March 31, 2024 is not explicitly stated in a single count, but the board composition breakdown as of May 29, 2024 (and listed by categories as of March 31, 2024) is as follows: * **Executive Directors:** 2 [Tata Steel Limited, pp. 10-12, 230-231] * **Non-Executive (Non-Independent) Directors:** 3 [Tata Steel Limited, pp. 10-12, 230-231] * **Independent Directors:** 5 [Tata Steel Limited, pp. 10-12, 230-231]
  - Items extracted: Executive Directors: 2 \|\| Non-Executive (Non-Independent) Directors: 3 \|\| Independent Directors: 5

### t061 (aggregation): What changes did Tata Steel's board go through during FY2023-24?

- Gold: Dr. Shekhar C. Mande appointed June 1, 2023; O P Bhatt ceased June 9, 2023 (second term completed); T V Narendran re-appointed CEO & MD from September 19, 2023
- graph [graph; score 0.80]: During FY2023-24, Tata Steel's board changes were: Shekhar C. Mande was appointed as a current director on June 1, 2023, and O P Bhatt ceased to be a director on June 9, 2023.
  - Cypher: `MATCH p = (person:Person)-[d:DIRECTOR_OF]->(c:Company {uid: 'L27100MH1907PLC000260'}) WHERE d.own_report AND (d.status = 'ceased' OR d.appointed_on IS NOT NULL) RETURN person.name, d.title, d.status, d.appointed_on, d.ceased_on, p LIMIT 100`
  - Items extracted: Shekhar C. Mande was appointed as a current director on June 1, 2023 \|\| O P Bhatt ceased to be a director on June 9, 2023
- baseline [baseline; score 0.00]: During FY2023-24, the changes in Tata Steel's Board of Directors included: * Mr. O P Bhatt retired from the Board after serving for a decade [Tata Steel Limited, p. 9]. * Dr. Shekhar Mande joined the Board as a Director [Tata Steel Limited, p. 9] (appointed as an Independent Director [Tata Steel Limited, p. 238]). * Any changes that took place during the period under review were in compliance with applicable provisions [Tata Steel Limited, p. 271].
  - Items extracted: Mr. O P Bhatt retired from the Board after serving for a decade \|\| Dr. Shekhar Mande joined the Board as a Director (appointed as an Independent Director)

### t062 (aggregation): Which of the five pilot companies use Parikh & Associates as their secretarial auditor?

- Gold: Tata Consultancy Services; Tata Motors; Tata Steel
- graph [graph; score 1.00]: Tata Steel Limited, Tata Consultancy Services Limited, and Tata Motors Limited.
  - Cypher: `MATCH p = (c:Company)-[a:AUDITED_BY]->(f:AuditFirm {uid: 'F-000002'}) WHERE c.nse_symbol IS NOT NULL AND a.audit_type = 'secretarial' RETURN c.name, c.nse_symbol, a.audit_type, p LIMIT 100`
  - Items extracted: Tata Steel Limited \|\| Tata Consultancy Services Limited \|\| Tata Motors Limited
- baseline [baseline; score 1.00]: Based on the provided excerpts, the companies that use Parikh & Associates as their secretarial auditor are: * **Tata Steel Limited** [Tata Steel Limited, pp. 181-182] * **Tata Motors Limited** [Tata Motors Limited, pp. 145-146] * **Tata Consultancy Services Limited** [Tata Consultancy Services Limited, pp. 68-69] The provided excerpts do not mention Parikh & Associates for Infosys Limited or Tata Consumer Products Limited (which instead uses Dr. Asim Kumar Chattopadhyay) [Tata Consumer Products Limited, pp. 235-236; Infosys Limited, p. 40].
  - Items extracted: Tata Steel Limited \|\| Tata Motors Limited \|\| Tata Consultancy Services Limited

### t063 (aggregation): Which Tata Consumer Products directors were appointed or retired during FY2024, and when?

- Gold: Ajit Krishnakumar appointed November 1, 2023; L Krishnakumar (Lakshmanan Krishna Kumar) retired October 31, 2023
- graph [graph; score 0.67]: Lakshmanan Krishna Kumar ceased to be a director of Tata Consumer Products Limited on October 31, 2023.
  - Cypher: `MATCH p = (person:Person)-[d:DIRECTOR_OF]->(:Company {uid: 'L15491WB1962PLC031425'}) WHERE d.own_report AND (d.status = 'ceased' OR d.appointed_on IS NOT NULL) RETURN person.name, d.status, d.appointed_on, d.ceased_on, p LIMIT 100`
  - Items extracted: Lakshmanan Krishna Kumar ceased to be a director of Tata Consumer Products Limited on October 31, 2023
- baseline [baseline; score 0.80]: Based on the provided excerpts, the following appointments and retirements of Directors occurred during FY 2023-24: * **Mr. N. Chandrasekaran:** Retired by rotation and was re-appointed as a Non-Executive (Non-Independent) Director at the 60th Annual General Meeting held on June 6, 2023 [Tata Consumer Products Limited, pp. 230-231]. * **Mr. L. Krishnakumar:** Re-appointed as Executive Director & Group CFO effective from April 1, 2023, up to October 31, 2023 (approved at the June 6, 2023 AGM), and subsequently retired from his position at the close of business hours on October 31, 2023 [Tata Consumer Products Limited, pp. 230-231]. * **Mr. Ajit Krishnakumar:** Appointed as a Whole-time Director, designated as Executive Director and Chief Operating Officer (COO), for a 5-year term starting November 1, 2023 [Tata Consumer Products Limited, pp. 230-231].
  - Items extracted: Mr. N. Chandrasekaran: Retired by rotation and was re-appointed as a Non-Executive (Non-Independent) Director at the 60th Annual General Meeting held on June 6, 2023 \|\| Mr. L. Krishnakumar: Re-appointed as Executive Director & Group CFO effective from April 1, 2023, up to October 31, 2023, and subsequently retired from his position at the close of business hours on October 31, 2023 \|\| Mr. Ajit Krishnakumar: Appointed as a Whole-time Director, designated as Executive Director and Chief Operating Officer (COO), for a 5-year term starting November 1, 2023

### t064 (aggregation): Which companies does Tata Consumer Products list under 'Subsidiaries and Joint Ventures of Promoter' for Other Expenses (Net), and how much was each?

- Gold: Tata AIG General Insurance Limited ₹41.74 crore; Tata Consultancy Services Limited ₹15.90 crore; Tata Communications Limited ₹13.13 crore
- graph [baseline; score 1.00]: Based on the provided excerpts, the companies listed under "Subsidiaries and Joint Ventures of Promoter" for Other Expenses (Net) and their respective amounts for the year ended March 31, 2024, are: * **Tata AIG General Insurance Limited:** Rs. 41.74 Crores (Standalone) [Tata Consumer Products Limited, p. 425] / Rs. 43.21 Crores (Consolidated) [Tata Consumer Products Limited, p. 518] * **Tata Consultancy Services Limited:** Rs. 15.90 Crores (Standalone) [Tata Consumer Products Limited, p. 425] / Rs. 28.89 Crores (Consolidated) [Tata Consumer Products Limited, p. 518] * **Tata Communications Limited:** Rs. 13.13 Crores (Standalone) [Tata Consumer Products Limited, p. 425] / Rs. 13.28 Crores (Consolidated) [Tata Consumer Products Limited, p. 518]
  - Items extracted: Tata AIG General Insurance Limited: Rs. 41.74 Crores (Standalone) / Rs. 43.21 Crores (Consolidated) \|\| Tata Consultancy Services Limited: Rs. 15.90 Crores (Standalone) / Rs. 28.89 Crores (Consolidated) \|\| Tata Communications Limited: Rs. 13.13 Crores (Standalone) / Rs. 13.28 Crores (Consolidated)
- baseline [baseline; score 1.00]: Based on the provided excerpts, the companies listed under "Subsidiaries and Joint Ventures of Promoter" for Other Expenses (Net) and their respective amounts for the year ended March 31, 2024, are: * **Tata AIG General Insurance Limited:** Rs. 41.74 Crores (Standalone) [Tata Consumer Products Limited, p. 425] / Rs. 43.21 Crores (Consolidated) [Tata Consumer Products Limited, p. 518] * **Tata Consultancy Services Limited:** Rs. 15.90 Crores (Standalone) [Tata Consumer Products Limited, p. 425] / Rs. 28.89 Crores (Consolidated) [Tata Consumer Products Limited, p. 518] * **Tata Communications Limited:** Rs. 13.13 Crores (Standalone) [Tata Consumer Products Limited, p. 425] / Rs. 13.28 Crores (Consolidated) [Tata Consumer Products Limited, p. 518]
  - Items extracted: Tata AIG General Insurance Limited: Rs. 41.74 Crores (Standalone) / Rs. 43.21 Crores (Consolidated) \|\| Tata Consultancy Services Limited: Rs. 15.90 Crores (Standalone) / Rs. 28.89 Crores (Consolidated) \|\| Tata Communications Limited: Rs. 13.13 Crores (Standalone) / Rs. 13.28 Crores (Consolidated)

### t065 (aggregation): Which related parties does Tata Consumer Products name individually as receiving dividends from it in FY2024, and how much did each receive?

- Gold: Tata Sons Private Limited ₹228.62 crore; Tata Investment Corporation Limited ₹37.41 crore
- graph [graph; score 0.00]: The query results do not name any related parties individually as receiving dividends from Tata Consumer Products in FY2024 (the parties that received dividends are listed only by categories such as Subsidiaries, Promoter, etc., while the specific entities named—Tata Sons Private Limited and Tata Investment Corporation Limited—are recorded under "Dividend Paid" rather than receiving dividends from the company).
  - Cypher: `MATCH p = (c:Company {uid: 'L15491WB1962PLC031425'})-[t:RELATED_PARTY_TXN]->(party) WHERE toLower(t.nature) CONTAINS 'dividend' RETURN party.name, t.nature, t.amount_inr_crore, t.amount_as_printed, p LIMIT 100`
  - Items extracted: (none)
- baseline [baseline; score 0.00]: The provided report excerpts do not contain information regarding individual related parties receiving dividends from Tata Consumer Products in FY2024. Therefore, the answer is not available in the excerpts.
  - Items extracted: (none)

### t066 (aggregation): Who does Tata Consumer Products list as Key Management Personnel in its related-party note?

- Gold: Sunil D'Souza (Managing Director & CEO); L Krishnakumar (Executive Director & Group CFO, up to October 31, 2023); Ajit Krishnakumar (Executive Director & COO, from November 1, 2023)
- graph [baseline; score 1.00]: Based on the provided excerpts, Tata Consumer Products lists the following Key Management Personnel in its related-party note: * Mr. Sunil D'Souza - Managing Director & CEO [Tata Consumer Products Limited, pp. 516-517, 421-422] * Mr. L Krishnakumar - Executive Director & Group CFO (upto October 31, 2023) [Tata Consumer Products Limited, pp. 516-517, 421-422] * Mr. Ajit Krishnakumar - Executive Director & COO (w.e.f. November 01, 2023) [Tata Consumer Products Limited, pp. 516-517, 421-422]
  - Items extracted: Mr. Sunil D'Souza - Managing Director & CEO \|\| Mr. L Krishnakumar - Executive Director & Group CFO (upto October 31, 2023) \|\| Mr. Ajit Krishnakumar - Executive Director & COO (w.e.f. November 01, 2023)
- baseline [baseline; score 1.00]: Based on the provided excerpts, Tata Consumer Products lists the following Key Management Personnel in its related-party note: * Mr. Sunil D'Souza - Managing Director & CEO [Tata Consumer Products Limited, pp. 516-517, 421-422] * Mr. L Krishnakumar - Executive Director & Group CFO (upto October 31, 2023) [Tata Consumer Products Limited, pp. 516-517, 421-422] * Mr. Ajit Krishnakumar - Executive Director & COO (w.e.f. November 01, 2023) [Tata Consumer Products Limited, pp. 516-517, 421-422]
  - Items extracted: Mr. Sunil D'Souza - Managing Director & CEO \|\| Mr. L Krishnakumar - Executive Director & Group CFO (upto October 31, 2023) \|\| Mr. Ajit Krishnakumar - Executive Director & COO (w.e.f. November 01, 2023)

### t067 (aggregation): How many Infosys subsidiaries are incorporated in Germany?

- Gold: 10
- graph [baseline; score 0.00]: Based on the provided reports, the following subsidiaries of Infosys are incorporated in Germany: 1. Infosys Financial Services GmbH (formerly Panaya GmbH) [Infosys Limited, pp. 249-250, 329-330] 2. Stater Gmbh [Infosys Limited, pp. 249-250, 329-330] 3. Infosys Germany GmbH (formerly Kristall 247. GmbH (“Kristall”)) [Infosys Limited, pp. 249-250, 329-330] 4. WongDoody Gmbh (formerly known as oddity GmbH) [Infosys Limited, pp. 249-250, 329-330] 5. Panaya Germany GmbH [Infosys Limited, pp. 329-330] 6. Infosys Consulting GmbH [Infosys Limited, pp. 329-330] 7. GuideVision Deutschland GmbH [Infosys Limited, pp. 329-330] 8. Infosys Germany Holding Gmbh [Infosys Limited, p. 329] 9. Infosys Automotive and Mobility GmbH & Co. KG [Infosys Limited, p. 329] 10. Infosys Austria GmbH [Infosys Limited, p. 329] *(Note: Although named Austria GmbH, the report lists its country of incorporation as Germany in the standalone/consolidated financial statement listings or tables, or alternatively refers to Infosys Austria GmbH).* Let me double check: the table lists "Infosys Austria GmbH" under country "Austria" [Infosys Limited, p. 329]. Therefore, strictly within Germany, the list includes the aforementioned companies based in Germany. Additionally, the report mentions the past/merged German entities (oddity space GmbH, oddity jungle GmbH, oddity waves GmbH, oddity group services GmbH, and oddity code GmbH) which were merged into WongDoody GmbH [Infosys Limited, pp. 330-331].
  - Items extracted: Infosys Financial Services GmbH (formerly Panaya GmbH) \|\| Stater Gmbh \|\| Infosys Germany GmbH (formerly Kristall 247. GmbH (“Kristall”)) \|\| WongDoody Gmbh (formerly known as oddity GmbH) \|\| Panaya Germany GmbH \|\| Infosys Consulting GmbH \|\| GuideVision Deutschland GmbH \|\| Infosys Germany Holding Gmbh \|\| Infosys Automotive and Mobility GmbH & Co. KG
- baseline [baseline; score 0.00]: Based on the provided reports, the following subsidiaries of Infosys are incorporated in Germany: 1. Infosys Financial Services GmbH (formerly Panaya GmbH) [Infosys Limited, pp. 249-250, 329-330] 2. Stater Gmbh [Infosys Limited, pp. 249-250, 329-330] 3. Infosys Germany GmbH (formerly Kristall 247. GmbH (“Kristall”)) [Infosys Limited, pp. 249-250, 329-330] 4. WongDoody Gmbh (formerly known as oddity GmbH) [Infosys Limited, pp. 249-250, 329-330] 5. Panaya Germany GmbH [Infosys Limited, pp. 329-330] 6. Infosys Consulting GmbH [Infosys Limited, pp. 329-330] 7. GuideVision Deutschland GmbH [Infosys Limited, pp. 329-330] 8. Infosys Germany Holding Gmbh [Infosys Limited, p. 329] 9. Infosys Automotive and Mobility GmbH & Co. KG [Infosys Limited, p. 329] 10. Infosys Austria GmbH [Infosys Limited, p. 329] *(Note: Although named Austria GmbH, the report lists its country of incorporation as Germany in the standalone/consolidated financial statement listings or tables, or alternatively refers to Infosys Austria GmbH).* Let me double check: the table lists "Infosys Austria GmbH" under country "Austria" [Infosys Limited, p. 329]. Therefore, strictly within Germany, the list includes the aforementioned companies based in Germany. Additionally, the report mentions the past/merged German entities (oddity space GmbH, oddity jungle GmbH, oddity waves GmbH, oddity group services GmbH, and oddity code GmbH) which were merged into WongDoody GmbH [Infosys Limited, pp. 330-331].
  - Items extracted: Infosys Financial Services GmbH (formerly Panaya GmbH) \|\| Stater Gmbh \|\| Infosys Germany GmbH (formerly Kristall 247. GmbH (“Kristall”)) \|\| WongDoody Gmbh (formerly known as oddity GmbH) \|\| Panaya Germany GmbH \|\| Infosys Consulting GmbH \|\| GuideVision Deutschland GmbH \|\| Infosys Germany Holding Gmbh \|\| Infosys Automotive and Mobility GmbH & Co. KG

### t068 (aggregation): Which Infosys subsidiaries are incorporated in India?

- Gold: Infosys BPM Limited; EdgeVerve Systems Limited; Infosys Green Forum; Danske IT and Support Services India Private Limited; Skava Systems Pvt. Ltd.
- graph [baseline; score 0.75]: Based on the provided excerpts, the subsidiaries of Infosys incorporated in India mentioned in the reports are: * Infosys BPM Limited [Infosys Limited, p.276, p.68] * EdgeVerve Systems Limited (EdgeVerve) [Infosys Limited, p.276, p.68] * Idunn Information Technology Private Limited (formerly Danske IT and Support Services India Private Limited) [Infosys Limited, p.251, p.276, p.49]
  - Items extracted: Infosys BPM Limited \|\| EdgeVerve Systems Limited (EdgeVerve) \|\| Idunn Information Technology Private Limited (formerly Danske IT and Support Services India Private Limited)
- baseline [baseline; score 0.75]: Based on the provided excerpts, the subsidiaries of Infosys incorporated in India mentioned in the reports are: * Infosys BPM Limited [Infosys Limited, p.276, p.68] * EdgeVerve Systems Limited (EdgeVerve) [Infosys Limited, p.276, p.68] * Idunn Information Technology Private Limited (formerly Danske IT and Support Services India Private Limited) [Infosys Limited, p.251, p.276, p.49]
  - Items extracted: Infosys BPM Limited \|\| EdgeVerve Systems Limited (EdgeVerve) \|\| Idunn Information Technology Private Limited (formerly Danske IT and Support Services India Private Limited)

### t069 (aggregation): How much dividend income did Infosys receive from its subsidiaries in fiscal 2024 in total, and which subsidiary paid the most?

- Gold: ₹2,976 crore in total; Infosys BPM Limited (₹1,887 crore)
- graph [baseline; score 0.67]: In fiscal 2024, Infosys received ₹2,976 crore of dividend from its subsidiaries, which is reflected in the Standalone financial statement [Infosys Limited, p. 72-73]. The provided excerpts do not contain information on which specific subsidiary paid the most dividend, so that cannot be answered.
  - Items extracted: dividend from its subsidiaries: ₹2,976 crore
- baseline [baseline; score 0.67]: In fiscal 2024, Infosys received ₹2,976 crore of dividend from its subsidiaries, which is reflected in the Standalone financial statement [Infosys Limited, p. 72-73]. The provided excerpts do not contain information on which specific subsidiary paid the most dividend, so that cannot be answered.
  - Items extracted: dividend from its subsidiaries: ₹2,976 crore

### t070 (aggregation): Which Infosys directors joined or left the board during fiscal 2024, and when?

- Gold: Uri Levine retired April 19, 2023; Helene Auriol Potier appointed May 26, 2023; Nitin Paranjpe appointed January 1, 2024
- graph [graph; score 1.00]: During fiscal 2024, the following directors joined or left the board of Infosys Limited: * Uri Levine ceased on April 19, 2023. * Helene Auriol Potier joined (current status) on May 26, 2023. * Nitin Paranjpe joined (current status) on January 01, 2024.
  - Cypher: `MATCH p = (person:Person)-[d:DIRECTOR_OF]->(:Company {uid: 'L85110KA1981PLC013115'}) WHERE d.own_report AND (d.status = 'ceased' OR d.appointed_on IS NOT NULL) RETURN person.name, d.status, d.appointed_on, d.ceased_on, p LIMIT 100`
  - Items extracted: Uri Levine ceased on April 19, 2023 \|\| Helene Auriol Potier joined (current status) on May 26, 2023 \|\| Nitin Paranjpe joined (current status) on January 01, 2024
- baseline [baseline; score 1.00]: Based on the provided report excerpts, the Infosys directors who joined or left the board during fiscal 2024 are: * **Uri Levine** retired as an Independent Director effective **April 19, 2023** [Infosys, pp. 38–39, 87]. * **Helene Auriol Potier** was appointed as an Independent Director effective **May 26, 2023** [Infosys, pp. 38–39, 87]. * **Nitin Paranjpe** was appointed as an Independent Director effective **January 1, 2024** [Infosys, pp. 38–39, 87].
  - Items extracted: Uri Levine retired as an Independent Director effective April 19, 2023 \|\| Helene Auriol Potier was appointed as an Independent Director effective May 26, 2023 \|\| Nitin Paranjpe was appointed as an Independent Director effective January 1, 2024

### t071 (text_only): What was TCS's LTM attrition rate in IT services for FY2024?

- Gold: 12.5%
- graph [baseline; grade 1 (judge 1)]: TCS's LTM attrition rate in IT services for FY 2024 was 12.5% [Tata Consultancy Services Limited, pp. 6-7, 8].
- baseline [baseline; grade 1 (judge 1)]: TCS's LTM attrition rate in IT services for FY 2024 was 12.5% [Tata Consultancy Services Limited, pp. 6-7, 8].

### t072 (text_only): What was TCS's consolidated revenue from operations in FY2024?

- Gold: ₹2,40,893 crore
- graph [baseline; grade 1 (judge 1)]: TCS's consolidated revenue from operations in FY 2024 was ₹2,40,893 crore [Tata Consultancy Services Limited, p. 4, 57].
- baseline [baseline; grade 1 (judge 1)]: TCS's consolidated revenue from operations in FY 2024 was ₹2,40,893 crore [Tata Consultancy Services Limited, p. 4, 57].

### t073 (text_only): How much did TCS spend on CSR projects in FY2024?

- Gold: ₹813 crore
- graph [baseline; grade 1 (judge 1)]: Based on the provided reports, TCS spent ₹813 crore on CSR projects (both Ongoing Project and other than Ongoing Project) for the financial year ended March 31, 2024 [Tata Consultancy Services Limited, p. 65].
- baseline [baseline; grade 1 (judge 1)]: Based on the provided reports, TCS spent ₹813 crore on CSR projects (both Ongoing Project and other than Ongoing Project) for the financial year ended March 31, 2024 [Tata Consultancy Services Limited, p. 65].

### t074 (text_only): How many Board meetings did Tata Motors hold in FY24?

- Gold: 7
- graph [baseline; grade 1 (judge 1)]: Based on the provided report excerpts, the Board held 7 (seven) meetings during FY24 [Tata Motors Limited, p. 144].
- baseline [baseline; grade 1 (judge 1)]: Based on the provided report excerpts, the Board held 7 (seven) meetings during FY24 [Tata Motors Limited, p. 144].

### t075 (text_only): What was Tata Motors' consolidated revenue from operations in FY24?

- Gold: ₹4,37,927.77 crore
- graph [baseline; grade 1 (judge 1)]: In FY24, Tata Motors' total consolidated revenue from operations including finance revenue increased by 26.6% to ₹4,37,928 crores (from ₹3,45,967 crores in FY23) [Tata Motors Limited, p.218, p.216].
- baseline [baseline; grade 1 (judge 1)]: In FY24, Tata Motors' total consolidated revenue from operations including finance revenue increased by 26.6% to ₹4,37,928 crores (from ₹3,45,967 crores in FY23) [Tata Motors Limited, p.218, p.216].

### t076 (text_only): How much did Tata Motors spend on CSR in FY24, and was it required to?

- Gold: ₹21.59 crore; not required (CSR obligation nil because of losses in preceding years)
- graph [baseline; grade 1 (judge 1)]: In FY24, Tata Motors spent ₹21.59 crore on Corporate Social Responsibility (CSR) [Tata Motors Limited, p. 446]. Regarding the requirement to spend, the report states that the amount required to be spent by the Company during the year was "-" (not applicable or nil), and the reason for any shortfall is marked as "NA" [Tata Motors Limited, p. 446, p. 153].
- baseline [baseline; grade 1 (judge 1)]: In FY24, Tata Motors spent ₹21.59 crore on Corporate Social Responsibility (CSR) [Tata Motors Limited, p. 446]. Regarding the requirement to spend, the report states that the amount required to be spent by the Company during the year was "-" (not applicable or nil), and the reason for any shortfall is marked as "NA" [Tata Motors Limited, p. 446, p. 153].

### t077 (text_only): Who are Tata Steel's cost auditors?

- Gold: Shome & Banerjee
- graph [baseline; grade 1 (judge 1)]: Tata Steel's cost auditors are Messrs Shome & Banerjee, Cost Accountants [Tata Steel Limited, pp. 557].
- baseline [baseline; grade 1 (judge 1)]: Tata Steel's cost auditors are Messrs Shome & Banerjee, Cost Accountants [Tata Steel Limited, pp. 557].

### t078 (text_only): What was Tata Steel's standalone revenue from operations in FY2023-24?

- Gold: ₹1,40,987.43 crore
- graph [baseline; grade 1 (judge 0.5)]: Tata Steel's standalone revenue from operations in FY2023-24 was ₹140,987 crore [Tata Steel Limited, pp. 211-212].
- baseline [baseline; grade 1 (judge 0.5)]: Tata Steel's standalone revenue from operations in FY2023-24 was ₹140,987 crore [Tata Steel Limited, pp. 211-212].

### t079 (text_only): What is Tata Steel's annual crude steel production capacity?

- Gold: 35 MTPA
- graph [baseline; grade 1 (judge 1)]: Tata Steel's consolidated crude steel production capacity is 35 MTPA [Tata Steel Limited, pp. 39-40, 3-6].
- baseline [baseline; grade 1 (judge 1)]: Tata Steel's consolidated crude steel production capacity is 35 MTPA [Tata Steel Limited, pp. 39-40, 3-6].

### t080 (text_only): What was Tata Consumer Products' consolidated revenue from operations in FY2024?

- Gold: ₹15,206 crore
- graph [baseline; grade 1 (judge 1)]: Based on the provided report excerpts, Tata Consumer Products' consolidated revenue for FY 2023-24 was INR 15,206 Crores [Tata Consumer Products Limited, pp. 9-13].
- baseline [baseline; grade 1 (judge 1)]: Based on the provided report excerpts, Tata Consumer Products' consolidated revenue for FY 2023-24 was INR 15,206 Crores [Tata Consumer Products Limited, pp. 9-13].

### t081 (text_only): How many times did Tata Consumer Products' board meet in FY2024?

- Gold: 7
- graph [baseline; grade 0 (judge 0)]: Based on the provided excerpts, the exact number of Board meetings held during FY 2023-24 is not explicitly stated as a single total, though individual director attendance records show that various directors attended up to 7 meetings during the year [Tata Consumer Products Limited, pp. 288-289].
- baseline [baseline; grade 0 (judge 0)]: Based on the provided excerpts, the exact number of Board meetings held during FY 2023-24 is not explicitly stated as a single total, though individual director attendance records show that various directors attended up to 7 meetings during the year [Tata Consumer Products Limited, pp. 288-289].

### t082 (text_only): What was Tata Consumer Products' CSR obligation for FY2024?

- Gold: ₹20.03 crore
- graph [baseline; grade 1 (judge 1)]: Tata Consumer Products' CSR obligation for FY 2024 was Rs 20.03 Crores [Tata Consumer Products Limited, p. 234, 417].
- baseline [baseline; grade 1 (judge 1)]: Tata Consumer Products' CSR obligation for FY 2024 was Rs 20.03 Crores [Tata Consumer Products Limited, p. 234, 417].

### t083 (text_only): What share of Infosys's India operations ran on renewable energy in fiscal 2024?

- Gold: 67.52%
- graph [baseline; grade 1 (judge 1)]: In fiscal 2024, 67.52% of Infosys's electricity in India operations was met through renewables [Infosys Limited, p. 65; Infosys Limited, p. 26].
- baseline [baseline; grade 1 (judge 1)]: In fiscal 2024, 67.52% of Infosys's electricity in India operations was met through renewables [Infosys Limited, p. 65; Infosys Limited, p. 26].

### t084 (text_only): What was Infosys's consolidated revenue from operations for fiscal 2024?

- Gold: ₹1,53,670 crore
- graph [baseline; grade 1 (judge 1)]: Infosys's consolidated revenue from operations for fiscal 2024 was ₹153,670 crore [Infosys Limited, p. 339].
- baseline [baseline; grade 1 (judge 1)]: Infosys's consolidated revenue from operations for fiscal 2024 was ₹153,670 crore [Infosys Limited, p. 339].

### t085 (text_only): How much did Infosys spend on CSR globally in fiscal 2024?

- Gold: ₹577 crore
- graph [baseline; grade 0 (judge 0)]: Based on the provided reports, Infosys spent ₹450.76 crore on CSR activities in India during fiscal 2024 [Infosys Limited, p. 94]. Additionally, Infosys expanded its CSR footprint globally, spending $4,698,267 (equivalent to ₹39 crore) towards CSR in Australia, Europe, and through Infosys Foundation USA [Infosys Limited, p. 90].
- baseline [baseline; grade 0 (judge 0)]: Based on the provided reports, Infosys spent ₹450.76 crore on CSR activities in India during fiscal 2024 [Infosys Limited, p. 94]. Additionally, Infosys expanded its CSR footprint globally, spending $4,698,267 (equivalent to ₹39 crore) towards CSR in Australia, Europe, and through Infosys Foundation USA [Infosys Limited, p. 90].

### t086 (none_or_unanswerable): Which Infosys directors also sit on the board of one of the four Tata pilot companies?

- Gold: none
- graph [clarify; score 0.00]: 'Tata' matches several entries in the graph: Tata SmartFoodz Ltd. (Company, in TATACONSUM); Tata Coffee Limited (Company, in TATACONSUM); Tata Technologies Limited (Company, India, in TATACONSUM, TATAMOTORS); Tata Technologies GmbH (Company, Germany, in TATAMOTORS); Tata Elxsi Limited (Company, in TCS); Tata Steel Foundation (Company, in TATASTEEL). Which one do you mean?
  - Items extracted: (none)
- baseline [baseline; score 1.00]: The provided excerpts do not contain information about any Infosys directors sitting on the board of a Tata pilot company.
  - Items extracted: (none)

### t087 (none_or_unanswerable): Which of Keki Mistry's other listed directorships, as given in TCS's report, are with other pilot companies?

- Gold: none
- graph [baseline; score 1.00]: Based on the provided excerpts, the report lists the following other directorships for Keki Mistry [Tata Consultancy Services Limited, p. 10]: 1. HDFC Life Insurance Company Limited (N) [Tata Consultancy Services Limited, p. 10] 2. HDFC ERGO General Insurance Company Limited [(N) Debt Listed] [Tata Consultancy Services Limited, p. 10] 3. HDFC Bank Limited (N) [Tata Consultancy Services Limited, p. 10] 4. The Great Eastern Shipping Company Limited (I) [Tata Consultancy Services Limited, p. 10] 5. Torrent Power Limited (I) [ceased w.e.f. March 31, 2024] [Tata Consultancy Services Limited, p. 10] The excerpts do not contain any information identifying which of these companies are "pilot companies."
  - Cypher: `MATCH p1 = (person:Person {uid: '00008886'})-[d1:DIRECTOR_OF]->(:Company {uid: 'L22210MH1995PLC084781'}) MATCH p2 = (person)-[d2:DIRECTOR_OF]->(c:Company) WHERE d2.reported_by = 'L22210MH1995PLC084781' AND d2.own_report = false AND c.nse_symbol IS NOT NULL AND c.uid <> 'L22210MH1995PLC084781' RETURN c.name, c.nse_symbol, d2.reported_by, p1, p2 LIMIT 100`
  - Items extracted: (none)
- baseline [baseline; score 1.00]: Based on the provided excerpts, the report lists the following other directorships for Keki Mistry [Tata Consultancy Services Limited, p. 10]: 1. HDFC Life Insurance Company Limited (N) [Tata Consultancy Services Limited, p. 10] 2. HDFC ERGO General Insurance Company Limited [(N) Debt Listed] [Tata Consultancy Services Limited, p. 10] 3. HDFC Bank Limited (N) [Tata Consultancy Services Limited, p. 10] 4. The Great Eastern Shipping Company Limited (I) [Tata Consultancy Services Limited, p. 10] 5. Torrent Power Limited (I) [ceased w.e.f. March 31, 2024] [Tata Consultancy Services Limited, p. 10] The excerpts do not contain any information identifying which of these companies are "pilot companies."
  - Items extracted: (none)

### t088 (none_or_unanswerable): Apart from Tata America International Corporation, which TCS subsidiaries are incorporated in the USA?

- Gold: none
- graph [baseline; score 1.00]: Based on the provided excerpts, the exact incorporation locations of TCS subsidiaries other than Tata America International Corporation are not fully detailed by country beyond a general listing of subsidiary names (such as TECHNOTHROUGH or others listed in the report); therefore, the excerpts do not contain a complete list of which specific subsidiaries are incorporated in the USA other than Tata America International Corporation [Tata Consultancy Services Limited, pp. 2, 55, 233].
  - Items extracted: (none)
- baseline [baseline; score 1.00]: Based on the provided excerpts, the exact incorporation locations of TCS subsidiaries other than Tata America International Corporation are not fully detailed by country beyond a general listing of subsidiary names (such as TECHNOTHROUGH or others listed in the report); therefore, the excerpts do not contain a complete list of which specific subsidiaries are incorporated in the USA other than Tata America International Corporation [Tata Consultancy Services Limited, pp. 2, 55, 233].
  - Items extracted: (none)

### t089 (none_or_unanswerable): Which subsidiaries does Tata Steel name individually in its related-party transactions note?

- Gold: none
- graph [baseline; score 0.00]: Based on the provided excerpts, the reports do not contain a specific list naming individual subsidiaries within the notes on related-party transactions (Note 42), which instead aggregates transactions by category (associates, joint ventures, and Tata Sons Private Limited, its subsidiaries and joint ventures) [Tata Steel Limited, p. 539-540]. However, the report excerpts do mention specific related-party transactions involving named subsidiaries in other sections, such as Tata Steel UK Limited (TSUK) transacting with Tata International West Asia DMCC (TIWA) [Tata Steel Limited, p. 559-560], and Tata Steel Downstream Products Limited transacting with Tata Motors Limited [Tata Steel Limited, p. 240-241].
  - Cypher: `MATCH p1 = (s:Company)-[:SUBSIDIARY_OF]->(:Company {uid: 'L27100MH1907PLC000260'}) MATCH p2 = (:Company {uid: 'L27100MH1907PLC000260'})-[t:RELATED_PARTY_TXN]->(s) RETURN DISTINCT s.name, collect(t.nature) AS natures, collect(p1)[0] AS p1, collect(p2) AS p2 LIMIT 100`
  - Items extracted: Tata Steel UK Limited (TSUK) \|\| Tata International West Asia DMCC (TIWA) \|\| Tata Steel Downstream Products Limited \|\| Tata Motors Limited
- baseline [baseline; score 0.00]: Based on the provided excerpts, the reports do not contain a specific list naming individual subsidiaries within the notes on related-party transactions (Note 42), which instead aggregates transactions by category (associates, joint ventures, and Tata Sons Private Limited, its subsidiaries and joint ventures) [Tata Steel Limited, p. 539-540]. However, the report excerpts do mention specific related-party transactions involving named subsidiaries in other sections, such as Tata Steel UK Limited (TSUK) transacting with Tata International West Asia DMCC (TIWA) [Tata Steel Limited, p. 559-560], and Tata Steel Downstream Products Limited transacting with Tata Motors Limited [Tata Steel Limited, p. 240-241].
  - Items extracted: Tata Steel UK Limited (TSUK) \|\| Tata International West Asia DMCC (TIWA) \|\| Tata Steel Downstream Products Limited \|\| Tata Motors Limited

### t090 (none_or_unanswerable): Which of Tata Motors' subsidiaries in its Form AOC-1 does it hold less than 50% of?

- Gold: none
- graph [baseline; score 1.00]: Based on Form AOC-1 in the report excerpts, Tata Motors holds 55.39% of Tata Technologies Ltd. (which is greater than 50%) [Tata Motors Limited, p. 476]. None of the other listed subsidiaries in Part A of Form AOC-1 show a shareholding of less than 50% (TML Business Services Limited, TMF Business Services Limited, Tata Motors Insurance Broking & Advisory Services Ltd., and TMF Holdings Ltd. are all held at 100%) [Tata Motors Limited, pp. 476-477]. Therefore, the provided excerpts do not contain any subsidiary in Form AOC-1 in which Tata Motors holds less than 50%.
  - Cypher: `MATCH p = (s:Company)-[r:SUBSIDIARY_OF]->(c:Company {uid: 'L28920MH1945PLC004520'}) WHERE r.stake_pct IS NOT NULL AND toFloat(replace(toString(r.stake_pct), '%', '')) < 50 RETURN s.name, r.stake_pct, p LIMIT 100`
  - Items extracted: (none)
- baseline [baseline; score 1.00]: Based on Form AOC-1 in the report excerpts, Tata Motors holds 55.39% of Tata Technologies Ltd. (which is greater than 50%) [Tata Motors Limited, p. 476]. None of the other listed subsidiaries in Part A of Form AOC-1 show a shareholding of less than 50% (TML Business Services Limited, TMF Business Services Limited, Tata Motors Insurance Broking & Advisory Services Ltd., and TMF Holdings Ltd. are all held at 100%) [Tata Motors Limited, pp. 476-477]. Therefore, the provided excerpts do not contain any subsidiary in Form AOC-1 in which Tata Motors holds less than 50%.
  - Items extracted: (none)

### t091 (1hop): Who audits Jaguar Land Rover Automotive plc?

- Gold: KPMG (appointed September 11, 2017)
- graph [baseline; score 1.00]: Based on the provided excerpts, Jaguar Land Rover Automotive Plc is audited by KPMG [Tata Motors Limited, pp. 258-259].
  - Items extracted: KPMG
- baseline [baseline; score 1.00]: Based on the provided excerpts, Jaguar Land Rover Automotive Plc is audited by KPMG [Tata Motors Limited, pp. 258-259].
  - Items extracted: KPMG

### t092 (none_or_unanswerable): Who is the statutory auditor of Infosys BPM Limited?

- Gold: unanswerable
- graph [baseline; score 1.00]: Based on the provided excerpts, the answer to your question is not mentioned.
  - Items extracted: (none)
- baseline [baseline; score 1.00]: Based on the provided excerpts, the answer to your question is not mentioned.
  - Items extracted: (none)

### t093 (none_or_unanswerable): What is the CIN of Tata Consultancy Services Japan, Ltd.?

- Gold: unanswerable
- graph [graph; score 1.00]: The provided query results do not contain the CIN of Tata Consultancy Services Japan, Ltd.
  - Cypher: `MATCH p = (c:Company {uid: 'C-000057'}) RETURN c.name, c.uid, p LIMIT 100`
  - Items extracted: (none)
- baseline [baseline; score 1.00]: The provided excerpts do not contain the Corporate Identification Number (CIN) for Tata Consultancy Services Japan, Ltd.
  - Items extracted: (none)

### t094 (none_or_unanswerable): What was Tata Steel's revenue from operations in FY2025?

- Gold: unanswerable
- graph [baseline; score 1.00]: The provided excerpts do not contain information about Tata Steel's revenue from operations in FY2025.
  - Items extracted: (none)
- baseline [baseline; score 1.00]: The provided excerpts do not contain information about Tata Steel's revenue from operations in FY2025.
  - Items extracted: (none)

### t095 (none_or_unanswerable): Who was Tata Consumer Products' Company Secretary on March 31, 2024?

- Gold: The report names no successor; the previous Company Secretary, Neelabja Chakrabarty, resigned on February 7, 2024.
- graph [graph; score 0.00]: Neelabja Chakrabarty was the Company Secretary of Tata Consumer Products Limited, with a ceased status on February 07, 2024.
  - Cypher: `MATCH p = (person:Person)-[k:KMP_OF {role: 'Company Secretary'}]->(:Company {uid: 'L15491WB1962PLC031425'}) WHERE coalesce(k.after_fy_end, false) = false RETURN person.name, k.status, k.appointed_on, k.ceased_on, p LIMIT 100`
  - Items extracted: Neelabja Chakrabarty: Company Secretary of Tata Consumer Products Limited, with a ceased status on February 07, 2024
- baseline [baseline; score 1.00]: Based on the provided reports, the excerpts do not state who the Company Secretary of Tata Consumer Products was on March 31, 2024 [Tata Consumer Products Limited, pp. 248-251, 314-316, 526-527]. However, the records mention that Mr. Neelabja Chakrabarty resigned from the position of Company Secretary and Compliance Officer with effect from February 7, 2024 [Tata Consumer Products Limited, pp. 248-251].
  - Items extracted: (none)
