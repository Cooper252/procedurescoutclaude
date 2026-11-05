# Test plan

What is tested and how.

## Current suite (Phase 0)

| File | Covers |
|---|---|
| `test_money.py` | Exact parsing, blanks → None, percent/float/negative/garbage rejection, no rounding |
| `test_no_float_money.py` | `float` banned in core and ingest packages |
| `test_state_machine.py` | Python transitions; DB transition table matches; trigger rejects illegal jumps; events logged |
| `test_migration.py` | Downgrade to empty and upgrade to head; single head |
| `test_price_constraints.py` | Every price CHECK; NULL stays NULL; Decimal round trip; CMS count values; all v3.0 code types; CPT license rule; one published dataset per facility |
| `test_payer_matching.py` | No auto-merge (Anthem vs BlueCard); unmapped recording; proposed mappings ignored; uniqueness |
| `test_access_control.py` | API role cannot read fixtures or raw prices or write; published view hides staged data |
| `test_enums_match_db.py` | Python enums equal PostgreSQL enums |
| `test_api.py` | Health and version endpoints |

DB tests run inside rolled-back transactions on `TEST_DATABASE_URL`, rebuilt from scratch each run.

## Planned

Parser fixtures (v2.0–v3.0 JSON, CSV tall/wide, corrupt files, large streamed files), legacy regression cases (plan collapse, code expansion, invalid plan latency, missing-price reasons), estimator numerical cases, frontend and accessibility tests, load tests.
