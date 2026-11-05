# Progress

Status levels: Implemented → Tested → Deployed → Verified in production. Only evidence counts.

## 2026-11-05 — Phase 2, step 1: websites and cms-hpt.txt discovery

Implemented and tested on synthetic fixtures; not yet run against real hospital sites.

- `data/reference/facility_websites.csv`: all 46 CMS hospitals. 28 with a proposed website (evidence URL per row), 3 federal hospitals marked exempt (2 VA, 1 DoD), 15 with no website found by search. Researched by Claude with web search on 2026-11-05; for 7 sites a fetch of `/cms-hpt.txt` through the research tool showed the hospital's name (Renown ×2, Sunrise, North Vista, UMC, Northeastern Nevada Regional, Saint Mary's). **Approved by Cooper in chat on 2026-11-05 ("approve all")**, recorded as `reviewed_by = Cooper`, `reviewed_at = 2026-11-05`.
- `data/reference/facility_aliases_reviewed.csv`: header only; for names a person confirms (e.g. names used in cms-hpt.txt).
- Migration `0003_discovery.py`: website provenance on `ref.facility` (a website requires reviewer + date, enforced by CHECK), `hpt_exempt_reason`, `src.hpt_txt_fetch`, `src.hpt_txt_entry`.
- `procedurescout_ingest/discovery.py`: fetches `https://<site>/cms-hpt.txt` (redirects followed, 1 MB cap, web pages refused), parses blocks, stores every fetch and block as published, matches location names exactly through usable aliases, creates `src.transparency_source` per price-file URL (assigned to a facility only when every block listing that URL is matched to the same facility).
- `procedurescout_ingest/reference/websites.py`: loads only approved website/exempt rows and reviewed aliases.
- CLI: `websites`, `aliases`, `discover`; `nv-all` runs them after the reference loads, so the existing manual workflow now also performs discovery. No workflow file change needed.
- Smoke test: the real approved websites file loaded into a throwaway database (46 rows in, 28 websites, 3 exempt, 15 not found, 0 rejects).

Found and fixed while testing: a block whose mrf-url is not a URL was counted as unmatched (now invalid); a price file listed for one matched and one unmatched location was assigned to the matched facility (now unassigned).

`make lint typecheck test`: ruff clean, `Success: no issues found in 25 source files`, `200 passed, 1 warning`. Python 3.12.3: `200 passed, 1 warning`.

Next: run the Nevada workflow; review unmatched cms-hpt.txt names and add reviewed aliases.

## 2026-11-05 — Phase 1, fifth real Nevada run (GitHub Actions, run #5) — green

Artifact `reference-nv (4).zip` (read 2026-11-05). All steps succeeded. Same counts as run #4 for hospitals (46), ASCs (68), census lookups (180 ZCTAs, 17 counties), NPPES (63/65), HCPCS (8,770), MS-DRG (768). Geocoding this time:

- The Census **batch** endpoint answered (the HTTP 502 in runs #3–#4 was an outage, not a blocked request), so the one-address fallback was not needed and remains untested live.
- 107 of 114 facilities have address-level coordinates (90 exact, 17 non-exact matches), all passing the state and county checks (no `geocode_wrong_state` / `geocode_wrong_county` rejects).
- 7 at ZIP centroid: 290041 Summerlin Hospital (geocoder tie, not used), 29C0001131 (no match), and 5 ASCs with no street address (3 shared-NPI ASCs that got no NPI link, 2 NPPES ZIP mismatches).
- County FIPS missing for 1 facility (its ZCTA crosses county lines).

The coordinates themselves were not inspected (the artifact's facility list has no latitude/longitude columns); they are trusted only to the extent of the state/county agreement check.

**Phase 1 status:** loaders Implemented and Tested, and verified against the live official sources in a throwaway CI database. Nothing is Deployed: no persistent database exists yet, so the data is reloaded from source on each run.

Open items for Phase 1:
- AHRQ health systems: not loaded (file URL unconfirmed, Q7).
- Human review: 3 ASC pairs sharing an NPI (29C0001056/1079, 29C0001057/1077, 29C0001006/1084), 1 ASC listed twice by CMS (29C0001057), 5 names shared by more than one facility, Summerlin Hospital geocoder tie; campus relationships (Q8).
- Revenue codes / ICD not loaded (Q10).

## 2026-11-05 — Phase 1, fourth real Nevada run (GitHub Actions, run #4) — first green run

Workflow finished with a green check. Artifact `reference-nv (3).zip` (read 2026-11-05). All eight steps succeeded:

| Step | In | Loaded | Rejected | Notes |
|---|---|---|---|---|
| hospitals (PDC `xubh-q36u`, modified 2026-07-22) | 46 | 46 | 0 | 25 acute care, 13 critical access, 8 psychiatric; 25 carry a star rating |
| ASCs (PDC `4jcv-atw7`, modified 2025-12-16) | 69 | 68 | 1 | duplicate 29C0001057; 3 shared-NPI warnings |
| census lookups | 180 | 180 | 0 | 17 counties, 180 ZCTAs |
| NPPES addresses | 65 | 63 | 0 | 2 ZIP mismatches |
| geocode | 114 | 114 | 0 | **all 114 at ZCTA centroid**: the Census batch geocoder returned HTTP 502 on all 4 attempts (also in run #3), so no address-level coordinates. County FIPS for the 46 hospitals (from CMS county names); none for the 68 ASCs |
| relationships | 0 | 0 | 0 | review file empty, as intended |
| HCPCS Level II, October 2026 file | 8,770 | 8,770 | 0 | 1,322 with a termination date; 579 modifier records skipped; 0 numeric (CPT-like) codes found. Confirms the trimmed-line fix. Descriptor text not spot-checked (not in the artifact) |
| MS-DRG v44, FY2027 Table 5 correction notice | 768 | 768 | 0 | identical to the final-rule sheet |

AHRQ health systems were not loaded (no file URL given; Q7).

Fixes in this change:
- Geocoder: if the batch endpoint fails, the one-address endpoint (`/geocoder/geographies/address`, JSON, numbers read as Decimal) is used per facility; five failures in a row = unavailable → ZIP centroids. The source records `batch` or `single`. Tests: `test_single_response_parsing_uses_decimals`, `test_batch_failure_falls_back_to_single`, `test_single_endpoint_down_raises`.
- ZCTA fallback now sets county FIPS when the facility has none and the ZCTA lies wholly in one county; ZCTAs crossing county lines give no county. Test: `test_zcta_fallback_county_only_when_zcta_in_one_county`.
- An outage no longer adds one "missing result" warning per facility. Test: `test_outage_does_not_add_per_row_noise`.

`make lint typecheck test`: ruff clean, `Success: no issues found in 23 source files`, `191 passed, 1 warning`. Python 3.12.3: `191 passed, 1 warning`.

Next: run #5 to see whether the one-address geocoder works from GitHub Actions.

## 2026-11-05 — Phase 1, third real Nevada run (GitHub Actions, run #3)

Artifact `reference-nv (2).zip` (read 2026-11-05).

| Step | Status | In | Loaded | Rejected | Notes |
|---|---|---|---|---|---|
| hospitals | succeeded | 46 | 46 | 0 | |
| ASCs | succeeded | 69 | 68 | 1 | |
| census lookups | **succeeded** | 180 | 180 | 0 | 17 Nevada counties, 180 ZCTAs |
| NPPES addresses | succeeded | 65 | 63 | 0 | 2 ZIP mismatches (29C0001059, 29C0001125) |
| geocode | **failed** | — | — | — | `Census geocoder returned HTTP 502` (server error at the Census Bureau); the whole step rolled back, so no facility got even a ZIP-level location or county FIPS |
| HCPCS | **failed** | — | — | — | no zip member recognized. Archive holds `HCPC2026_OCT_ANWEB_09232026.txt` (3,208,022 bytes), `.xlsx`, transaction report, corrections, `HCPC2026_recordlayout.txt`, NOC codes, `proc_notes_OCT2026.txt`. Likely cause: the detector required lines of at least 293 characters; the 2026 file probably trims trailing blanks (not confirmed) |
| MS-DRG | **succeeded** | 768 | 768 | 0 | correction-notice sheet "FY 2027 Table 5 CN" used; vs final rule "FY 2027 Table 5 FR": 0 titles changed, 0 codes added, 0 removed |

Fixes in this change:
- Geocoder: server and network errors are retried (waits of 10, 30, 60 s); if the geocoder is still down the step continues with ZIP centroids and records a `geocoder_unavailable` warning. Tests: `test_geocoder_retries_server_errors`, `test_geocoder_gives_up_after_retries`, `test_geocoder_outage_falls_back_to_zcta`.
- HCPCS: the detector no longer requires full-length lines (it checks the code in columns 1–5 and the record id in column 11); a new guard refuses the load if most codes have no added date (the layout would have moved). If detection fails again the error includes line counts, length ranges and the first two lines of each text member. Tests: `test_hcpcs_trimmed_lines_detected_and_parsed`, `test_hcpcs_layout_without_dates_refused`, `test_describe_text_members`.

`make lint typecheck test`: ruff clean, `Success: no issues found in 23 source files`, `186 passed, 1 warning`. Python 3.12.3: `186 passed, 1 warning`.

Next: run #4.

## 2026-11-05 — Phase 1, second real Nevada run (GitHub Actions, run #2)

Artifact `reference-nv (1).zip` (read 2026-11-05). Every step now ran thanks to the continue-on-failure change.

| Step | Status | In | Loaded | Rejected | Notes |
|---|---|---|---|---|---|
| hospitals | succeeded | 46 | 46 | 0 | same as run #1 |
| ASCs | succeeded | 69 | 68 | 1 | same as run #1 |
| census lookups | **failed** | — | — | — | `bad coordinate '+144.751149'`: the 2026 Gazetteer writes signed coordinates |
| NPPES addresses | succeeded | 65 | 63 | 0 | 2 address mismatches (e.g. 29C0001059: NPPES ZIP 89113 vs CMS 89147) left at ZIP level |
| geocode | succeeded (did nothing) | 0 | 0 | 1 | `no_counties` because census lookups failed |
| HCPCS | **failed, unrecorded** | — | — | — | failed before its lineage row was written, so the reason is not in the artifact |
| MS-DRG (FY2027 Table 5) | succeeded | 1538 | 768 | 770 | the workbook holds two tables (final rule + correction notice); the loader read both as one and rejected the second as duplicates, so the 768 codes came from the **final-rule** table, not the correction notice |
| report | — | — | — | — | 5 names shared by more than one facility (ambiguous by design, e.g. two "DIGESTIVE DISEASE CENTER GREEN VALLEY" CCNs) |

Fixes in this change:
- Gazetteer coordinates may carry a `+` sign. Test: `test_gazetteer_signed_coordinates`.
- Table 5: each worksheet is read separately; if there are several, the one marked "Correction" is used and the titles/codes it changed are counted; several unmarked tables are refused. Tests: `test_table5_correction_notice_supersedes_final_rule`, `test_table5_two_unmarked_tables_refused`.
- `nv-all` records a `failed` lineage row (with the error) for a step that fails before loading starts, e.g. during download or unzip. Zip errors list the archive's contents. Tests: `test_nv_all_records_failures_that_happen_before_loading`, `test_unzip_error_lists_archive_contents`.

`make lint typecheck test`: ruff clean, `Success: no issues found in 23 source files`, `180 passed, 1 warning`. Python 3.12.3: `180 passed, 1 warning`.

Next: run #3.

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
