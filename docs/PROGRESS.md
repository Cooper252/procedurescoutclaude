# Progress

Status levels: Implemented → Tested → Deployed → Verified in production. Only evidence counts.

## 2026-11-05 — Phase 1, first real Nevada run (GitHub Actions, run #1)

Cooper ran the manual workflow `Reference data — Nevada (manual)` on commit `5d2f075`. Result: **failed after 36 s**. Artifact `reference-nv.zip` contents (read 2026-11-05):

| Step | Status | Rows in | Loaded | Rejected | Notes |
|---|---|---|---|---|---|
| cms_hospital_general_information (modified 2026-07-22) | succeeded | 46 | 46 | 0 | 25 acute care (incl. 2 VA, 1 DoD), 13 critical access, 8 psychiatric; 33 of 46 rated |
| cms_asc_facility (modified 2025-12-16) | succeeded | 69 | 68 | 1 | 29C0001057 listed twice (first kept). 3 NPI warnings: 29C0001079, 29C0001077, 29C0001084 share an NPI with 29C0001056, 29C0001057, 29C0001006 respectively — left unmerged, need human review |
| census_zcta_county_relationship | **failed** | — | — | — | `ZCTA Gazetteer file lacks columns ('geoid', 'aland', 'intptlat', 'intptlong')` — the 2026 Gazetteer file is not tab-delimited as the loader assumed |

Steps after the failure (NPPES, geocode, HCPCS, MS-DRG) did not run.

Fixes in this change:
- `census.parse_gazetteer` now detects the delimiter from the header (tab, pipe or comma) and error messages list the columns actually found. Tests: `test_gazetteer_other_delimiters`.
- `nv-all` keeps going after a failed step and exits non-zero at the end, so one run shows every problem. Test: `test_nv_all_continues_after_a_failed_step`.

`make lint typecheck test` after the fix: ruff clean, `Success: no issues found in 23 source files`, `175 passed, 1 warning`. Python 3.12.3: `175 passed, 1 warning`.

Next: re-run the workflow.

## 2026-11-04 — Phase 1 (facility and reference data), first pass

Built by Claude (Cowork) in a cloud workspace. **Not yet pushed; CI has not run on this change; no real data has been loaded.** The build workspace's network blocks data.cms.gov, census.gov, cms.gov, ahrq.gov and npiregistry.cms.hhs.gov (proxy policy 403), so every loader was tested only on synthetic fixtures (`tests/fixtures/reference/synthetic_*`). File layouts were checked against the official documentation and live API schema responses (see `DATA_SOURCES.md`), not against downloaded files.

### Implemented and tested (synthetic fixtures)

- Migration `0002_facility_reference.py`: 10-character ASC CCNs; raw CMS facility type and county; geocode precision (`address` / `zcta_centroid`) tied to `geom`; sourced health-system links; health systems keyed by (source, source_system_id) with `UNIQUE(name)` dropped (D-013); facility aliases with normalized key, match basis (ccn/npi/manual) and review state; relationship review state, evidence, one approved campus parent per child, reversed pairs refused by trigger; `ref.county`, `ref.zcta`; `ref.code.descriptor_short` under the CPT licence rule; `src.reference_load` + `src.reference_reject` lineage; API grants on the two new lookup tables.
- `procedurescout_core/facility_repo.py`: exact-only name resolution among usable aliases; shared names return *ambiguous*, never a match.
- `procedurescout_ingest/reference/`: `cms_pdc.py` (PDC datastore API paging with count check, or CSV), `facilities.py` (hospitals + ASCs, upsert by CCN, unknown types rejected), `census.py` (relationship + Gazetteer parsing, Census batch geocoder request/response), `geocode.py` (address match validated against state and county, else ZCTA centroid, else nothing), `nppes.py` (ASC street addresses only when state + ZIP agree), `ahrq.py` (health systems by CCN and AHRQ system id; manual links never overwritten), `relationships.py` (reviewed CSV / proposals), `codes.py` (HCPCS Level II fixed-width, MS-DRG Table 5 .xlsx/.txt), `common.py` (50 MB download cap, SHA-256, header normalization, lineage rows), `cli.py` (one command per source, `nv-all`, `report`).
- `data/reference/facility_relationships_reviewed.csv`: header only. No relationships are seeded; none could be verified from here.
- `.github/workflows/reference-nv.yml`: manual workflow that performs the real Nevada load on a throwaway PostGIS service and uploads the report, lineage, rejects and facility list as an artifact.
- `make reference-nv`, `make reference-report`.

### Verification evidence

Environment: Python 3.13.18 and 3.12.3, PostgreSQL 16 + PostGIS 3.4 (installed in the workspace; database created with `scripts/db_init.sql`).

`make lint typecheck test` (Python 3.13):

```
All checks passed!
58 files already formatted
Success: no issues found in 23 source files
platform linux -- Python 3.13.18, pytest-9.2.0, pluggy-1.7.0
collected 172 items
tests/test_access_control.py ....                                        [  2%]
tests/test_api.py ...                                                    [  4%]
tests/test_enums_match_db.py .                                           [  4%]
tests/test_migration.py ..                                               [  5%]
tests/test_money.py .........................................            [ 29%]
tests/test_no_float_money.py .                                           [ 30%]
tests/test_payer_matching.py ........                                    [ 34%]
tests/test_price_constraints.py .............................            [ 51%]
tests/test_reference_codes.py ...........                                [ 58%]
tests/test_reference_common.py .....................                     [ 70%]
tests/test_reference_facilities.py ................                      [ 79%]
tests/test_reference_geo.py .........                                    [ 84%]
tests/test_reference_identity.py ..........                              [ 90%]
tests/test_reference_links.py .....                                      [ 93%]
tests/test_state_machine.py ...........                                  [100%]
======================== 172 passed, 1 warning in 2.33s ========================
```

Same suite on Python 3.12.3 (CI's version): `ruff` clean, `mypy` clean, `172 passed, 1 warning`.

Other checks:

- Migration round trip (base → head → base → head) passes with 0002 (`tests/test_migration.py`).
- CLI smoke run in a throwaway database (`ps_cli_smoke_test`, dropped afterwards) with the synthetic files: hospitals 2 loaded; census 3 counties, 2 ZCTAs, 1 reject; geocode 2 ZCTA centroids; HCPCS 3 codes (1 numeric code and 2 modifier records skipped); MS-DRG 3 codes, 2 rejects; a second MS-DRG run with the default `--min-rows 700` was refused and recorded as `failed` in `src.reference_load`.
- Mutation check 1: made `resolve_facility_by_name` ignore ambiguity → `test_shared_name_is_ambiguous_not_merged` failed. Restored.
- Mutation check 2: removed the geocoder county check → `test_geocode_preference_order` failed. Restored.

### Not done / not verified

- **No real Nevada data loaded.** Run the `Reference data — Nevada (manual)` workflow (Actions tab) or `make reference-nv` on a machine with internet. Expected from the live API on 2026-11-04: 46 Nevada rows in Hospital General Information and 69 in the ASC facility file.
- Unverified against real files: HCPCS zip member name and that the 2026 text layout still matches the CMS record layout; Table 5 zip contents and header text; Census batch output column order for matches (from documentation and memory of the format, not a live response); NPPES rate limits.
- AHRQ: the hospital linkage file URL could not be confirmed (ahrq.gov pages render empty to the fetch tool); the loader needs `--ahrq-file`. Newest year seen: 2023.
- Revenue codes (NUBC, licensed) and ICD were not loaded (out of scope; licensing review for RC).
- ASCs in the CMS file are those in the ASC Quality Reporting program (2024 data year), not every licensed Nevada ASC.
- Phase 0 CI: Cooper reports CI is green on GitHub; not observed from this workspace.

## 2026-11-04 — Phase 0 (foundation)

Built by Claude (Cowork) in a cloud workspace, not yet pushed to GitHub, CI not yet run.

### Implemented and tested

- Repository layout, `pyproject.toml`, pinned `requirements*.txt`, `Makefile`, `.env.example`, `docker-compose.yml`, `scripts/db_init.sql`, CI workflow.
- Migration `0001_initial_schema.py`: schemas `ref`, `src`, `price`, `fixture`; 19 enums; all tables from `DATABASE_DESIGN.md`; price CHECK constraints; LIST(state) partitioning; import-transition triggers; `price.published_price` view; API-role grants.
- `procedurescout_core`: `money.py` (Decimal parsing), `enums.py`, `import_state.py`, `matching.py`, `payer_repo.py`.
- `procedurescout_ingest/base.py`: parser adapter interface only.
- API: `/healthz`, `/v1/meta/version`.
- All 26 documents (CLAUDE.md + 25 in `docs/`, plus `LEGACY_AUDIT.md`).

### Found and fixed during Phase 0

1. Import-run event logging ran before the row existed (FK violation) → split into BEFORE (validate) and AFTER (log) triggers. Caught by tests.
2. Code-system enum had 10 values; CMS v3.0 allows 21 → aligned exactly (D-007).
3. CMS `count` is text ("1 through 10") → stored as validated text (D-005).
4. v2 `estimated_amount` had no home → `estimated_allowed` price type (D-006).
5. Amounts widened to NUMERIC(16,4) to avoid rounding sub-cent drug prices (D-008).

### Verification evidence

Environment: Python 3.13.18 (CI pins 3.12), PostgreSQL 16 + PostGIS 3.4 installed locally (no Docker daemon available in the build workspace).

`make lint typecheck test`:

```
All checks passed!
51 files already formatted
Success: no issues found in 11 source files
============================= test session starts ==============================
platform linux -- Python 3.13.18, pytest-9.2.0, pluggy-1.7.0
rootdir: /home/claude/procedurescout
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.16.0
collected 100 items

tests/test_access_control.py ....                                        [  4%]
tests/test_api.py ...                                                    [  7%]
tests/test_enums_match_db.py .                                           [  8%]
tests/test_migration.py ..                                               [ 10%]
tests/test_money.py .........................................            [ 51%]
tests/test_no_float_money.py .                                           [ 52%]
tests/test_payer_matching.py ........                                    [ 60%]
tests/test_price_constraints.py .............................            [ 89%]
tests/test_state_machine.py ...........                                  [100%]

=============================== warnings summary ===============================

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 100 passed, 1 warning in 1.29s ========================
```

The one warning is a third-party deprecation notice (Starlette TestClient prefers `httpx2`), not a project issue.

Additional checks run:

- `scripts/db_init.sql` executed on a brand-new PostgreSQL 16 cluster, then the full suite: `85 passed` (before the CMS-alignment tests were added; same steps CI runs).
- Mutation check 1: made `parse_dollar` return `Decimal(0)` for missing input → `tests/test_money.py` failed (1 failed, 40 passed). Restored.
- Mutation check 2: granted the API role read access to `fixture.synthetic_price` → confirmed the role could read it (the condition `test_api_role_cannot_read_fixture_schema` asserts against). Revoked; full suite `100 passed`.

### Not done / not verified

- CI has not run (repository not yet on GitHub).
- `docker compose up` not exercised (no Docker daemon here). The MinIO image tag is unverified.
- No deployment exists.

## Next

1. Run the Nevada reference workflow; paste its report here; fix whatever the real files reveal.
2. Review the rejects (unknown hospital types, county-name mismatches, NPPES mismatches) and fill `facility_relationships_reviewed.csv` from evidence.
3. Phase 2: discovery of `cms-hpt.txt` for the loaded facilities.
