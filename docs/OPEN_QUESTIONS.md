# Open questions

| # | Question | Owner | Needed by |
|---|---|---|---|
| Q1 | Will a healthcare attorney review MRF redistribution, CPT code-number display, HIPAA applicability, and disclaimer text before public launch? | Cooper | Before public launch |
| Q2 | Hosting preference (AWS, GCP, Azure, or a simpler host such as Render/Fly)? | Cooper | Phase 3 |
| Q3 | Monthly budget ceiling for staging infrastructure and raw-file storage? | Cooper | Phase 2 |
| Q4 | Who clinically reviews code mappings and bundle templates? | Cooper | Phase 3 |
| Q5 | Exact CMS Provider Data Catalog dataset ID for Hospital General Information today (legacy used `xubh-q36u`)? | Engineering | Phase 1 |
| Q6 | Python 3.12 (CI) vs 3.13 (where Phase 0 was built): pin one for production. | Engineering | Phase 3 |

## Resolved

- Old code: audited 2026-11-04 (`LEGACY_AUDIT.md`).
- CPT licensing: no license at launch (D-002).
- Keep procedurescout.com up during rebuild: no.
- Old price files: none exist; download fresh.
