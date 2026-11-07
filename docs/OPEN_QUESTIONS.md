# Open questions

| # | Question | Owner | Needed by |
|---|---|---|---|
| Q1 | Will a healthcare attorney review MRF redistribution, CPT code-number display, HIPAA applicability, and disclaimer text before public launch? | Cooper | Before public launch |
| Q2 | Hosting preference (AWS, GCP, Azure, or a simpler host such as Render/Fly)? Run #12 measured Nevada at 45.2 million price rows, 16.5 GB with indexes (free database tiers hold 0.5–1 GB). Options with prices checked 2026-11-07 are in PROGRESS.md (run #12). | Cooper | Phase 3 |
| Q3 | Monthly budget ceiling for staging infrastructure and raw-file storage? | Cooper | Phase 2 |
| Q4 | Who clinically reviews code mappings and bundle templates? | Cooper | Phase 3 |
| Q6 | Python 3.12 (CI) vs 3.13 (where Phase 0 was built): pin one for production. | Engineering | Phase 3 |
| Q7 | Where should the AHRQ Compendium hospital linkage CSV come from (exact URL), and is the 2023 file the newest? | Cooper / Engineering | Before the first AHRQ load |
| Q8 | Who reviews facility campus relationships and fills `data/reference/facility_relationships_reviewed.csv`? | Cooper | Before Phase 2 file→facility mapping |
| Q9 | ASCs outside the ASC Quality Reporting file: add a second source (CMS Provider of Services file or Nevada DPBH licensing list)? | Cooper | Phase 3 |
| Q11 | Websites for Harmon Hospital (290042) and Thrive Behavioral Hospital (294016); where the St. Rose North Las Vegas campus publishes prices; Reno Behavioral's price file (its page refuses access). | Cooper | Phase 2 |
| Q13 | Send the drafted emails to Renown (Auditandcompliance@renown.org) and Tahoe Forest (mhambrick@TFHD.COM) asking them to allow automated access. | Cooper | When the site is running |
| Q10 | NUBC revenue code descriptions: licence or code-only display? | Cooper (counsel) | Phase 3 |

## Resolved

- Q12: sites that refuse GitHub's servers are fetched live from Cooper's computer via a self-hosted runner (D-021).
- Q5: Hospital General Information is still `xubh-q36u` (PDC metastore, modified 2026-07-22). ASC facility file is `4jcv-atw7`.
- Old code: audited 2026-11-04 (`LEGACY_AUDIT.md`).
- CPT licensing: no license at launch (D-002).
- Keep procedurescout.com up during rebuild: no.
- Old price files: none exist; download fresh.
