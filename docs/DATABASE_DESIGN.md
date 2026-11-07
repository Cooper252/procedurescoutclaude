# Database design

PostgreSQL 16 + PostGIS 3.4. Defined in `db/migrations/versions/0001_initial_schema.py` and `0002_facility_reference.py`.

## Schemas

| Schema | Holds | API role access |
|---|---|---|
| `ref` | Facilities, health systems, codes, procedures, payers, plans, aliases | SELECT |
| `src` | Sources, files, import runs + events, validation results, dataset versions, audit log | SELECT on sources, files, file↔facility, dataset versions only |
| `price` | `price.price` (partitioned by state) and view `price.published_price` | View only |
| `fixture` | Synthetic test data | None |

## Key tables

- `ref.facility` — one row per facility/campus; `ccn` unique when present; `geom geography(Point,4326)` with GiST index; rating requires an as-of date; geometry requires a geocode source.
- `ref.code` — PK (system, code, version). CHECK: a CPT row may not carry a descriptor unless `descriptor_licensed`.
- `ref.procedure_code` — links consumer procedures to codes; `approved` requires reviewer + time.
- `ref.payer` / `ref.plan` — canonical entities. `ref.payer_alias` / `ref.plan_alias` — raw names, unique on normalized text; `match_type = 'unmapped'` exactly when no canonical link exists.
- `src.transparency_file` — sha256, bytes, HTTP status, reported date, schema version, format, object store key, attestation; unique (source, sha256).
- `src.import_run` — state machine enforced by trigger against `src.import_transition`; every change logged in `src.import_run_event`.
- `src.dataset_version` — staged → published → retired; partial unique index guarantees one published version per facility.
- `price.price` — long format: one row per published amount (see below).

## price.price

Columns: identity (`state_code`, `id`), lineage (`dataset_version_id`, `facility_id`, `raw_row_ref`), service (`code_system`, `code`, `modifiers`, `setting`, `billing_class`, `description_raw`, `drug_unit`, `drug_unit_type`), payer (`payer_name_raw`, `plan_name_raw`, `payer_id`, `plan_id`, `match_type`), value (`price_type`, `amount NUMERIC(16,4)`, `percentage NUMERIC(9,4)`, `algorithm`, `methodology`, `allowed_count_raw`), derivation (`amount_derived`, `derivation_rule`), notes and quality flags.

Named CHECK constraints (all tested):

| Constraint | Rule |
|---|---|
| `price_has_value` | amount, percentage or algorithm must be present |
| `price_payer_required` | negotiated / allowed-amount / estimated rows need raw payer and plan |
| `price_payer_forbidden` | gross, cash, de-identified min/max carry no payer |
| `price_formula_only_negotiated` | percentages and algorithms only on negotiated rows |
| `price_negotiated_needs_methodology` | negotiated rows need a methodology |
| `price_derivation_documented` | a computed dollar amount needs its rule and source formula |
| `price_allowed_count_scope` | count only on median/p10/p90 rows |
| `price_mapping_labeled` | a canonical payer/plan link needs a non-unmapped match type |
| `price_plan_needs_payer` | plan link requires payer link |

Amounts: nullable, no defaults, `>= 0`. Percentages 0–1000.

Partitioning: LIST (`state_code`) with `price_nv` and a DEFAULT partition. Indexes: (code_system, code, facility_id), (plan_id, code_system, code) where plan_id is set, (dataset_version_id).

## Phase 1 additions (migration 0002)

- `ref.facility`: CCN may be 6 characters (hospital) or `NNCNNNNNNN` (ASC); `cms_facility_type_raw`, `county_name` as published; `geocode_precision` (`address` | `zcta_centroid`), required exactly when `geom` is set; `geocoded_at`; `health_system_source`, required when `health_system_id` is set; `source_last_seen_at`.
- `ref.health_system`: `source`, `source_system_id` (unique together), `source_year`, `hq_city`, `hq_state`. No unique name (D-013).
- `ref.facility_alias`: `alias_normalized` (indexed, not unique), `alias_type`, `match_basis` (ccn/npi/manual), review fields. CHECK: approved requires an identifier basis or a named reviewer.
- `ref.facility_relationship`: review fields and `evidence`; approved requires reviewer, time and evidence; partial unique index allows one approved `campus_of` parent per child; trigger refuses a reversed pair.
- `ref.county` (FIPS, state, name) and `ref.zcta` (ZCTA, state, primary county, crosses-counties flag, land area, internal point, Gazetteer year). API role may read both.
- `ref.code.descriptor_short`, under the same CPT licence CHECK.
- `src.reference_load` (dataset, source, SHA-256, size, modified date, parameters, status, counts, summary, error) and `src.reference_reject`.

## Phase 2 additions (migration 0003)

- `ref.facility`: `website` must be `https://<host>` and requires `website_reviewed_by` + `website_reviewed_at`; `website_evidence_url`; `hpt_exempt_reason`.
- `src.hpt_txt_fetch`: every attempt to read a site's cms-hpt.txt (status, final URL after redirects, SHA-256, size, error, entry count).
- `src.hpt_txt_entry`: each block as published, with `match_status` (matched / unmatched / ambiguous / invalid), `problems`, and `facility_id` exactly when matched. Not readable by the API role.

## Migration 0004

- `src.hpt_txt_fetch.content_source` (`live` | `captured`); captured rows require `captured_at`, `captured_from`, `copy_reviewed_by`.
- `src.transparency_source.review_note`; required when `discovery_method = 'manual'`.

## Migrations 0005–0006

- `src.hpt_txt_fetch.fetched_via` (`github` | `home_runner`).
- `src.source_probe`: headers-only size/date checks of each price-file URL (nothing downloaded).

## Migration 0007

- `src.hpt_txt_entry.match_status` adds `co_listed`; `co_listed_with` names the hospital whose file lists that location (required exactly when co_listed). See D-023.
- `src.transparency_file.object_store_key` is optional (NULL = downloaded, checked and deleted, D-025); new columns `final_url`, `content_type`, `server_last_modified`, `last_updated_raw` (as published), `header` (jsonb, top-level fields as published), `read_summary` (jsonb counts), `read_error` (problems found).
- Reference-load dataset `price_file_check`.

## Migration 0008

- `src.transparency_file.fetched_via` (`github` | `home_runner`), D-026.

## Deletion behaviour

Lineage references use `ON DELETE RESTRICT` (files, runs, dataset versions, facilities cannot be deleted while prices point at them). Child detail rows (aliases, events, validation results) cascade with their parent.

## Roles

`ps_owner` owns objects and runs migrations. `ps_api` is granted read access by migration 0001 (role name from `PS_API_ROLE`).
