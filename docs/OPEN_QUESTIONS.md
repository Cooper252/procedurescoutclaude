# Open questions

| # | Question | Owner | Needed by |
|---|---|---|---|
| Q1 | Will a healthcare attorney review MRF redistribution, CPT code-number display, HIPAA applicability, and disclaimer text before public launch? | Cooper | Before public launch |
| Q2 | Approve D-033 (prices as Parquet in object storage + a small PostgreSQL)? Then: hosting preference (AWS, GCP, Azure, or a simpler host such as Render/Fly)? Run #12 measured Nevada at 45.2 million price rows, 16.5 GB with indexes (free database tiers hold 0.5–1 GB). Options with prices checked 2026-11-07 are in PROGRESS.md (run #12). | Cooper | Phase 3 |
| Q3 | Monthly budget ceiling for staging infrastructure and raw-file storage? | Cooper | Phase 2 |
| Q4 | Who clinically reviews code mappings and bundle templates? The three proposed bundles (upper endoscopy, colonoscopy, vaginal birth) wait for this review (D-036). | Cooper | Before bundles go live |
| Q6 | Python 3.12 (CI) vs 3.13 (where Phase 0 was built): pin one for production. | Engineering | Phase 3 |
| Q7 | Where should the AHRQ Compendium hospital linkage CSV come from (exact URL), and is the 2023 file the newest? | Cooper / Engineering | Before the first AHRQ load |
| Q8 | Who reviews facility campus relationships and fills `data/reference/facility_relationships_reviewed.csv`? | Cooper | Before Phase 2 file→facility mapping |
| Q9 | ASCs outside the ASC Quality Reporting file: add a second source (CMS Provider of Services file or Nevada DPBH licensing list)? | Cooper | Phase 3 |
| Q11 | Websites for Harmon Hospital (290042) and Thrive Behavioral Hospital (294016); where the St. Rose North Las Vegas campus publishes prices; Reno Behavioral's price file (its page refuses access). | Cooper | Phase 2 |
| Q13 | Send the drafted emails to Renown (Auditandcompliance@renown.org) and Tahoe Forest (mhambrick@TFHD.COM) asking them to allow automated access. | Cooper | When the site is running |
| Q14 | How is a provider's authority verified (NPI/CCN match, email on the approved website domain, phone call to the facility, document upload), and who approves? | Cooper | Phase 9 |
| Q15 | When a hospital's correction differs from its own published file, which is shown first, and must the hospital also fix its file? (Proposed: show the correction labeled, keep the file value one click away, ask the hospital to update its file.) | Cooper (counsel) | Phase 9 |
| Q16 | CDT (dental) descriptor licence from the ADA, or code numbers with our own names only? | Cooper (counsel) | Before dental launch |
| Q17 | Paid listings (D-031, rules confirmed 2026-11-07): length of the free period and the prices; counsel review of the advertising terms. | Cooper (counsel) | Before Phase 9 |
| Q20 | Review the 13 proposed hospital financial assistance policies on the review page (UMC, 3 HCA, 3 St. Rose, 2 Renown, Carson Tahoe, North Vista, Saint Mary's, Banner Churchill); still to find: the Valley Health System (UHS) Las Vegas hospitals, Northern Nevada Medical Center, rural hospitals. | Cooper | Before launch |
| Q22 | Confirm NRS 439B.260 (30% off billed charges for uninsured patients at certain Nevada hospitals) applies as North Vista's policy says, before it is shown (SITE_DESIGN §4.9). | Engineering + counsel | Before launch |
| Q23 | Approve the 30 proposed everyday search words (`data/reference/service_synonyms.csv`, e.g. "knee scope" → knee arthroscopy). | Cooper | Before launch |
| Q24 | After the next run: approve the list of Nevada plans as printed on cards and which hospital spellings belong to each (from `payer-plan-names.csv`). | Cooper | Before launch |
| Q10 | NUBC revenue code descriptions: licence or code-only display? | Cooper (counsel) | Phase 3 |

## Resolved

- Q21: everything in `PRODUCT_REVIEW.md` approved (D-039, 2026-11-08); verification strictness per provider type to be set when the portal is built.

- Q18: Cooper approved all proposed services and provider types (2026-11-08).
- Q19: clean refreshes publish automatically (D-035, 2026-11-08).

- Q12: sites that refuse GitHub's servers are fetched live from Cooper's computer via a self-hosted runner (D-021).
- Q5: Hospital General Information is still `xubh-q36u` (PDC metastore, modified 2026-07-22). ASC facility file is `4jcv-atw7`.
- Old code: audited 2026-11-04 (`LEGACY_AUDIT.md`).
- CPT licensing: no license at launch (D-002).
- Keep procedurescout.com up during rebuild: no.
- Old price files: none exist; download fresh.
