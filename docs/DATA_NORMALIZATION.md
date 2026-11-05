# Data normalization

Rules for turning raw published values into canonical records without losing the original.

## Money

- `parse_dollar` / `parse_percentage` in `procedurescout_core/money.py`.
- Blank tokens (empty, N/A, NaN, null, -) → None. Never 0.
- Floats rejected. Negative values rejected. More than 4 decimal places rejected (never rounded).
- A percentage sign in a dollar field is an error, not a conversion.

## Raw values are kept

Every price row keeps `payer_name_raw`, `plan_name_raw`, `description_raw`, `raw_row_ref`, and `additional_notes_raw` exactly as published.

## Derived amounts

A dollar amount computed from a percentage or algorithm must set `amount_derived = true` and `derivation_rule` (DB-enforced). Derivation is out of scope until a rule is documented and reviewed.

## TODO

- Setting / billing class normalization tables.
- Modifier handling.
- Drug unit normalization (CMS units GR, ML, ME, UN, F2, GM, EA).
