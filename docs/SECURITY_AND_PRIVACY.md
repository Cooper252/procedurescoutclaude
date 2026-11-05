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
