# Medical code mapping

How everyday procedure words map to billing codes.

## Model

`ref.procedure` (consumer concept) ↔ `ref.procedure_code` (code, role: primary/variant/related, review state) ↔ `ref.code`. Synonyms in `ref.procedure_synonym`. Only `approved` rows are used in search.

## Rules

- A common term that covers several services opens a disambiguation step; nothing is expanded silently.
- CPT descriptors: not stored without a license (D-002). Plain-English names are ours.
- AI may propose synonyms or codes (`source = ai_suggested`); they stay `proposed` until a person approves.
- Known legacy failures to test against: "Brain MRI" must offer 70551/70552/70553; "ER" levels must not be merged into one price; screening vs diagnostic colonoscopy must be distinguished.

## TODO

- First 50 consumer terms with reviewed code sets (Phase 3).
- Code-system version handling across years.
