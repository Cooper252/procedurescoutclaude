# System architecture

How the parts fit together and why.

## Layers

1. **Public sources** — hospital MRFs, CMS facility data, code references, assistance inputs.
2. **Ingestion workers (Python, queued)** — discover → download → validate + parse → normalize + stage.
3. **Storage, kept separate** — object store (original files, kept forever), Parquet staging (parsed rows per run), PostgreSQL + PostGIS (reference + published prices), Redis (job queue, cache).
4. **Serving (FastAPI)** — public API `/v1` and an admin API with MFA and audit.
5. **People** — Next.js consumer site (no account, no ad trackers) and an admin console.

## Principles

- Raw files, staged rows and published prices never share a store.
- The API reads published data only (DB-enforced, D-004).
- Start with one PostgreSQL; add an analytical engine (e.g. ClickHouse) only when measured national load requires it.
- Each layer scales independently: workers horizontally, API with read replicas, site via CDN.

## Price sources (D-030)

Three sources feed published prices and stay distinguishable end to end: hospital files (ingestion workers), provider-submitted prices and provider corrections (provider portal, verified accounts, audited, optionally held for review). The consumer site labels every price with its source and date.

## Storage experiment (NAT-02)

After a price load, `storage_experiment.py` measures the same prices three ways: the current one-row-per-amount PostgreSQL table; a normalized PostgreSQL layout (item rows + small amount rows + payer/plan rows), estimated from exact distinct counts and sampled column sizes; and compressed Parquet files per facility (DuckDB, zstd), measured, with a check that every amount comes back exactly and a timed lookup of one common code against PostgreSQL. The result (`storage-experiment.json`) decides the national layout before any hosting is bought.

## TODO

- Queue technology choice (Dramatiq vs Celery) — Phase 2.
- Object store choice for staging/production — Phase 2.
- Frontend hosting — Phase 3.
