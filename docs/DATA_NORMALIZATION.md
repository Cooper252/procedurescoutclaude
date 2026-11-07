# Data normalization

Rules for turning raw published values into canonical records without losing the original.

## Money

- `parse_dollar` / `parse_percentage` in `procedurescout_core/money.py`.
- Blank tokens (empty, N/A, NaN, null, -) → None. Never 0.
- Floats rejected. Negative values rejected. Stored exactly as published, up to 15 decimal places (D-029); more is refused, never rounded.
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

## Price files (Phase 2 step 2b, `price_parser.py`)

- **One row per published amount.** Gross, discounted cash, de-identified min/max once per charge item and setting; negotiated (dollar, percentage and/or algorithm), v2 estimated amount and v3 median/10th/90th percentile once per payer/plan. In tall CSVs the gross/cash/min/max repeated on every payer row are stored once.
- **Primary code.** An item with several codes is stored under the most specific one, in this order: MS-DRG, APR-DRG, MS-LTC-DRG, other DRG families, CPT, HCPCS, CDT, NDC, HIPPS, APC, EAPG, CMG, ICD, RC, LOCAL, CDM. All other codes are kept as published in `other_codes` ("TYPE:code"). Code types are matched to the CMS list ignoring case, spaces and underscores ("ms drg" = MS-DRG); anything else (e.g. "CPT4") is refused, not guessed.
- **Methodology** must be one of the five CMS values (case, spaces and underscores ignored); a negotiated rate without one, or without a payer and plan, is refused.
- **Text encoding.** CSV cells that are not valid UTF-8 are decoded as Windows-1252 and the price is flagged `text_decoded_cp1252`.
- **Drug units** are kept only when the unit is a positive number and the type is one of the CMS units (GR, ML, ME, UN, F2, GM, EA); otherwise dropped and flagged `drug_unit_amount_unreadable` or `drug_unit_type_unknown`.
- **Column names** are compared without case or spaces around "|"; within one wide CSV, a payer/plan's columns are grouped by label ignoring case and extra spaces, and the label as first published is stored (D-029).
- **Counts** for allowed amounts must be "0", "1 through 10" or a whole number ≥ 11; otherwise dropped and flagged `allowed_count_unreadable`.
- Payer and plan names are stored exactly as published; `payer_id`/`plan_id` stay empty until approved aliases exist.

## Derived amounts

A dollar amount computed from a percentage or algorithm must set `amount_derived = true` and `derivation_rule` (DB-enforced). Derivation is out of scope until a rule is documented and reviewed.

## TODO

- Setting / billing class normalization tables.
- Modifier handling.
- Drug unit normalization (CMS units GR, ML, ME, UN, F2, GM, EA).
