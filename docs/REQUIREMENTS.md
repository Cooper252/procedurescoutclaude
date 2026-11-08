# Requirements

Functional requirements with IDs used in `FEATURE_MATRIX.md`. Priority: Must / Should / Could.

**Scope (Cooper, 2026-11-07):** the launched product covers every US state: all hospitals, surgery centers, dental offices and any other medical or wellness provider (medical spas, weight-loss clinics, ...). People search by service (e.g. Botox) or by provider type (D-032). Nevada is the pilot. Providers can sign up to enter their own prices (to compete with hospital prices), and hospitals can sign up to correct their own prices so that what is shown is accurate. See D-030.

| ID | Area | Requirement | Priority | Phase | Acceptance check |
|---|---|---|---|---|---|
| FND-01 | Foundation | Repo, docs, local env, CI | Must | 0 | `make check` green; CI workflow present |
| FND-02 | Foundation | Canonical schema with integrity constraints | Must | 0 | Migration round-trip test passes |
| FND-03 | Foundation | Exact Decimal money parsing | Must | 0 | Money tests pass; float ban test passes |
| FND-04 | Foundation | Import state machine enforced in code and DB | Must | 0 | Transition tests pass |
| FAC-01 | Facilities | Import CMS Hospital General Information | Must | 1 | All NV hospitals present; count reconciles to source |
| FAC-02 | Facilities | Geocode facilities (PostGIS) with source recorded | Must | 1 | 100% NV facilities geocoded |
| FAC-03 | Facilities | Aliases, health systems, campus relationships | Must | 1 | HCA/UHS NV campuses resolved without false merges |
| FAC-04 | Facilities | ASC import, flagged separately | Should | 1 | ASCs labeled; no hospital-style MRF claim |
| REF-01 | Codes | HCPCS II, MS-DRG, revenue code, ICD-10 references, versioned | Must | 1 | Loaded with version + effective date |
| REF-02 | Codes | CPT codes without AMA descriptors | Must | 0–1 | DB rejects unlicensed CPT descriptors (tested) |
| REF-03 | Codes | Plain-English names, synonyms, disambiguation, reviewed | Must | 3 | 50 top terms map to reviewed code sets |
| SRC-01 | Discovery | cms-hpt.txt + website discovery | Must | 2 | Every NV hospital has a source or documented "not found" |
| SRC-02 | Discovery | URL, status, size, hash, reported date, schema version stored | Must | 2 | Fields non-null per downloaded file |
| ING-01 | Ingestion | Streaming parsers: JSON v2.x/v3.0, CSV tall/wide, ZIP | Must | 2 | 5 GB fixture parsed under 2 GB RAM |
| ING-02 | Ingestion | Validation with malformed-row reports | Must | 2 | Corrupt fixtures produce errors, never silent drops |
| ING-03 | Ingestion | Checkpoints, retries, idempotency | Must | 2 | Re-run of same file gives identical dataset hash |
| ING-04 | Ingestion | Staged publication + rollback | Must | 2 | Failed import leaves published version unchanged |
| NRM-01 | Normalization | Raw→canonical payer/plan with match type | Must | 2 | Anthem ≠ BlueCard regression passes |
| NRM-02 | Normalization | Methodology preserved; percentages never stored as dollars | Must | 0–2 | DB constraints tested |
| SRCH-01 | Search | Guided flow: location → payment → carrier → plan → procedure | Must | 3 | Back navigation preserves selections |
| SRCH-02 | Search | One row per distinct plan rate | Must | 3 | Plan-collapse regression passes |
| SRCH-03 | Search | Missing-price reason codes | Must | 3 | Every no-price row has one reason code |
| SRCH-04 | Search | Provenance panel per price | Must | 3 | Price links to file, date, raw payer/plan, raw code |
| SRCH-05 | Search | Whitelisted filters, bounded queries | Must | 3 | Invalid plan → 422 in < 50 ms, zero price reads |
| FA-01 | Assistance | Versioned policies + poverty guidelines by year | Must | 4 | Each NV hospital has policy URL or "not found" |
| FA-02 | Assistance | Potential-assistance check | Should | 4 | Matches hand-computed examples; never says "eligible" |
| EST-01 | Estimator | Rules engine for deductible, coinsurance, copay, OOP max | Must | 5 | 30+ documented cases pass |
| EST-02 | Estimator | "Cannot estimate" when essentials missing | Must | 5 | Missing allowed amount → no estimate |
| BUN-01 | Bundles | Reviewed bundle templates, no double counting | Should | 6 | Packaged components never summed |
| ADM-01 | Admin | Coverage, ingestion, validation, mapping dashboards | Must | 2–3 | Per-file state and errors visible |
| ADM-02 | Admin | Mapping review queue, audit trail, MFA | Must | 2 | Every mapping change audited |
| SEC-01 | Privacy | No account for search; no ad trackers; minimal logs | Must | 3 | Privacy checklist passes |
| A11Y-01 | UX | WCAG 2.2 AA | Must | 3 | axe-core zero serious issues + keyboard walkthrough |
| NAT-01 | National | Every US state: hospitals (CMS), ASCs, and other providers (dental offices, imaging, labs, clinics) from public registries such as NPPES | Must | 7 | Facility counts reconcile to each source per state |
| NAT-02 | National | Price storage and search sized for national data (Nevada pilot: 45.2M rows, ≈17 GB; national extrapolation in the billions of rows) | Must | 2–7 | Measured load and query times at a stated national volume before launch |
| PRV-01 | Providers | Provider accounts with verified authority to speak for a facility (e.g. NPI/CCN match, work email on the facility's approved website domain, manual review), MFA | Must | 9 | Unverified accounts cannot change anything public |
| PRV-02 | Providers | Providers without a CMS file (ASCs, dental, etc.) enter their own prices: code, price type, cash or payer/plan, effective date, attestation | Must | 9 | Shown labeled "submitted by the provider" with date; never mixed unlabeled with hospital-file prices |
| PRV-03 | Providers | Hospitals correct or annotate their published prices | Must | 9 | The original file value is kept; the correction is labeled, dated, attributed and audited; nothing is overwritten |
| PRV-04 | Providers | Terms of use, attestation and full audit trail for every provider change | Must | 9 | Every change has who, when, before, after; counsel-reviewed terms (Q1) |
| PRV-05 | Providers | Review and anomaly checks on provider-entered prices (new accounts, large changes, $0) | Must | 9 | Flagged changes wait for review before publishing |
| PRV-07 | Providers | Any medical or wellness provider can list (med spas, weight-loss clinics, imaging, labs, urgent care, chiropractors, ...); each tagged with reviewed provider types | Must | 9 | Provider type filter returns only providers with that type |
| SRCH-06 | Search | Home search by service (our own catalog, e.g. "Botox") across all provider types near the person, with an optional provider-type filter (e.g. medical spas) | Must | 3/9 | Results never mix units (per unit vs per area) without saying so |
| PRV-06 | Providers | Paid listings of provider-entered prices after a free period (D-031); payment never changes ranking or labels; paid placements labeled "Sponsored" | Should | 9 | Billing status cannot affect search order or labels (tested) |
| UX-01 | Site | Pages and layouts in `SITE_DESIGN.md` §1–2 (home with free-care panel, results with one headline price and badges, service-by-city, facility, price details, bundle builder, help paying, already got a bill, Learn, providers) | Must | 3 | Each page reachable in two taps from home; free-care banner on every page |
| UX-02 | Site | Ease-of-use rules in `SITE_DESIGN.md` §3 (synonyms and misspellings, plan picker by card name, remembered choices in the browser, no dead ends, plain words, Spanish) | Must | 3 | Usability test with 5 people finds a price and a free-care result unaided |
| PRC-01 | Pricing | Headline "your price", typical local range (shown with 5+ prices), price confidence and freshness | Must | 3 | Never mixes price types or units in a comparison (tested) |
| PRC-02 | Pricing | Outlier holds, price history across refreshes, Medicare reference price (labeled) | Should | 3 | Outlier fixtures held; history shows change between two datasets |
| HELP-01 | Help | Medicaid/marketplace nudges, community health centers and free clinics, "already got a bill?" tools, application checklists | Must | 3–4 | Each nudge cites a reviewed official limit |
| EXP-01 | Export | CSV/XLSX/Parquet async exports | Could | 8 | Large export runs as a job with expiring link |
