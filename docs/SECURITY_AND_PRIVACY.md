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

## Self-hosted runner (2026-11-06)

Cooper's computer runs a GitHub self-hosted runner for the manual Nevada workflow (D-021). Rules: the repository must be private; the runner is used only by the `home-fetch` job of `reference-nv.yml` (label `procedurescout-home`); that job only reads `data/reference/facility_websites.csv` and writes `hpt-home/`; no credentials are kept in the checkout (`persist-credentials: false`). Remove the runner in GitHub Settings → Actions → Runners if it is no longer needed.
