# Requirements

Functional requirements with IDs used in `FEATURE_MATRIX.md`. Priority: Must / Should / Could.

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
| EXP-01 | Export | CSV/XLSX/Parquet async exports | Could | 8 | Large export runs as a job with expiring link |
