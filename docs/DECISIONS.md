# Decisions

Newest first. Each entry: decision, reason, consequences.

## 2026-11-05 — D-018: Discovery starts from approved websites only
Hospital websites are proposed (with evidence) and used only after a named person approves them; the database refuses a website without reviewer and date. Price files are found through `/cms-hpt.txt` on those sites. A cms-hpt.txt location is tied to a facility only by an exact name match through usable aliases; other names are stored and reported for review. A price file listed for several locations, or for any unmatched location, is not assigned to a single facility; the facility mapping happens per file when it is downloaded and read (Phase 2 step 2). Federally owned hospitals are marked exempt rather than searched.

## 2026-11-05 — D-017: Table 5 correction notice supersedes the final rule
When the IPPS Table 5 workbook contains both the final-rule table and a correction-notice table, the correction notice is loaded and the differences are counted in the load summary. If several tables exist and exactly one is not marked as a correction, the load is refused rather than guessing.

## 2026-11-04 — D-016: Reference loads are idempotent upserts with lineage
Every reference load writes a `src.reference_load` row (source URL or file, SHA-256, size, source modified date, counts) and its rejects to `src.reference_reject`. Data changes run in one transaction; a failed load leaves only its `failed` lineage row. Facilities absent from a newer CMS file are not deleted or marked closed automatically (`source_last_seen_at` records when they were last seen); closing a facility needs evidence.

## 2026-11-04 — D-015: Codes are versioned by code-set year (HCPCS) and grouper version (MS-DRG)
HCPCS rows use version = HCPCS year ("2026"); each quarterly file updates that year's descriptors and termination dates. MS-DRG rows use version = grouper ("v44") with effective dates from the fiscal year (FY2027 = 2026-10-01 to 2027-09-30). Only Level II HCPCS codes (letter + 4 digits) are stored; numeric five-character codes in any HCPCS file are skipped so no AMA text can enter (D-002). Modifiers are skipped for now. MS-DRG codes read from spreadsheet cells as 1–99 are restored to three digits ("001"); ZIPs and CCNs that lost leading zeros are refused instead, because those come from text files where a short value signals corruption.

## 2026-11-04 — D-014: Geocoding preference and validation
Address-level coordinates come only from the Census Geocoder (public, no key; batch endpoint first, one-address endpoint if the batch endpoint fails), and only when the match's state and county agree with the facility's published state and county; ties are never used. Otherwise the facility gets its ZCTA internal point, labeled `zcta_centroid`; otherwise no location. Precision is stored and the database requires it whenever `geom` is set. Search-time ZIP lookups use the local `ref.zcta` table only.

## 2026-11-04 — D-013: Facility and health-system identity by identifier, never by name
Facilities are keyed by CCN (6 characters for hospitals, 10 for ASCs, e.g. 29C0001035); NPIs link ASCs to NPPES. Names become aliases: identifier-linked aliases are usable at once, other aliases need a named reviewer. A name shared by two facilities resolves to *ambiguous*, never to one of them. Health systems are keyed by (source, source id); `UNIQUE(name)` on `ref.health_system` was dropped because a name match must not merge two systems. AHRQ links never overwrite a link entered by a person. Campus relationships are never inferred; only reviewed rows with evidence count.

## 2026-11-04 — D-012: CMS Provider Data Catalog via the datastore API, filtered by state
Hospitals (`xubh-q36u`) and ASCs (`4jcv-atw7`) are read through the PDC datastore query API for one state, paged, and refused if the received count differs from the API's count. A downloaded CSV is accepted too; its column titles normalize to the API's machine names. The dataset's `modified` date dates the star rating. Unknown CMS hospital types are rejected, not mapped to "other"; VA and DoD acute-care hospitals map to `acute_care_hospital` with the raw type kept; Rural Emergency Hospitals map to `other`.

## 2026-11-04 — D-011: Real reference data verified in CI, not in the build workspace
The cloud build workspace cannot reach government data hosts. Loaders are tested on synthetic fixtures modeled on the official layouts, and a manual GitHub Actions workflow (`reference-nv.yml`) performs the real Nevada load on a throwaway database and publishes its report. Nothing from that run is kept.

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
