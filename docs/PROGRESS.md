# Progress

Status levels: Implemented → Tested → Deployed → Verified in production. Only evidence counts.

## 2026-11-11 — Price-list templates with upload checking (Cooper's idea)
- `procedurescout_core/price_templates.py`, routes `GET /v1/portal/price-template?types=…` (CSV, opens in Excel) and `POST /v1/portal/facilities/{id}/price-upload` (check, then confirm). One file for several kinds of care; a shared service goes in the more specialised section. Each line: ready / skipped (blank price) / problem (shown on its line) / new to our list. Lines with only a code are matched by code. Nothing is sent until there are no problems and the practice confirms; prices then go to the usual review.
- Migration `0023_price_upload_suggestions.py`: `prov.service_suggestion` and a staff queue "New services from price lists" on /admin/providers.
- New kinds: Orthodontist, Oral surgeon (NUCC Dentist specializations); orthodontic consult, retainer, IV sedation, bone graft; braces/aligners and extractions/wisdom teeth/implant posts filed under them; teeth cleaning (adult) now listed for dental offices.
- Portal "Prices" tab: tick your kinds of care, download, upload, see every line's result, confirm (English and Spanish).
- Load workflows: a newer database is accepted (the site can be updated during the week-long all-states run).
- Tests: `test_price_list_template_and_upload` (sections, no duplicates, $ and commas accepted, 3 decimals refused, code match, confirm refused while problems remain, 4 sent for review, 1 suggestion, staff marks it added). `pytest -q` → `360 passed, 1 skipped, 1 warning in 18.31s`; ruff, mypy, tsc clean.

## 2026-11-11 — Nevada is live (first real load), and a search fix
- Run 43046998045 succeeded (1 h 23 min). Price files: 25 chosen, 11 read this run (17,776,924 prices, 0 refused) plus 10 already published by the earlier run, 3 downloads failed, 1 not a price file. Live database 79 MB afterwards (was 6.3 GB of leftovers before `clear-staged`).
- Checked on the live API: hospitals with prices for a brain MRI include University Medical Center ($250 list), Sunrise ($241), North Vista, MountainView, St. Rose (2), Southern Hills (Las Vegas); Saint Mary's, Carson Tahoe, Banner Churchill (Reno area); Northeastern Nevada Regional (Elko). 60 Nevada cities.
- Bug found: a search without a type picked the 50 nearest places, all unpriced offices, so no hospital prices showed in Las Vegas. Places with a published file or a provider price for the service now come first (`search.py`). Test: `test_places_with_prices_are_not_pushed_out_by_nearer_offices`. `pytest -q` → `359 passed, 1 skipped, 1 warning in 20.64s`; ruff clean.
## 2026-11-11 — Specialists, psychiatrists, referral label, more services, unpriced places folded
- Migration `0022_specialties_referral.py`: `ref.provider_type.grouping` and `.referral` ('hmo' / 'none'). 19 new types (psychiatry, dermatology, cardiology, orthopedics, OB-GYN, ENT, gastroenterology, urology, allergy, neurology, endocrinology, rheumatology, pulmonology, nephrology, oncology, pain medicine, sleep medicine, fertility, plastic surgery); 27 NUCC taxonomy rows mapped (spellings are checked against NUCC by the next offices load).
- Search menu grouped (Specialists, Mental health, Cosmetic and weight loss, ...); facility pages say when a referral is usually needed; proper names in English and Spanish.
- 27 new services (cosmetic surgery, psychiatry, fertility, specialist visit, skin check, IUD, hearing aids) with Spanish names and 49 everyday search words ("boob job", "nose job", "lipo", "bbl", "med management").
- Search: places without prices fold under "N more nearby that haven't posted prices".
- Correction to my earlier message: therapy sessions, first therapy visit, GLP-1 programs and telehealth visits were already in the list since 2026-11-08.
- Tests: `test_committed_catalog_files_load_with_review_state` (35 types; psychiatry 'hmo', OB-GYN 'none'). `pytest -q` → `358 passed, 1 skipped, 1 warning in 22.00s`; ruff, mypy, tsc clean.

## 2026-11-11 — First live load: what broke and the fix (D-059)
- Run 1 stopped at the safety check (database address). Run 2 (1 h 50 min): reference data, websites and discovery loaded into the live database (46 hospitals, 68 surgery centers, codes, service list, insurance names, 204 help-paying limits, 80 health centers); then staging a big price file inside the live database made it unavailable (`FATAL: service temporarily unavailable`, after `cannot allocate memory for output buffer`); disk 63% used afterwards.
- Live API log: searches failed with `ValueError: endpoint must look like https://host[:port], got 'https://…r2.cloudflarestorage.com/procedurescout-prices'` — the bucket name on the end of the address. `S3Store` now accepts it (`test_settings_validation`).
- Fix: price rows staged in a throwaway database on the GitHub computer (`WORK_DATABASE_URL`, `prepare-work-db`, `rows=`/`rows_conn=` in `publish.py`, `price_load.py`, `price_files.py`); `clear-staged` frees the live database. Checked locally with two real databases: 1 file published, 2 code summaries in the live database, 0 price rows left in either. Tests: `test_rows_kept_elsewhere_publish_or_are_set_aside`, `test_rows_kept_elsewhere_publish_with_summaries`. `pytest -q` → `358 passed, 1 skipped, 1 warning in 25.18s`; ruff, mypy clean.

## 2026-11-10 — Hosting live (not yet on procedurescout.com); every-state loader
- Cooper signed up for Cloudflare R2 and Render; the Blueprint created the database, API and website. Checked from the browser: API `/healthz` 200, website loads with no sample-data label and reaches the API through `/api`. Database empty until the first load. Status: **Deployed** (onrender.com addresses); data not loaded.
- First live load started: Nevada (`load-state-production.yml`).
- New `.github/workflows/load-all-states.yml`: every state in one run (one job per state, one at a time, a state's failure doesn't stop the rest), plus a monthly refresh on the 1st (price files only). Not run yet.

## 2026-11-10 — Second "Test every state" run (after the fixes)
- `all-states (1).zip`: 50 of 51 states fully ok (was 34). Hospitals with a verified website 1,392 → 2,174 of 5,306 (41%); hospitals with a price link 1,432 → 2,156; files published 109 → 133 of 153 read; download failures 1 → 0; read failures 6 → 0. Connecticut, Iowa, Minnesota now publish 3, 3, 2.
- Louisiana: the hospital is found by search but its most-listed code has no cash, list or insurer dollar amount (not a failure of search; worth a look).
- Remaining gap: 59% of hospitals still have no verified website. Known causes: sites refusing GitHub's computers, names that differ with no usable address in the file header, and hospitals in the DoltHub list but not in CMS's hospital list (DoltHub has 7,231 hospitals; CMS's list gives us 5,306). DoltHub also lists a price-file link for 4,205 hospitals (often old) — a possible next source, checked by the same header-address rule.

## 2026-11-10 — Fixes from the state logs (CA, CT, IA, MN, SC)
- Connecticut (Nuvance) JSON files start with a byte-order mark: now skipped (`price_parser.skip_bom`, used by the check and the reader).
- Iowa files say template version 4.0.0: a note now, not a file problem (every price is still read by field name; 0 of 216,335 refused in the test run).
- Minnesota: a few rows with stray bytes (13 of 151,276; 4,069 of 1.9 million) are a note when at most 1% of rows.
- South Carolina (Prisma Health): the 3 links served ~1 KB each, not price files; the report now shows what the file starts with.
- California: 131 hospitals were refused because the system's list names them differently; new header-address check (D-058, `website_verify.header_address_keys`). 94 sites answered 403 to GitHub's computers (still a limit); 256 DoltHub hospitals aren't in CMS's hospital list.
- Tests: `test_all_states_findings_bom_bad_bytes_and_newer_version`, `test_newer_template_version_is_a_note`, `test_header_address_keys_from_json_and_csv`, `test_a_system_file_listing_the_hospitals_address_verifies_it`. `pytest -q` → `356 passed, 1 skipped, 1 warning in 17.21s`; ruff, mypy clean.
- Next: run "Test every state" again and compare.

## 2026-11-10 — First "Test every state" run (all 51, 3 price files each)
- Result (`all-states.zip`): every state loaded with no failed steps; 5,306 hospitals; cities and nearby search worked in all 51. 34 states fully ok.
- Bug found and fixed: the price read capped rows for the WHOLE search (5,000), so a big hospital with thousands of insurer rates for a code hid nearby hospitals' prices (13 states showed "published prices not found by search"). `price_store.find_prices` now caps per facility and `search.py` asks only for the price types it shows. Test: `test_a_big_hospital_cannot_crowd_others_out_of_a_search`.
- `scripts/state_check.py` now also tries an insurer search (the hospital's most-listed insurer) and tells "hospital missing" apart from "no price of that kind". Checked locally: `search_cash "80", search_list "100.1", search_plan "75.25"`.
- Still open: CT, IA, MN, SC published none of their 3 files (reasons in their state downloads); hospital websites found for 1,392 of 5,306 hospitals (26%), so most hospitals have no price link yet.
- Tests (this session): `pytest -q` → `352 passed, 1 skipped, 1 warning in 20.42s`; ruff and mypy clean.

## 2026-11-10 — Pre-launch check: every state, Cooper's answers, fixes found
- Cooper's answers: first files publish automatically (D-055, live-load default on); domain procedurescout.com (D-057: `render.yaml` domains, `SITE_URL`, `EMAIL_FROM`); Claude confirms state rules with sources (D-056).
- Help paying, all states: `data/reference/coverage_limits.csv` now has 204 rows (51 states + DC x adults, children, pregnancy, marketplace), each with its official source (MACPAC Exhibits 35/36, July 2025, + 5-point disregard; expansion status checked against healthinsurance.org, updated 2026-03-31).
- Nevada uninsured discount (NRS 439B.260/439B.115) confirmed from the Legislature's site and shown on the help-paying page for Nevada (English + Spanish).
- Free all-states test: `.github/workflows/test-all-states.yml` + `scripts/state_check.py` (loads each state into a throwaway database like the live run, reads a few price files, publishes to a temp folder, then asks the real API for cities, nearby places and a priced search; one summary table).
- Fixes found by the review:
  - Website built without `API_URL` silently became the sample-data preview; live builds now stop instead (`next.config.ts`).
  - Help pages assumed Nevada when no place was chosen; facility help used Nevada's poverty amounts for every state (now the facility's own state; matters for Alaska and Hawaii).
  - Price-file size summary measured only Nevada's partition (now every state).
  - Price-file size check re-probed every state on each state's run (now one state).
  - Big states: price files stop cleanly before GitHub's limit (`PRICE_TIME_BUDGET_MINUTES`) and continue on the next run; the live run checks the database version first.
  - Spanish city page said "Precios de Medical"; `/admin` now goes to the review page.
- Checked: Render plan names valid (render.com/docs/compute-plans.md), Hobby workspace has no fee and includes 2 custom domains (render.com/pricing.md).
- End to end on a local throwaway database (synthetic file): load → publish → code index → `state_check.py` → `cities 1, nearby 5, facility_page 200, search_cash "80", search_list "100.1", priced_search_works true`. Site built against that API and walked in English and Spanish: every page 200, no console errors, except expected 404s.
- Tests (this session): `ruff check .` → All checks passed!; `mypy` → Success: no issues found in 63 source files; `pytest -q` → `351 passed, 1 skipped, 1 warning in 20.43s`; `tsc --noEmit` ok; `next build` ok.
- Not done: "Test every state" has not been run yet (Cooper starts it in GitHub); its results decide what else to fix before sign-up.
- Status: Implemented + Tested (synthetic). Not deployed.

## 2026-11-10 — Ready for national loading: websites found automatically, file-by-file publishing, rate limits, all states
- Hospital websites: `website_verify.dolthub_candidates` (DoltHub `standard-charge-files`, 7,143 homepages, CC BY-SA 4.0; only hints) + automatic check by cms-hpt.txt; runs as the `find_websites` step of every state run and as `find-websites`.
- File-by-file publishing (D-054): migration `0021_published_summaries.py`; `publish.write_summaries` on every approval, `publish.prune_published`, code and insurer indexes from summaries, insurance-name matching reads summaries; `check_price_files(after_load=…)`; production mode (`PUBLISH_AS_YOU_GO`, optional `AUTO_PUBLISH_FIRST_FILES`, Q35) commits after each file; `prune-published` command; new workflow `.github/workflows/load-state-production.yml` (writes to the live database and R2; needs secrets).
- Rate limits on the API (`ratelimit.py`: sign-in and review emails 10 per 10 minutes, reports 20 per 10 minutes, other changes 60 a minute, reads 300 a minute, per visitor, in memory only).
- Website lists every state and DC; free-clinic help points to 211 outside Nevada.
- Go-live checklist: `docs/GO_LIVE.md`.
- Tests (this session): `ruff check .` → All checks passed; `mypy` → Success: no issues found in 63 source files; `tsc --noEmit` ok; `pytest -q` → `348 passed, 1 skipped, 1 warning in 16.37s` (new: `test_after_publishing_staged_rows_go_but_index_and_search_remain`, `test_first_files_publish_automatically_only_when_allowed`, `test_publish_as_you_go_hook_runs_after_each_file`, `test_dolthub_candidates_page_through_and_validate`, `test_sign_in_is_limited_per_visitor_and_health_is_not`).
- Not done: the live-load run hasn't run (no hosting yet); the DoltHub list hasn't been queried from a real run (checked by hand: Nevada rows match our reviewed websites).
- Status: Implemented + Tested (synthetic). Not deployed.

## 2026-11-10 — First real office load: Nevada (any-state run, NPPES November 2026)
- Run "Reference data — any state" for NV with offices ticked (report `reference-nv (15).zip`). Every step succeeded.
- NPPES: 9,891,116 rows read; **8,238 Nevada offices added**; 63 NPIs already belonged to hospitals or surgery centers and were not duplicated. All 25 approved taxonomy rows matched the NUCC list (179 codes; no `taxonomy_not_in_nucc`).
- By type (places / with a map location): doctor's office 2,726/2,725; mental health 2,191/2,190; dental 1,364/1,362; physical therapy 583/583; eye care 500/499; chiropractor 429/429; surgery center 185/185 (117 from NPPES + CMS ASCs); urgent care 163/162; laboratory 161/161; podiatry 138/138; hearing 67/67; imaging 61/61; massage 50/50; hospital 46/46.
- Map locations for offices: 7,877 by street address, 355 at the ZIP's center, 6 none.
- Names come from the NPPES file (d/b/a name when given); some read as legal names ("… LLC"); providers can correct them when they claim their page.
- Status: Verified in a throwaway run (nothing kept); not deployed.

## 2026-11-09 — Email, staff logins, reports, stars, billing (off), national offices, any-state run
- Email (D-053): `mailer.py` sends `prov.outbox` through Resend or SMTP, right after each request (background) and by `send-email`; bodies with links cleared after sending; 5 retries within an hour; sent rows deleted after 30 days.
- Review pages (ADM-02, D-053): per-person staff accounts (`prov.staff`, `add-staff`) signed in with the email link + authenticator; shared password only outside production; `/admin/*` reachable through the website.
- Wrong-price reports: `price_reports.py`, `POST /v1/price-reports`, review-page queue, "Report a wrong price" on result details and facility pages; nothing about the person stored.
- Review stars in search results; Sponsored spots returned apart from results (at most 2, labeled).
- Billing (D-051, off): `billing.py` (plans by provider type, Stripe Checkout + customer portal, signed webhooks applied once, Sponsored slots), `bill.listing_shown()` gates the provider's own content only once a fee start date passes; "Plan" tab says listing is free; provider page says "Free to list".
- National offices (D-052): `reference/nppes_offices.py` + `nppes-offices` command (streams the NPPES zip; organizations only; taxonomy map checked against NUCC; NPIs of hospitals/ASCs never duplicated; deactivated → inactive); practices can ask to be added (`listing_requests.py`, account form, review queue). Taxonomy map waits for approval (Q33).
- Any-state pipeline: `.github/workflows/reference-state.yml` (state input, optional offices load); `website_verify.py` + `verify-websites` accept proposed hospital websites only when their cms-hpt.txt names the hospital (D-048); price-file refreshes skip files whose server date and size are unchanged and don't reload identical content.
- Migration `0020_national_offices_billing_staff.py`.
- Accessibility: axe-core 4.10.2 (WCAG 2.0/2.1 A and AA rules) on 11 pages in preview: one problem found (a link inside the account tab list) and fixed; final run reports no violations. Automated checks only; a screen-reader pass by a person is still needed.
- Tests (this session): `ruff check .` → All checks passed; `mypy` → Success: no issues found in 62 source files; `tsc --noEmit` ok; `next build` ok; `pytest -q` → `343 passed, 1 skipped, 1 warning in 14.85s` (new: `test_mailer.py` 3, `test_billing_reports.py` 4, `test_nppes_offices.py` 4, `test_website_verify.py` 1, `test_refresh_skips_a_file_with_the_same_content`, `test_review_pages_need_staff_with_authenticator`). Phone width checked (390 = screen).
- Not done: the date/size skip before download is not covered by a test (the same-content skip is); no real NPPES or Stripe run yet; candidate websites for ~6,000 hospitals still need a source (Q34).
- Status: Implemented + Tested (synthetic). Not deployed.

## 2026-11-08 — Provider price entry: prices, specials, packages (PRV-02/08/09)
- Database: `0019_provider_price_review.py` (a live price stays live while a change waits, `proposed_price`; review fields for specials and packages; published views `prov.published_listing/offer/package/package_item` for the public API; withdrawn specials no longer checked against the regular price).
- Core: `provider_prices.py` (exact dollar parsing, refuses fractions of cents; standard service or official code; sessions; specials checked against the regular price; packages up to 12 pieces; review; specials automatically withdrawn when a lowered regular price makes them no longer lower; public read and search shaping). `search.py` now includes reviewed provider regular prices (labeled `provider_entered`, counted in comparisons per D-042) and each facility's best active special (never in comparisons).
- API: portal routes for prices, specials and packages; `GET /v1/facilities/{id}/provider-prices`; search results carry `special` with its own `regular`; review page queues for prices (changes show old → new and flag more-than-double/half), specials and packages.
- Website: "Prices" tab in the provider account (add/change/remove prices, specials, packages, statuses and review notes); "Prices from the provider" on facility pages; result cards compare a special with the provider's own regular price. English and Spanish.
- Tests (this session): `ruff check .` → All checks passed; `mypy` → Success: no issues found in 56 source files; `tsc --noEmit` ok; `next build` ok; `pytest -q` → `329 passed, 1 skipped, 1 warning in 15.84s` (new: 6 in `tests/test_provider_prices.py`, `test_provider_prices_over_http`). Preview screenshots at desktop and iPhone 13 width (a phone overflow in the package form found and fixed; final width 390 = screen).
- Not done: patients can't yet search providers that aren't in public records (non-hospital providers, NPPES not loaded); the website hasn't run against a live API.
- Status: Implemented + Tested (synthetic). Not deployed.

## 2026-11-08 — Provider homepages, provider account, reviews and counts (D-050)
- Database: `0018_provider_portal.py` (accounts, sign-in links, sessions, memberships, homepage versions, images, reviews, review links, replies, reports, email outbox, daily counts; published views for the public API; new `ps_portal` role, no DELETE on reviews). `scripts/db_init.sql` and `scripts/prod_db_setup.py` create the portal role.
- Core: `portal_auth.py` (email link, authenticator app TOTP, lockout after 5 wrong codes, claiming with automatic domain match or manual check), `provider_pages.py` (homepage drafts reviewed before publishing, image checks for PNG/JPEG/WebP ≤ 2 MB), `reviews.py` (email-confirmed and provider-invited reviews, moderation, replies with a HIPAA warning, reports, public removed count), `provider_stats.py` (daily totals, 0.1° search grid, numbers under 10 hidden, boost estimates). Images stored with `put_media`/`get_media` in both stores.
- API: `portal_routes.py` (public homepage, reviews, images, counting, review flow; portal sign-in, authenticator, claims, homepage editor, uploads, numbers, invites, replies, reports; custom header required on every change), `admin_portal_routes.py` (review page at `/admin/providers`). Searches are counted in the background.
- Website: facility pages show logo, about, hours, languages, access, insurance note, booking and website links, photos and reviews, and count views and clicks; `/review` (write a review from a link); real provider sign-in and `/providers/sign-in/verify`; `/providers/account` (authenticator setup, claiming, Overview numbers + nearby demand + Sponsored-spot estimates, page editor with images, reviews with invite links, replies and reports). English and Spanish (`lib/i18n_portal.ts`). Preview data only in `lib/synthetic_portal_demo.ts`.
- Tests (this session): `ruff check .` → All checks passed; `mypy` → Success: no issues found in 55 source files; `tsc --noEmit` ok; `next build` ok; `pytest -q` → `322 passed, 1 skipped, 1 warning in 13.89s` (new: 19 in `test_provider_portal.py`, 5 in `test_portal_api.py`). Preview screenshots checked at desktop and iPhone 13 width (no horizontal scroll, no browser errors).
- Not done: the website has not been run against a live API in a browser (needs a database with real facilities; synthetic rows may not go into `ref`). No email service yet (Q26), so sign-in and review emails wait in `prov.outbox`. Price entry in the portal is not built. Payments not built (Q30).
- Status: Implemented + Tested (synthetic). Not deployed.

## 2026-11-08 — Hosting prepared (R2 store, Render blueprint); provider pages specified
- `S3Store` in `object_store.py`: uploads published Parquet byte for byte with boto3, refuses to overwrite, validates keys, never shows its secret; the API reads with DuckDB httpfs. `open_store()` picks folder or `s3://` bucket from settings (API, admin page, CLI).
- `render.yaml`: website 0.5c-512mb ($7), API 1c-2g ($25), PostgreSQL 16 0.5c-1g ($19 + storage), plans and prices checked on render.com 2026-11-08. `scripts/prod_db_setup.py` (PostGIS + `ps_api` role, repeatable), `scripts/install_duckdb_extensions.py`, host URLs normalized to psycopg (`db_url.py`), website accepts a bare `host:port` API address. Guide: `docs/DEPLOYMENT_PLAN.md`.
- New packages: boto3/botocore 1.43.126; moto[server] 5.2.5 (tests only).
- Tests (this session): `ruff check .` → All checks passed; `mypy` → Success: no issues found in 49 source files; `tsc --noEmit` ok; `pytest -q` → `298 passed, 1 skipped, 1 warning in 11.27s` (skipped: `test_duckdb_reads_exact_amounts_from_the_bucket`, DuckDB extension download blocked in this sandbox; runs in GitHub Actions).
- Provider homepages, dashboard analytics, reviews and payments readiness written up as a proposal: `docs/PROVIDER_PAGES_SPEC.md` (Q30–Q32). Nothing built.
- Status: Implemented + partly Tested. Not deployed.

## 2026-11-08 — Repository going public (D-049, answers Q29)
- Cooper chose public so national downloads run on free GitHub runners.
- Checked before switching (workspace copy): no keys or tokens in committed files; `.env` is git-ignored; workflow passwords are throwaway CI-only values; run artifacts hold public hospital data only.
- Required setting right after switching (GitHub shows it only on public repositories): Actions → "Require approval for all external contributors" (protects the self-hosted runner on Cooper's computer).
- Switched to public by Cooper (2026-11-08); an unauthenticated clone succeeded. Full history (25 commits, all branches) scanned: no keys, tokens or private-key files; only local development passwords (`postgres_dev_only`, `minio_dev_password`, CI-only values). Commit author email cooper252@gmail.com is visible in history.
- Status: done (public, approval setting on).

## 2026-11-08 — Hosting approved, national scope (D-048)

Cooper approved about $53 a month of hosting (Render + Cloudflare R2) and a national site. No code changed in this entry; plan recorded in D-048, open question Q29 (where national downloads run). Corrected estimate: national Parquet is about 55 GB (0.28 GB for 29 Nevada hospitals), not 15 GB as said earlier; still under $1 a month on R2.


- `procedurescout_ingest/plan_resolver.py` + CLI `resolve-plans` (run in `nv-all` after prices load): a new spelling is matched only when its insurer is already known unambiguously (approved spellings all point to one insurer, or it is the insurer's own name) and the plan text is a plain type (HMO, PPO, EPO, POS, Medicaid, Medicare Advantage, marketplace, all plans) the insurer has a card name for. Recorded as `reviewed_by = "automatic rule (D-047)"`. Everything else is listed in the run report (`unresolved_top`) for Claude to research; it stays findable as written.
- Test: `test_new_spellings_are_matched_only_when_certain`.

`make lint typecheck test`: `294 passed, 1 warning` (3.13); `/tmp/v312/bin/python -m pytest -q`: `294 passed, 1 warning in 10.59s`.


Also added 10 provider networks people see on their cards (MultiPlan, PHCS, First Health, Prominence HealthFirst, Health Services Coalition, Beech Street, Coventry, Three Rivers, Universal Health Network, Nevada Preferred Professionals) as "Network on your card", with 47 hospital spellings. Matched spellings now cover 94.3% of Nevada plan prices in run #15 (was 80.9%); the rest are workers' comp, jails, hospice, behavioral-only, research and catch-all rows, plus 2 with an unclear company, all findable as written.

16 more Nevada spellings matched with evidence in `payer_aliases.csv` notes; 2 new card names (Sierra Health and Life PPO; Sierra Health, one rate for both companies). CLAUDE.md rules 9 and 10 updated for the delegation. Remaining unmatched Nevada spellings are networks, workers' comp, jails/hospice and other non-plan rows, plus 2 with an unclear company; all stay findable as written.

`make lint typecheck test`: `293 passed, 1 warning` (3.13); `/tmp/v312/bin/python -m pytest -q`: `293 passed, 1 warning`.


- Cooper approved 6 of the 12 new Humboldt General spellings (One Health, Silver Summit ×2, CareSource Medicaid, Saint Mary's Health, TriWest); added "Saint Mary's Health Plan / All plans". The other 6 stay out (state not stated, networks, workers' comp, unclear company).
- `ref.payer_index` (migration 0017) rebuilt with the code index; `search(payer_raw=...)` shows negotiated rates published under exactly that spelling (validated against the index, rule 12); `GET /v1/payers/suggest`; search param `payer`.
- Website: "Don't see your plan? Search the insurance name as hospitals write it" under the plan picker, with a labeled note on results.
- Test: `test_any_published_insurer_name_can_be_searched_as_written`.

`make lint typecheck test`: `293 passed, 1 warning` (3.13); `/tmp/v312/bin/python -m pytest -q`: `293 passed, 1 warning`. Website `tsc` clean, build succeeded, insurer-name search walked at 390 px without horizontal scroll.


Every step succeeded. Highlights from `reference-nv-report.txt`:
- `hrsa_health_center_sites`: 80 Nevada health center sites loaded, all with a location (the column names guessed from HRSA's published layout matched).
- `service_catalog`: 202 services, 161 synonyms, 16 provider types, 2 approved packages (3 medical bundles still proposed), 159 card-name plans, 431 approved hospital spellings (11 payer spellings shared by several companies), 4 coverage limits approved, 13 assistance policies still proposed.
- Prices: 29 of 31 files loaded, 48,972,607 prices staged, 16 refused (same as run #13); Parquet round trip exact, lookup 81 ms vs 418 ms.
- `payer-plan-names.csv`: 639 spellings, 12 new since run #14 (all Humboldt General Hospital, whose file changed); approved aliases cover 80.9% of plan prices. The 12 new spellings need review (Q24).
- The code index was not built in this run because nothing is published in the throwaway database; it builds after each approval or automatic publish.


- Migration `0017_code_index_provider_packages.py`: `ref.code_index` (API read), provider prices by approved service or official code with `quantity`, `prov.package` and `prov.package_item` (trigger: pieces must be approved services or official codes).
- `procedurescout_ingest/code_index.py` + CLI `code-index` (also run after `approve` and `auto-publish`).
- `search.suggest` adds billing codes (by number or by hospital wording); `search()` returns `code_description` for code searches. API: suggestion `kind`, `code_system`, `code`; search `code_description`.
- Website: code suggestions ("CPT 70551 · …", tagged "billing code"); results by code show "As hospitals describe it".
- Tests: `tests/test_code_index.py` (2).

`make lint typecheck test`: `292 passed, 1 warning` (3.13); `/tmp/v312/bin/python -m pytest -q`: `292 passed, 1 warning in 8.67s`. Website `tsc` clean, build succeeded; typing "7055" suggested CPT 70551 and the code search showed results with the hospital wording (preview data).


Cooper approved: the standard service list (184 new services, 131 synonyms, 5 provider types; all now reviewed_by Cooper), the two dental packages (the 3 medical bundles still wait for a clinician), and the 4 Nevada coverage limits. Website: the "Full price" choice is gone from search and the bundle builder; it stays in Details and the bill steps; "No cash price published" is shown where there is none. Tests updated to the approved files.

`make lint typecheck test`: `290 passed, 1 warning` (3.13); `/tmp/v312/bin/python -m pytest -q`: `290 passed, 1 warning`. Website `tsc` clean, build succeeded, no horizontal scroll at 390/1280 px.


- Migration `0016_help_paying_sources.py`: `ref.health_center` (HRSA sites, API read) and `ref.coverage_limit` (proposed until reviewed), dataset `hrsa_health_center_sites`.
- `reference/health_centers.py` + CLI `health-centers` (run in `nv-all`): loads HRSA's "Health Center Service Delivery and Look-Alike Sites" CSV for the state (active sites, location). The workspace cannot reach data.hrsa.gov (proxy 403), so the file is fetched in the GitHub run; columns are found by name and the step stops with the headers it saw if a required one is missing. **Not yet run on the real file.**
- `data/reference/coverage_limits.csv` (proposed): Nevada adults Medicaid up to 138%, children (Medicaid or Nevada Check Up) up to 205%, pregnancy up to 205% (DWSS MAGI chart effective 4/1/2025), marketplace premium tax credit 138 to 400% (KFF: enhanced credits ended after 2025). `catalog.load_coverage_limits`; `assistance.coverage` turns approved limits into dollars for the household; the help check returns `coverage`.
- API: `GET /v1/health-centers/near`.
- Website help page: "You may also qualify for" (programs with dollar limits and apply links), community health centers near you (call, directions, website), free and charitable clinics (Nevada 211 link).
- Tests: `tests/test_help_paying.py` (4), nv-all step list updated.

`make lint typecheck test`: `290 passed, 1 warning` (3.13). Website `tsc` clean, build succeeded; help page walk-through at 390 px (2 people, $25,000: three Medicaid lines, two sample centers, 211 link), no horizontal scroll.


- Migration `0015_master_catalog_offers.py`: `ref.procedure.includes`, `ref.procedure_provider_type`, six new units, schema `prov` with `listing_price` and `offer` (triggers: only approved services can be priced; a special must be lower than the regular price). API role has no access to `prov`.
- `scripts/catalog_proposal.py` added **184 proposed services** (dental, chiropractic, massage, physical therapy, med spa, IV, weight loss, doctor and urgent care visits, ER levels, shots, labs, imaging, heart and sleep tests, eye and hearing care, surgery, mental health), each with what it includes and who offers it, plus 131 proposed synonyms and 5 proposed provider types (massage therapy, mental health, eye care, hearing care, podiatry). Two proposed dental packages in `bundles.csv`. All unreviewed (rule 10); Cooper's 18 approved services are unchanged.
- `catalog.load_services` reads the optional `includes` and `provider_types` columns.
- `procedurescout_core/offers.py`: rules, exact price with a special, plain wording.
- Website: "List price" is now "Full price" with an explanation; provider results show "Regular price" with a labeled special underneath; units for the new kinds of prices.
- Tests: `tests/test_catalog_offers.py` (5).

`make lint typecheck test`: `286 passed, 1 warning` (3.13); `/tmp/v312/bin/python -m pytest -q`: `286 passed, 1 warning`. Website `tsc` clean, `npm run build` succeeded, special shown on the sample dentist at 390 px without horizontal scroll.


- API: `GET /v1/places/cities?state=` and `GET /v1/places/city/{state}/{slug}` (cities with active geocoded facilities; center = center of their facilities). Core: `procedurescout_core/places.py`. Test: `test_city_places`.
- Website, rendered on the server for search engines: `/prices` (cities + ZIP box), `/prices/{state}`, `/prices/{state}/{city}` (services), `/prices/{state}/{city}/{service}` and `/prices/zip/{zip}/{service}` (published cash prices within 25 miles, typical range, places with no price, disclaimer, free-care link, FAQ with structured data built only from the published prices, links to other services and nearby cities). `sitemap.xml` lists every city × service page; `robots.txt` and page `noindex` block indexing in preview mode so sample data is never indexed.
- Results page: distance (5/10/25/50/100 miles), provider type and sort (lowest price / nearest; exact decimal comparison, no floats) filters; "search N miles" steps up when nothing is near.

Checks run here: `make lint typecheck test`: `281 passed, 1 warning` (3.13); `/tmp/v312/bin/python -m pytest -q`: `281 passed, 1 warning`. Website: `tsc` clean; `npm run build` succeeded; Playwright: city page, ZIP box → ZIP page, 5-mile filter (2 places) and nearest-first sort at 390 and 1280 px, no horizontal scroll, no console errors; unknown city or service returns 404.


Cooper answered all three questions in writing ("1- 1, 2- 1, 3- 1"): one-for-all rates labeled, employer and union plans in the picker, high + medium proposals approved. `payers.csv` (159) and `payer_aliases.csv` (431) now carry reviewed_by Cooper, 2026-11-08. Test renamed back to `test_committed_plan_names_load_approved`.

## 2026-11-08 — One-for-all plan rates labeled (D-041); plan names waiting for approval

- Correction: Cooper's "1" answered only the first of three questions (the other two were not shown to him). The plan names were first committed as reviewed by Cooper in error; they are now **unreviewed** and unused until he approves (rules 9, 10).
- `data/reference/payers.csv` (159 card names) and `payer_aliases.csv` (431 hospital spellings) from the high/medium proposals, no reviewer yet.
- `plans.all_plans_spellings` + `search.py`: an insurer's one-for-all rate is used only for its commercial HMO/PPO/EPO/POS/HDHP plans, only where the plan has no rate of its own, and flagged (`FacilityResult.all_plans_rate`; API `plan_rate_is_all_plans`, per price `plan_match`).
- `catalog.load_payer_aliases`: a payer spelling shared by several companies keeps its first payer alias (`payer_spelling_shared`).
- Website: the plan picker groups plans by insurer; a result using a one-for-all rate is labeled "All <insurer> plans" with a note, and the details table tags those rows. Preview data adds "Sample Health EPO" to show it.
- Tests: `test_all_plans_rate_is_used_only_when_the_plan_has_none_and_is_labeled`, `test_api_labels_all_plans_rates`, `test_committed_plan_names_wait_for_review`.

`make lint typecheck test`: `280 passed, 1 warning` (3.13); `/tmp/v312/bin/python -m pytest -q`: `280 passed, 1 warning`. Website: `tsc` clean, `npm run build` succeeded, no horizontal scroll on 10 pages at 390 px.


Run #14's `payer-plan-names.csv`: 626 payer + plan spellings (344 payer spellings) across 29 hospitals, 40,164,770 prices with a payer. `scripts/draft_plan_names.py` drafted a proposal for every spelling (`data/reference/proposed/plan_names_proposed.csv`; review copy `plan-names-review.xlsx` sent to Cooper): 163 card names (insurer + plan as on a card) covering 83.0% of those prices; the rest are networks, doctor groups, workers' comp, jails, hospice, specialty-only contracts, out-of-state Blue plans and test rows, kept out of the picker. Confidence: high 53.8% of prices, medium ("one rate for all of the insurer's plans") 28.4%, low 1.9% ("Sierra" with no company). **All proposed; nothing loaded into `payers.csv` / `payer_aliases.csv` until Cooper approves** (rules 9, 10).


- API: `GET /v1/facilities/{id}` (details; website only when reviewed) and `GET /v1/facilities/{id}/prices?service=` (every published price at one facility under the service's approved codes; unapproved services refused, nothing guessed when no file). Core: `procedurescout_core/facilities.py`. Test: `test_facility_page_endpoints`.
- Website: `app/facility/[id]/page.tsx` (call, directions, emergency room, Medicare rating where published, help paying here in dollars, prices grouped cash / plans / list with codes, whole-procedure links, how we got these prices, claim link); result names link to it. `app/bundles/page.tsx` (pick a procedure and a place, required pieces locked, optional pieces as checkboxes, each piece's published price or "not published here", running total marked complete or missing pieces). `app/learn/page.tsx` with `lib/learn.ts` (7 short guides, EN/ES; the No Surprises Help Desk number and Good Faith Estimate timing checked against cms.gov). Home links to both; footer and phone menu link Learn.
- Preview data adds sample facility details, sample bundles shaped like `bundles.csv`, and sample estimates (`lib/synthetic_demo.ts`). Live bundles stay empty until the proposed bundles get clinical review.

Checks run here: `make lint typecheck test`: `277 passed, 1 warning` (3.13); `/tmp/v312/bin/python -m pytest -q`: `277 passed, 1 warning`. `npx tsc --noEmit` clean; `npm run build` succeeded (13 pages). Playwright: results → facility page → colonoscopy bundle → tick biopsy; birth bundle via ZIP and place picker; Learn; at 390 and 1280 px, no console errors.


Cooper asked for a provider login and disclaimers.
- `apps/web/app/providers/page.tsx` (For providers: claim, verification, posting prices, corrections, rules, "free to start") and `app/providers/sign-in/page.tsx` (sign-in screen). **Provider accounts are not built**: the sign-in form is disabled and says accounts are not open yet; nothing is sent. "Provider sign in" is in the header, the phone menu and the footer.
- Disclaimers: `lib/legal.ts` with `app/disclaimer`, `app/terms`, `app/privacy` (English and Spanish), each marked "Draft, pending legal review" (Q25). Short disclaimer in every footer; "Before you go" box under every result list (not a quote, other bills, insurance cost sharing, Good Faith Estimate right); the help-paying results say the check is not an application or decision.
- Header switches to the menu button below 1,200 px so the longer Spanish labels never overflow (checked at 920/1100/1200/1280/1440 px in both languages: no horizontal scroll).

Checks run here: `npx tsc --noEmit` clean; `npm run build` succeeded (11 pages). Playwright screenshots of the new pages at 390, 1000 and 1280 px with no console errors. No Python code changed.


Implemented in `apps/web` (Next.js 15.5.28, React 19.3.1, TypeScript 5.9.3, no other dependencies):
- Pages: home (`app/page.tsx`: search with suggestions, ZIP or "use my location", provider-type choice, popular searches, free-care panel in dollars, "Already got a bill?", trust strip), results (`app/search/page.tsx`: cash / my insurance / list switch, plan picker, typical range, one big price per place, badges, change since last file, details table with codes, places with no published price listed separately), help paying (`app/help-paying/page.tsx`: household size, income, ZIP → each nearby hospital "free care likely / discount likely / ask them", other help), bill help (`app/bill/page.tsx`), how we get prices (`app/how-it-works/page.tsx`).
- Every page: free-care banner, emergency line, English/Español switch (`lib/i18n.ts`; Spanish needs a native-speaker review), footer with sources.
- Money shown with string/BigInt arithmetic only (`lib/money.ts`); income and household size stay in memory, never in a URL or storage; only the language choice is remembered.
- Preview mode: without `API_URL` the site answers from `lib/synthetic_demo.ts` ("Sample …" facilities, made-up prices) with a "Preview: sample data" bar on every page. With `API_URL` it calls the API through `/api` (Next.js rewrite).
- API additions: `GET /v1/places/zip/{zip5}` (ZIP centre from Census ZCTA) and `GET /v1/facilities/near` (nearest facilities, no prices; for the help-paying check); `search.nearby()`.
- Cooper approved the 30 everyday search words (`service_synonyms.csv`, Q23 resolved).

Checks run here: `npx tsc --noEmit` clean; `npm run build` succeeded (all 6 pages, first load 111–124 kB). Playwright walked home → suggestions → results → details → insurance switch, home free-care panel → help-paying check, bill page, Spanish results, at 390 px and 1280 px with no console errors (screenshots sent to Cooper). Python: `make lint typecheck test`: `276 passed, 1 warning` (3.13); `/tmp/v312/bin/python -m pytest -q`: `276 passed, 1 warning` (`test_zip_lookup`, `test_facilities_near`, `test_committed_synonyms_load_approved`).

Not done / not verified: the website has only been run in preview mode; it has not been run against the API with real data, has no automated browser tests in CI, and is not deployed. Still to build: facility page, price details page, bundle builder, service-by-city pages, Learn, compare tray, accessibility audit.

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
