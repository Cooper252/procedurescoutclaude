# Data normalization

Rules for turning raw published values into canonical records without losing the original.

## Money

- `parse_dollar` / `parse_percentage` in `procedurescout_core/money.py`.
- Blank tokens (empty, N/A, NaN, null, -) → None. Never 0.
- Floats rejected. Negative values rejected. More than 4 decimal places rejected (never rounded).
- A percentage sign in a dollar field is an error, not a conversion.

## Raw values are kept

Every price row keeps `payer_name_raw`, `plan_name_raw`, `description_raw`, `raw_row_ref`, and `additional_notes_raw` exactly as published.

## Facilities (Phase 1)

- Identity is the CCN; ASCs also carry their NPI. Names are aliases (`ref.facility_alias`) with a normalized key from `matching.normalize_name` (case, accents, whitespace, stray punctuation only).
- `resolve_facility_by_name` returns matched / unmatched / ambiguous. No fuzzy matching; "Synthetic Regional" does not match "Synthetic Regional Medical Center".
- ZIP: 5 digits, `NNNNN-NNNN` or 9 digits → first five; anything else (including 3–4 digit values) is refused, not padded.
- CMS hospital type: mapped by an explicit table; unknown values reject the row. Raw value kept.
- Star rating: 1–5 or "Not Available" (→ NULL); dated by the dataset's modified date; no date → rating dropped.
- County: CMS county name matched exactly (ignoring "County" suffix and case) to `ref.county` in the same state.
- Address changes clear the stored geocode so it is redone.

## Derived amounts

A dollar amount computed from a percentage or algorithm must set `amount_derived = true` and `derivation_rule` (DB-enforced). Derivation is out of scope until a rule is documented and reviewed.

## TODO

- Setting / billing class normalization tables.
- Modifier handling.
- Drug unit normalization (CMS units GR, ML, ME, UN, F2, GM, EA).
