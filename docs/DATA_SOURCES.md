# Data sources and licensing

Checked 2026-11-04. "Verified" means the source was opened during Phase 0; "Unverified" rows must be confirmed when the phase that uses them starts.

| Source | Use | Licensing / permitted use | Status |
|---|---|---|---|
| [CMSgov/hospital-price-transparency](https://github.com/CMSgov/hospital-price-transparency) (commit 5333564, 2026-06-09) | JSON schemas v2.0.0–v3.0.0, CSV tall/wide templates, data dictionaries | Public, CMS-published | Verified |
| [CY 2026 OPPS/ASC final rule fact sheet](https://www.cms.gov/newsroom/fact-sheets/cy-2026-opps-ambulatory-surgical-center-final-rule-hospital-price-transparency-policy-changes) | v3.0 requirements; effective 2026-01-01, enforced 2026-04-01 | Public | Verified |
| [CMS Validator V2.0 / HPT tools](https://cmsgov.github.io/hpt-tool/) | Reference validator | Public | Unverified (not run yet) |
| Hospital MRFs (via `cms-hpt.txt` at each hospital site root, and transparency pages) | Prices | Published under 45 CFR 180; redistribution of factual price data to be confirmed by counsel | cms-hpt.txt format per the CMS TXT file FAQ (fields location-name, source-page-url, mrf-url, contact-name, contact-email; file at the root of the domain hosting the MRF; redirects allowed). Seen live on 7 Nevada sites 2026-11-05 via the research tool. Price files not yet downloaded. |
| Hospital websites (`data/reference/facility_websites.csv`) | Where to look for cms-hpt.txt | Public websites | 28 approved by Cooper 2026-11-05; 15 not found |
| CMS Provider Data Catalog — Hospital General Information, dataset `xubh-q36u` | CCN, type, ownership, ER, star rating | U.S. government work | Verified 2026-11-04: metastore (modified 2026-07-22) and datastore schema; 46 NV rows reported. Data not yet loaded (workspace network blocked). |
| CMS PDC — ASC Quality Measures - Facility, dataset `4jcv-atw7` | ASC list (10-char CCN, NPI, city, ZIP; no street address) | Public | Verified 2026-11-04: schema; 69 NV rows reported (data year 2024, modified 2025-12-16). Only ASCQR participants. |
| NPPES NPI Registry API v2.1 (`npiregistry.cms.hhs.gov/api/`) | ASC street addresses, taxonomy | Public, free | Verified 2026-11-04: response shape (`addresses[].address_purpose = LOCATION`). Rate limits unverified. |
| CMS HCPCS Level II quarterly files — October 2026 Alpha-Numeric HCPCS File (`cms.gov/files/zip/october-2026-alpha-numeric-hcpcs-file.zip`, updated 2026-09-23) | HCPCS codes + descriptors | Public | Link verified 2026-11-04; record layout from CMS `2020-hcpcs-record-layout.txt`. File contents not yet opened. |
| CMS FY2027 IPPS final rule Table 5 (`cms.gov/files/zip/fy2027-ipps-fr-table-5.zip`, final rule + correction notice) | MS-DRG v44 codes, titles | Public | Link verified 2026-11-04; contents not yet opened. Grouper v44 for FY2027 is our assumption from the yearly sequence (v43 = FY2026) — confirm when the file is opened. |
| NUBC revenue codes | Revenue code meanings | Licensed by AHA/NUBC; codes appear in MRFs, descriptor reuse needs review | Unverified |
| AMA CPT | Code numbers appear in MRFs | **Descriptors require an AMA license.** Decision 2026-11-04: no license at launch; no AMA descriptor text stored (DB-enforced). Legal review before public launch. Reference: [AMA 2026 distribution pricing](https://compliance.ama-assn.org/hc/en-us/articles/15166274293399-Notice-Standard-CPT-Distribution-Pricing-Schedule-2026) | Decided |
| HHS/ASPE poverty guidelines | Assistance math, versioned per year | Public | Load current year in Phase 4; never hard-code |
| Hospital financial assistance policies | Assistance rules | Public documents; our summaries are ours | Phase 4 |
| U.S. Census 2026 Gazetteer, ZCTA national file (`www2.census.gov/.../2026_Gazetteer/2026_Gaz_zcta_national.zip`) | ZCTA internal point, land area | Public domain | Link and record layout verified 2026-11-04 (GEOID, GEOIDFQ, ALAND, AWATER, ALAND_SQMI, AWATER_SQMI, INTPTLAT, INTPTLONG). First real load 2026-11-05 showed the file is not tab-delimited; loader now detects the delimiter. |
| U.S. Census 2020 ZCTA–county relationship file (`tab20_zcta520_county20_natl.txt`) | County names/FIPS; ZCTA primary county | Public domain | Column layout verified 2026-11-04 (census.gov record layout page). Delimiter assumed pipe; the loader detects it. |
| U.S. Census Geocoder batch API (`geocoding.geo.census.gov/geocoder/geographies/addressbatch`, benchmark `Public_AR_Current`, vintage `Current_Current`) | Facility coordinates + county FIPS at load time | Public, no key | Input format and 10,000-row limit verified from Census docs. Live: HTTP 502 from GitHub Actions in runs #3 and #4 (2026-11-05); the one-address endpoint (`/geocoder/geographies/address`, JSON) is now the fallback, not yet seen live. |
| AHRQ Compendium of U.S. Health Systems — hospital linkage file (newest seen: 2023) | Hospital → health system | Public (AHRQ) | Variables verified from the 2022 technical documentation. File URL unconfirmed. |
| Payer references (NAIC codes, CMS MA contract list, state Medicaid MCO lists) | Canonical payers; MA vs Medicaid distinctions | Public | Unverified |

## Watch list

- PatientRightsAdvocate.org v. AMA (filed 2026-08-13, N.D. Ill.) challenging CPT copyright.
- CMS CY2027 Physician Fee Schedule proposed rule, section II.H, request for comment on CPT licensing (comments closed 2026-09-14).
