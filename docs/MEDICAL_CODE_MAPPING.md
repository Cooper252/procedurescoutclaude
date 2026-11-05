# Medical code mapping

How everyday procedure words map to billing codes.

## Model

`ref.procedure` (consumer concept) ↔ `ref.procedure_code` (code, role: primary/variant/related, review state) ↔ `ref.code`. Synonyms in `ref.procedure_synonym`. Only `approved` rows are used in search.

## Rules

- A common term that covers several services opens a disambiguation step; nothing is expanded silently.
- CPT descriptors: not stored without a license (D-002). Plain-English names are ours.
- AI may propose synonyms or codes (`source = ai_suggested`); they stay `proposed` until a person approves.
- Known legacy failures to test against: "Brain MRI" must offer 70551/70552/70553; "ER" levels must not be merged into one price; screening vs diagnostic colonoscopy must be distinguished.

## Reference codes loaded (Phase 1)

- HCPCS Level II from the CMS quarterly alpha-numeric file: code, long and short descriptor (public CMS text), added and termination dates. Version = HCPCS year.
- MS-DRG from IPPS Table 5: code and title. Version = grouper (`v44` for FY2027).
- Not loaded: CPT text (D-002), revenue code text (NUBC licence, Q10), ICD-10.

## TODO

- First 50 consumer terms with reviewed code sets (Phase 3).
- Code-system version handling across years.
