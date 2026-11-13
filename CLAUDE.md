# CLAUDE.md — ProcedureScout

Instructions for any AI coding agent (Claude Code or Claude) working in this repository. Read this file and `docs/PROGRESS.md` before changing anything.

## The principle

**No price is better than a false price.** Never fabricate prices, codes, payers, plans, ratings, eligibility results, or test results. A search that honestly returns "not published" is a correct result.

## Hard rules

1. Never claim a test passed unless you ran it in this session and can show the output. Paste real output into `docs/PROGRESS.md`.
2. Track four separate status levels and never merge them: **Implemented → Tested → Deployed → Verified in production.** Generated code alone is not "done".
3. Every change updates `docs/PROGRESS.md` and `docs/FEATURE_MATRIX.md`. An "Implemented" cell needs a file path as evidence; a "Tested" cell needs a test name.
4. Money is `decimal.Decimal` in Python and unconstrained `NUMERIC` in PostgreSQL (exact as published, D-029). `float` is banned in `packages/core` and `packages/ingest` (enforced by `tests/test_no_float_money.py`). Never round source values; refuse values that would need rounding.
5. Missing amounts are `NULL`/`None`, never `0`. Amount columns have no defaults.
6. Sample or synthetic data lives only in the `fixture` schema and in files named `synthetic_*`. It never reaches `ref`, `src`, or `price`, and the API role cannot read it.
7. The API reads prices only through published data: the Parquet files listed in `price.published_file` (D-033) or the `price.published_price` view. Never grant the API role access to `price.price`, `src.published_file`, staged files or `fixture`.
8. Never silently substitute a different plan, procedure, code, or facility. Alternatives are returned separately and labeled.
9. Payer/plan names are matched only through approved alias rows (`ref.payer_alias`, `ref.plan_alias`). No fuzzy auto-merging. A plan with another state's name stays a different payer unless evidence shows it is the local plan. Cooper delegated insurance-name matching to Claude (D-047): Claude may approve an alias only with written evidence in its notes (a source URL or a clear reason from the hospital's own file), as `reviewed_by = "Claude (delegated by Cooper, D-047)"`; a name that cannot be placed with evidence stays unmatched and is still findable exactly as written (D-046). Never ask Cooper to review insurance spellings. State laws and public program limits are also Claude's to confirm (D-056): only from a cited official source, `reviewed_by = "Claude (delegated by Cooper, D-056)"`. So are hospital financial-assistance policies (D-060): only from the hospital's own policy document, `reviewed_by = "Claude (delegated by Cooper, D-060)"`; never ask Cooper to review policies. So are new services, search words, explanations and cost bundles (D-061): only from official code definitions, source in `notes`, `reviewed_by = "Claude (delegated by Cooper, D-061)"`; never ask Cooper to review them.
10. AI output (code suggestions, synonym ideas, policy extraction) is stored as `proposed` and is never used until a person approves it, except insurance-name matching, sourced state rules, sourced hospital assistance policies and sourced services/bundles, which Cooper delegated (rule 9, D-047, D-056, D-060, D-061).
11. CPT: show code numbers and our own plain-English names. **Do not load AMA CPT descriptor text** (the database refuses it unless `descriptor_licensed` is true; decision of 2026-11-04).
12. Validate every user-supplied filter (payer, plan, code, facility) against lookup tables before running any price query. No unbounded scans.

## Constraints

- Ask first before: paid infrastructure, production deploys, destructive migrations or deletes, downloads over 50 MB, any monetization feature.
- Do not use Grok, xAI, or their infrastructure.
- Stack: Python 3.12+, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, PostgreSQL 16 + PostGIS 3.4, pytest, ruff, mypy (strict). Frontend (Phase 3): TypeScript + Next.js.
- Migrations are frozen history: never edit a migration that has been applied to staging or production; add a new one. (0001–0014 are not yet applied anywhere shared.)

## Commands

```
make setup      # virtualenv + pinned dependencies
make up         # PostgreSQL/PostGIS (+ MinIO) in Docker; runs scripts/db_init.sql on first start
make migrate    # alembic upgrade head on DATABASE_URL
make check      # ruff + mypy + pytest (tests rebuild TEST_DATABASE_URL from scratch)
make api        # run the API on :8000
make reference-nv AHRQ=<csv path or url>   # load Nevada reference data (needs internet)
cd apps/web && npm ci && npm run build && npm start   # website on :3000 (preview data unless API_URL is set)
```

Without Docker: install PostgreSQL 16 + PostGIS, run `scripts/db_init.sql` as a superuser, then the same commands.

## Layout

- `apps/api/procedurescout_api` — FastAPI app
- `apps/web` — the website (Next.js + TypeScript). `lib/api.ts` is the only API client; `lib/synthetic_demo.ts` is preview data used only when `API_URL` is unset (labeled on every page); `lib/i18n.ts` holds English and Spanish; `lib/money.ts` formats exact decimal strings without floats; `lib/estimate.ts` is the "What will I pay?" math (whole cents, `npm test`)
- `packages/core/procedurescout_core` — money parsing, enums, import state machine, payer matching
- `packages/ingest/procedurescout_ingest` — parser adapter interface (adapters arrive in Phase 2); `reference/` holds the Phase 1 reference-data loaders and their CLI (`python -m procedurescout_ingest.reference.cli`); `discovery.py` reads cms-hpt.txt on approved hospital websites; `price_files.py` downloads, checks and deletes each assigned price file; `price_parser.py` reads its prices and `price_load.py` stages them (never publishes); `storage_experiment.py` measures storage layouts for national scale; `publish.py` is the review step (approve/reject), `parquet_io.py` writes published Parquet files and `code_index.py` indexes every published code; `reference/nppes_offices.py` loads offices from the national provider list; `website_verify.py` finds candidate hospital websites (DoltHub list) and accepts those whose cms-hpt.txt names them. In `packages/core`: `object_store.py` (where published files live: a folder, or an S3-compatible bucket such as Cloudflare R2), `db_url.py` (host database URLs to the psycopg driver), `price_store.py` (validated reads of published prices) and `search.py` (search by service near a place), `bundles.py` (bundle estimates), `assistance.py` (financial assistance message and check), `pricing.py` (headline, typical range, badges, change), `plans.py` (plans by card name), `offers.py` (provider specials) and `places.py` (cities); `portal_auth.py` (provider sign-in, authenticator, claiming), `provider_pages.py` (provider homepages, images), `reviews.py` (verified reviews, moderation) and `provider_stats.py` (privacy-safe counts, boost estimates), `provider_prices.py` (provider prices, specials, packages; review; search shaping), `price_templates.py` (price-list templates and checked uploads), `mailer.py` (sends waiting emails: Resend or SMTP), `billing.py` (listing fee and Sponsored spots via Stripe; off by default), `price_reports.py` (wrong-price reports), `listing_requests.py` (practices asking to be added); `reference/catalog.py` loads provider types and the service catalog; `reference/health_centers.py` loads HRSA health center sites. In `apps/api`: `search_routes.py` (public search) and `admin_routes.py` (review page) and `care_routes.py` (bundles, assistance), `portal_routes.py` (provider homepages, reviews, counts, provider portal) and `admin_portal_routes.py` (provider page review at `/admin/providers`)
- `db/migrations` — Alembic; `0001_initial_schema.py` (core schema), `0002_facility_reference.py` (Phase 1 reference data), `0003_discovery.py` (Phase 2 websites + cms-hpt.txt discovery), `0004_captured_hpt.py` (captured cms-hpt.txt copies, manual sources), `0005_home_runner.py` (which network fetched a cms-hpt.txt), `0006_source_probe.py` (price-file size checks), `0007_price_file_check.py` (reviewed co-listed locations, price files checked without keeping them), `0008_price_file_via.py` (which network downloaded a price file), `0009_price_other_codes.py` (other codes of a price item), `0010_exact_numeric.py` (amounts stored exactly), `0011_published_files.py` (review fields, published Parquet manifest), `0012_service_catalog.py` (service catalog, provider types), `0013_bundles_assistance.py` (bundles, poverty guidelines, assistance policies), `0014_published_history.py` (price history view), `0015_master_catalog_offers.py` (standard service list details, provider prices and specials), `0016_help_paying_sources.py` (health centers, coverage limits), `0017_code_index_provider_packages.py` (code index, provider prices by code, packages), `0018_provider_portal.py` (provider accounts, homepages, reviews, counts; portal role), `0019_provider_price_review.py` (provider price review, published price views), `0020_national_offices_billing_staff.py` (offices, listing requests, price reports, staff, email retries, billing), `0021_published_summaries.py` (per-file summaries; staged rows removed after publishing), `0022_specialties_referral.py` (specialty groups, referral label), `0023_price_upload_suggestions.py` (services practices priced that aren't listed yet), `0024_delivery_copay.py` (in person / online prices, copay note), `0025_published_payers.py` (insurer names per place from published files, for the nearby insurance list), `0026_site_analytics.py` (owner analytics: daily totals only), `0027_state_plan_alias.py` (insurance spellings matched per state, D-062)
- `render.yaml` — Render hosting blueprint (D-048, `docs/DEPLOYMENT_PLAN.md`); `scripts/prod_db_setup.py` (PostGIS + API role before each deploy), `scripts/state_check.py` (end-to-end check of one loaded state, used by `test-all-states.yml`), `scripts/install_duckdb_extensions.py` (build step)
- `data/reference/` — small, human-reviewed reference files committed to the repo (e.g. reviewed facility relationships)
- `tests/` — pytest; DB tests run inside rolled-back transactions
- `docs/` — the living specification (list below)

## Docs

`PRODUCT_VISION.md`, `REQUIREMENTS.md`, `FEATURE_MATRIX.md`, `DATA_SOURCES.md`, `CMS_SCHEMA_SUPPORT.md`, `SYSTEM_ARCHITECTURE.md`, `DATABASE_DESIGN.md`, `INGESTION_PIPELINE.md`, `DATA_NORMALIZATION.md`, `PAYER_PLAN_MATCHING.md`, `MEDICAL_CODE_MAPPING.md`, `COST_ESTIMATOR_SPEC.md`, `BUNDLED_PRICING_SPEC.md`, `FINANCIAL_ASSISTANCE_SPEC.md`, `CONSUMER_USER_FLOWS.md`, `SECURITY_AND_PRIVACY.md`, `DATA_QUALITY_RULES.md`, `API_CONTRACTS.md`, `TEST_PLAN.md`, `PERFORMANCE_PLAN.md`, `DEPLOYMENT_PLAN.md`, `COST_AND_SCALING_PLAN.md`, `DECISIONS.md`, `OPEN_QUESTIONS.md`, `PROGRESS.md`, `PRODUCT_REVIEW.md` (ideas and priorities, approved D-039), `SITE_DESIGN.md` (site map, layouts, pricing features, build order), `PROVIDER_PAGES_SPEC.md` (provider homepages, dashboard, reviews, payments readiness), `GO_LIVE.md` (everything still needed to launch), plus `LEGACY_AUDIT.md`.

Keep them accurate when the code changes. If code and docs disagree, fix one of them in the same change.
