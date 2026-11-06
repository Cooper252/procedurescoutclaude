# CLAUDE.md — ProcedureScout

Instructions for any AI coding agent (Claude Code or Claude) working in this repository. Read this file and `docs/PROGRESS.md` before changing anything.

## The principle

**No price is better than a false price.** Never fabricate prices, codes, payers, plans, ratings, eligibility results, or test results. A search that honestly returns "not published" is a correct result.

## Hard rules

1. Never claim a test passed unless you ran it in this session and can show the output. Paste real output into `docs/PROGRESS.md`.
2. Track four separate status levels and never merge them: **Implemented → Tested → Deployed → Verified in production.** Generated code alone is not "done".
3. Every change updates `docs/PROGRESS.md` and `docs/FEATURE_MATRIX.md`. An "Implemented" cell needs a file path as evidence; a "Tested" cell needs a test name.
4. Money is `decimal.Decimal` in Python and `NUMERIC` in PostgreSQL. `float` is banned in `packages/core` and `packages/ingest` (enforced by `tests/test_no_float_money.py`). Never round source values; refuse values that would need rounding.
5. Missing amounts are `NULL`/`None`, never `0`. Amount columns have no defaults.
6. Sample or synthetic data lives only in the `fixture` schema and in files named `synthetic_*`. It never reaches `ref`, `src`, or `price`, and the API role cannot read it.
7. The API reads prices only through `price.published_price`. Never grant the API role access to `price.price` or `fixture`.
8. Never silently substitute a different plan, procedure, code, or facility. Alternatives are returned separately and labeled.
9. Payer/plan names are matched only through approved alias rows (`ref.payer_alias`, `ref.plan_alias`). No fuzzy auto-merging. "Anthem Blue Cross Blue Shield" and out-of-state BCBS/BlueCard are different payers until a person approves otherwise.
10. AI output (code suggestions, synonym ideas, policy extraction) is stored as `proposed` and is never used until a person approves it.
11. CPT: show code numbers and our own plain-English names. **Do not load AMA CPT descriptor text** (the database refuses it unless `descriptor_licensed` is true; decision of 2026-11-04).
12. Validate every user-supplied filter (payer, plan, code, facility) against lookup tables before running any price query. No unbounded scans.

## Constraints

- Ask first before: paid infrastructure, production deploys, destructive migrations or deletes, downloads over 50 MB, any monetization feature.
- Do not use Grok, xAI, or their infrastructure.
- Stack: Python 3.12+, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, PostgreSQL 16 + PostGIS 3.4, pytest, ruff, mypy (strict). Frontend (Phase 3): TypeScript + Next.js.
- Migrations are frozen history: never edit a migration that has been applied to staging or production; add a new one. (0001–0005 are not yet applied anywhere shared.)

## Commands

```
make setup      # virtualenv + pinned dependencies
make up         # PostgreSQL/PostGIS (+ MinIO) in Docker; runs scripts/db_init.sql on first start
make migrate    # alembic upgrade head on DATABASE_URL
make check      # ruff + mypy + pytest (tests rebuild TEST_DATABASE_URL from scratch)
make api        # run the API on :8000
make reference-nv AHRQ=<csv path or url>   # load Nevada reference data (needs internet)
```

Without Docker: install PostgreSQL 16 + PostGIS, run `scripts/db_init.sql` as a superuser, then the same commands.

## Layout

- `apps/api/procedurescout_api` — FastAPI app
- `packages/core/procedurescout_core` — money parsing, enums, import state machine, payer matching
- `packages/ingest/procedurescout_ingest` — parser adapter interface (adapters arrive in Phase 2); `reference/` holds the Phase 1 reference-data loaders and their CLI (`python -m procedurescout_ingest.reference.cli`); `discovery.py` reads cms-hpt.txt on approved hospital websites
- `db/migrations` — Alembic; `0001_initial_schema.py` (core schema), `0002_facility_reference.py` (Phase 1 reference data), `0003_discovery.py` (Phase 2 websites + cms-hpt.txt discovery), `0004_captured_hpt.py` (captured cms-hpt.txt copies, manual sources), `0005_home_runner.py` (which network fetched a cms-hpt.txt)
- `data/reference/` — small, human-reviewed reference files committed to the repo (e.g. reviewed facility relationships)
- `tests/` — pytest; DB tests run inside rolled-back transactions
- `docs/` — the living specification (list below)

## Docs

`PRODUCT_VISION.md`, `REQUIREMENTS.md`, `FEATURE_MATRIX.md`, `DATA_SOURCES.md`, `CMS_SCHEMA_SUPPORT.md`, `SYSTEM_ARCHITECTURE.md`, `DATABASE_DESIGN.md`, `INGESTION_PIPELINE.md`, `DATA_NORMALIZATION.md`, `PAYER_PLAN_MATCHING.md`, `MEDICAL_CODE_MAPPING.md`, `COST_ESTIMATOR_SPEC.md`, `BUNDLED_PRICING_SPEC.md`, `FINANCIAL_ASSISTANCE_SPEC.md`, `CONSUMER_USER_FLOWS.md`, `SECURITY_AND_PRIVACY.md`, `DATA_QUALITY_RULES.md`, `API_CONTRACTS.md`, `TEST_PLAN.md`, `PERFORMANCE_PLAN.md`, `DEPLOYMENT_PLAN.md`, `COST_AND_SCALING_PLAN.md`, `DECISIONS.md`, `OPEN_QUESTIONS.md`, `PROGRESS.md`, plus `LEGACY_AUDIT.md`.

Keep them accurate when the code changes. If code and docs disagree, fix one of them in the same change.
