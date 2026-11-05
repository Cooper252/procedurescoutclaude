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

## TODO

- Queue technology choice (Dramatiq vs Celery) — Phase 2.
- Object store choice for staging/production — Phase 2.
- Frontend hosting — Phase 3.
