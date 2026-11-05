# Data quality rules

Rules that stop misleading prices from being stored or shown.

## Enforced by the database (Phase 0, tested)

See `DATABASE_DESIGN.md` for constraint names: value required; payer required/forbidden by price type; formulas only on negotiated rows; methodology required; derived amounts documented; count format per CMS; CPT descriptors need a license; one published dataset per facility; import transitions enforced.

## Enforced by code (Phase 0, tested)

Blank is None not 0; floats rejected; no rounding; percentage never parsed as dollars; payer names never auto-merged.

## Reference data (Phase 1, tested)

PDC row count must equal the API's count; unknown hospital types, malformed CCNs and state mismatches are rejected; HCPCS loads stop if more than 1% of records fail the layout; MS-DRG loads stop below 700 codes by default; downloads over 50 MB are refused; every reject is stored in `src.reference_reject`.

## Planned (Phase 2 quality review)

- Row-count swing > 30% vs previous version → hold for review.
- $0 amounts, implausible ratios (cash > gross, negotiated > 10× gross) → flag.
- Reported `last_updated_on` older than 12 months → stale warning.
- v3.0 conditional rules from `CMS_SCHEMA_SUPPORT.md`.

## Consumer rules (Phase 3)

Null is shown as "not published" with a reason; one comparison basis per ranking; alternatives never mixed into exact results.
