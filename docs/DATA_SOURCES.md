# Data sources and licensing

Checked 2026-11-04. "Verified" means the source was opened during Phase 0; "Unverified" rows must be confirmed when the phase that uses them starts.

| Source | Use | Licensing / permitted use | Status |
|---|---|---|---|
| [CMSgov/hospital-price-transparency](https://github.com/CMSgov/hospital-price-transparency) (commit 5333564, 2026-06-09) | JSON schemas v2.0.0–v3.0.0, CSV tall/wide templates, data dictionaries | Public, CMS-published | Verified |
| [CY 2026 OPPS/ASC final rule fact sheet](https://www.cms.gov/newsroom/fact-sheets/cy-2026-opps-ambulatory-surgical-center-final-rule-hospital-price-transparency-policy-changes) | v3.0 requirements; effective 2026-01-01, enforced 2026-04-01 | Public | Verified |
| [CMS Validator V2.0 / HPT tools](https://cmsgov.github.io/hpt-tool/) | Reference validator | Public | Unverified (not run yet) |
| Hospital MRFs (via `cms-hpt.txt` at each hospital site root, and transparency pages) | Prices | Published under 45 CFR 180; redistribution of factual price data to be confirmed by counsel | Unverified |
| CMS Provider Data Catalog — Hospital General Information | CCN, type, ownership, ER, star rating | U.S. government work | Unverified (confirm dataset ID in Phase 1; legacy code used `xubh-q36u`) |
| CMS ASC quality reporting data | ASC list + measures | Public | Unverified |
| NPPES NPI registry | Type 2 organizational NPIs | Public, free | Unverified |
| CMS HCPCS Level II quarterly files | HCPCS codes + descriptors | Public | Unverified |
| CMS MS-DRG definitions | DRG codes, titles | Public | Unverified |
| NUBC revenue codes | Revenue code meanings | Licensed by AHA/NUBC; codes appear in MRFs, descriptor reuse needs review | Unverified |
| AMA CPT | Code numbers appear in MRFs | **Descriptors require an AMA license.** Decision 2026-11-04: no license at launch; no AMA descriptor text stored (DB-enforced). Legal review before public launch. Reference: [AMA 2026 distribution pricing](https://compliance.ama-assn.org/hc/en-us/articles/15166274293399-Notice-Standard-CPT-Distribution-Pricing-Schedule-2026) | Decided |
| HHS/ASPE poverty guidelines | Assistance math, versioned per year | Public | Load current year in Phase 4; never hard-code |
| Hospital financial assistance policies | Assistance rules | Public documents; our summaries are ours | Phase 4 |
| U.S. Census ZCTA / Gazetteer | ZIP → coordinates, county (local lookup, no third-party geocoding at search time) | Public domain | Unverified |
| Payer references (NAIC codes, CMS MA contract list, state Medicaid MCO lists) | Canonical payers; MA vs Medicaid distinctions | Public | Unverified |

## Watch list

- PatientRightsAdvocate.org v. AMA (filed 2026-08-13, N.D. Ill.) challenging CPT copyright.
- CMS CY2027 Physician Fee Schedule proposed rule, section II.H, request for comment on CPT licensing (comments closed 2026-09-14).
