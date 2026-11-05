# API contracts

Versioned API surface.

## Implemented

| Method | Path | Response |
|---|---|---|
| GET | `/healthz` | `{"status": "ok"}` (no DB access) |
| GET | `/v1/meta/version` | `{"api_version": "v1", "app_version": "0.1.0"}` |

OpenAPI at `/openapi.json`, docs at `/docs`.

## Planned (Phase 3)

Facility search by location, procedure search and disambiguation, payers and plans available in an area, price comparison, provenance for a price, coverage stats. All filters validated against lookup tables first (unknown plan → 422, no price query), cursor pagination, stable sorting, standard error body.

## TODO

- Error schema; pagination contract; generated TypeScript client.
