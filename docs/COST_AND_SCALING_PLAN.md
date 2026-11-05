# Cost and scaling plan

Expected costs and scaling path.

## Status

No costs incurred. Estimates will be based on measured Nevada workloads in Phase 2, not guesses.

## Scaling path

Nevada on one PostgreSQL → more states as partitions → horizontal ingestion workers → analytical engine only if measured query load requires it.

## TODO

- Storage estimate per state from real file sizes.
- Budget ceiling (OPEN_QUESTIONS Q3).
