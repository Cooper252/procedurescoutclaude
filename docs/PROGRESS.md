# Progress

Status levels: Implemented → Tested → Deployed → Verified in production. Only evidence counts.

## 2026-11-04 — Phase 0 (foundation)

Built by Claude (Cowork) in a cloud workspace, not yet pushed to GitHub, CI not yet run.

### Implemented and tested

- Repository layout, `pyproject.toml`, pinned `requirements*.txt`, `Makefile`, `.env.example`, `docker-compose.yml`, `scripts/db_init.sql`, CI workflow.
- Migration `0001_initial_schema.py`: schemas `ref`, `src`, `price`, `fixture`; 19 enums; all tables from `DATABASE_DESIGN.md`; price CHECK constraints; LIST(state) partitioning; import-transition triggers; `price.published_price` view; API-role grants.
- `procedurescout_core`: `money.py` (Decimal parsing), `enums.py`, `import_state.py`, `matching.py`, `payer_repo.py`.
- `procedurescout_ingest/base.py`: parser adapter interface only.
- API: `/healthz`, `/v1/meta/version`.
- All 26 documents (CLAUDE.md + 25 in `docs/`, plus `LEGACY_AUDIT.md`).

### Found and fixed during Phase 0

1. Import-run event logging ran before the row existed (FK violation) → split into BEFORE (validate) and AFTER (log) triggers. Caught by tests.
2. Code-system enum had 10 values; CMS v3.0 allows 21 → aligned exactly (D-007).
3. CMS `count` is text ("1 through 10") → stored as validated text (D-005).
4. v2 `estimated_amount` had no home → `estimated_allowed` price type (D-006).
5. Amounts widened to NUMERIC(16,4) to avoid rounding sub-cent drug prices (D-008).

### Verification evidence

Environment: Python 3.13.18 (CI pins 3.12), PostgreSQL 16 + PostGIS 3.4 installed locally (no Docker daemon available in the build workspace).

`make lint typecheck test`:

```
All checks passed!
51 files already formatted
Success: no issues found in 11 source files
============================= test session starts ==============================
platform linux -- Python 3.13.18, pytest-9.2.0, pluggy-1.7.0
rootdir: /home/claude/procedurescout
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.16.0
collected 100 items

tests/test_access_control.py ....                                        [  4%]
tests/test_api.py ...                                                    [  7%]
tests/test_enums_match_db.py .                                           [  8%]
tests/test_migration.py ..                                               [ 10%]
tests/test_money.py .........................................            [ 51%]
tests/test_no_float_money.py .                                           [ 52%]
tests/test_payer_matching.py ........                                    [ 60%]
tests/test_price_constraints.py .............................            [ 89%]
tests/test_state_machine.py ...........                                  [100%]

=============================== warnings summary ===============================

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 100 passed, 1 warning in 1.29s ========================
```

The one warning is a third-party deprecation notice (Starlette TestClient prefers `httpx2`), not a project issue.

Additional checks run:

- `scripts/db_init.sql` executed on a brand-new PostgreSQL 16 cluster, then the full suite: `85 passed` (before the CMS-alignment tests were added; same steps CI runs).
- Mutation check 1: made `parse_dollar` return `Decimal(0)` for missing input → `tests/test_money.py` failed (1 failed, 40 passed). Restored.
- Mutation check 2: granted the API role read access to `fixture.synthetic_price` → confirmed the role could read it (the condition `test_api_role_cannot_read_fixture_schema` asserts against). Revoked; full suite `100 passed`.

### Not done / not verified

- CI has not run (repository not yet on GitHub).
- `docker compose up` not exercised (no Docker daemon here). The MinIO image tag is unverified.
- No deployment exists.

## Next: Phase 1 — facility and reference data

CMS Hospital General Information import for Nevada, geocoding with a local Census ZIP table, facility aliases/campus relationships, HCPCS/MS-DRG/revenue code references, ASC list.
