# Progress

Status levels: Implemented → Tested → Deployed → Verified in production. Only evidence counts.

## 2026-11-08 — Build step 1: headline prices, typical ranges, badges, likely-error flags, price history, plans by card name, search suggestions

Implemented and tested (synthetic) per D-040:
- `procedurescout_core/pricing.py`, `plans.py`; `search()` gains `mode` (cash/list/plan) and `plan_id`, per-facility headline, badges and change since the last file, and a typical range.
- `price_parser`: `under_one_dollar`, `over_ten_million` flags. `PublishedPrice.quality_flags` read from Parquet.
- Migration `0014_published_history.py`; `find_prices(previous=True)`.
- `reference/catalog.py`: `load_payers`, `load_payer_aliases`, `collect_unmapped_plans`, `load_synonyms` (run by `catalog`); data files `payers.csv`, `payer_aliases.csv` (headers only until the real spellings are reviewed), `service_synonyms.csv` (30 proposals).
- API: `GET /v1/plans`, `GET /v1/services/suggest`, search `mode`/`plan_id`, headline/badge/typical fields.
- Workflow export `payer-plan-names.csv` (every Nevada payer/plan spelling with price and facility counts) for the plan review.
- Tests: `tests/test_pricing.py` (6), parser flag test, suggestion and synonym tests.

`make lint typecheck test`: `274 passed, 1 warning` (Python 3.13); `/tmp/v312/bin/python -m pytest -q`: `274 passed, 1 warning`.

## 2026-11-08 — Product review approved (D-039); site design written

Cooper approved everything in `PRODUCT_REVIEW.md` and asked for a look at every aspect. Wrote `docs/SITE_DESIGN.md` (site map, page-by-page layouts, ease of use, better pricing, trust, providers, growth, operations, measurement, build order). New requirements UX-01/02, PRC-01/02, HELP-01; Q21 resolved; Q22 added (Nevada uninsured-discount law to confirm). No code changed.

## 2026-11-08 — Assistance limits in dollars (D-038), 13 hospital policies proposed, product review

- `assistance.plain_message`, `facility_policy`, `site_message`: "You may qualify for free care at X if your household makes under $31,920 (1 person) or $66,000 (family of 4)…", exact from the reviewed percentage × HHS guideline, shown rounded down. API: `GET /v1/assistance/message?state=`, `GET /v1/facilities/{id}/assistance`, and `message` in the check result.
- `data/reference/assistance_policies.csv`: 13 proposed policies with evidence from the hospitals' or systems' own pages (UMC, Sunrise/MountainView/Southern Hills via HCA's company page, the 3 St. Rose campuses, Renown ×2, Carson Tahoe, North Vista, Saint Mary's, Banner Churchill); unreviewed. A Virginia "Valley Health System" policy and a California "St. Rose Hospital" policy turned up in searches and were rejected as the wrong organizations.
- Review page lists proposed assistance policies and bundles.
- `docs/PRODUCT_REVIEW.md`: what is missing and suggested order (Q21).

`make lint typecheck test`: `265 passed, 1 warning` (Python 3.13); `/tmp/v312/bin/python -m pytest -q`: `265 passed, 1 warning`.

## 2026-11-08 — Auto-publish (D-035), approved catalog, bundles (D-036), financial assistance (D-037), implemented and tested

Cooper: yes to automatic publishing of clean refreshes and to approving all proposed services and provider types; bundles with optional pieces; financial assistance on every page.
- `publish.auto_check` / `auto_publish_pending`, CLI `auto-publish`.
- `data/reference/service_catalog.csv` and `provider_types.csv`: all rows reviewed by Cooper (2026-11-08).
- Migration `0013_bundles_assistance.py`; loaders in `reference/catalog.py` (bundles, poverty guidelines, assistance policies; run by `catalog`).
- `procedurescout_core/bundles.py` (estimate by cash/list/one published plan; missing pieces never $0; complete flag), `data/reference/bundles.csv` (upper endoscopy, colonoscopy, vaginal birth; proposed, need clinical review).
- `procedurescout_core/assistance.py` (site message, guideline lookup, may-qualify check), `data/reference/poverty_guidelines.csv` (HHS 2026, checked against the ASPE detailed-guidelines PDF), `data/reference/assistance_policies.csv` (header only, to be collected).
- API `care_routes.py`: assistance message and check, bundles, facility plans, bundle estimate. `/v1/services` now lists services only (bundles separately).
- Found and fixed: `choose_per_facility` failed when a facility had no CCN (providers outside CMS lists); the nv-all tests now keep the catalog, alias, website, discovery and probe steps offline instead of writing to the test database.
- New docs: `BUNDLED_PRICING_SPEC.md`, `FINANCIAL_ASSISTANCE_SPEC.md`.
- Tests: `tests/test_bundles_assistance.py` (5); catalog tests updated for the approvals.

`make lint typecheck test`: `265 passed, 1 warning` (Python 3.13); `/tmp/v312/bin/python -m pytest -q`: `265 passed, 1 warning`.

## 2026-11-08 — Service catalog, provider types, search API and review page, implemented and tested

Cooper: yes to all three next steps. Recorded as D-034.
- Migration `0012_service_catalog.py`; `reference/catalog.py` (CLI `catalog`, also in `nv-all`): provider types from `data/reference/provider_types.csv` (5 approved by Cooper's list, 6 proposed), CMS facility types mapped to hospital / surgery center, services from `data/reference/service_catalog.csv` (18 AI-suggested entries, all `proposed`; code numbers only).
- `procedurescout_core/search.py` + `apps/api/procedurescout_api/search_routes.py`: `GET /v1/services`, `GET /v1/provider-types`, `GET /v1/search` (approved service or known code, near a point, optional provider type; exact amounts as strings; nearby facilities without published prices listed as such). `docs/API_CONTRACTS.md` created.
- `apps/api/procedurescout_api/admin_routes.py`: `/admin/reviews` page with approve/reject per hospital, interim name + password sign-in, forged-form protection; proposed services and provider types listed. Off unless configured.
- Tests: `tests/test_search_and_review.py` (12).
- Not yet: hosting (so nothing is live), multi-factor sign-in, the website itself.

`make lint typecheck test`: `260 passed, 1 warning` (Python 3.13); `/tmp/v312/bin/python -m pytest -q`: `260 passed, 1 warning`.

## 2026-11-08 — D-033 approved; review step and published Parquet files, implemented and tested

Cooper approved D-033 ("Yes").
- Migration `0011_published_files.py`: review fields on `src.dataset_version`; `src.published_file` manifest (exact sums, SHA-256, one current file per facility and price source); `price.published_file` view for the API role.
- `procedurescout_ingest/publish.py`: `pending_reviews`, `approve` (exact Parquet via `parquet_io.write_dataset`, verified against the database, stored without overwrite, previous dataset and file retired, audit event, one transaction), `reject` (reason required).
- `procedurescout_core/object_store.py` (local store; S3-compatible store waits for the hosting decision) and `procedurescout_core/price_store.py` (`find_prices`: validates facilities, code type and code before reading; only current published files; Decimal amounts).
- CLI: `review-list`, `approve --dataset --reviewer [--note]`, `reject --dataset --reviewer --reason`; store folder from `PRICE_STORE_DIR`.
- CLAUDE.md rule 7 updated for published Parquet files.
- Not yet: a persistent database or store (nothing is reviewed or published for real until hosting is chosen and approved); an admin console page for the review; an API endpoint.
- Tests: `tests/test_publish.py` (6).

`make lint typecheck test`: `248 passed, 1 warning` (Python 3.13); `/tmp/v312/bin/python -m pytest -q`: `248 passed, 1 warning`.

## 2026-11-08 — Run #13: 29 Nevada hospitals, 48,972,607 prices staged, 16 refused; storage comparison

Artifact `reference-nv (12).zip` (read 2026-11-08), plus `prices-home (1).zip` (Carson Valley downloaded on Cooper's computer).

- Price load: 31 files chosen, 30 downloaded (5,880,788,068 bytes), **29 loaded, 48,972,607 prices staged, 16 refused** (run #12: 156,776 refused). The 16 are Banner Churchill's trailing rows without a code. Nothing published.
- Fixes confirmed: Seven Hills 14,069 prices (was 0); Pershing 28,743 (was 15,678 with 13,065 refused); UHS sub-cent rates kept and flagged `more_than_4_decimals` (e.g. Summerlin 24,328); Banner, Mesa View, Mt. Grant recovered; the HCA drug-unit flags are gone (their units had more than 4 decimals).
- New: Spring Valley loaded (3,384,551 prices; its cms-hpt.txt answered this time) and Carson Valley via Cooper's computer (268,097 prices).
- Still without a file: Renown ×2 (429), Incline Village (403), William Bee Ririe, St. Rose North Las Vegas, Reno Behavioral, 2 state hospitals, Harmon, Thrive, 3 federal; Grover C. Dils (dead link); South Lyon (not the CMS template).
- `price.price_nv` 18,899,877,888 bytes with indexes; database 18,922,320,355 bytes.
- **Storage comparison** (`storage-experiment.json`): current 18,899,951,616 bytes; normalized ≈6.8 GB estimated (3,131,046 distinct items, 639 payer/plan pairs); **Parquet per facility 281,912,696 bytes**, `round_trip_exact: true`, lookup of HCPCS C1713 (22 facilities, 7,660,778 rows) 76 ms in Parquet vs 805 ms in PostgreSQL. Parquet export took 1,429 s. Proposal recorded as D-033 (awaiting Cooper).

## 2026-11-07 — Storage experiment for national scale (NAT-02), implemented and tested

- `procedurescout_ingest/storage_experiment.py`: for the loaded prices, measures (A) the current PostgreSQL table, (B) a normalized PostgreSQL layout, estimated from exact distinct item and payer/plan counts and sampled column sizes, and (C) compressed Parquet files per facility written with DuckDB (sorted by code, zstd), with an exact round-trip check of all amounts and percentages and a timed lookup of the most widely listed CPT/HCPCS code in Parquet vs PostgreSQL. Intermediate CSVs are gzip-compressed and deleted; Parquet files live in a temporary folder.
- CLI `storage-experiment`; `nv-all` runs it after the price load when `PRICE_LOAD=1` (a failure is printed, never fails the run). Workflow artifact gains `storage-experiment.json`.
- New dependency `duckdb==1.5.6` (released 2026-09-28; 24 MB wheel). A `pyarrow` wheel (55 MB) was downloaded into the build workspace while checking options, before noticing it exceeded the 50 MB ask-first limit; it was deleted and is not used.
- Workspace run on 848,430 synthetic rows (all identical items, so compression there is not representative): experiment 9.0 s, round trip exact, lookup 6 ms Parquet vs 185 ms PostgreSQL.
- Test: `test_storage_experiment_measures_layouts`.

`make lint typecheck test`: `242 passed, 1 warning` (Python 3.13); `/tmp/v312/bin/python -m pytest -q`: `242 passed, 1 warning`.

## 2026-11-07 — All provider types and search by service recorded (D-032); D-031 rules confirmed

Cooper: any medical or wellness provider may list (e.g. medical spas, weight-loss clinics); the home search picks a service (e.g. Botox) across everyone nearby, or narrows to a provider type. Recorded as D-032 (provider types, our own service catalog with units, code links where codes exist), PRV-07, SRCH-06, Q18. The D-031 paid-listing rules are confirmed. No code changed.

## 2026-11-07 — Paid provider listings recorded (D-031)

Cooper: provider listings free for a few months, then paid. Recorded as D-031, PRV-06 and an updated Q17 with proposed safeguards (hospital-file prices always shown, own-error corrections free, paid placements labeled and never re-ranked). D-031 also records why prices are stored rather than read live from hospital files, and that the storage redesign will compare low-cost compressed files in object storage with a full PostgreSQL table. No code changed.

## 2026-11-07 — Scope recorded: national, all provider types, provider-entered prices and hospital corrections

Cooper: the launched site covers every US state and all provider types (hospitals, surgery centers, dental offices, others); providers sign up to enter their own prices, hospitals to correct theirs. Recorded as D-030, requirements NAT-01/02 and PRV-01–05, open questions Q14–Q17, architecture "Price sources". No code changed in this entry. Next engineering step: redesign the price layout for national volume (NAT-02) and include a source field (hospital file / provider-submitted / provider correction) from the start.

## 2026-11-07 — Run #12: first real price load (Nevada, throwaway database); fixes; hosting numbers

Artifact `reference-nv (11).zip` (read 2026-11-07). Home runner and `download_price_files` ticked.

**Measured:** 30 files chosen, 28 downloaded (5,634,642,372 bytes), 27 loaded (South Lyon not in the CMS template). **45,162,271 prices staged**, 156,776 refused. `price.price_nv` 17,691,525,120 bytes with indexes (14,604,566,528 table only); whole database 17,713,877,475 bytes. Nothing published. Largest: UMC 15,536,335 prices (1,674 s), Sunrise 5,399,799, MountainView 3,204,221, the four UHS Las Vegas files 3,152,020 each, Southern Hills 2,908,512. Disk guard not triggered.

New this run: Humboldt back (155,547 prices) and Centennial Hills assigned (3,152,020). Not downloaded: Carson Valley (connection reset again → now also downloaded on Cooper's computer as a fallback, `home_runner_price_sites.csv`), Grover C. Dils (dead link). Spring Valley's cms-hpt.txt timed out from Cooper's computer and was refused by GitHub this run.

Refusals investigated (the first 5 examples per rule, plus the header rows of two files read in the in-app browser on Cooper's computer):
- ~120,000 `bad_amount` for more than 4 decimal places (UHS sub-cent rates, Banner "2781.00000", Mesa View and Mt. Grant float artifacts) → amounts now stored exactly (migration 0010, D-029).
- Seven Hills: all 13,141 rows `no_code` because its columns are named "code |1" → column names compared without spaces around "|".
- Pershing: 13,065 `missing_methodology` because its dollar columns say "Hometown Health Plan NV | All" and its methodology columns "hometown health plan nv|all" → one file's payer/plan columns grouped by label ignoring case and spaces.
- Banner Churchill: 16 `no_code` rows at the very end of the file (left as refused).
- HCA files and Carson Tahoe: ~93,700 prices flagged `drug_unit_unreadable` (drug information dropped, price kept) → now split into `drug_unit_amount_unreadable` / `drug_unit_type_unknown` to see which.

**Hosting numbers** (prices checked 2026-11-07 on the providers' pages; nothing bought): free tiers hold 0.5–1 GB, so Nevada (≈17 GB today) needs a paid database.
- Supabase Pro: $25/month including 8 GB disk and a 1 GB-RAM "Micro" server; extra disk $0.125/GB; 2 GB RAM "Small" $15/month (the plan's $10 credit covers Micro). About $31/month for Nevada as stored today.
- Neon Launch: no minimum; storage $0.35/GB-month (≈$6 for 17 GB) plus compute $0.106 per CU-hour, which sleeps when idle.
- DigitalOcean managed PostgreSQL: from $15/month (1 GiB RAM); extra storage $0.215/GiB-month.
The row layout repeats descriptions and long row references on every price; moving them to a per-item table could roughly halve the size before anything is bought.

Tests after the fixes: `test_spaced_column_names_and_payer_labels_in_different_case`, `test_sub_cent_amounts_kept_and_flagged`, `test_sub_cent_values_kept_exactly`; refusal test now uses 16 decimal places.

`make lint typecheck test`: `241 passed, 1 warning` (Python 3.13); `/tmp/v312/bin/python -m pytest -q`: `241 passed, 1 warning`.

## 2026-11-07 — Price reader (step 2b), implemented and tested; not yet run on real files

- `procedurescout_ingest/price_parser.py`: CMS JSON, CSV tall and CSV wide (v2.x and v3.x) → one `ParsedPrice` per published amount, or a `RejectedRow` with a reason. Exact Decimal amounts via `procedurescout_core.money`; negotiated rates need payer, plan and methodology; primary code by `CODE_PRIORITY`, others kept in `other_codes`; Windows-1252 fallback per CSV cell; drug units and allowed-amount counts validated (D-028, `DATA_NORMALIZATION.md`).
- `procedurescout_ingest/price_load.py`: import run moved through the state machine to `quality_review`, staged dataset version, PostgreSQL COPY into `price.price`. Nothing published.
- `price_files.check_price_files(load=True)`: loads each file in its own savepoint (a broken file is rolled back and reported `load_failed`), stores the load summary in `transparency_file.read_summary.load`, stops loading when free disk falls under 4 GiB, and reports the size of `price.price_nv` and of the database.
- Migration `0009_price_other_codes.py`. `ParsedPrice` gains `drug_unit`, `drug_unit_type`, `other_codes`, `quality_flags`.
- CLI: `PRICE_LOAD=1` turns loading on. Workflow: the same "download_price_files" tick box now also loads; a disk-cleanup step frees space on GitHub's machine first; job limit 300 minutes; new outputs `price-load.csv` (per hospital: prices staged/refused by type and rule, flags) and `price-size.txt` (rows and database size).
- Workspace measurement: 848,430 rows from a 100 MB synthetic JSON loaded in 18.3 s (≈46,000 rows/s), ≈368 bytes per row with indexes (one row per amount; descriptions repeat per row).
- Tests: `tests/test_price_parser.py` (6), `test_load_stages_prices_and_publishes_nothing`, `test_load_skipped_when_disk_is_low`.

`make lint typecheck test`: `238 passed, 1 warning` (Python 3.13); `/tmp/v312/bin/python -m pytest -q`: `238 passed, 1 warning`.

## 2026-11-07 — Run #11: 27 Nevada price files read; Centennial Hills and Spring Valley decisions; TLS 1.3 at home

Artifact `reference-nv (10).zip` (read 2026-11-07), plus `prices-home.zip` and `hpt-home (3).zip` produced by the run.

- Price-file check: 28 chosen, **27 downloaded and read** (5,500,329,327 bytes). New since run #10: Carson Valley (CSV tall, 153,291 rows, 2026-03-27; the dropped-connection retry or a calmer server), **Boulder City and Desert Parkway downloaded on Cooper's computer** (`fetched_via = home_runner`).
  - Boulder City: CSV tall v2.0.0, 51,548 rows, `last_updated_on` 9/30/2025 (**over a year old**), 87 rows with non-UTF-8 bytes (likely a Windows-1252 file: the price reader must handle it).
  - Desert Parkway: CSV wide v3.0.0, 41 rows, 2026-02-05.
  - Still not downloaded: Grover C. Dils (dead Change Healthcare link).
- **Humboldt dropped out this run**: its cms-hpt.txt answered 403 to GitHub (it worked in runs #8–#10), and Cooper's computer failed with "Could not create SSL/TLS secure channel" (Windows PowerShell 5.1 allowed only TLS 1.2). Both home scripts now also allow TLS 1.3 where Windows supports it (parse-checked and re-run under PowerShell 7.4.6; not yet run on Windows PowerShell 5.1).
- **Spring Valley's and Centennial Hills' cms-hpt.txt were read** this time (both matched), but their files were held back: Centennial Hills' file also lists 2 of its ERs; Spring Valley's lists its ER at Blue Diamond plus Spring Mountain Sahara (294010) and Spring Mountain Treatment Center (294011), separate CMS facilities described as its extensions. Cooper's answer "1" → D-027: 3 more co-listed rows, 2 approved `campus_of` relationships, and discovery now gives a file to the parent when the only other named facilities are its approved campus children (`listed_in_parent_file` for each child). New consumer status `in_parent_file`.

Tests: `test_campus_child_listed_with_parent_gives_file_to_parent`; `test_reviewed_relationships_file_is_well_formed` replaces the header-only check now that the file holds reviewed rows.

`make lint typecheck test`: `230 passed, 1 warning` (Python 3.13); `/tmp/v312/bin/python -m pytest -q`: `230 passed, 1 warning`.

## 2026-11-07 — Run #10: Nevada price files downloaded, read and deleted; home-computer fallback for price files

Artifact `reference-nv (9).zip` (read 2026-11-07). Home runner job and `download_price_files` both ticked.

Discovery: 49 entries recorded as co-listed (the 31 approved names; some appear in more than one file), **31 price files assigned to one hospital** (22 in run #9). Probe checked only the 32 Nevada files and skipped 104 out-of-area ones.

Price-file check (`price_file_check`): 29 files chosen (one per hospital; the older Sunrise and MountainView hospital-site links skipped as decided), **25 downloaded and read**, 5,448,758,364 bytes in total, about 3.0 million charge items/rows. Formats: 10 JSON, 10 CSV wide, 4 CSV tall, 1 not the CMS template. Versions: 22 × 3.0/3.0.0, 2 × 2.0.0. UMC (2.4 GB JSON) read in 177 s; Sunrise (788 MB) in 37 s.

- Dates written inside the files: 22 dated 2026, Seven Hills 2025-12-31, **Pershing 2024-10-15 (flagged: over a year old)**.
- **South Lyon**: not in the CMS template (no version, no last_updated_on, no payer columns) → status `not_published`.
- Small encoding problems: 1–3 rows each in the UHS files (Valley, Northern Nevada, Summerlin, Henderson, West Henderson) and Seven Hills contain bytes that are not UTF-8; one ragged row at Valley. The price reader must handle these per row.
- Summerlin, Henderson and West Henderson files are different files (different SHA-256) with the same 210,460 rows: the UHS Las Vegas hospitals publish the same chargemaster.
- **Not downloaded (4)**: Carson Valley (connection reset by peer, transient: now retried once), Boulder City and Desert Parkway (HTTP 403 to GitHub: now downloaded on Cooper's computer, D-026), Grover C. Dils / Lincoln County (assets.changehealthcare.com does not exist: dead link, hospital to be told).
- Still no file: Renown ×2 (429), Incline Village (403), William Bee Ririe (no cms-hpt.txt), Spring Valley + its two behavioral units (403 to GitHub; Cooper's computer could not resolve the name this time), St. Rose North Las Vegas, Reno Behavioral, 2 state hospitals, Harmon, Thrive, 3 federal.

Changes after the run:
- `price_files.http_downloader`: one retry after a dropped connection.
- `price_files.load_home_price_files` + `with_home_fallback`; CLI reads `HOME_PRICE_DIR`. `scripts/fetch_prices_home.ps1` (tested with PowerShell 7.4.6 on Linux against a local test server: ok, 503 then 200 retried, 403 recorded, over-limit file removed, duplicate URLs downloaded once, mixed-case `MRF-URL` lines, missing site reported). `data/reference/home_runner_price_sites.csv` (bchcares.org, desertparkway.com).
- Migration `0008_price_file_via.py`; `price-files.csv` export gains `fetched_via`.
- Workflow: the home job also downloads those price files when `download_price_files` is ticked (non-blocking step, artifact `prices-home` kept 1 day); the load job uses them only when GitHub's download fails.
- Tests: `test_downloader_retries_a_dropped_connection`, `test_load_home_price_files`, `test_home_fallback_only_when_github_fails`, `test_check_records_home_download_and_deletes_it`.

`make lint typecheck test`: `229 passed, 1 warning` (Python 3.13); `/tmp/v312/bin/python -m pytest -q`: `229 passed, 1 warning`.

## 2026-11-06 — Cooper's approvals; price-file download + check (step 2a), implemented and tested

Cooper answered "1, 1, 1" (2026-11-06):
1. Assign the 7 held-back files to their hospitals → `data/reference/hpt_co_listed_locations_reviewed.csv` (31 exact location/hospital pairs from run #9), `match_status = 'co_listed'` (D-023).
2. Use the newer Sunrise/MountainView links → general rule: newest server Last-Modified wins per hospital (D-024).
3. Download the Nevada price files on GitHub's throwaway runner (≈5 GB) → D-025.

Built:
- Migration `0007_price_file_check.py` (co_listed status + `co_listed_with`; `transparency_file.object_store_key` optional and check-result columns; dataset `price_file_check`).
- `discovery.load_co_listed` and the co-listed pass in `discover` (only when the file's matched locations are one hospital and every other name is approved for that hospital; ambiguous names still block). Matched entries from another site's cms-hpt.txt now show their CCN instead of `ccn:?`.
- `procedurescout_ingest/price_files.py`: one file per hospital (newest server date), streamed download with SHA-256 and a 4 GiB limit, format detection, one bounded-memory read (JSON via `ijson` events, numbers as Decimal and only counted; CSV tall/wide), results to `src.transparency_file` + `src.file_facility`, temporary file deleted. Flags: missing/unsupported version, missing/invalid/over-a-year-old `last_updated_on`, ragged CSV rows, non-UTF-8 bytes, Excel, ZIP oddities.
- CLI `price-files`; `nv-all` runs it only when `PRICE_FILE_DOWNLOADS=1`.
- Workflow `reference-nv.yml`: new tick box `download_price_files` (default off), job time limit 150 minutes, new export `price-files.csv`. (Protected file: Cooper copies it.)
- New dependency `ijson==3.6.0` (C backend). Reading a 300 MB synthetic JSON took 9.2 s in the workspace.
- Tests: `tests/test_price_files.py` (10 tests) and 3 co-listed tests in `tests/test_discovery.py`; synthetic fixtures in `tests/fixtures/price_files/`.

`make lint typecheck test`: `225 passed, 1 warning` (Python 3.13); `/tmp/v312/bin/python -m pytest -q`: `225 passed, 1 warning`.

Status: Implemented and Tested (synthetic). Not yet run against real files.

## 2026-11-06 — Size-check run #9 (headers only, nothing downloaded); probe narrowed

Artifact `reference-nv (8).zip` (read 2026-11-06). Home runner job ran.

- 135 price-file URLs were checked; **113 of them were out-of-area or shared** (CommonSpirit and Banner network cms-hpt.txt files list hospitals in other states). The headline `total_reported: 8654.8 MB` therefore overstates Nevada.
- **Nevada files only** (22 assigned + 7 held back), sizes as the servers report them:
  - Sized, assigned (8): UMC 2438.7 MB, West Henderson 168.4, Carson Valley 57.1, Banner Churchill 25.8, Northeastern Nevada 16.6, Seven Hills 8.1, Battle Mountain 1.3, Pershing 0.9 = 2716.9 MB.
  - Held back, sized (7 hospitals): Sunrise 953.2 (hospital-site link) / 788.1 (sunrisehealthinfo.com link), MountainView 576.6 / 471.9, Southern Hills 433.1, Summerlin 168.4, Henderson 168.4, Northern Nevada Medical Center 71.8, Valley 59.5.
  - Size not reported (9): North Vista, Saint Mary's, the 3 Dignity St. Rose campuses, Mt. Grant, Mesa View, Desert View, South Lyon.
  - Failed (5): Carson Tahoe and Humboldt (Craneware API, HEAD answered 404), Boulder City and Desert Parkway (HTTP 403 to GitHub; both cms-hpt.txt files came from the home runner), Grover C. Dils / Lincoln County (assets.changehealthcare.com does not resolve: the published link looks dead).
  - Known Nevada total ≈ 4.9 GB (using the newer Sunrise/MountainView links) plus 9 files of unknown size.
- **Why 7 hospitals are held back**: each file also lists the hospital's own freestanding ERs or clinics ("ER at Green Valley Ranch, an Extension of Henderson Hospital", "SLS - SUNRISE HOSPITAL AND MC", …), which are not CMS hospitals in `ref.facility`. The rule that a shared file is assigned only when every location matches did its job; these need a reviewer's decision.
- **Server dates worth flagging** (Last-Modified header, a server claim, not the file's own `last_updated_on`): South Lyon 2023-11-30, Pershing 2024-10-14, Sunrise and MountainView hospital-site links 2025-01-03 (the sunrisehealthinfo.com links say 2026-10-21).
- Spring Valley and Centennial Hills cms-hpt.txt timed out from the home computer this time (they worked in run #8); dpbh.nv.gov timed out too.

Changes after the run:
- `discovery.probe_sources` now checks only files assigned to one of our facilities or held back with at least one matched entry; out-of-area files are counted as `probe_skipped_out_of_area`, and held-back rows name the matched CCNs.
- `discovery.http_prober` reads GET headers when HEAD returns 404 (pricing APIs such as Craneware may answer only GET).
- Tests updated: `test_prober_reads_headers_without_downloading`, `test_probe_sources_records_sizes`.

`make lint typecheck test`: `212 passed, 1 warning` (Python 3.13); `/tmp/v312/bin/python -m pytest -q`: `212 passed, 1 warning`.

## 2026-11-06 — Price-file size check (no downloads), implemented and tested

Before any price file is downloaded (CLAUDE.md: ask before downloads over 50 MB), the run now asks each known price-file server for headers only.

- Migration `0006_source_probe.py`: `src.source_probe` (method HEAD or GET-headers, status, final URL, Content-Length, Content-Type, Last-Modified, error).
- `discovery.http_prober` (HEAD; if refused or no size, a GET whose body is never read; one retry on 429/5xx) and `discovery.probe_sources`; CLI `probe`; `nv-all` runs it after discovery. Results appear in the rejects export as `probe_ok` / `probe_failed` with size and last-modified per file.
- Tests: `test_prober_reads_headers_without_downloading` (asserts the exact requests made), `test_probe_sources_records_sizes`.

`make lint typecheck test`: `212 passed, 1 warning` (Python 3.13 and 3.12).

## 2026-11-06 — Discovery run #8: live from GitHub + Cooper's computer (all live, no saved copies)

Artifacts `reference-nv (7).zip` and `hpt-home.zip` (read 2026-11-06). Repository confirmed private (lock icon). Self-hosted runner `DESKTOP-69FBOU0`, labels self-hosted/Windows/X64/procedurescout-home, runner 2.338.2.

- **Home runner job on Windows PowerShell 5.1 succeeded**: 29 of 34 sites fetched. Failures there: dpbh.nv.gov 404, renown.org 429, tfhd.com 403, wbrhely.org 403, hghospital.org "Could not create SSL/TLS secure channel" (GitHub's own fetch of hghospital.org worked, so no effect).
- Discovery: 34 sites; 8 refused GitHub (403) and were read from the home runner's live fetch (Boulder City, Mesa View, Spring Valley, Centennial Hills, Desert Parkway, Henderson, Summerlin, Valley Hospital); 4 failed from both networks.
- **33 hospitals matched to a live price-file entry**; 22 price files assigned to one hospital. Desert Parkway now matches (alias approved) and Banner Churchill matched again.
- Not found, by reason: Renown Regional + Renown South Meadows (HTTP 429 to both networks, opens in a normal browser), Incline Village (HTTP 403 to both networks, opens in a browser), William Bee Ririe (no cms-hpt.txt), St. Rose North Las Vegas (not listed), Reno Behavioral (file lists no Reno location), 2 state hospitals (PDF only), Harmon and Thrive (no website), 3 federal (exempt).
- No saved copies were used (`captured_copies_available: 0`); the manual William Bee Ririe link stayed unapproved.

Status: SRC-01 discovery Implemented, Tested, and run against live sources for Nevada (throwaway database). Not Deployed.

## 2026-11-06 — Home-computer fetches (D-021), implemented and tested; then run as #8

- Migration `0005_home_runner.py`: `src.hpt_txt_fetch.fetched_via`.
- `scripts/fetch_hpt_home.ps1`: fetches approved sites' cms-hpt.txt (redirects followed, 429/502/503/504 retried up to 3 times, other errors recorded), writes files byte-for-byte plus `fetches.json`. Tested with PowerShell 7.4.6 on Linux against a local test server: ok, redirect (final URL recorded), 403 (recorded, no file), 429 then 200 (retried), unreviewed and not-found rows skipped, CRLF bytes preserved. The first run found and fixed a file-naming bug. **Not yet run on Windows PowerShell 5.1** (Cooper's computer). PowerShell 7.4.6 (72 MB) was downloaded into the build workspace only for this test; it is not part of the project.
- `discovery.load_home_fetches` + `discover(..., home=...)`; `HPT_HOME_DIR` read by the CLI. Tests: `test_home_runner_fetch_used_when_github_is_refused`, `test_home_runner_failure_is_reported`, `test_no_home_directory_means_no_home_fetches`.
- `.github/workflows/reference-nv.yml`: new optional `home-fetch` job on `[self-hosted, windows, procedurescout-home]`; the `load` job downloads its output and passes it on. Input `use_home_computer` (default on).
- The repository was found to be **public** (2026-11-06); it must be made private before connecting the runner.

`make lint typecheck test`: `210 passed, 1 warning` (Python 3.13 and 3.12).

## 2026-11-06 — Saved copies switched off (D-020); Desert Parkway alias approved

- Cooper: do not use anything saved. All 20 rows in `data/reference/hpt_captured/manifest.csv` (19 approved copies + the pending Renown copy) are now unapproved; the William Bee Ririe manual link is unapproved. Added `data/reference/hpt_captured/README.md` explaining why the files remain.
- Cooper confirmed "Desert Parkway Behavioral Healthcare Hospital" = 294013 (alias approved 2026-11-06).
- Expected effect on the next run: the sites that refuse GitHub's servers (in run #7: Boulder City, Spring Valley incl. the two Spring Mountain hospitals, Centennial Hills, Henderson, Summerlin, Tahoe Forest/Incline Village, Valley Hospital; plus Renown ×2 if it rate-limits again) will be reported as not reachable instead of matched.

`make lint typecheck test`: `207 passed, 1 warning`.

## 2026-11-06 — Discovery run #7 (GitHub Actions)

Artifact `reference-nv (6).zip` (read 2026-11-06). First push failed with GitHub's server-side "fatal error in commit_refs_rules"; it succeeded on retry.

- 34 sites, 167 cms-hpt.txt blocks; **32 hospitals matched to a price-file entry**; 21 price files assigned to a single hospital; William Bee Ririe's hand-entered link loaded (33 hospitals with a known price-file location).
- 7 sites refused GitHub's servers (HTTP 403) and were read from the approved captured copies (Boulder City, Spring Valley, Centennial Hills, Henderson, Summerlin, Tahoe Forest, Valley Hospital); the other 12 captured copies were not needed because the live fetch worked.
- Not matched: Renown ×2 (HTTP 429 even after waiting), Banner Churchill (Banner answered HTTP 502 this time; matched live in run #6), Desert Parkway (name differs by ", LLC"; alias awaiting confirmation), Reno Behavioral (its file lists no Reno location), St. Rose North Las Vegas (no file listed), William Bee Ririe (no cms-hpt.txt; manual link instead), the two state hospitals (PDF only).
- MountainView and Sunrise also appear in sunrisehealthinfo.com's file with different price-file URLs than in their own sites' files; both are stored.

Changes: temporary server errors (502/503/504) are now retried like 429 (`test_temporary_server_error_is_retried`). A captured copy of Renown's cms-hpt.txt (923 bytes, matches the browser's length) and the Desert Parkway alias were added **unreviewed**, so they are not used until Cooper approves.

`make lint typecheck test`: `207 passed, 1 warning` (Python 3.13 and 3.12).

## 2026-11-05 — Browser-check proposals approved

Cooper replied "approve all" (2026-11-05): 22 website rows, 10 aliases, 19 captured cms-hpt.txt copies and 1 manual price-file link now carry `reviewed_by = Cooper`, `reviewed_at = 2026-11-05`. Offline check in a throwaway database (live fetches disabled, captured copies only): 41 approved websites, 19 sites read from captured copies, 20 hospitals matched, 12 price files assigned to a single hospital, 1 manual source loaded. The other sites need the live run. One more name needs confirmation: "Desert Parkway Behavioral Healthcare Hospital" vs CMS "DESERT PARKWAY BEHAVIORAL HEALTHCARE HOSPITAL, LLC" (not added).

`make lint typecheck test`: `206 passed, 1 warning`.

## 2026-11-05 — Browser check of the remaining hospitals (proposals awaiting approval)

With Cooper's permission ("Allow"), Claude used the browser built into the Claude app on Cooper's computer to read public cms-hpt.txt files that refused automated requests from GitHub's servers, and to find the remaining websites. A search engine's "are you human" challenge appeared after the first browser search; it was not answered and searching switched back to the web-search tool. No price files were downloaded.

Found:
- 19 cms-hpt.txt copies saved exactly in `data/reference/hpt_captured/` with `manifest.csv` (source URL, date, who captured; reviewer empty until approved). Byte lengths match the browser's for every copy checked (e.g. Seven Hills 360, NNMC 1,044, Desert Parkway 342).
- Website corrections: Southern Hills → sunrisehealthinfo.com (its old domain redirects there), Henderson → hendersonhospital.com, West Henderson → westhendersonhospital.com, Spring Mountain Treatment Center and Spring Mountain Sahara → springvalleyhospital.com (listed there as extensions of Spring Valley Hospital), the four St. Rose campuses → commonspirit.org, Seven Hills → sevenhillsbi.com.
- New websites for 12 previously not-found hospitals (nnmc.com, mgghnv.org, wbrhely.org, bmgh.org, pershinghospital.org, carsonvalleyhealth.org, hghospital.org, desertviewhospital.com, gcdmc.org, slmcnv.org, desertparkway.com, renobehavioral.com).
- 10 name aliases to confirm (e.g. "Mt. Grant General Hospital", "Lincoln County Hospital District" for Grover C. Dils, "Rose de Lima/San Martin/Siena Hospital").
- 1 hand-entered price-file link (William Bee Ririe: homepage link to an .xlsx; no cms-hpt.txt).
- Still not found: Harmon Hospital (290042), Thrive Behavioral (294016). Problems to note: no price file listed for the St. Rose North Las Vegas campus; Reno Behavioral's cms-hpt.txt lists only out-of-state sister hospitals and its pricing page returned "Access denied" in a normal browser; South Lyon's file is dated 2023; the state psychiatric hospitals publish a PDF only.

Code (tested, synthetic): migration `0004_captured_hpt.py` (fetch rows record `live` vs `captured` with capture provenance enforced; manual sources must carry a review note); `discovery.load_captured_copies` (only approved copies, used only when the live fetch fails); `discovery.load_manual_sources`; CLI `manual-sources`; `nv-all` uses both. Tests: `test_captured_copy_used_only_when_live_fetch_fails`, `test_captured_copy_requires_provenance`, `test_manual_sources`, `test_committed_captured_manifest_matches_files`. `tests/conftest.py` factory now gives its manual source a review note.

`make lint typecheck test`: ruff clean, `Success: no issues found in 25 source files`, `206 passed, 1 warning`. Python 3.12.3: `206 passed, 1 warning`.

## 2026-11-05 — Reviewed aliases and blocked sites

- Cooper confirmed in chat (2026-11-05, "Yes to all") the three cms-hpt.txt names: "University Medical Center of Southern Nevada" → 290007, "Carson Tahoe Regional Healthcare" → 290019, "Mesa View Regional" → 291307. Recorded in `data/reference/facility_aliases_reviewed.csv`; they take effect on the next run.
- Sites that refused automated access (HTTP 403) or had no cms-hpt.txt: web search found public pricing pages for some (Dignity Health `dignityhealth.org/price-transparency`, Tahoe Forest `tfhd.com/shoppable-services/`, Boulder City `bchcares.org/cost-of-care/`) but no direct price-file links. Southern Hills appears on the Sunrise Health system site (`sunrisehealthinfo.com`), so the approved `southernhillshospital.com` may be the wrong place to look. No price-file URLs were recorded by hand; nothing was guessed.

## 2026-11-05 — Phase 2, step 1: first real discovery run (GitHub Actions, run #6)

Artifact `reference-nv (5).zip` (read 2026-11-05). All steps green; Phase 1 counts unchanged (107 address-level locations, 8,770 HCPCS, 768 MS-DRG).

Discovery on the 21 distinct approved sites:
- **9 sites returned a cms-hpt.txt** (57 location blocks): MountainView, Saint Mary's, Sunrise, Banner Health, Carson Tahoe, Mesa View, Northeastern Nevada Regional, North Vista, UMC.
- **6 hospitals matched exactly** by name: MountainView (290039), Saint Mary's (290009), Sunrise (290003), Banner Churchill (291313), Northeastern Nevada Regional (290008), North Vista (290005).
- **4 price files assigned to a single hospital**: Saint Mary's, Banner Churchill, Northeastern Nevada Regional, North Vista. MountainView's and Sunrise's files stay unassigned because the same file is listed for unmatched locations (freestanding ERs, physician groups, "SLS -" departments of other HCA hospitals). That is the intended rule (D-018); the per-file mapping comes in step 2.
- **3 names that need a person's confirmation** (the hospital's own file uses a different name than CMS): "University Medical Center of Southern Nevada" (umcsn.com → 290007), "Carson Tahoe Regional Healthcare" (carsontahoe.com → 290019), "Mesa View Regional" (mesaviewhospital.com → 291307).
- **12 sites gave no file**: HTTP 403 (refused automated access from GitHub's servers) at bchcares.org, springvalleyhospital.com, centennialhillshospital.com, summerlinhospital.com, tfhd.com, valleyhealthsystemlv.com, valleyhospital.net; HTTP 404 (no file at that domain) at dpbh.nv.gov, acadiahealthcare.com, dignityhealth.org; HTTP 429 (rate limit) at renown.org; southernhillshospital.com returned a web page.
- 33 of Banner's blocks are hospitals in other states; correctly left unmatched.

Fix in this change: a 429 answer is retried after the site's Retry-After (or 15 s, then 45 s); 403 and other refusals are recorded and not retried or worked around. Tests: `test_rate_limited_site_is_retried_after_waiting`, `test_forbidden_site_is_not_retried`.

`make lint typecheck test`: ruff clean, `Success: no issues found in 25 source files`, `202 passed, 1 warning`. Python 3.12.3: `202 passed, 1 warning`.

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
