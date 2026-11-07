# Data quality rules

Rules that stop misleading prices from being stored or shown.

## Enforced by the database (Phase 0, tested)

See `DATABASE_DESIGN.md` for constraint names: value required; payer required/forbidden by price type; formulas only on negotiated rows; methodology required; derived amounts documented; count format per CMS; CPT descriptors need a license; one published dataset per facility; import transitions enforced.

## Enforced by code (Phase 0, tested)

Blank is None not 0; floats rejected; no rounding; percentage never parsed as dollars; payer names never auto-merged.

## Reference data (Phase 1, tested)

PDC row count must equal the API's count; unknown hospital types, malformed CCNs and state mismatches are rejected; HCPCS loads stop if more than 1% of records fail the layout; MS-DRG loads stop below 700 codes by default; downloads over 50 MB are refused; every reject is stored in `src.reference_reject`.

## Price-file check (Phase 2 step 2a, tested)

Flagged per file (`file_problem`, stored in `src.transparency_file.read_error`): no `version`, or not a 2.x/3.x template; no `last_updated_on`, not a date, or more than a year old (CMS requires annual updates); CSV rows with a different column count than the header; bytes that are not valid UTF-8; fewer than three rows (not the CMS CSV template); invalid JSON; Excel workbooks; ZIPs with no or several JSON/CSV files. Download failures (`download_failed`) and files over the size limit are reported, never retried around.

## Price rows (Phase 2 step 2b, tested)

Refused (counted per file by rule, first 5 examples kept): `bad_amount` (negative, malformed, more than 15 decimal places, percentage outside 0–1000), `missing_methodology`, `unknown_methodology`, `missing_payer_or_plan`, `no_code`, `unknown_code_type`, `not_cms_csv`. Flagged but kept: `zero_amount`, `more_than_4_decimals`, `text_decoded_cp1252`, `drug_unit_amount_unreadable`, `drug_unit_type_unknown`, `allowed_count_unreadable`. A file that fails part-way is rolled back entirely (no partial datasets). Loaded prices are a *staged* dataset whose import run waits in `quality_review`; nothing is published automatically.

## Planned (Phase 2 quality review)

- Row-count swing > 30% vs previous version → hold for review.
- $0 amounts, implausible ratios (cash > gross, negotiated > 10× gross) → flag.
- v3.0 conditional rules from `CMS_SCHEMA_SUPPORT.md`.

## Consumer rules (Phase 3)

Null is shown as "not published" with a reason; one comparison basis per ranking; alternatives never mixed into exact results.
