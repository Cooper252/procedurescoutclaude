# ProcedureScout: handoff to a new chat (2026-11-13)

You are continuing work on ProcedureScout for Cooper. The previous chat lost its connection to his computer. Read this whole file before doing anything.

## 0. First things to do, in this order

1. **Save the three attached files into the repo.** Cooper attached these files to this chat along with this handoff. They hold today's unsaved work.

   | Attached file | Save it to |
   |---|---|
   | `data__reference__assistance_policies.csv` | `data/reference/assistance_policies.csv` |
   | `docs__PROGRESS.md` | `docs/PROGRESS.md` |
   | `docs__FEATURE_MATRIX.md` | `docs/FEATURE_MATRIX.md` |

   - The repo is `C:\Users\hotch\Documents\GitHub\procedurescoutclaude` on Cooper's computer.
   - Use the computer shell (device_bash) to copy them into place. If only the file tools are available, commit the files and then re-read them to confirm.
   - **Check the result:** the CSV has 175 rows whose `ccn` starts with `system:` plus 46 hospital (CCN) rows. It uses LF line endings only.
   - **If the files are not attached:** ask Cooper for them once. The alternative is redoing the work from section 4.
2. **Run the checks.** If Python and Postgres work on his computer, run `make check`. Expected result: `396 passed, 1 skipped`. If not, tell Cooper to push and let GitHub CI run the checks.
3. **Tell Cooper to push in GitHub Desktop.** Give him the exact files to push (the three above) and one short sentence on what changed.
4. **Read the new load reports.** Cooper has downloaded the latest finished state-load reports (GitHub Actions artifacts, zip files) into his Downloads folder. Open the newest ones and do section 3a.

## 1. Who Cooper is and how to work with him

- **No tech background.** Use plain, short, step-by-step language. He pushes with **GitHub Desktop**.
- **Standing instruction:** "Just keep going until you absolutely need me." Don't stop to ask for approval on routine work, and don't stop after a few changes to ask him to upload. Batch the work, save it to his folder yourself, and only stop when he must click or push something and you can't continue without it.
- Every time you stop, tell him exactly which files to push.
- **Website access:** you may use any website needed for this project.
- **Never:**
  - create accounts or enter passwords;
  - paste secrets;
  - share his email address.
- **`.github/workflows/*` are protected.** You can't save them. Give him the file and he copies it in himself.
- **Ask first before:** paid infrastructure, production deploys, destructive migrations or deletes, downloads over 50 MB, or any monetization feature.
- **Do not use** Grok, xAI or their infrastructure.

## 2. Project facts

- **Product:** ProcedureScout, a national medical price transparency site at procedurescout.com.
- **GitHub:** Cooper252/procedurescoutclaude. Your `gh` login cannot see this repo, so workflow artifacts only reach you through Cooper's Downloads folder.
- **Hosting:**
  - Render: API, web and Postgres; it deploys only after CI passes.
  - Cloudflare R2: published price files.
  - Resend: email.
- **Stack:**
  - FastAPI, SQLAlchemy 2, PostgreSQL 16 + PostGIS, Alembic (latest migration: 0027).
  - Next.js frontend in `apps/web`.
  - Checks: `make check` runs ruff, mypy (strict) and pytest.
- **Read before changing anything:** `CLAUDE.md` (hard rules), `docs/PROGRESS.md` (newest entries at the top), `docs/GO_LIVE.md`, `docs/DECISIONS.md`.
- **Key rules from CLAUDE.md:**
  - Never fabricate prices, codes, payers, plans, eligibility or test results. No price is better than a false price.
  - Every change updates `docs/PROGRESS.md` and `docs/FEATURE_MATRIX.md`, with real test output.
- **What Cooper delegated to you.** Never ask him to review these:
  - **Insurance-name matching (D-047):** only with written evidence. Use `reviewed_by = "Claude (delegated by Cooper, D-047)"`.
  - **State laws and program limits (D-056):** only from official sources.
  - **Hospital financial-assistance policies (D-060):** only from the hospital's or system's own document. Use `reviewed_by = "Claude (delegated by Cooper, D-060)"`.
  - **Services, search words and bundles (D-061):** only from official code definitions.

## 3. Work left, in priority order

### 3a. Insurance names from the new state loads (do first)

- Each load report lists the 25 most-used unmatched insurance spellings for each state (`unresolved_by_state`).
- For each newly loaded state, place what you can with evidence. Use the insurer's own website, or the state Medicaid or BCBSA lists.
- The files involved, all in `data/reference/`:
  - `payers.csv`: insurer and plan.
  - `payer_states.csv`: insurers limited to certain states.
  - `payer_name_rules.csv`: columns pattern, payer, plan, states, notes, reviewed_by, reviewed_at.
  - `payer_aliases.csv`
- **How matching works (D-062, migration 0027):**
  - Spellings are matched per state. `ref.plan_alias.state_code` is either `''` (every state) or a single state.
  - `ref.payer.only_states` limits an insurer to certain states.
  - The resolver is `packages/ingest/procedurescout_ingest/plan_resolver.py`.
  - In states with two Blue Cross companies (CA, ID, KS, MO, NY, PA, VA, WA), only the company's own name is matched.
- **Tests:** add cases to `tests/test_pricing.py`. `REAL_SPELLINGS` is a dict keyed by state. See `test_regional_insurers_by_their_own_names` and `test_state_medicaid_programs_by_their_names`.
- **If the reports show load errors:** fix them first and tell Cooper what to re-run.

### 3b. Check the Los Angeles plans list

- At the last check, the LA insurance list still showed Nevada-only insurers:
  - "Anthem Blue Cross Blue Shield (Nevada)"
  - "Select Health (Intermountain)"
  - "Teachers Health Trust"
- They should disappear after the next state load's catalog and resolve steps run.
- Check on the live site with the built-in browser. If they're still there after a completed load, investigate the catalog loader and `payer_states.csv`. Nevada employer plans belong only in NV; Select Health only in UT, ID, NV and CO.

### 3c. Check health-system policy name patterns on the live site

- Rows like `system:TX:^COOK CHILDREN` match hospitals by their CMS name within that state (`catalog.load_assistance_policies`). A hospital's own CCN row wins.
- The ~40 rows added on 2026-11-13 were never checked against real hospital names, because the computer link was down.
- **What to do:** look up each system's hospitals on the live site. Fix any pattern that misses a hospital, or that catches a hospital it shouldn't.
- **Pattern rules:**
  - PostgreSQL regex, case-insensitive.
  - Word boundaries are `\y`, never `\b`.
  - `(?!...)` works.
  - Inside a tier description, use a comma, never `;` (`;` separates tiers).
  - No two system rows may match the same hospital.
- **Rows to check, by state:**
  - **TN:** Erlanger, Covenant
  - **MI:** McLaren, Sparrow, Bronson
  - **TX:** University Health, Children's Health, Cook Children's, Methodist Dallas
  - **NJ:** Hackensack Meridian, RWJBarnabas
  - **PA:** Geisinger, Main Line
  - **MA:** Mass General Brigham, Beth Israel Lahey
  - **CA:** Scripps, Cedars-Sinai/Huntington, Stanford, UCLA
  - **WV:** WVU Medicine
  - **NH/VT:** Dartmouth, UVM
  - **ME:** MaineHealth
  - **RI:** Brown Health
  - **OR/WA:** Legacy, OHSU
  - **SC:** AnMed, Spartanburg
  - **GA:** Phoebe, NGMC
  - **VA:** Riverside
  - **DE:** Bayhealth, Beebe
  - **HI:** HPH
  - **NY:** WMCHealth
  - **LA:** Lake Charles
  - **KY:** UK HealthCare
  - **WI:** Marshfield
  - **NC:** Cone

### 3d. Keep adding health-system assistance policies

- Coverage: 175 system rows plus 46 hospital rows, across 49 states and DC. Nevada has hospital rows only.
- **Not yet covered, or skipped for lack of clear tiers:**
  - Parkland
  - Northwell (New York has no blanket state rule here yet)
  - Renown
  - Queen's (HI)
  - Sharp
  - Sarasota Memorial
  - Nebraska Medicine
  - ChristianaCare (its summary and policy disagree)
  - Lee Health (2021 figures)
  - Roper St. Francis (only a 2022 copy opened)
  - Deaconess
  - Lehigh Valley
  - Willis-Knighton (file wouldn't open)
  - Trinity Health Michigan
  - Prisma
  - Piedmont
  - OhioHealth
  - Emory
  - UNC
  - Orlando Health
  - Memorial Hermann
  - Vanderbilt
  - Johns Hopkins
  - Hartford HealthCare
  - Community Health Network (IN)
  - Franciscan Health
  - UNM
  - Presbyterian (NM)
- Retry these if a newer document gives clear income tiers, and add any other large systems.
- **Row format:**
  - `ccn` = `system:ST:regex`
  - `source` = `ai_suggested`
  - `reviewed_by` = `Claude (delegated by Cooper, D-060)`
  - `reviewed_at` and `checked_at` = today
  - `evidence` quotes the document and ends with "Checked YYYY-MM-DD."
  - `tiers` look like `free<=200;discount<=400:50` (the number is a percent off) or `discount<=400:free text`.
  - Never guess an effective date.
- After adding rows, update the counts and names in the PROGRESS entry ("2026-11-13 — More health-system assistance policies") and in the FEATURE_MATRIX FA-01..02 row.

### 3e. Docs that are out of date

- `docs/GO_LIVE.md` section 3 still says "only 13 Nevada policies proposed so far." Update it to the real coverage.

### 3f. Later, or needs Cooper

- **Lawyer review** of the terms, privacy notice and disclaimers (Q25, before public launch).
- **Screen-reader tester:** a person tries the site with a screen reader.
- **Spanish review:** Cooper finds a Spanish speaker to read the Spanish pages.
- **Database backups and uptime check on Render:** paid plan, so ask first.
- **npm audit warning** in `apps/web`.
- **Big states and GitHub's 6-hour limit:** if CA, TX, FL or NY exceed it, split their loads.
- **State hospital-bill laws:** add more states beyond the 16 in `apps/web/lib/stateLaws.ts`, each from the state's own source.

## 4. If the attached files were lost: the work to redo

- **2026-11-13 health-system assistance policies (~45 rows):**
  - Texas Children's, Parkview, Baptist Health KY, FMOL
  - UK HealthCare, McLaren, Marshfield, Cone, Erlanger, Lake Charles Memorial
  - Cook Children's, Covenant, Sparrow, University Health, Children's Health, Geisinger
  - Hackensack Meridian, RWJBarnabas, Mass General Brigham, Beth Israel Lahey, WVU Medicine
  - Dartmouth, MaineHealth, UVM, Brown Health, Legacy, OHSU, Main Line, Scripps
  - Cedars-Sinai, Stanford, UCLA, Bayhealth, Beebe, Hawai'i Pacific Health, WMCHealth
  - AnMed, Spartanburg, Phoebe Putney, NGMC, Methodist Dallas, Riverside, Bronson
- The last version saved on Cooper's computer was verified at 104 system rows. Anything beyond that is in the attached CSV.

## 5. Lessons from the last chat

- **The commit tool sometimes reported success but wrote stale content.** After every save, re-read the file on the computer and compare it with what you meant to write.
- **Work on the computer directly with device_bash** when it's available. It's faster and avoids the stale-copy problem.
- **The computer link drops often.** When it drops, keep working. Use `send_later` to retry instead of stopping.
- **Postgres in a cloud workspace stops often.** Restart it with `service postgresql start`.
