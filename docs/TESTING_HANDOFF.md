# Full testing handoff (for the chat that runs complete back-end and front-end testing)

Cooper wants every piece of ProcedureScout tested, back end and front end. Read `CLAUDE.md`, this file, `docs/FEATURE_MATRIX.md` and the top of `docs/PROGRESS.md` first.

## Where things stand (2026-11-14)

- `make check` (ruff, mypy strict, pytest): `398 passed, 1 skipped` (the skip needs a DuckDB extension download).
- Website (`apps/web`): `npx tsc --noEmit`, `npm test` (only 3 unit files: `lib/estimate.test.mts`, `lib/cardRead.test.mts`, `lib/stateLaws.test.mts`), `npm run build`. No click-through (end-to-end) tests in the repo yet; checks so far were Playwright screenshots run by hand.
- `docs/TEST_PLAN.md` describes only Phases 0–1 and is out of date: it lists 22 test files, the repo has 40 (`ls tests`). Update it as part of this work.
- `docs/FEATURE_MATRIX.md` "Tested" column: 31 rows "Yes (synthetic)", 15 "Yes", 8 "—" (not tested), 3 "Preview build + screenshots only", 3 "Partly", 1 "tsc only". Start with the "—", screenshot-only, partly and tsc-only rows.
- GitHub workflows: `ci.yml` (runs `make check` on push; Render deploys only after it passes), `site-check.yml`, `test-all-states.yml` (`scripts/state_check.py`, end-to-end check of each loaded state against production), plus the load workflows. Workflows are protected: Cooper copies changed workflow files in himself.

## What "everything" covers

1. Back end: every API route (`apps/api/procedurescout_api/*_routes.py`), validation and 422s, rate limits, auth (provider portal sign-in, authenticator, admin review pages), access-control rules (API role can't read raw prices or fixtures).
2. Data pipeline: reference loaders, discovery, price-file check/parse/stage/publish, insurer matching (`plan_resolver.py`), assistance policies, bundles, code index. All with synthetic fixtures only (CLAUDE.md rule 6).
3. Money and pricing math: exact Decimal everywhere, headline/typical range/badges, "What will I pay?" estimates (`lib/estimate.ts`).
4. Website: every page in English and Spanish, phone (390px) and computer widths, no sideways scrolling, keyboard use, screen-reader labels (automated checks such as axe; a human screen-reader test is still a separate item for Cooper), preview mode vs real API, empty/error/loading states.
5. Provider portal and admin flows: claiming, price entry and review, reviews moderation, wrong-price reports, emails (mailer in test mode).
6. Production smoke checks (read-only) through `test-all-states.yml` or the built-in browser.

## Constraints

- The cloud workspace cannot reach procedurescout.com (proxy). Production checks go through the built-in browser on Cooper's computer (read-only GETs) or GitHub Actions.
- Never create accounts, submit forms, send emails or write data on the live site without asking Cooper first; do that testing against a local or test database.
- Local setup: `service postgresql start`; test DB `postgresql://ps_owner:ps_owner_dev@localhost:5432/procedurescout_test`; `.venv/bin/python`; website `cd apps/web && npx next build && npx next start -p 3100` (preview data when `API_URL` is unset). Playwright and Chromium are preinstalled in the cloud workspace (`require('playwright')`); don't reinstall.
- Adding Playwright tests to the repo needs a dev dependency and probably a workflow change (Cooper copies workflows in).
- Every change updates `docs/PROGRESS.md` and `docs/FEATURE_MATRIX.md` with real test output; never claim a test passed without running it.

## Saving to Cooper's computer

Files go to `C:\Users\hotch\Documents\GitHub\procedurescoutclaude` with the device commit tool, then are re-read and compared. Cooper pushes with GitHub Desktop; tell him the file count in plain words, batch work, and only stop when he must do something.
