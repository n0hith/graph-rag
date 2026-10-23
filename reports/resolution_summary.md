# Entity resolution summary

Generated 2026-10-22 from code at commit `14080ac`. Resolved entities, relations, the merge log and the review list are in `data/resolved/` (gitignored).

## Before and after merging

Mentions: every place a fact names one (a director row, a KMP line, a subsidiary row, a related party, ...). Per-report names: distinct normalised names within one report. Entities: after merging across reports.

| Kind | Mentions | Per-report names | Entities | In more than one report |
|---|---|---|---|---|
| Person | 156 | 64 | 54 | 6 |
| Company | 897 | 518 | 476 | 18 |
| AuditFirm | 10 | 10 | 6 | 3 |
| RelatedPartyGroup | 104 | 13 | 13 | 0 |

## Merge rules applied

- same name (country from the other mention): 273
- same name: 128
- same group: 91
- same DIN: 86
- same name, same report: 12
- same name, same country: 12
- override merges.csv: 8
- override alias recorded: 6
- same FRN: 2
- short name of 'Infosys Public Services, Inc.': 1
- short name of 'Infosys Technologies (China) Co. Limited': 1
- short name of 'Infosys Technologies S. de R. L. de C. V.': 1
- short name of 'Infosys Technologies (Shanghai) Company Limited': 1
- short name of 'Infosys Technologies (Sweden) AB': 1
- short name of 'Skava Systems Pvt. Ltd.': 1

## Hand-confirmed decisions (data/overrides/merges.csv)

- 'L. Krishnakumar' (TATACONSUM) joined 'Mr. Lakshmanan Krishna Kumar' (TATACONSUM) [override merges.csv: L. Krishnakumar = DIN 00423616]
- 'L Krishnakumar' (TATACONSUM) joined 'Mr. Lakshmanan Krishna Kumar' (TATACONSUM) [override merges.csv: L. Krishnakumar = DIN 00423616]
- 'Mr. O. P. Bhatt' (TATASTEEL) joined 'O P Bhatt' (TCS) [override merges.csv: O. P. Bhatt = DIN 00548091]
- 'P B Balaji' (TATAMOTORS) joined 'P. B. Balaji' (TATACONSUM) [override merges.csv: P B Balaji = DIN 02762983]
- override alias recorded: 'TCS Technology Solutions AG' on 'TCS Technology Solutions GmbH'
- override alias recorded: 'TCS Technology Solution GmbH' on 'TCS Technology Solutions GmbH'
- 'Tata Consultancy Service Limited' (TATACONSUM) joined 'Tata Consultancy Services Limited' (TCS) [override merges.csv: Tata Consultancy Service Limited = Tata Consultancy Services Limited]
- override alias recorded: 'Tata Consultancy Service Limited' on 'Tata Consultancy Services Limited'
- 'Tata AIG General Insurance Limited' (TATACONSUM) joined 'Tata AIG General Insurance Company Limited' (TATASTEEL) [override merges.csv: Tata AIG General Insurance Limited = Tata AIG General Insurance Company Limited]
- override alias recorded: 'Tata AIG General Insurance Limited' on 'Tata AIG General Insurance Company Limited'
- 'Infosys McCamish System LLC' (INFY) joined 'Infosys McCamish Systems LLC' (INFY) [override merges.csv: Infosys McCamish System LLC = Infosys McCamish Systems LLC]
- override alias recorded: 'Infosys McCamish System LLC' on 'Infosys McCamish Systems LLC'
- 'Infosys Norway' (INFY) joined 'Infosys Norway A/S' (INFY) [override merges.csv: Infosys Norway = Infosys Norway A/S]
- override alias recorded: 'Infosys Norway' on 'Infosys Norway A/S'

Recorded as relations, the companies staying separate: MERGED_INTO Saudi Desert Rose Holding B.V. -> Tata Consultancy Services Netherlands BV; FORMERLY_NAMED Jaguar Land Rover Limited -> Jaguar Cars Limited

Rule: two rows of the same report's subsidiary list are always two companies. Merges it blocked in this run: 0.


## People in more than one report (6)

- **N. Chandrasekaran** (DIN 00121863; TATACONSUM, TATAMOTORS, TATASTEEL, TCS); also printed as 'Mr N Chandrasekaran', 'Mr. N. Chandrasekaran', 'N Chandrasekaran'
- **O P Bhatt** (DIN 00548091; TATAMOTORS, TATASTEEL, TCS); also printed as 'Mr O P Bhatt', 'Mr. O. P. Bhatt'
- **Al-Noor Ramji** (DIN 00230865; TATAMOTORS, TCS); also printed as 'Mr Al-Noor Ramji'
- **Bharat Puri** (DIN 02173566; TATACONSUM, TATAMOTORS); also printed as 'Mr Bharat Puri'
- **Hanne Sorensen** (DIN 08035439; TATAMOTORS, TCS); also printed as 'Ms Hanne Sorensen'
- **P. B. Balaji** (DIN 02762983; TATACONSUM, TATAMOTORS); also printed as 'P B Balaji'

## Companies in more than one report (18)

- **Tata Chemicals Limited** (TATACONSUM, TATAMOTORS, TATASTEEL, TCS; as other_directorship)
- **Tata Consultancy Services Limited** (TATACONSUM, TATAMOTORS, TATASTEEL, TCS; as other_directorship, related_party); also printed as 'Tata Consultancy Service Limited'
- **Tata Consumer Products Limited** (TATACONSUM, TATAMOTORS, TATASTEEL, TCS; as other_directorship); also printed as 'Tata Consumer Products Ltd.'
- **Tata Motors Limited** (TATACONSUM, TATAMOTORS, TATASTEEL, TCS; as other_directorship)
- **Tata Sons Private Limited** (TATACONSUM, TATAMOTORS, TATASTEEL, TCS; as group_anchor, related_party); also printed as 'Tata Sons Pvt Ltd'
- **Tata Steel Limited** (TATACONSUM, TATAMOTORS, TATASTEEL, TCS; as other_directorship)
- **The Indian Hotels Company Limited** (TATACONSUM, TATAMOTORS, TATASTEEL, TCS; as other_directorship)
- **The Tata Power Company Limited** (TATACONSUM, TATAMOTORS, TATASTEEL, TCS; as other_directorship)
- **Aadhar Housing Finance Limited** (TATAMOTORS, TCS; as other_directorship)
- **HDFC Life Insurance Company Limited** (TATASTEEL, TCS; as other_directorship)
- **Hindustan Unilever Limited** (TATAMOTORS, TCS; as other_directorship)
- **Jaguar Land Rover Limited** (TATAMOTORS, TCS; as related_party, subsidiary)
- **Tata AIG General Insurance Company Limited** (TATACONSUM, TATASTEEL; as other_directorship, related_party); also printed as 'Tata AIG General Insurance Limited'
- **Tata Capital Limited** (TATASTEEL, TCS; as other_directorship)
- **Tata Communications Limited** (TATACONSUM, TCS; as other_directorship, related_party)
- **Tata Investment Corporation Limited** (TATACONSUM, TATASTEEL; as other_directorship, related_party)
- **Tata Technologies Limited** (TATACONSUM, TATAMOTORS; as other_directorship, related_party, subsidiary); also printed as 'Tata Technologies Ltd'
- **Torrent Power Limited** (TATAMOTORS, TCS; as other_directorship)

## Audit firms in more than one report (3)

- **Parikh & Associates** (TATAMOTORS, TATASTEEL, TCS)
- **B S R & Co. LLP** (TATAMOTORS, TCS)
- **Deloitte Haskins & Sells LLP** (INFY, TATACONSUM); also printed as 'DELOITTE HASKINS & SELLS LLP'

## Relations

| Relation | Count |
|---|---|
| RELATED_PARTY_TXN | 479 |
| SUBSIDIARY_OF | 402 |
| DIRECTOR_OF | 102 |
| KMP_OF | 18 |
| AUDITED_BY | 10 |
| GROUP_OF | 3 |
| MERGED_INTO | 1 |
| FORMERLY_NAMED | 1 |

Status of a board seat or KMP role combines all its mentions: 'appointed' and 'current' both mean current, only 'ceased' means the person left; every stated date is kept. A seat known only from another company's report has no status.

Seats/roles whose mentions disagreed on status: 0


Related-party groups (a category of parties, not one company; one node per report and label): TCS: Subsidiaries of the Company; TCS: Subsidiaries of Tata Sons Private Limited; TCS: Associates / joint ventures of Tata Sons Private Limited and their subsidiaries; TCS: Other related parties; TATASTEEL: Subsidiaries; TATASTEEL: Associates; TATASTEEL: Joint Ventures; TATASTEEL: Tata Sons Private Limited, its subsidiaries and joint ventures; TATACONSUM: Subsidiaries; TATACONSUM: Associates; TATACONSUM: Subsidiaries and Joint Ventures of Promoter; TATACONSUM: Joint Ventures; TATACONSUM: Promoter

## Uncertain matches for review (0), not merged

Also in `data/resolved/uncertain.csv` (with a blank `decision` column). Confirmed merges or splits go in `data/overrides/merges.csv`: people by `to_din`; companies with `action` merge / split.

| # | Kind | A | B | Why they might be the same |
|---|---|---|---|---|
