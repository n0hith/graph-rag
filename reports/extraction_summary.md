# Extraction summary

Generated 2026-10-21 from code at commit `a496152`. Raw facts are in `data/extracted/` (gitignored); this file is the tracked record.

## Facts per company

| Company | auditor | director | kmp | other_directorship | related_party | subsidiary | total | LLM calls (last run) |
|---|---|---|---|---|---|---|---|---|
| TCS | 2 LLM | 11 table | 5 LLM | 20 table | 52 LLM | 52 table | 142 | 10 |
| TATAMOTORS | 2 LLM | 10 LLM | 3 LLM | 21 LLM | 57 LLM | 90 LLM | 183 | 19 |
| TATASTEEL | 2 LLM | 11 LLM | 6 LLM | 21 LLM | 76 LLM | 129 LLM | 245 | 22 |
| TATACONSUM | 2 LLM | 10 LLM | 7 LLM | 17 LLM | 67 LLM | 40 LLM | 143 | 20 |
| INFY | 2 LLM | 10 LLM | 4 LLM | 0 | 307 LLM | 91 LLM | 414 | 27 |

## Completeness (counted independently from the section text)

Subsidiaries: numbered AOC-1 Part A rows vs extracted, with each extracted name located in its row. Directors: the certificate of non-disqualification (board on March 31) vs extracted; every extracted director not on it must have ceased during the year or joined after it.

| Company | AOC-1 rows | Subsidiaries extracted | Rows missing | Extras | Certificate | Directors extracted | On certificate | Ceased in FY | After FY end | Unexplained | Certificate not extracted | No DIN |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TCS | 52 | 52 | 0 | 0 | 9 | 11 | 9 | 2 | 0 | 0 | 0 | 0 |
| TATAMOTORS | 90 | 90 | 0 | 0 | 8 | 10 | 8 | 1 | 1 | 0 | 0 | 0 |
| TATASTEEL | 129 | 129 | 1 | 1 | 10 | 11 | 10 | 1 | 0 | 0 | 0 | 1 |
| TATACONSUM | 40 | 40 | 0 | 0 | 9 | 10 | 9 | 1 | 0 | 0 | 0 | 0 |
| INFY | 91 | 91 | 0 | 0 | 9 | 10 | 9 | 1 | 0 | 0 | 0 | 1 |

**TCS**

- ceased in FY: Rajesh Gopinathan (06365813), ceased June 1, 2023
- ceased in FY: Don Callahan (08326836), ceased January 10, 2024

**TATAMOTORS**

- ceased in FY: Mr Mitsuhiko Yamashita (08871753), ceased October 27, 2023
- appointed after FY end: Mr Bharat Puri (02173566), appointed May 15, 2024

**TATASTEEL**

- AOC-1 row 103 not extracted: Fischer Profil Produktions -und-
- extra subsidiary: Fischer Profil Produktions -und-Vertriebs - GmbH (p.265): not found verbatim
- ceased in FY: Mr. O. P. Bhatt (no DIN), ceased June 9, 2023
- director without DIN: Mr. O. P. Bhatt (no DIN)

**TATACONSUM**

- ceased in FY: Mr. Lakshmanan Krishna Kumar (00423616), ceased October 31, 2023

**INFY**

- ceased in FY: Uri Levine (no DIN), ceased April 19, 2023
- director without DIN: Uri Levine (no DIN)

## DIN conflicts

- TCS: **Al-Noor Ramji** DIN 00230865; conflict {'certificate_din': '08326836', 'certificate_page': 117}; resolution: 00230865 (3 mention(s) elsewhere in TCS's report; TATAMOTORS p.236)
- TCS: **Don Callahan** DIN 08326836; conflict {'certificate_name_for_this_din': 'Al-Noor Ramji', 'certificate_page': 117}; resolution: 08326836 (1 mention(s) elsewhere in TCS's report; no other pilot report lists this person)

## Cross-report directorships (check-directorships)

18 claims that a director sits on another pilot company's board: 18 match

- [match] TATACONSUM says N. Chandrasekaran (DIN 00121863) is on TATAMOTORS's board (Non-Executive, Non-Independent Director). TATAMOTORS lists 'Mr N Chandrasekaran' (DIN 00121863)
- [match] TATACONSUM says N. Chandrasekaran (DIN 00121863) is on TATASTEEL's board (Non-Executive, Non-Independent Director). TATASTEEL lists 'Mr. N. Chandrasekaran' (DIN 00121863)
- [match] TATACONSUM says N. Chandrasekaran (DIN 00121863) is on TCS's board (Non-Executive, Non-Independent Director). TCS lists 'N Chandrasekaran' (DIN 00121863); company name matched loosely ('Tata Consultancy Service Limited')
- [match] TATAMOTORS says Mr N Chandrasekaran (DIN 00121863) is on TATACONSUM's board (NINED). TATACONSUM lists 'N. Chandrasekaran' (DIN 00121863)
- [match] TATAMOTORS says Mr N Chandrasekaran (DIN 00121863) is on TATASTEEL's board (NINED). TATASTEEL lists 'Mr. N. Chandrasekaran' (DIN 00121863)
- [match] TATAMOTORS says Mr Al-Noor Ramji (DIN 00230865) is on TCS's board (ID). TCS lists 'Al-Noor Ramji' (DIN 00230865)
- [match] TATAMOTORS says Mr N Chandrasekaran (DIN 00121863) is on TCS's board (NINED). TCS lists 'N Chandrasekaran' (DIN 00121863)
- [match] TATAMOTORS says Mr O P Bhatt (DIN 00548091) is on TCS's board (ID). TCS lists 'O P Bhatt' (DIN 00548091)
- [match] TATAMOTORS says Ms Hanne Sorensen (DIN 08035439) is on TCS's board (ID). TCS lists 'Hanne Sorensen' (DIN 08035439)
- [match] TATASTEEL says Mr. N. Chandrasekaran (DIN 00121863) is on TATACONSUM's board (Non-Executive, Non-Independent, Chairman). TATACONSUM lists 'N. Chandrasekaran' (DIN 00121863)
- [match] TATASTEEL says Mr. N. Chandrasekaran (DIN 00121863) is on TATAMOTORS's board (Non-Executive, Non-Independent, Chairman). TATAMOTORS lists 'Mr N Chandrasekaran' (DIN 00121863)
- [match] TATASTEEL says Mr. N. Chandrasekaran (DIN 00121863) is on TCS's board (Non-Executive, Non-Independent, Chairman). TCS lists 'N Chandrasekaran' (DIN 00121863)
- [match] TCS says N Chandrasekaran (DIN 00121863) is on TATACONSUM's board (Non-Independent, Non-Executive Director). TATACONSUM lists 'N. Chandrasekaran' (DIN 00121863)
- [match] TCS says Al-Noor Ramji (DIN 00230865) is on TATAMOTORS's board (Independent, Non-Executive Director). TATAMOTORS lists 'Mr Al-Noor Ramji' (DIN 00230865)
- [match] TCS says Hanne Sorensen (DIN 08035439) is on TATAMOTORS's board (Independent, Non-Executive Director). TATAMOTORS lists 'Ms Hanne Sorensen' (DIN 08035439)
- [match] TCS says N Chandrasekaran (DIN 00121863) is on TATAMOTORS's board (Non-Independent, Non-Executive Director). TATAMOTORS lists 'Mr N Chandrasekaran' (DIN 00121863)
- [match] TCS says O P Bhatt (DIN 00548091) is on TATAMOTORS's board (Independent, Non-Executive Director). TATAMOTORS lists 'Mr O P Bhatt' (DIN 00548091)
- [match] TCS says N Chandrasekaran (DIN 00121863) is on TATASTEEL's board (Non-Independent, Non-Executive Director). TATASTEEL lists 'Mr. N. Chandrasekaran' (DIN 00121863)

## Run details per company

### TCS

Dropped: 1 (1× evidence not found in source text)
- [related_party] evidence not found in source text: "Tata ConsultancyServices Deutschland GmbH\n 3,593"

Director checks:
- DIN conflict: Al-Noor Ramji 00230865 vs certificate {'certificate_din': '08326836', 'certificate_page': 117}
- DIN conflict: Don Callahan 08326836 vs certificate {'certificate_name_for_this_din': 'Al-Noor Ramji', 'certificate_page': 117}

Regressions / key-field changes vs previous run:
- related_party / related_party: new run found 13, previous run 52; kept the previous facts

### TATAMOTORS

Dropped: 8 (1× evidence not found in source text; 6× in a summary block repeating rows listed above it; 1× not on an FY2024 board/attendance table or certificate)
- [kmp] evidence not found in source text: "Mr P B Balaji\nChief Financial Officer"
- [subsidiary] in a summary block repeating rows listed above it: "Tata Technologies Limited"
- [subsidiary] in a summary block repeating rows listed above it: "Tata Motors Finance Holding Ltd"
- [subsidiary] in a summary block repeating rows listed above it: "TML Holdings Pte. Limited Singapore**"
- [subsidiary] in a summary block repeating rows listed above it: "Jaguar \nLand \nRover \nAutomotive \nPlc"
- … 3 more (see data/extracted/<SYMBOL>.run.json)

Merges:
- DIN filled from certificate: Mr N Chandrasekaran -> 00121863 (p.264)
- DIN filled from certificate: Mr Om Prakash Bhatt -> 00548091 (p.264)
- DIN filled from certificate: Ms Hanne Sorensen -> 08035439 (p.264)
- DIN filled from certificate: Ms Vedika Bhandarkar -> 00033808 (p.264)
- DIN filled from certificate: Mr K V Chowdary -> 08485334 (p.264)
- DIN filled from certificate: Mr Al-Noor Ramji -> 00230865 (p.264)
- DIN filled from certificate: Mrs Usha Sangwan -> 02609263 (p.264)
- 'Mr N Chandrasekaran' (p.242) -> 'Mr N Chandrasekaran' (same DIN 00121863)
- 'Mr Om Prakash Bhatt' (p.242) -> 'Mr O P Bhatt' (same DIN 00548091)
- 'Ms Hanne Sorensen' (p.242) -> 'Ms Hanne Sorensen' (same DIN 08035439)
- 'Ms Vedika Bhandarkar' (p.242) -> 'Ms Vedika Bhandarkar' (same DIN 00033808)
- 'Mr K V Chowdary' (p.242) -> 'Mr K V Chowdary' (same DIN 08485334)
- … 4 more (see data/extracted/<SYMBOL>.run.json)

Director checks:
- appointed_on from certificate: Mrs Usha Sangwan 15/05/2023 (p.264)
- ceased_on from text: Mr Mitsuhiko Yamashita October 27, 2023
- appointed_on from text: Mr Bharat Puri May 15, 2024
- not an FY2024 director (no board/attendance/certificate mention): Mr Guenter Butschek 07427375 p.248

Regressions / key-field changes vs previous run:
- related_party / related_party: new run found 47, previous run 57; kept the previous facts

### TATASTEEL

Dropped: 0

Director checks:
- appointed_on from certificate: Dr. Shekhar C. Mande June 1, 2023 (p.261)
- ceased_on from text: Mr. O. P. Bhatt June 9, 2023

Regressions / key-field changes vs previous run:
- related_party / related_party: new run found 47, previous run 76; kept the previous facts

### TATACONSUM

Dropped: 0

Merges:
- 'N. Chandrasekaran' (p.289, no DIN) -> 'N. Chandrasekaran' (DIN 00121863, p.284)
- 'K. P. Krishnan' (p.289, no DIN) -> 'K. P. Krishnan' (DIN 01099097, p.284)
- 'Siraj Chaudhry' (p.289, no DIN) -> 'Siraj Chaudhry' (DIN 00161853, p.284)
- 'Bharat Puri' (p.289, no DIN) -> 'Bharat Puri' (DIN 02173566, p.284)
- 'Shikha Sharma' (p.289, no DIN) -> 'Shikha Sharma' (DIN 00043265, p.284)
- 'P. B. Balaji' (p.289, no DIN) -> 'P. B. Balaji' (DIN 02762983, p.284)
- 'David Crean' (p.289, no DIN) -> 'David Crean' (DIN 09584874, p.284)
- 'Sunil D’Souza' (p.289, no DIN) -> 'Sunil D’Souza' (DIN 07194259, p.284)
- 'Ajit Krishnakumar' (p.289, no DIN) -> 'Ajit Krishnakumar' (DIN 08002754, p.284)
- 'L Krishnakumar' (p.295, no DIN) -> 'L. Krishnakumar' (DIN none, p.289)
- override: 'L. Krishnakumar' (p.289, DIN none) -> 'Mr. Lakshmanan Krishna Kumar' (DIN 00423616) [Same person as Mr. Lakshmanan Krishna Kumar (DIN 00423616, p.317), retired as Executive Director. Confirmed by user 2026-10-21.]

Director checks:
- ceased_on from text: Mr. Lakshmanan Krishna Kumar October 31, 2023

Regressions / key-field changes vs previous run:
- kmp neelabja chakrabarty / Company Secretary: ceased_on was 'February 07, 2024', now empty
- kmp / corporate_governance: new run found 5, previous run 7; kept the previous facts
- related_party / related_party: new run found 55, previous run 67; kept the previous facts
- auditor / secretarial_audit: new run found 0, previous run 1; kept the previous facts

### INFY

Dropped: 0

Merges:
- DIN filled from certificate: D. Sundaram -> 00016304 (p.118)
- DIN filled from certificate: Nitin Paranjpe -> 00045204 (p.118)
- DIN filled from certificate: Michael Gibbs -> 08177291 (p.118)
- DIN filled from certificate: Bobby Parikh -> 00019437 (p.118)
- DIN filled from certificate: Chitra Nayak -> 09101763 (p.118)
- DIN filled from certificate: Govind Iyer -> 00169343 (p.118)
- DIN filled from certificate: Helene Auriol Potier -> 10166891 (p.118)
- DIN filled from certificate: Nandan M. Nilekani -> 00041245 (p.118)
- DIN filled from certificate: Salil Parekh -> 01876159 (p.118)
- 'Bobby Parikh' (p.88) -> 'Bobby Parikh' (same DIN 00019437)
- 'D. Sundaram' (p.92) -> 'D. Sundaram' (same DIN 00016304)
- 'Govind Iyer' (p.94) -> 'Govind Iyer' (same DIN 00169343)
- … 5 more (see data/extracted/<SYMBOL>.run.json)

Director checks:
- appointed_on from certificate: Nitin Paranjpe January 01, 2024 (p.118)
- appointed_on from certificate: Helene Auriol Potier May 26, 2023 (p.118)
- ceased_on from text: Uri Levine April 19, 2023

Regressions / key-field changes vs previous run:
- director helene auriol potier: appointed_on was 'April 19, 2023', now 'May 26, 2023'
- related_party / related_party: new run found 234, previous run 307; kept the previous facts

## Known gaps

- Related-party facts in this run are the PREVIOUS run's (commit 7b2dd6c prompt, 2 pages per call): the new prompt requiring the amount inside the quote returned fewer items for every company (TCS 13 vs 52, Tata Motors 47 vs 57, Tata Steel 47 vs 76, Tata Consumer 55 vs 67, Infosys 234 vs 307), so the regression guard kept the previous facts. Their amounts are not tied to the quote by code; the 50-fact sample weights them heavily.
- Infosys p.254: the table at the top of the page continues 'Unbilled revenues' from p.253, which falls in the previous 2-page call, so 8 parties got a second 'Trade payables' fact holding their unbilled-revenues balance (all FY2024-column figures; the genuine trade payable is the other fact of each pair).
- Tata Consumer secretarial auditor (Dr. Asim Kumar Chattopadhyay, individual) and Tata Consumer KMP (7) are kept from the previous run: the latest prompts returned 0 auditors and 5 KMP.
- Directors without a DIN in their own governance section: Uri Levine (Infosys; DIN 08733837 is printed on p.51, Board's report) and O. P. Bhatt (Tata Steel; DIN 00548091 printed on p.177). The extractor only reads the governance section, so these stay empty.
- TCS's certificate (p.117) gives Al-Noor Ramji DIN 08326836, which is Don Callahan's DIN everywhere else in TCS's report; TCS's other pages and Tata Motors (pp.236, 248, 264) all print Ramji as 00230865. Recorded as din_conflict + din_resolution, both DINs kept.
- Tata Steel AOC-1 row 103 shows as 1 missing + 1 extra only because the text breaks the name across lines ('-und-' / 'Vertriebs'); it is the same subsidiary, extracted once. Tata Steel is 129/129.
- Table cells (not page text) still carry rupee-font stand-in letters and, on Tata Steel p.249/409 and Infosys p.114, a missing first letter; no fact is read from those cells.
