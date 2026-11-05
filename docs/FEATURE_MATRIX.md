# Feature matrix

Status levels are separate on purpose. A cell is filled only with evidence. Deployed / Verified-in-prod stay empty until a real deployment exists.

| ID | Requirement | Phase | Implemented | Tested | Deployed | Verified-in-prod | Evidence |
|---|---|---|---|---|---|---|---|
| FND-01 | Repo, docs, local env, CI | 0 | Yes | Partly | — | — | `Makefile`, `docker-compose.yml`, `.github/workflows/ci.yml`; local suite run 2026-11-04 (see PROGRESS). CI has not run yet; Docker compose not exercised (no Docker daemon in build sandbox). |
| FND-02 | Canonical schema + integrity constraints | 0 | Yes | Yes | — | — | `db/migrations/versions/0001_initial_schema.py`; `tests/test_migration.py`, `tests/test_price_constraints.py` |
| FND-03 | Exact Decimal money parsing | 0 | Yes | Yes | — | — | `packages/core/procedurescout_core/money.py`; `tests/test_money.py`, `tests/test_no_float_money.py` |
| FND-04 | Import state machine (code + DB trigger) | 0 | Yes | Yes | — | — | `procedurescout_core/import_state.py`, trigger in 0001; `tests/test_state_machine.py` |
| NRM-01 | No auto-merge of payer names | 0 (guard) | Partly | Yes | — | — | `procedurescout_core/matching.py`, `payer_repo.py`; `tests/test_payer_matching.py`. Review queue UI is Phase 2. |
| NRM-02 | Percentages never stored as dollars; methodology required | 0 (schema) | Partly | Yes | — | — | price CHECK constraints in 0001; `tests/test_price_constraints.py`. Parsers are Phase 2. |
| REF-02 | No unlicensed CPT descriptors | 0 (schema) | Yes | Yes | — | — | `ref.code` CHECK; `test_cpt_descriptor_requires_license` |
| SEC-01 (part) | API role sees published prices only, never fixtures | 0 (schema) | Yes | Yes | — | — | grants + `price.published_price` view in 0001; `tests/test_access_control.py` |
| API-00 | `/healthz`, `/v1/meta/version` | 0 | Yes | Yes | — | — | `apps/api/procedurescout_api/main.py`; `tests/test_api.py` |
| FAC-01 | CMS Hospital General Information import | 1 | — | — | — | — | |
| FAC-02 | Geocoding | 1 | — | — | — | — | |
| FAC-03 | Facility aliases/relationships | 1 | Schema only | — | — | — | tables in 0001 |
| FAC-04 | ASC import | 1 | — | — | — | — | |
| REF-01 | HCPCS/DRG/RC/ICD references | 1 | Schema only | — | — | — | `ref.code` |
| REF-03 | Reviewed consumer terms | 3 | Schema only | — | — | — | `ref.procedure*` |
| SRC-01 | File discovery | 2 | Schema only | — | — | — | `src.transparency_source` |
| SRC-02 | File metadata | 2 | Schema only | — | — | — | `src.transparency_file` |
| ING-01 | Streaming parsers | 2 | Interface only | — | — | — | `procedurescout_ingest/base.py` |
| ING-02 | Validation | 2 | Schema only | — | — | — | `src.validation_result` |
| ING-03 | Checkpoints, retries | 2 | Schema only | — | — | — | `src.import_run.checkpoint` |
| ING-04 | Staged publication + rollback | 2 | Schema only | Partly | — | — | one-published-per-facility index tested |
| SRCH-01..05 | Consumer search | 3 | — | — | — | — | |
| FA-01..02 | Financial assistance | 4 | — | — | — | — | |
| EST-01..02 | Estimator | 5 | — | — | — | — | |
| BUN-01 | Bundles | 6 | — | — | — | — | |
| ADM-01..02 | Admin | 2–3 | — | — | — | — | |
| A11Y-01 | Accessibility | 3 | — | — | — | — | |
| EXP-01 | Exports | 8 | — | — | — | — | |
