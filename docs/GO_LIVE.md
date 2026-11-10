# Going live: everything still needed (2026-11-10)

Plain-language checklist. **Owner** says who does it. Costs are monthly unless
noted and were checked 2026-11-08 to 2026-11-09 (see DEPLOYMENT_PLAN.md).

## 1. Decisions only Cooper can make

| # | Decision | Why it matters |
|---|---|---|
| Done | First price files publish automatically when every check passes (D-055). | |
| Done | Domain: procedurescout.com (D-057). | |
| Q25 | **Lawyer review** of the terms of use, privacy notice and disclaimers (English and Spanish), the review rules, and health-data privacy laws. | Should happen before the public launch. |
| Done | Nevada uninsured discount confirmed by Claude from the law's text (D-056); state rules are Claude's job from now on. | |

## 1b. Before signing up: test every state for free

Cooper clicks **Actions → "Test every state (free, nothing kept)" → Run workflow** (states: all, price files per state: 3). Claude reads the summary table and fixes what breaks. Repeat until clean.

## 2. Accounts to create (Cooper, with Claude walking through each screen)

| Account | Cost | Notes |
|---|---|---|
| Render (website, API, database) | about $54 (Hobby workspace, no plan fee; 5 GB traffic included, then $0.15/GB) | `render.yaml` sets everything up. |
| Cloudflare R2 (published price files) | under $1 at first | 10 GB free; about 55 GB nationally ≈ $1. |
| Resend (email) | free to 3,000 a month | Verify the domain; switchable to Amazon SES later. |
| Domain name DNS | ~$10–20 a year if not already owned | Point it at Render. |
| Stripe | none until charging | Only when you decide to charge (D-051). |

After sign-up: add the GitHub secrets for the live-load run, run `add-staff` for each reviewer, and check `/healthz`, a search and the review pages.

## 3. Loading the country (Claude runs, Cooper clicks "Run workflow")

- **Run "Load a state into the live site"** for each state (`load-state-production.yml`). Each run: reference data, hospital websites (found and checked automatically), price files (published one at a time, staged rows removed), offices from the national provider list, code index, insurance names.
- **Big states may exceed GitHub's 6-hour limit** per run (California, Texas, Florida, New York). If so, those states get split into parts; measure on a mid-size state first.
- **Insurance names per state**: matched automatically when certain; Claude researches the rest with evidence (D-047).
- **Help paying, per state**: income limits for every state + DC are in (D-056). Still to do: each state's own uninsured-discount law (Claude researches with sources).
- **Hospital financial-assistance policies**: only 13 Nevada policies proposed so far; national coverage is a later step (the site says "ask about financial assistance" until a policy is reviewed).

## 4. Built and ready (no action needed)

Search, provider pages, accounts with the authenticator app, reviews, provider prices and specials, counts, wrong-price reports, review pages with per-person logins, email sending, rate limits, billing (off), offices from the national provider list (tested on real Nevada data: 8,238 offices), any-state runs, automatic website checks, file-by-file publishing.

## 5. Before opening to the public (Claude unless noted)

- First live load (Nevada), then check the hosted site end to end in a browser: search, a provider page, sign-in email arrives, a review, the review pages.
- A person tries the site with a screen reader (automatic checks pass).
- A Spanish speaker reads the Spanish pages (Cooper finds someone).
- Turn on Render's database backups and an uptime check (Render includes both on paid plans; confirm at sign-up).
- Remove `PORTAL_DEV_LINKS` (it's off in production automatically).
