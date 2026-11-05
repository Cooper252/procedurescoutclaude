# Performance plan

Targets and how they are measured.

## Starting targets (to be set from Phase 2 measurements)

- Parser: bounded memory (target < 2 GB for a 5 GB file).
- Search: p95 under 800 ms for procedure + 50-mile radius (proposal).
- Invalid filter rejection: < 50 ms with zero price-table reads.

## Approach

Indexes chosen from measured query plans; `EXPLAIN ANALYZE` captured for expensive endpoints; no per-facility query loops; cursor pagination.

## TODO

- Realistic multimillion-row fixtures; benchmark harness.
