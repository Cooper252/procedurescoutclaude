# Database design

PostgreSQL 16 + PostGIS 3.4. Defined in `db/migrations/versions/0001_initial_schema.py`.

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

## Deletion behaviour

Lineage references use `ON DELETE RESTRICT` (files, runs, dataset versions, facilities cannot be deleted while prices point at them). Child detail rows (aliases, events, validation results) cascade with their parent.

## Roles

`ps_owner` owns objects and runs migrations. `ps_api` is granted read access by migration 0001 (role name from `PS_API_ROLE`).
