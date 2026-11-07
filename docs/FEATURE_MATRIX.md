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
| FAC-01 | CMS Hospital General Information import | 1 | Yes | Yes (synthetic) | — | — | `reference/cms_pdc.py`, `reference/facilities.py`; `tests/test_reference_facilities.py`, `test_pdc_pages_until_count`. Real NV load ran in CI (throwaway DB) 2026-11-05: 46/46 loaded. |
| FAC-02 | Geocoding | 1 | Yes | Yes (synthetic) | — | — | `reference/census.py`, `reference/geocode.py`, `ref.zcta`/`ref.county` in 0002; `tests/test_reference_geo.py` (`test_geocode_preference_order`, `test_batch_failure_falls_back_to_single`). Real CI run #5: 107/114 address-level (state/county checked), 7 ZIP-level. One-address fallback not yet exercised live. |
| FAC-03 | Facility aliases/relationships | 1 | Yes | Yes | — | — | `procedurescout_core/facility_repo.py`, `reference/relationships.py`, 0002; `tests/test_reference_identity.py` (`test_shared_name_is_ambiguous_not_merged`, `test_child_has_one_approved_campus_parent`). No relationships seeded. |
| FAC-04 | ASC import | 1 | Yes | Yes (synthetic) | — | — | `reference/facilities.py` (`load_ascs`), `reference/nppes.py`; `test_asc_ten_character_ccn_and_npi`, `test_nppes_mismatches_are_reported_not_applied`. Real CI run #2 2026-11-05: 68/69 loaded; NPPES street addresses for 63/65. |
| REF-01 | HCPCS/DRG/RC/ICD references | 1 | Partly (HCPCS, MS-DRG) | Yes (synthetic) | — | — | `reference/codes.py`; `tests/test_reference_codes.py`. Real CI run #4 (green): 8,770 HCPCS 2026 codes, 768 MS-DRG v44 codes (correction notice). RC (NUBC licence) and ICD not loaded. |
| FAC-05 | Health-system links (AHRQ Compendium) | 1 | Yes | Yes (synthetic) | — | — | `reference/ahrq.py`; `test_ahrq_links_by_ccn_and_reports_the_rest`, `test_ahrq_never_overwrites_manual_link`. Source file URL unconfirmed. |
| REF-04 | Reference-load lineage | 1 | Yes | Yes | — | — | `src.reference_load`/`reference_reject` (0002), `reference/cli.py`; `test_load_lineage_success_and_failure` |
| REF-03 | Reviewed consumer terms | 3 | Schema only | — | — | — | `ref.procedure*` |
| SRC-01 | File discovery | 2 | Yes (cms-hpt.txt on approved websites) | Yes (synthetic) | — | — | `procedurescout_ingest/discovery.py`, `reference/websites.py`, migration 0003; `tests/test_discovery.py` (`test_discover`, `test_only_reviewed_websites_are_used`). 28 approved hospital websites; real run #6: 9 sites with cms-hpt.txt, 6 hospitals matched, 4 files assigned, 12 sites refused or missing. Real run #7: 32 hospitals matched, 7 sites via captured copies (captured copies switched off afterwards, D-020). Home-computer fetch: `scripts/fetch_hpt_home.ps1`, migration 0005; `test_home_runner_fetch_used_when_github_is_refused`. Real run #8 (all live): 33 hospitals matched; home runner worked on Windows PowerShell 5.1. Reviewed co-listed locations (D-023): `discovery.load_co_listed`, migration 0007; `test_co_listed_location_lets_file_be_assigned`, `test_co_listed_approval_for_another_hospital_does_not_assign`. Captured-copy fallback and manual sources: `discovery.py`, migration 0004; `test_captured_copy_used_only_when_live_fetch_fails`, `test_manual_sources`. |
| SRC-02 | File metadata | 2 | Partly (headers-only size/date probe, Nevada-scoped) | Yes (synthetic) | — | — | `discovery.probe_sources`, migration 0006; `test_prober_reads_headers_without_downloading`, `test_probe_sources_records_sizes`. Run live as #9 (throwaway DB): Nevada ≈ 4.9 GB known + 9 unsized. Download + SHA-256 + header/count check: `procedurescout_ingest/price_files.py`, migration 0007; `tests/test_price_files.py` (`test_check_price_files_records_and_deletes`, `test_downloader_streams_hashes_and_limits`). Run live as #10: 25 of 29 Nevada files downloaded and read (5.4 GB). Home-computer fallback for sites refusing GitHub: `scripts/fetch_prices_home.ps1`, migration 0008; `test_home_fallback_only_when_github_fails`, `test_check_records_home_download_and_deletes_it`. |
| ING-01 | Streaming parsers | 2 | Partly (format detection + header/count read; no price rows yet) | Yes (synthetic) | — | — | `procedurescout_ingest/base.py`, `price_files.read_json`/`read_csv`; `test_read_json_header_and_counts`, `test_read_csv_tall`, `test_read_csv_wide_and_ragged_row` |
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
