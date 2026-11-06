# Ingestion pipeline

How a hospital file becomes published prices.

## State machine

`discovered → queued → downloading → downloaded → validating → parsing → normalizing → loading → quality_review → published`, plus `failed` (from any working state), `stale`, `retired`. Defined in `procedurescout_core/import_state.py` and enforced by the `src.import_run` trigger (D-003). A downloaded file whose hash matches the last published run goes straight to `retired`.

## Stages (Phase 2)

1. **Discover** — `cms-hpt.txt` at the site root, then the transparency page; record URL, method, facility link.
2. **Download** — stream to object storage; record HTTP status, bytes, SHA-256.
3. **Validate** — detect format and `version`; run CMS schema and conditional checks (`CMS_SCHEMA_SUPPORT.md`); unsupported versions stop with `unsupported_version`.
4. **Parse** — version-specific streaming adapter (`ParserAdapter`), bounded memory, checkpoints; malformed rows recorded with line numbers.
5. **Normalize** — payer/plan aliases, codes, settings, methodology; raw values kept beside canonical ones.
6. **Load** — bulk COPY into `price.price` under a new *staged* dataset version.
7. **Quality review** — automatic rules (see `DATA_QUALITY_RULES.md`) block publish; a person approves flagged runs.
8. **Publish** — flip the facility's published dataset version in one transaction; previous version retired but kept.

## Step 2a (built 2026-11-06): download, check, delete

`procedurescout_ingest/price_files.py`, CLI `price-files`, workflow input `download_price_files`. For each facility with an assigned file (one link per facility; newest server date wins, D-024): stream to a temporary file with SHA-256 and a size limit; detect the format from the bytes (JSON, CSV tall/wide, ZIP; Excel reported as not machine-readable); read once in bounded memory (`ijson` events for JSON) to record the header as published and counts (charge items, payer names, code types, settings); store in `src.transparency_file` with `object_store_key` NULL; delete the file. No prices are loaded yet.

## TODO

- Adapter list and parser_version scheme.
- Checkpoint format.
- Throughput and memory targets (`PERFORMANCE_PLAN.md`).
