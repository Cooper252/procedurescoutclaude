# Security and privacy

Protecting users and the platform.

## Implemented in Phase 0

- Least-privilege DB role for the API: published prices only, no writes, no fixture access (tested).
- No credentials in the repository; dev-only passwords in `.env.example` and `scripts/db_init.sql`.
- Migration validates the API role name before using it in SQL.

## Planned

- No account for search; minimal, aggregate search analytics; short log retention.
- No ad trackers in sensitive flows; no third-party geocoding of what users type (local Census ZIP table).
- TLS, encryption at rest, admin MFA, role-based admin access, rate limiting, audit log (`src.audit_event`).
- HIPAA applicability analysis based on actual data flows (counsel).

## TODO

- Threat model; retention schedule; privacy notice.

## Review page (interim sign-in)

`/admin/reviews` is disabled unless `ADMIN_TOKEN` and `ADMIN_DATABASE_URL` are set. Sign-in is a name plus the admin password over HTTP Basic (HTTPS required when hosted); the name is recorded as the reviewer. Each form carries an HMAC token tied to the dataset so another site cannot submit decisions. Multi-factor sign-in and per-person accounts replace this before launch (ADM-02).

## Published price files (D-033)

The API may read only published Parquet files listed in `price.published_file`. When an S3-compatible store is set up, the API's credentials will be read-only and limited to the `published/` prefix; ingestion credentials are separate. Keys are validated (`object_store.published_key`) and the local store refuses paths outside its folder and refuses to overwrite a published file.

## Self-hosted runner (2026-11-06)

Cooper's computer runs a GitHub self-hosted runner for the manual Nevada workflow (D-021). Rules: the repository must be private; the runner is used only by the `home-fetch` job of `reference-nv.yml` (label `procedurescout-home`); that job only reads `data/reference/facility_websites.csv` and `data/reference/home_runner_price_sites.csv` and writes `hpt-home/` and (when price downloads are ticked) `prices-home/`, which holds public hospital price files for at most 500 MB each and is kept as a GitHub artifact for 1 day; no credentials are kept in the checkout (`persist-credentials: false`). Remove the runner in GitHub Settings → Actions → Runners if it is no longer needed.
