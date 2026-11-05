# Decisions

Newest first. Each entry: decision, reason, consequences.

## 2026-11-04 — D-010: Price table partitioned by LIST(state_code)
Rollout is state by state; most consumer searches are within one region; a state partition can be loaded, vacuumed, reindexed or detached independently. Facility-level replacement uses `dataset_version` pointers, not partition swaps. Consequence: PK is (state_code, id); a state partition can be sub-partitioned by hash later if one state grows too large.

## 2026-11-04 — D-009: Long-format price rows
One row per published amount, typed by `price_type`, instead of one wide row with gross/cash/negotiated columns. Reason: makes it structurally impossible to rank a cash price against a negotiated rate by accident, and lets constraints differ per type. Cost: roughly 1.5–3× more rows than wide format; acceptable for Nevada, revisit with measurements before national scale. Supersedes the wide layout sketched in the Phase 0 plan.

## 2026-11-04 — D-008: Amounts stored as NUMERIC(16,4), not NUMERIC(14,2)
Per-unit drug prices and some fee schedules are published with sub-cent precision. Two decimal places would round source values. The parser refuses values with more than 4 decimal places instead of rounding. Display rounding happens only in presentation.

## 2026-11-04 — D-007: Code systems match CMS v3.0 exactly
`ref.code_system` uses the 21 CMS v3.0 `code_information.type` values. An earlier draft had 10 values and would have rejected valid files (APC, HIPPS, CDT, etc.).

## 2026-11-04 — D-006: v2 `estimated_amount` kept as its own price type
v2.0/v2.2 files contain an estimated allowed amount that v3.0 removed. Stored as `estimated_allowed`, never shown as a negotiated rate.

## 2026-11-04 — D-005: Allowed-amount count stored as published text
CMS defines `count` as "0", "1 through 10", or a whole number ≥ 11. Stored verbatim in `allowed_count_raw` with a CHECK, because "1 through 10" has no integer value.

## 2026-11-04 — D-004: API reads only `price.published_price`
The restricted role has no grant on `price.price` or `fixture`. Staged or failed imports and synthetic data are unreachable from the API by database permissions, not just by query filters (the legacy app relied on ~30 separate `is_sample` filters).

## 2026-11-04 — D-003: Import transitions enforced in the database
A BEFORE trigger validates transitions against `src.import_transition`; an AFTER trigger logs them. The Python state machine uses the same list; a test checks they match.

## 2026-11-04 — D-002: CPT without an AMA license at launch
Store and show CPT code numbers as hospitals publish them, our own plain-English names, and hospital-published descriptions labeled as such. AMA descriptor text is refused by a DB constraint unless `descriptor_licensed` is true. Legal review before public launch.

## 2026-11-04 — D-001: Rebuild, don't migrate, the legacy app
Legacy MongoDB data (17.3M rows) is not migrated; procedurescout.com is taken down during the rebuild; all hospital files are downloaded fresh. See `LEGACY_AUDIT.md`.
