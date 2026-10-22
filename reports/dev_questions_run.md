# Practice questions run (Phase 6 development set)

Code at commit `be39d9e`. 16 of 16 passed. These questions are for building and tuning only and must not be reused in the Phase 7 test set.

| id | category | question | route | correct | what went wrong |
|---|---|---|---|---|---|
| dev01 | 1hop | Who is the statutory auditor of Tata Steel? | graph | yes |  |
| dev02 | 1hop | Who are the directors of Tata Consumer Products? | graph | yes |  |
| dev03 | 1hop | Who is the CEO of TCS? | graph | yes |  |
| dev04 | 1hop | What is N Chandrasekaran's DIN? | graph | yes |  |
| dev05 | 2hop | Which directors of TaMo also sit on the board of TCS? | graph | yes |  |
| dev06 | 2hop | Which pilot companies share the same statutory auditor? | graph | yes |  |
| dev07 | 2hop | Which subsidiaries of Tata Motors are also related parties of TCS? | graph | yes |  |
| dev08 | 2hop | On which pilot company's board does the CFO of Tata Motors sit? | graph | yes |  |
| dev09 | 3hop | Which audit firms are the statutory auditors of the other pilot companies whose boards include a director of Tata Steel? | graph | yes |  |
| dev10 | 3hop | Which companies are connected to both Tata Motors and TCS within two steps? | graph | yes |  |
| dev11 | aggregation | How many subsidiaries does Tata Steel list in its Form AOC-1? | graph | yes |  |
| dev12 | aggregation | Which pilot company lists the most subsidiaries? | graph | yes |  |
| dev13 | aggregation | How many directors were on Infosys's board in FY2024? | graph | yes |  |
| dev14 | text_only | How many employees did TCS have on March 31, 2024? | baseline | yes |  |
| dev15 | text_only | What dividend per share did Tata Steel's board recommend for FY2024? | baseline | yes |  |
| dev16 | 1hop | What role does Krishnakumar hold at Tata Consumer? | clarify | yes |  |

## Answers

### dev01: Who is the statutory auditor of Tata Steel?

- Route: graph (passed)
- Answer: The statutory auditor of Tata Steel Limited is Price Waterhouse & Co Chartered Accountants LLP.
- Cypher: `MATCH p = (c:Company {uid: 'L27100MH1907PLC000260'})-[a:AUDITED_BY {audit_type: 'statutory'}]->(f:AuditFirm) RETURN f.name, f.firm_registration_no, p LIMIT 100`
- Paths (1): Tata Steel Limited -[AUDITED_BY]-> Price Waterhouse & Co Chartered Accountants LLP
- Sources: TATASTEEL.pdf p.299
- Notes: 'Tata Steel' -> Tata Steel Limited (pilot company name (TATASTEEL)); LIMIT added by the guard

### dev02: Who are the directors of Tata Consumer Products?

- Route: graph (passed)
- Answer: The directors of Tata Consumer Products Limited are: - P. B. Balaji (Non-Executive, Non Independent Director) - Siraj Chaudhry (Independent Director) - K. P. Krishnan (Independent Director) - N. Chandrasekaran (Chairman) - David Crean (Independent Director) - Ajit Krishnakumar (Executive Director & Chief Operating Officer) - Bharat Puri (Independent Director) - Sunil D’Souza (Managing Director & Chief Executive Officer) - Shikha Sharma (Independent Director)
- Cypher: `MATCH p = (person:Person)-[d:DIRECTOR_OF]->(c:Company {uid: 'L15491WB1962PLC031425'}) WHERE d.own_report AND d.status = 'current' AND coalesce(d.after_fy_end, false) = false RETURN person.name, person.din, d.roles, d.is_independent, d.is_executive, p LIMIT 100`
- Paths (9): P. B. Balaji -[DIRECTOR_OF]-> Tata Consumer Products Limited; Siraj Chaudhry -[DIRECTOR_OF]-> Tata Consumer Products Limited; K. P. Krishnan -[DIRECTOR_OF]-> Tata Consumer Products Limited; N. Chandrasekaran -[DIRECTOR_OF]-> Tata Consumer Products Limited; David Crean -[DIRECTOR_OF]-> Tata Consumer Products Limited ...
- Sources: TATACONSUM.pdf p.284; TCS.pdf p.98; TATAMOTORS.pdf p.236; TATASTEEL.pdf p.230
- Notes: 'Tata Consumer Products' -> Tata Consumer Products Limited (pilot company name (TATACONSUM)); LIMIT added by the guard

### dev03: Who is the CEO of TCS?

- Route: graph (passed)
- Answer: The CEOs of Tata Consultancy Services Limited are Rajesh Gopinathan (ceased on June 1, 2023) and K Krithivasan (current, appointed on June 1, 2023).
- Cypher: `MATCH p = (person:Person)-[k:KMP_OF {role: 'CEO'}]->(:Company {uid: 'L22210MH1995PLC084781'}) RETURN person.name, k.status, k.appointed_on, k.ceased_on, p LIMIT 100`
- Paths (2): Rajesh Gopinathan -[KMP_OF]-> Tata Consultancy Services Limited; K Krithivasan -[KMP_OF]-> Tata Consultancy Services Limited
- Sources: TCS.pdf p.98; TCS.pdf p.115
- Notes: 'TCS' -> Tata Consultancy Services Limited (pilot company name (TCS)); LIMIT added by the guard

### dev04: What is N Chandrasekaran's DIN?

- Route: graph (passed)
- Answer: N Chandrasekaran's DIN is 00121863.
- Cypher: `MATCH p = (person:Person {uid: '00121863'}) RETURN person.name, person.uid AS din, p LIMIT 100`
- Paths (1): N. Chandrasekaran
- Notes: 'N Chandrasekaran' -> N. Chandrasekaran (same name); LIMIT added by the guard

### dev05: Which directors of TaMo also sit on the board of TCS?

- Route: graph (passed)
- Answer: Hanne Sorensen, Al-Noor Ramji, O P Bhatt, and N. Chandrasekaran.
- Cypher: `MATCH p1 = (person:Person)-[d1:DIRECTOR_OF]->(:Company {uid: 'L28920MH1945PLC004520'}) MATCH p2 = (person)-[d2:DIRECTOR_OF]->(:Company {uid: 'L22210MH1995PLC084781'}) WHERE d1.own_report AND d1.status = 'current' AND coalesce(d1.after_fy_end, false) = false AND d2.own_report AND d2.status = 'current' AND coalesce(d2.after_fy_end, false) = false RETURN person.name, person.din, collect(p1)[0] AS p1, collect(p2)[0] AS p2 LIMIT 100`
- Paths (8): Hanne Sorensen -[DIRECTOR_OF]-> Tata Motors Limited; Hanne Sorensen -[DIRECTOR_OF]-> Tata Consultancy Services Limited; Al-Noor Ramji -[DIRECTOR_OF]-> Tata Motors Limited; Al-Noor Ramji -[DIRECTOR_OF]-> Tata Consultancy Services Limited; O P Bhatt -[DIRECTOR_OF]-> Tata Motors Limited ...
- Sources: TCS.pdf p.98; TATAMOTORS.pdf p.236; TATASTEEL.pdf p.230; TATACONSUM.pdf p.289
- Notes: 'TaMo' -> Tata Motors Limited (pilot company name (TATAMOTORS)); 'TCS' -> Tata Consultancy Services Limited (pilot company name (TCS)); LIMIT added by the guard

### dev06: Which pilot companies share the same statutory auditor?

- Route: graph (passed)
- Answer: The pilot companies that share the same statutory auditor are: * **Deloitte Haskins & Sells LLP**: Tata Consumer Products Limited and Infosys Limited * **B S R & Co. LLP**: Tata Consultancy Services Limited and Tata Motors Limited
- Cypher: `MATCH p1 = (c1:Company)-[a1:AUDITED_BY {audit_type: 'statutory'}]->(f:AuditFirm)<-[a2:AUDITED_BY {audit_type: 'statutory'}]-(c2:Company) WHERE c1.nse_symbol IS NOT NULL AND c2.nse_symbol IS NOT NULL AND c1.uid < c2.uid RETURN f.name AS auditor, c1.name AS company1, c2.name AS company2, [p1] AS paths LIMIT 100`
- Paths (2): Tata Consumer Products Limited -[AUDITED_BY]-> Deloitte Haskins & Sells LLP <-[AUDITED_BY]- Infosys Limited; Tata Consultancy Services Limited -[AUDITED_BY]-> B S R & Co. LLP <-[AUDITED_BY]- Tata Motors Limited
- Sources: TATACONSUM.pdf p.374; INFY.pdf p.184; TCS.pdf p.245; TATAMOTORS.pdf p.391
- Notes: LIMIT added by the guard

### dev07: Which subsidiaries of Tata Motors are also related parties of TCS?

- Route: graph (passed)
- Answer: Jaguar Land Rover Limited.
- Cypher: `MATCH p1 = (s:Company)-[:SUBSIDIARY_OF]->(:Company {uid: 'L28920MH1945PLC004520'}) MATCH p2 = (:Company {uid: 'L22210MH1995PLC084781'})-[t:RELATED_PARTY_TXN]->(s) RETURN DISTINCT s.name, collect(t.nature) AS natures, collect(p1)[0] AS p1, collect(p2) AS p2 LIMIT 100`
- Paths (2): Jaguar Land Rover Limited -[SUBSIDIARY_OF]-> Tata Motors Limited; Tata Consultancy Services Limited -[RELATED_PARTY_TXN]-> Jaguar Land Rover Limited
- Sources: TATAMOTORS.pdf p.477; TCS.pdf p.302
- Notes: 'Tata Motors' -> Tata Motors Limited (pilot company name (TATAMOTORS)); 'TCS' -> Tata Consultancy Services Limited (pilot company name (TCS)); LIMIT added by the guard

### dev08: On which pilot company's board does the CFO of Tata Motors sit?

- Route: graph (passed)
- Answer: Tata Consumer Products Limited.
- Cypher: `MATCH p1 = (cfo:Person)-[:KMP_OF {role: 'CFO'}]->(:Company {uid: 'L28920MH1945PLC004520'}) MATCH p2 = (cfo)-[d:DIRECTOR_OF]->(target:Company) WHERE target.nse_symbol IS NOT NULL AND d.own_report AND d.status = 'current' AND coalesce(d.after_fy_end, false) = false RETURN target.name, target.nse_symbol, collect(p1)[0] AS p1, collect(p2)[0] AS p2 LIMIT 100`
- Paths (2): P. B. Balaji -[KMP_OF]-> Tata Motors Limited; P. B. Balaji -[DIRECTOR_OF]-> Tata Consumer Products Limited
- Sources: TATAMOTORS.pdf p.262; TATACONSUM.pdf p.284
- Notes: 'Tata Motors' -> Tata Motors Limited (pilot company name (TATAMOTORS)); LIMIT added by the guard

### dev09: Which audit firms are the statutory auditors of the other pilot companies whose boards include a director of Tata Steel?

- Route: graph (passed)
- Answer: The statutory auditors of the other pilot companies are B S R & Co. LLP (for Tata Motors Limited and Tata Consultancy Services Limited) and Deloitte Haskins & Sells LLP (for Tata Consumer Products Limited).
- Cypher: `MATCH p1 = (:Company {uid: 'L27100MH1907PLC000260'})<-[d1:DIRECTOR_OF]-(person:Person)-[d2:DIRECTOR_OF]->(other:Company) WHERE other.nse_symbol IS NOT NULL AND other.uid <> 'L27100MH1907PLC000260' AND d1.own_report AND d1.status = 'current' AND coalesce(d1.after_fy_end, false) = false AND d2.own_report AND d2.status = 'current' AND coalesce(d2.after_fy_end, false) = false MATCH p2 = (other)-[a:AUDITED_BY {audit_type: 'statutory'}]->(f:AuditFirm) RETURN DISTINCT f.name, f.firm_registration_no, other.name, person.name, collect(p1)[0] AS p1, collect(p2)[0] AS p2 LIMIT 100`
- Paths (6): Tata Steel Limited <-[DIRECTOR_OF]- N. Chandrasekaran -[DIRECTOR_OF]-> Tata Motors Limited; Tata Motors Limited -[AUDITED_BY]-> B S R & Co. LLP; Tata Steel Limited <-[DIRECTOR_OF]- N. Chandrasekaran -[DIRECTOR_OF]-> Tata Consumer Products Limited; Tata Consumer Products Limited -[AUDITED_BY]-> Deloitte Haskins & Sells LLP; Tata Steel Limited <-[DIRECTOR_OF]- N. Chandrasekaran -[DIRECTOR_OF]-> Tata Consultancy Services Limited ...
- Sources: TCS.pdf p.98; TATAMOTORS.pdf p.236; TATASTEEL.pdf p.230; TATACONSUM.pdf p.289; TATAMOTORS.pdf p.391; TATACONSUM.pdf p.284; TATACONSUM.pdf p.374; TCS.pdf p.245
- Notes: 'Tata Steel' -> Tata Steel Limited (pilot company name (TATASTEEL)); attempt 1 failed: the query ran but returned no rows; check relationship directions and filters; LIMIT added by the guard

### dev10: Which companies are connected to both Tata Motors and TCS within two steps?

- Route: graph (passed)
- Answer: The companies connected to both Tata Motors and TCS within two steps are: 1. Tata Steel Limited 2. Tata Chemicals Limited 3. Tata Consumer Products Limited 4. The Indian Hotels Company Limited 5. The Tata Power Company Limited 6. Hindustan Unilever Limited 7. Aadhar Housing Finance Limited 8. Torrent Power Limited 9. Tata Sons Private Limited 10. Jaguar Land Rover Limited
- Cypher: `MATCH (tm:Company {uid: 'L28920MH1945PLC004520'}) MATCH (tcs:Company {uid: 'L22210MH1995PLC084781'}) MATCH p1 = (c:Company)-[:SUBSIDIARY_OF|MERGED_INTO|DIRECTOR_OF|KMP_OF|RELATED_PARTY_TXN|GROUP_OF*1..2]-(tm) MATCH p2 = (c)-[:SUBSIDIARY_OF|MERGED_INTO|DIRECTOR_OF|KMP_OF|RELATED_PARTY_TXN|GROUP_OF*1..2]-(tcs) WHERE c <> tm AND c <> tcs WITH c, collect(p1)[0] AS p1, collect(p2)[0] AS p2 RETURN c.name, p1, p2 LIMIT 100`
- Paths (20): Tata Steel Limited <-[DIRECTOR_OF]- O P Bhatt -[DIRECTOR_OF]-> Tata Motors Limited; Tata Steel Limited <-[DIRECTOR_OF]- N. Chandrasekaran -[DIRECTOR_OF]-> Tata Consultancy Services Limited; Tata Chemicals Limited <-[DIRECTOR_OF]- N. Chandrasekaran -[DIRECTOR_OF]-> Tata Motors Limited; Tata Chemicals Limited <-[DIRECTOR_OF]- N. Chandrasekaran -[DIRECTOR_OF]-> Tata Consultancy Services Limited; Tata Consumer Products Limited <-[DIRECTOR_OF]- P. B. Balaji -[KMP_OF]-> Tata Motors Limited ...
- Sources: TATASTEEL.pdf p.230; TCS.pdf p.98; TATAMOTORS.pdf p.236; TATACONSUM.pdf p.289; TATACONSUM.pdf p.284; TATAMOTORS.pdf p.262; TATAMOTORS.pdf p.464; TCS.pdf p.299
- Notes: 'Tata Motors' -> Tata Motors Limited (pilot company name (TATAMOTORS)); 'TCS' -> Tata Consultancy Services Limited (pilot company name (TCS)); LIMIT added by the guard

### dev11: How many subsidiaries does Tata Steel list in its Form AOC-1?

- Route: graph (passed)
- Answer: Tata Steel lists 129 subsidiaries.
- Cypher: `MATCH p = (s:Company)-[:SUBSIDIARY_OF]->(:Company {uid: 'L27100MH1907PLC000260'}) RETURN count(s) AS subsidiaries, collect(p)[..50] AS paths LIMIT 100`
- Paths (50): Tata Steel Nederland Technology BV -[SUBSIDIARY_OF]-> Tata Steel Limited; Tata Steel UK Consulting Limited -[SUBSIDIARY_OF]-> Tata Steel Limited; Runblast Limited -[SUBSIDIARY_OF]-> Tata Steel Limited; Tata Steel Belgium Packaging Steels N.V. -[SUBSIDIARY_OF]-> Tata Steel Limited; Corus International (Overseas Holdings) Limited -[SUBSIDIARY_OF]-> Tata Steel Limited ...
- Sources: TATASTEEL.pdf p.265; TATASTEEL.pdf p.264; TATASTEEL.pdf p.266; TATASTEEL.pdf p.263
- Notes: 'Tata Steel' -> Tata Steel Limited (pilot company name (TATASTEEL)); LIMIT added by the guard

### dev12: Which pilot company lists the most subsidiaries?

- Route: graph (passed)
- Answer: Tata Steel Limited lists the most subsidiaries, with a count of 129.
- Cypher: `MATCH p = (s:Company)-[:SUBSIDIARY_OF]->(c:Company) WHERE c.nse_symbol IS NOT NULL WITH c, count(s) AS subsidiary_count, collect(p) AS paths ORDER BY subsidiary_count DESC LIMIT 1 RETURN c.name, subsidiary_count, paths LIMIT 100`
- Paths (129): Tata Steel Nederland Technology BV -[SUBSIDIARY_OF]-> Tata Steel Limited; Tata Steel UK Consulting Limited -[SUBSIDIARY_OF]-> Tata Steel Limited; Runblast Limited -[SUBSIDIARY_OF]-> Tata Steel Limited; Tata Steel Belgium Packaging Steels N.V. -[SUBSIDIARY_OF]-> Tata Steel Limited; Corus International (Overseas Holdings) Limited -[SUBSIDIARY_OF]-> Tata Steel Limited ...
- Sources: TATASTEEL.pdf p.265; TATASTEEL.pdf p.264; TATASTEEL.pdf p.266; TATASTEEL.pdf p.263
- Notes: LIMIT added by the guard

### dev13: How many directors were on Infosys's board in FY2024?

- Route: graph (passed)
- Answer: There were 9 directors on Infosys's board: Helene Auriol Potier, Govind Iyer, D. Sundaram, Michael Gibbs, Salil Parekh, Chitra Nayak, Bobby Parikh, Nandan M. Nilekani, and Nitin Paranjpe.
- Cypher: `MATCH p = (person:Person)-[d:DIRECTOR_OF]->(:Company {uid: 'L85110KA1981PLC013115'}) WHERE d.own_report AND d.status = 'current' AND coalesce(d.after_fy_end, false) = false RETURN count(person) AS director_count, collect(p) AS paths LIMIT 100`
- Paths (9): Helene Auriol Potier -[DIRECTOR_OF]-> Infosys Limited; Govind Iyer -[DIRECTOR_OF]-> Infosys Limited; D. Sundaram -[DIRECTOR_OF]-> Infosys Limited; Michael Gibbs -[DIRECTOR_OF]-> Infosys Limited; Salil Parekh -[DIRECTOR_OF]-> Infosys Limited ...
- Sources: INFY.pdf p.82; INFY.pdf p.85
- Notes: 'Infosys' -> Infosys Limited (pilot company name (INFY)); LIMIT added by the guard

### dev14: How many employees did TCS have on March 31, 2024?

- Route: baseline (passed)
- Answer: Based on the provided reports, Tata Consultancy Services (TCS) had a total of 631,858 employees at the end of FY 2023-24 (March 31, 2024), comprising 601,546 permanent employees and 30,312 other-than-permanent employees [Tata Consultancy Services Limited, pp. 129-130].
- Sources: TCS.pdf pp.8-9; TCS.pdf pp.1-3; TCS.pdf pp.147-148; TCS.pdf pp.195-197; TCS.pdf pp.306-307; TCS.pdf pp.129-130
- Notes: 'TCS' -> Tata Consultancy Services Limited (pilot company name (TCS)); graph can't answer it: The graph database contains information about directors, KMPs, subsidiaries, audit firms, related-party transactions, and company linkages, but does not store employee headcount figures.

### dev15: What dividend per share did Tata Steel's board recommend for FY2024?

- Route: baseline (passed)
- Answer: Tata Steel's board recommended a dividend of ₹3.60 per Ordinary (equity) Share of face value of ₹1/- each for the Financial Year 2023-24 [Tata Steel Limited, pp. 156-157].
- Sources: TATASTEEL.pdf pp.292-293; TATASTEEL.pdf pp.156-157; TATAMOTORS.pdf p.136; TATAMOTORS.pdf p.318; TATASTEEL.pdf p.39
- Notes: 'Tata Steel' -> Tata Steel Limited (pilot company name (TATASTEEL)); graph can't answer it: Dividends and financial performance figures are prose and financial result details not stored as graph relationships or nodes in this schema.

### dev16: What role does Krishnakumar hold at Tata Consumer?

- Route: clarify (passed)
- Answer: 'Krishnakumar' matches several entries in the graph: Ajit Krishnakumar (Person, DIN 08002754, in TATACONSUM); Lakshmanan Krishna Kumar (Person, DIN 00423616, in TATACONSUM). Which one do you mean?
- Notes: stopped before writing Cypher: ambiguous name

## LLM usage

```
LLM usage (approximate):
  baseline.ask: 0 API calls, 2 from cache, 0 input tokens, 0 output tokens [answered by: gemini-3.5-flash-lite x2]
  qa.answer: 0 API calls, 13 from cache, 0 input tokens, 0 output tokens [answered by: gemini-3.5-flash-lite x13]
  qa.cypher: 0 API calls, 16 from cache, 0 input tokens, 0 output tokens [answered by: gemini-3.5-flash-lite x16]
  qa.entities: 0 API calls, 16 from cache, 0 input tokens, 0 output tokens [answered by: gemini-3.5-flash-lite x16]
```
