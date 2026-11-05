# Legacy audit (2026-11-04)

Audited from `ProcedureScout-main.zip` (GitHub `Cooper252/ProcedureScout`): React frontend, FastAPI + MongoDB backend (~32,000 lines of Python), built on the Emergent platform. Legacy notes report 17.3M price rows from 10 Nevada hospitals.

**Verdict: rebuild, not migrate.** The old site is retired and no old price data is carried over; all hospital files are downloaded fresh. No legacy code is copied into this repository.

## Bugs still present in the legacy code

- **Plan collapse:** `/compare` returned one headline price per hospital; other plans were secondary.
- **Procedure-code mapping:** "Brain MRI" mapped only to 70551; "ER" merged visit levels 99283–99285; codes were silently expanded through aliases.
- **Float money:** `price: float`, `float()` parsing, `ijson use_float=True`.
- **Sample prices in production collection:** `seed_data.build_sample_prices` wrote synthetic prices into the same `prices` collection, guarded only by `is_sample` filters.
- **No CMS v3.0 support.**
- **Per-hospital query loop:** up to 500 hospitals × up to three queries per search.
- **Poverty guidelines hard-coded to 2025.**
- Partly fixed: carrier/plan confusion (typed options added, but regex slugs merged e.g. "Blue Shield" variants into one bucket); missing-price explanations (rows without dollar amounts dropped silently); slow invalid-plan queries (timeout, not allow-list).

## Worth reusing as reference (re-implemented, reviewed)

Payer/union/employer plan name lists (as seed rows for alias review), procedure alias seeds (as input to the reviewed term map), streaming fetch/checkpoint ideas, CMS roster + `cms-hpt.txt` discovery approach, facility-vs-professional price composition idea, and the legacy forensic audit findings as regression test cases.

## Not carried over

MongoDB storage and data, synthetic seed prices, Emergent platform files, Nominatim geocoding at search time (privacy), Brave Search dependency (paid key; revisit in Phase 2).
