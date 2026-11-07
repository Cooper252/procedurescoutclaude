# Test plan

What is tested and how.

## Current suite (Phases 0–1)

| File | Covers |
|---|---|
| `test_money.py` | Exact parsing, blanks → None, percent/float/negative/garbage rejection, no rounding |
| `test_no_float_money.py` | `float` banned in core and ingest packages |
| `test_state_machine.py` | Python transitions; DB transition table matches; trigger rejects illegal jumps; events logged |
| `test_migration.py` | Downgrade to empty and upgrade to head; single head |
| `test_price_constraints.py` | Every price CHECK; NULL stays NULL; Decimal round trip; CMS count values; all v3.0 code types; CPT license rule; one published dataset per facility |
| `test_payer_matching.py` | No auto-merge (Anthem vs BlueCard); unmapped recording; proposed mappings ignored; uniqueness |
| `test_access_control.py` | API role cannot read fixtures or raw prices or write; published view hides staged data |
| `test_enums_match_db.py` | Python enums equal PostgreSQL enums |
| `test_api.py` | Health and version endpoints |
| `test_reference_facilities.py` | Hospital/ASC parsing and upsert; CSV titles = API keys; unknown types and bad CCNs rejected; rating needs a date; address change clears geocode; NPI conflicts |
| `test_reference_identity.py` | Exact-only name resolution; shared names ambiguous; unreviewed aliases ignored; two systems may share a name; relationship review rules, one campus parent, reversed pairs refused |
| `test_reference_geo.py` | Census relationship/Gazetteer parsing; lookups for one state; geocoder request and response format; address → ZCTA → none preference with state/county validation |
| `test_reference_links.py` | NPPES addresses only when consistent; AHRQ links by CCN, unknown CCNs reported, manual links kept, systems keyed by id |
| `test_reference_codes.py` | HCPCS fixed-width parsing, wrapping, CPT-like codes and modifiers skipped, layout change refused; Table 5 .txt/.xlsx; minimum row guard; CPT text refused |
| `test_discovery.py` | cms-hpt.txt parsing (blocks, case, missing fields, bad URLs); fetcher (redirect, web page, 404, size cap); only reviewed websites used (and DB refusal); discovery matching, sources, failures; reviewed aliases; committed websites file well formed |
| `test_price_files.py` | Price-file check on synthetic files: JSON header and counts, broken JSON, CSV tall and wide, ragged rows, bad bytes, non-template CSV, ZIP and Excel detection, date parsing, newest-link choice, streamed download with hash and size limit, records written and temporary files deleted, stale date flagged, dropped-connection retry, files from Cooper's computer used only when GitHub fails (and deleted after reading), staged load with nothing published and a broken file rolled back, disk-space guard |
| `test_price_parser.py` | Price rows from synthetic JSON, CSV tall (no repeated gross) and CSV wide; explicit refusals (no methodology, no plan, unknown methodology, unknown code type, no code, negative, too many decimals); v2 estimated amounts, drug units, Windows-1252 text, zero amounts, unreadable counts; code-type spellings; spaced column names and payer labels spelled differently within one file; sub-cent amounts kept and flagged |
| `test_reference_common.py` | Committed reviewed-relationships file well formed; header normalization, ZIP parsing, download size cap, zip member choice, PDC paging and count check, load lineage on success and failure |

Price-file fixtures live in `tests/fixtures/price_files/synthetic_*`. Reference fixtures live in `tests/fixtures/reference/synthetic_*` (invented values in the official layouts). Real-file verification: `.github/workflows/reference-nv.yml` (manual).

DB tests run inside rolled-back transactions on `TEST_DATABASE_URL`, rebuilt from scratch each run.

## Planned

Parser fixtures (v2.0–v3.0 JSON, CSV tall/wide, corrupt files, large streamed files), legacy regression cases (plan collapse, code expansion, invalid plan latency, missing-price reasons), estimator numerical cases, frontend and accessibility tests, load tests.
