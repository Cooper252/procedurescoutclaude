# Decisions

Newest first. Each entry: decision, reason, consequences.

## 2026-11-12 — D-060: Claude approves hospital financial-assistance policies, with sources
Cooper delegated this (2026-11-12: "You approve them"). Claude approves a hospital's policy only from the hospital's own policy document (or its plain-language summary) with the document URL and the exact limits recorded; `reviewed_by = "Claude (delegated by Cooper, D-060)"`. A limit that cannot be read clearly from the document is not guessed: that hospital keeps "we have not reviewed its policy yet". Cooper is never asked to review policies.

## 2026-11-11 — D-059: Price rows are staged on the loading computer, not in the live database
First live Nevada load: staging one hospital's file in the live database (10 GB disk, 1 GB memory) took it down (University Medical Center's file is 15.5 million prices, about 6 GB with indexes; the run's log shows "service temporarily unavailable"). Now each live run starts a throwaway PostGIS database on the GitHub computer (migrated, links to live-only tables dropped, every price check kept); a file's rows are staged there, checked, written to Parquet in R2, summarised into the live database, and deleted. The live database holds only hospitals, files, summaries and decisions. Because the rows don't stay anywhere, a file that fails the automatic checks is set aside with its reasons (reviewer "automatic checks (D-035)") instead of waiting for a person; it is read again when the hospital posts a new file. `clear-staged` (a tick box on the single-state run, Cooper's OK) removes rows earlier runs left in the live database; published prices are untouched. Also: the bucket address is accepted with the bucket name on the end, as Cloudflare shows it.

## 2026-11-10 — D-058: A hospital's own price-file header can verify its website
All-states test: health systems list hospitals under other names (Providence lists "Providence St Joseph Hospital Eureka"; CMS says "PROVIDENCE ST JOSEPH HOSPITAL"), so only 1,392 of 5,306 hospitals got a website. Now, when a candidate site's cms-hpt.txt doesn't name the hospital, the first 256 KB of each listed price file (at most 150 per site) are read; if the CMS header's `hospital_address` gives the hospital's street number and ZIP code, the site is accepted (`website_reviewed_by` = "automatic (the price file's header gives this hospital's address, D-058)", evidence = that file's link) and the listed name is saved as an approved `mrf_name` alias so the file is linked to the hospital. A name already belonging to another hospital is never reused. Same test also changed: JSON files starting with a byte-order mark are read; a few stray bytes (at most 1% of rows) and template version 4.x are notes, not reasons to hold a file; a non-price file's first characters are reported.

## 2026-11-10 — D-057: The site lives at procedurescout.com
Cooper owns procedurescout.com. `SITE_URL`/`NEXT_PUBLIC_SITE_URL` are `https://procedurescout.com`, email is sent from an address at that domain (verified in Resend), and the domain's DNS points at Render.

## 2026-11-10 — D-056: Claude confirms state laws and program limits, with sources
Cooper: "You confirm it. I can't go through 50 state laws." Claude may approve state rules (uninsured-discount laws, Medicaid/CHIP and marketplace income limits, similar public rules) only from an official or recognised source cited in the row (`source_url`), recorded as `reviewed_by = "Claude (delegated by Cooper, D-056)"`. Anything that can't be sourced stays proposed and is not shown. Wording always says "may qualify" and that the agency or hospital decides. First use: income limits for all 50 states + DC (MACPAC Exhibits 35/36, July 2025, plus the standard 5-point disregard; California children use the statewide 266%), and Nevada's uninsured discount (NRS 439B.260 / 439B.115, read on the Legislature's site, revised 2026-04-15), shown on the help-paying page for Nevada only as a conditional rule (inpatient, uninsured, private hospital with 200+ beds) because we don't hold bed counts. Lawyer review (Q25) still covers the site's wording.

## 2026-11-10 — D-055: First price files publish automatically when every check passes
Cooper answered Q35 yes. A hospital's first file publishes when it has prices, no file problems and at most 1% of rows refused; otherwise it waits on the review page as before. The live-load run's `first_files_automatic` now defaults to on.

## 2026-11-10 — D-054: Publish file by file; staged rows removed after publishing
National storage: the live database (10 GB to start) can't hold whole states' staged prices. The live-load run (`load-state-production.yml`) stages one hospital file, publishes it to R2 when the automatic checks pass, removes its staged rows (the Parquet file is what the site reads), and commits before the next file. Small per-file summaries (codes and insurance spellings) are kept so the code index, insurer search and insurance-name matching stay complete. Hospital website candidates come from the community-built DoltHub list (`dolthub/standard-charge-files`, CC BY-SA 4.0), used only as hints: each is accepted only if the site's own cms-hpt.txt names the hospital (D-048). Whether a hospital's first file may publish without a person is Cooper's decision (Q35); the run has a switch for it, off by default.

: Email by Resend (switchable); per-person review logins
- Email: Cooper chose Resend (free up to 3,000 emails a month, 100 a day; then $20 a month), on the condition it can be changed later. The sender is generic: Resend's API or any SMTP service (Amazon SES and others) by settings, no code change (`procedurescout_core/mailer.py`). Sent emails have their one-time link removed; sent rows are deleted after 30 days.
- Review pages: each reviewer has their own account (email link + authenticator app), added with `add-staff`; decisions are recorded under their email. The shared password works only outside production (ADM-02).

## 2026-11-09 — D-052: Offices from the national provider list; practices can ask to be added
- Cooper approved downloading the NPPES monthly file (about 1.1 GB) in the free GitHub run. Organizations (entity type 2) with an active NPI in the chosen state are loaded when one of their taxonomy codes maps to one of our provider types (`data/reference/nppes_taxonomy_map.csv`, by NUCC classification name, checked against the NUCC list at run time). The map was Claude's proposal; Cooper approved it as is on 2026-11-09 (rule 10).
- An NPI already belonging to a hospital or surgery center never creates a second listing. Deactivated NPIs become inactive.
- Practices not in public records (for example med spas) can ask to be added from their account; a person checks each one; on approval the requester owns the new page.

## 2026-11-09 — D-051: Monthly listing fee and Sponsored spots, built but free for now
Cooper: providers will eventually pay a monthly fee to be listed, priced by kind of business (his rough ideas: hospitals about $999, surgery centers about $500, dentists about $250, chiropractors about $150; not decided), plus Sponsored spots. For now the site says listing is free, and nothing is charged; he doesn't know when charging will start and doesn't want providers with few visitors to expect a fee.
- Built switched off: plans by provider type (`bill.plan.provider_type`), Stripe Checkout and customer portal, signed webhooks, Sponsored spots (labeled, at most 2 per search, never change order or labels, only for services the provider has a published price for).
- Turning it on needs, each by Cooper: plan prices (`set-plan`), a start date (`set-fee-start`), and Stripe keys.
- Once a fee is in force, an unpaid provider's own content (prices, specials, packages, homepage, photos) is hidden. Public-record listings, hospital price-file prices and reviews never depend on payment (FTC rule on reviews; price files are public by law).

: Provider homepages, dashboard and reviews built
Cooper asked for provider homepages (logo, links, photos, more information), a provider account with numbers (views, nearby demand, what a boost would do) and reviews, all built before paying for hosting. Decisions:
- **Review verification (Q31, Cooper):** no receipts. A visit is confirmed by a one-time link, either emailed by us after the person asks ("Did you visit…?", shown as "Visit confirmed by email") or given by the provider ("Invited by the provider"). Reviewers confirm they visited and are not staff, family or paid. One review per person per provider.
- **Unclaimed providers can be reviewed (Q32, Cooper)**, labeled "Not claimed by the provider yet".
- **Reviews follow the FTC rule (16 CFR Part 465):** providers reply and report but never remove; a person checks every review and reply; removed reviews are counted publicly; replies that may confirm someone was a patient are flagged (HIPAA).
- **Sign-in (Q26, proposed default built):** one-time email link plus an authenticator-app code before any change. Only hashes of links and sessions are stored. Emails wait in `prov.outbox` until an email service is chosen (Q26 still open for the service).
- **Counts are privacy-safe:** daily totals only, searches on a 0.1° grid, no IP/device/account; numbers under 10 shown as "fewer than 10".
- **Boost = labeled "Sponsored" spot**, shared by up to 2 providers, never changes regular order (PRV-06). The dashboard shows estimates only; nothing is sold until Cooper approves payments (Q30).
- **Database roles:** the public API role reads only published views; a new portal role writes provider pages, reviews and counts only and cannot delete reviews.

: The GitHub repository becomes public (answers Q29)
Cooper chose to make `Cooper252/procedurescoutclaude` public so GitHub's standard Actions runners are free with no monthly cap, which the national downloads need (about 1 TB and many runner-hours per full refresh). Consequences:
- The code is visible to anyone. Passwords, database addresses and storage keys live only in GitHub Actions secrets and hosting settings, never in files; `.env` is git-ignored and only `.env.example` (no real values) is committed. Before switching, the files and history were checked for keys.
- No open-source license is added, so the code stays "all rights reserved": visible but not licensed for reuse.
- Workflows must never print secrets or upload them as run artifacts, and must not run on pull requests from forks.
- Run logs and uploaded run files become public too. Today they hold only public hospital data and throwaway test-database passwords that exist only inside each run.
- The self-hosted runner on Cooper's computer is the one real risk: on a public repository, a stranger's pull request could try to run code on it. The `home-fetch` job only starts by hand (`workflow_dispatch`), and right after the switch the repository is set to "Require approval for all external contributors" (Settings → Actions → General; GitHub shows this option only on public repositories), so no outside pull request runs anything without Cooper's click.

## 2026-11-08 — D-048: Hosting approved; the site is national
Cooper approved the hosting plan (about $53 a month to start: Render for the website, API and PostgreSQL; Cloudflare R2 for published Parquet files) and wants a full national website: every state, every hospital, surgery center and provider. Plan, in order:
1. Prepare hosting without spending: an S3-compatible store for R2, deployment files, then sign-up with Cooper.
2. Make every step state-by-state and repeatable: reference data and HRSA health centers for all states; hospital websites found and verified by their own cms-hpt.txt (which names the hospital), so no one reviews them by hand; price files parsed straight to Parquet per hospital and published to R2, skipping files that have not changed since the last run.
3. Insurance names, coverage limits and assistance policies placed by Claude per state with evidence (D-047).
Scale (from Nevada, 29 hospitals: 5.9 GB downloaded, 0.28 GB Parquet): roughly 6,000 hospitals nationally means about 1 TB of downloads for a full refresh and about 55 GB of Parquet on R2 (under $1 a month). The open question is where that downloading runs (Q29).

## 2026-11-08 — D-047: Claude places insurance names; Cooper does not review them
Cooper: "You need to figure out where they all go." Claude now resolves every hospital insurance spelling itself, from evidence it can check (insurers' and states' own pages, the hospital's file), and records the evidence in each alias's notes with `reviewed_by = "Claude (delegated by Cooper, D-047)"`. Names that cannot be placed with evidence are not guessed: they stay unmatched and remain findable exactly as written (D-046), and Claude keeps researching them each run. First batch (Nevada): plain "Sierra" HMO -> Health Plan of Nevada, PPO -> Sierra Health and Life (Sierra Health and Life is the PPO/POS/EPO company, HPN the HMO); Sierra "all plans" -> a combined Sierra card name; state-less "BCBS"/"Blue Cross" and "Anthem BCBS Colorado" at Nevada hospitals -> Anthem BCBS Nevada (Anthem is Nevada's Blue licensee, its Nevada plans are issued by Rocky Mountain Hospital and Medical Service / HMO Colorado dba HMO Nevada, and BlueCard prices visiting Blue members at the local plan's rates); Cigna's Wyoming company -> Cigna. Provider networks named by hospitals (MultiPlan, PHCS, First Health, Health Services Coalition and others) are card names too, as "Network on your card", because members see the network logo on their card. Left unmatched: "Northern Nevada | Medicare Advantage" and "Sierra Health | Medicare" (company unclear), networks, workers' comp and non-plan rows.

## 2026-11-08 — D-046: No published insurance rate is hidden while its name waits for review
Cooper: everything hospitals publish must be findable, not just the insurers we have matched. Cash prices, full prices and every negotiated rate were already published and visible in each place's Details. Now, in "My insurance", a person whose plan is not yet in the card-name list can search the insurer's name exactly as hospitals wrote it (`ref.payer_index`, built from all published prices) and see those rates, labeled as written and noting that one name can cover several plans. This is not a match (rule 9 is unchanged): nothing is merged or relabeled; card-name matching still needs approved aliases.

## 2026-11-08 — D-045: Three layers so the list never has to hold every procedure
Cooper pointed out that 202 services cannot cover millions of published prices without endless approvals.
1. **Every billing code is searchable automatically.** After each publish, `ref.code_index` lists every code in published prices with how many places publish it and the description hospitals most often use, shown labeled "As hospitals describe it" (D-002). People can type a code number or words from that wording; codes join `ref.code` by number only, so searches stay validated (rule 12) and no CPT descriptor is stored (rule 11). No approval is needed: the codes and wording are the hospitals' own published data.
2. **The standard service list is the friendly layer** for what people commonly shop for and for services with no billing code (massage, med spa). It grows over time; additions are approved in batches.
3. **Providers build on official pieces without new approvals:** they can price any approved standard service or any official billing code in `ref.code` (dentists by CDT number, doctors by CPT number), sell several sessions for one price (`quantity`), and create their own packages from those pieces (`prov.package`, `prov.package_item`). Package names are theirs; the pieces are standard, so packages stay searchable and comparable piece by piece. The usual listing review still applies.

## 2026-11-08 — D-044: The full (chargemaster) price is not a search choice
Almost nobody pays a hospital's full price, so showing it as a third way of paying confused people (Cooper). Searches offer only "Paying cash" and "My insurance"; the bundle builder shows cash prices. The full price stays in each place's Details table and on the "Already got a bill?" page, where it helps people check a bill. A place with no published cash price says so instead of showing the full price as a headline. The API keeps `mode=list` for tools that need it.

## 2026-11-08 — D-043: Public coverage limits and health centers on "Help paying"
- Medicaid, CHIP (Nevada Check Up) and marketplace-savings income limits are stored as a percent of the poverty guideline with the official source and shown in dollars for the person's household ("up to about $29,863 a year for 2 people"), always as "may qualify". Limits are policy text read by Claude, so they stay proposed until Cooper approves them (rule 10). Dollar amounts use the latest HHS guideline; agencies count monthly income with their own rules, so the page says the program decides.
- Community health centers come from HRSA's public site list (federally funded and look-alike centers charge on a sliding fee scale). Free clinics have no public national dataset; the page links to the state's 211 list (Nevada 211) instead of guessing.

## 2026-11-08 — D-042: One standard service list; providers pick from it; specials never replace regular prices
Cooper asked that providers choose services from a complete list instead of typing names, so the same thing is never listed three ways.
- **Standard list** (`ref.procedure`, `data/reference/service_catalog.csv`): one entry per thing a patient would compare. Different things get different entries (filling on 1 vs 2 surfaces; massage 60 vs 90 minutes; spine vs full-spine adjustment); the same thing in other words is one entry plus reviewed synonyms ("back adjustment", "back alignment"). Each entry says what it includes, which kinds of provider offer it (`ref.procedure_provider_type`) and its unit; new units per tooth, quarter of the mouth, arch, eye, vial and shot. Combinations ("cleaning with X-rays") are packages (bundles), not new services. Code numbers only (rules 11, Q16).
- **Providers can only price approved standard services** (database trigger on `prov.listing_price`). A missing service is requested and reviewed before anyone can use it.
- **Specials** (`prov.offer`): special price, percent off or dollars off, for new patients or everyone, with dates and short terms. The database refuses a special that is not lower than the regular price. Specials are shown as labeled specials next to the regular price; sorting, "lowest near you" and the typical range use regular prices only (`procedurescout_core/offers.py`).
- **"List price" renamed "Full price"** on the site (the hospital's starting, chargemaster price before discounts), with a plain explanation, because "list price" confused Cooper and would confuse patients.

## 2026-11-08 — D-041: Insurance plans by card name, from the real Nevada spellings
Cooper's answers (first "1" answered only question 1 because the other two were not shown to him; he then answered all three in writing: "1- 1, 2- 1, 3- 1"):
1. **One-for-all rates.** When a hospital published one rate for all of an insurer's plans ("Aetna | MANAGED_CARE", "All Plans") and no rate for the person's own plan, that rate is shown for regular employer or individual plans (HMO, PPO, EPO, POS, HDHP; commercial) and labeled "All <insurer> plans" with a note. Never for Medicare, Medicaid, marketplace or employer/union plans, and never mixed with the plan's own rate where one exists (`plans.all_plans_spellings`, `search.py`).
2. **Employer and union plans** (Culinary Health Fund, Teamsters, MGM Resorts, Clark County, ...) are choices in the picker under their own names.
3. **Approved:** the high- and medium-confidence proposals (159 card names, 431 hospital spellings) in `data/reference/payers.csv` and `payer_aliases.csv`, reviewed_by Cooper. Low-confidence rows (insurer unclear, e.g. plain "Sierra") and everything not meant for the picker (networks, doctor groups, workers' comp, jails, hospice, specialty-only contracts, out-of-state Blue plans, test rows) stay unapproved in `data/reference/proposed/plan_names_proposed.csv`.
A hospital payer spelling that holds plans of several companies (UMC's "Sierra Health and Life" also lists HPN Medicaid and employer plans) keeps one payer alias; matching uses only the plan alias rows.

## 2026-11-08 — D-040: How headline prices, typical ranges, badges and history are computed
Build step 1 of `SITE_DESIGN.md` (`procedurescout_core/pricing.py`, `plans.py`):
- **Headline:** per facility, the lowest published dollar amount of one price type only (cash, list, or the chosen plan's negotiated rate); several amounts are shown as a range.
- **Typical range:** one headline per facility, then the 25th/50th/75th percentiles by nearest rank, so every number shown is a price someone actually published; only with 5 or more facilities.
- **Likely file errors:** amounts under $1 or $10,000,000 and over are flagged at load (`under_one_dollar`, `over_ten_million`), kept and shown with a warning, but never used as a headline when another price exists, never "lowest", never in a typical range.
- **Badges:** lowest near you (with at least two prices), below typical (under the 25th percentile), cash cheaper than your plan.
- **History:** the headline compared with the facility's most recently retired published file (`price.published_file_history`, migration 0014; retired files were once public).
- **Plans by card name:** `data/reference/payers.csv` (plans as on cards) and `payer_aliases.csv` (a hospital's exact payer + plan spelling → that plan, approved by a person); plan searches use only approved spellings and never show another plan's rate in its place. The real Nevada spellings come from the next run (`payer-plan-names.csv`).
- **Search box:** suggestions from service names and approved everyday words (`service_synonyms.csv`; the 30 starting words are proposals).

## 2026-11-08 — D-039: Everything in the product review is in scope; site design written
Cooper (2026-11-08): "I like all of that so let's do all of it", and asked for a look at every aspect (ease of use, layout, better pricing). All of `PRODUCT_REVIEW.md` is approved, including community health centers and free clinics at launch, Medicare reference prices (labeled), and the full provider verification. `SITE_DESIGN.md` adds the site map, page layouts, ease-of-use rules, pricing features (headline "your price", typical local range, confidence, outlier holds, price history, Nevada uninsured discount if verified) and the build order. Paid hosting and billing still need Cooper's approval before they are set up.

## 2026-11-08 — D-038: Assistance limits shown in dollars; first policies proposed
Cooper (2026-11-08): say "You may qualify for this procedure for free if you make under $X single or $Y household", not poverty-level percentages, which people don't know. Messages now state dollar limits for 1 person and a family of 4, computed exactly from each hospital's reviewed percentage and the HHS guideline, shown rounded down to whole dollars (`assistance.plain_message`, `site_message`). Policies for 13 Nevada hospitals were found on the hospitals' and systems' own pages and recorded as proposals (`data/reference/assistance_policies.csv`, unreviewed) with evidence and notes on what is uncertain; they appear on the review page. The Valley Health System (UHS) Las Vegas hospitals' policy was not found yet (a same-named Virginia system's policy was rejected as the wrong organization).

## 2026-11-08 — D-037: Financial assistance is on every page and prominent on the home page
Cooper (2026-11-08): telling people they may qualify for free or reduced procedures under each hospital's guidelines was one of the biggest parts of the previous site and must be on every page, especially prominent on the home page. Built: HHS 2026 poverty guidelines (exact), reviewed per-hospital policy tables, a site-wide message and a "you may qualify" check that never says "eligible" and never stores the person's income (`FINANCIAL_ASSISTANCE_SPEC.md`). The hospitals' policies still have to be collected and reviewed (Q20).

## 2026-11-08 — D-036: Bundles: everything a procedure needs, with optional pieces as checkboxes
Cooper (2026-11-08): a procedure such as an endoscopy must show everything needed (facility, doctor, anesthesia, ...), with optional pieces (e.g. an epidural with a vaginal birth) as checkboxes. Built as `ref.bundle_component` (required/optional, default on/off, billing code) and `bundles.estimate`, which never counts a missing piece as $0 and says whether the total is complete (`BUNDLED_PRICING_SPEC.md`). Bundle contents are clinical decisions: the three starting bundles stay proposed until a clinical reviewer approves them (Q4).

## 2026-11-08 — D-035: Clean refreshes publish automatically; everything else waits for a person
Cooper (2026-11-08, answering Q19 "yes"): a new file for a hospital that already has approved prices publishes without a person when nothing got worse: refused rows not more than in the approved file, price count within ±30%, no new file problems, and the file's own date not older. First files and anything else wait for a person. Built as `publish.auto_check` / `auto_publish_pending` (CLI `auto-publish`); the reviewer recorded is "automatic checks (D-035)" with the reasons in the audit log.

Cooper also approved all 18 proposed services and the 6 proposed provider types (Q18, 2026-11-08); the catalog files now record him as reviewer.

## 2026-11-08 — D-034: Service catalog, provider types, search and the review page
- **Catalog:** `ref.procedure` is the service catalog (slug, unit, review state; migration 0012). Services and their code links come from `data/reference/service_catalog.csv`; the 18 starting entries are AI suggestions and stay `proposed` until Cooper approves them (rule 10). Code links point to code numbers only; no CPT or CDT descriptor text.
- **Provider types:** `data/reference/provider_types.csv`; the five Cooper named (hospital, surgery center, dental office, medical spa, weight-loss clinic) are approved, six suggestions are proposed. CMS facility types map hospitals and ASCs automatically.
- **Search:** `procedurescout_core/search.py` and `GET /v1/search` find published prices for one approved service near a point, optionally for one provider type; facilities nearby without published prices are listed with that status.
- **Review:** one decision per hospital file, not per price; the reviewer sees totals, refusals, flags, the file's own date and problems (`/admin/reviews`). Whether clean refreshes of an already-approved hospital may publish without a person is open (Q19).

## 2026-11-08 — D-033 (approved by Cooper 2026-11-08): Published prices stored as compressed Parquet files; PostgreSQL keeps the small, changing data
Run #13 measured the same 48,972,607 Nevada prices three ways (`storage-experiment.json`):
- current PostgreSQL table: 18,899,951,616 bytes with indexes;
- normalized PostgreSQL (estimate): ≈6.8 GB before indexes (3,131,046 distinct items, 639 distinct payer/plan pairs);
- **Parquet, one zstd file per facility: 281,912,696 bytes (≈67× smaller)**, every amount and percentage identical after the round trip, and the lookup of one common code across all 22 facilities listing it took 76 ms vs 805 ms in PostgreSQL (same 7,660,778 rows found).

Proposal: each published dataset version becomes one Parquet file per facility in object storage, read by the API with DuckDB only for the facilities a search needs; PostgreSQL keeps facilities, the service catalog, payer/plan aliases, provider accounts, provider-submitted prices and corrections, review state and lineage. Staging and quality review stay in PostgreSQL during ingestion. The API's "published only" guarantee (D-004) moves from a database view to storage permissions: the API can read only the published prefix. Rough national figure (≈10 billion rows extrapolated by hospital count): about 60 GB of Parquet, i.e. under $1/month of storage at Cloudflare R2's $0.015/GB-month (no egress fees), checked 2026-11-08; compute for the API is separate. Cooper approved on 2026-11-08 ("Yes"). Built first: the review step (`publish.py`), the exact Parquet writer (`parquet_io.py`), a local object store (`object_store.py`; the S3-compatible store waits for the hosting decision) and the validated read path (`price_store.py`). Amounts are stored in Parquet as DECIMAL(38,15): every value is numerically identical (checked on every publish), though trailing zeros are not preserved as text.

## 2026-11-07 — D-032: Any medical or wellness provider can list; search by service and by provider type
Cooper (2026-11-07): listings are open to any medical or wellness provider, not only surgery centers and dental offices (e.g. medical spas, weight-loss clinics). The home search lets a person pick what they are looking for (e.g. Botox) and search every provider near them that offers it, or narrow to one provider type (e.g. medical spas).

Consequences:
- **Provider types** become a reviewed list (hospital, surgery center, dental office, medical spa, weight-loss clinic, imaging center, lab, urgent care, chiropractor, ...), each provider tagged with one or more.
- **A service catalog of our own.** Many such services have no billing code (cosmetic Botox is priced per unit or per area; weight-loss programs per month). Searchable services are entries in our own catalog with plain-English names and units; an entry links to billing codes (CPT, HCPCS, CDT, DRG) when they exist. Hospital-file prices reach the catalog only through reviewed code links; provider-entered prices are entered against catalog entries. Prices with different units (per unit, per area, per session, per month) are never compared as if they were the same.
- The price layout being redesigned (NAT-02) carries price source (D-030), provider type and catalog entry from the start.

Cooper also confirmed the three D-031 rules (2026-11-07): payment buys a listing, never a better rank or different labels, and paid placements are marked "Sponsored"; hospital-file prices stay shown free; correcting your own errors is free.

## 2026-11-07 — D-031: Providers will pay to list their own prices (after a free period)
Cooper (2026-11-07): provider listings start free for a few months, then become paid; surgery centers and others who want to advertise their prices pay to do so. This is the approval CLAUDE.md asks for before monetization is *designed*; building the billing feature still waits for Phase 9 and its own go-ahead.

Rules (confirmed by Cooper 2026-11-07, see D-032):
- Payment buys a listing of the provider's own prices, never a different ranking of results, different labels, or the removal of anyone else's prices. Any paid placement is labeled "Sponsored".
- Prices from hospitals' government-required files stay shown whether or not the hospital pays, so comparisons stay complete.
- A hospital correcting an error in its own prices should not need to pay (otherwise accuracy becomes something we sell).
- Advertising rules (e.g. FTC disclosure of paid placements) and these terms are part of the counsel review (Q1).

Also recorded: why there is a price database at all. Searching hospital files live is not workable: one search would have to download gigabytes from dozens of sites (minutes per search), several sites refuse automated requests or limit them, and codes and payer names must be matched before prices can be compared. Files are therefore downloaded on a schedule and stored in a searchable form. To keep national storage cheap, the redesign (NAT-02) will test storing prices as compressed per-hospital files in low-cost object storage, read only for the hospitals a search needs, with a small database for facilities and codes, against a full PostgreSQL table.

## 2026-11-07 — D-030: National scope; providers enter and correct their own prices
Cooper (2026-11-07): the launched site covers every US state and every kind of provider (hospitals, surgery centers, dental offices and others), not only Nevada. Providers will sign up to enter their own prices, and hospitals to correct theirs, so the site is accurate and ProcedureScout is not the one asserting the prices.

Consequences, built into the design from now on:
- **Every price carries its source**, and the sources are never blended silently: `hospital_file` (CMS machine-readable file), `provider_submitted` (entered by a verified provider), `provider_correction` (a hospital's correction of its own file price). Display labels say which.
- **Nothing is overwritten.** A correction is a new, attributed, dated row linked to the file price it replaces; the file value stays stored and reachable. Rule 8 (no silent substitution) applies.
- **Authority is verified before anything goes public** (PRV-01), every change is audited (who, when, before, after), and changes can be held for review (PRV-05). Provider prices are subject to the same exactness rules (Decimal, no rounding, no invented values).
- **Liability:** provider attestation and terms of use help but do not by themselves remove liability; counsel review stays a launch requirement (Q1).
- **Scale:** Nevada's pilot load was 45.2 million price rows (≈17 GB). Extrapolated by hospital count (≈1.7 million rows per hospital × ≈6,000 US hospitals) that is on the order of 10 billion rows (several TB) in the current layout, before ASCs and other providers; a very rough figure. The price layout is redesigned for this before any hosting is chosen (NAT-02).
- **Dental codes (CDT)** are owned by the American Dental Association, like CPT by the AMA: show code numbers and our own names until licensing is settled (Q16).

## 2026-11-07 — D-029: Amounts stored exactly as published (unconstrained NUMERIC); supersedes D-008's 4-place limit
Run #12 refused about 120,000 real prices for having more than 4 decimal places: sub-cent negotiated rates (UHS files: 2669.73225, 1.53765) and spreadsheet artifacts (460.370000000001; JSON 19.380000000000003). Rounding is not allowed, so `amount`, `percentage` and `drug_unit` become unconstrained NUMERIC (migration 0010; its downgrade refuses rather than rounds) and the parsers accept up to 15 decimal places. Such prices are flagged `more_than_4_decimals`; rounding to cents happens only on screen. Trailing zeros ("2781.00000") are kept as published.

Also from run #12: CSV column names are compared without case or spaces around "|" ("code |1" = "code|1", Seven Hills), and inside one wide CSV the columns of one payer/plan are grouped by label without case or extra spaces ("Hometown Health Plan NV | All" with "hometown health plan nv|all", Pershing). This only joins one file's own columns; the stored payer and plan names are the labels as first published, and matching to canonical payers still needs approved aliases.

## 2026-11-07 — D-028: Prices are read into staged datasets; publishing needs a person
`price_parser.py` turns each CMS file into one row per published amount and `price_load.py` copies them into `price.price` under a new *staged* `src.dataset_version`; the import run stops in `quality_review`. Staged rows are invisible to the API (`price.published_price` shows published datasets only), so no price reaches a user before a person reviews the load. Each item is stored once under its most specific code, the other codes kept in `price.price.other_codes` (migration 0009), instead of one row per code (which would multiply the table 2–3×). Anything that cannot be read exactly is refused with a reason (see `DATA_QUALITY_RULES.md`). In the manual workflow, the price load runs in GitHub's throwaway database to measure real row counts and size before any hosting decision.

## 2026-11-07 — D-027: Centennial Hills and Spring Valley files; campus children point to the parent's file
Cooper answered "1" (2026-11-07) to two questions whose first options were: approve Centennial Hills' two ERs as co-listed (as in D-023); and use Spring Valley's file for Spring Valley only. Spring Valley's cms-hpt.txt lists Spring Mountain Sahara (294010) and Spring Mountain Treatment Center (294011) "an Extension of Spring Valley Hospital" with the same file. Recorded as approved `campus_of` relationships (290046 parent) in `data/reference/facility_relationships_reviewed.csv`; discovery gives a file to the parent when the only other facilities it names are the parent's approved campus children, and reports each child as `listed_in_parent_file`. The children show the `in_parent_file` status, never the parent's prices. The answer "1" was read as the first option for both questions; this can be reversed by removing those rows.

## 2026-11-07 — D-026: Price files from sites that refuse GitHub are downloaded on Cooper's computer
Extends D-021 to price files. Run #10: Boulder City and Desert Parkway answered 403 to GitHub's servers. Sites listed in `data/reference/home_runner_price_sites.csv` have the price files named in their cms-hpt.txt downloaded live on Cooper's computer in the same run (`scripts/fetch_prices_home.ps1`, 500 MB limit per file); the main job uses such a file only when its own download of that URL fails, and records `fetched_via = 'home_runner'` (migration 0008). Same rule as before: no browser disguise, no retrying around a refusal from the same network. Dropped connections (e.g. Carson Valley, "connection reset by peer") are now retried once after 15 seconds.

## 2026-11-06 — D-025: Price files downloaded, checked and deleted; nothing stored yet
Cooper (2026-11-06) approved downloading the Nevada price files (about 5 GB; CLAUDE.md requires approval over 50 MB) on GitHub's free, throwaway runner. Each file is streamed to a temporary file with its SHA-256, read once to record the header as published and counts, then deleted (`src.transparency_file.object_store_key` is NULL). Runs only when the workflow input `download_price_files` is ticked (`PRICE_FILE_DOWNLOADS=1`). A size limit (4 GiB per file by default, `PRICE_FILE_MAX_BYTES`) stops runaway downloads. Permanent storage and a hosted database are separate decisions, to be asked about before any paid service.

## 2026-11-06 — D-024: When a hospital has two price-file links, use the newer one
Cooper (2026-11-06), for Sunrise and MountainView: use the link whose server reports the newer Last-Modified date (the HCA sunrisehealthinfo.com links, 2026-10-21) over the hospital-site links (2025-01-03). Implemented as a general rule in `price_files.choose_per_facility`: newest server date wins, the other links are reported as `older_link_skipped`; if any link of that hospital has no usable date, all are read (no guessing). The date written inside the file (`last_updated_on`) is recorded too and flagged when older than a year.

## 2026-11-06 — D-023: Reviewed "co-listed" locations in a hospital's own price file
Seven Nevada hospitals (Sunrise, MountainView, Southern Hills, Summerlin, Henderson, Valley, Northern Nevada Medical Center) publish one file that also names their freestanding ERs, clinics or service lines. Cooper approved (2026-11-06) assigning each file to its hospital. Recorded in `data/reference/hpt_co_listed_locations_reviewed.csv` as exact (location name, hospital) pairs taken from run #9; such entries get `match_status = 'co_listed'` with `co_listed_with` (migration 0007) and do not block the assignment. They are not facilities of ours and get no prices of their own. A new, unapproved name in the same file, or an ambiguous one, holds the file back again.

## 2026-11-06 — D-022: Placeholders, not workarounds, for hospitals we cannot read
Cooper (2026-11-06): until Renown and Tahoe Forest allow automated access (emails drafted, to be sent once the site is running), those hospitals are listed with "Prices coming soon". Other hospitals without a usable file get a plain status (see `CONSUMER_USER_FLOWS.md`). Files downloaded by hand are not loaded for now; if added later they must carry who downloaded them, when, the source URL and SHA-256, be labeled as manually loaded, and be flagged once stale.

## 2026-11-06 — D-021: Live fetches from Cooper's computer for sites that refuse GitHub
Cooper chose option A: a GitHub self-hosted runner on his own computer (label `procedurescout-home`) fetches every approved site's /cms-hpt.txt live at the start of the manual Nevada workflow (`scripts/fetch_hpt_home.ps1`), and the main job uses those files only for sites whose fetch from GitHub fails. Every fetch row records `fetched_via` (`github` | `home_runner`). The runner job reads only the approved websites list and writes only its output folder. Because a self-hosted runner executes workflow code, the repository must be private before the runner is connected. When the computer is off, untick "use_home_computer" when starting the run.

## 2026-11-06 — D-020: Live sources only; no saved copies (supersedes D-019 in practice)
Cooper (2026-11-06): "Don't use anything saved. I want everything to use updated and correct pricing." Captured cms-hpt.txt copies are no longer approved and are ignored; every run reads each hospital's current cms-hpt.txt live, and a site that refuses the request is reported as not reachable that run. The hand-entered William Bee Ririe link (an .xlsx apparently from 2023) is also unapproved. The captured files stay in `data/reference/hpt_captured/` only as a dated record (see its README). The code path for captured copies remains but has no approved input. Price files themselves were never saved and are always downloaded live.

## 2026-11-05 — D-019: Browser-captured cms-hpt.txt copies as a labeled fallback
Some hospital sites refuse automated requests from cloud servers but serve the same public file to a person's browser. A copy captured in a browser is stored verbatim with its source URL and date, used only after a person approves it, used only when that site's live fetch fails, and every fetch row records whether its content was `live` or `captured`. Challenges meant to stop automation (CAPTCHAs) are never answered on anyone's behalf, and access refused to a browser is reported, not worked around. Hand-entered price-file links are allowed only with evidence and a reviewer, and carry a note explaining why they exist.

## 2026-11-05 — D-018: Discovery starts from approved websites only
Hospital websites are proposed (with evidence) and used only after a named person approves them; the database refuses a website without reviewer and date. Price files are found through `/cms-hpt.txt` on those sites. A cms-hpt.txt location is tied to a facility only by an exact name match through usable aliases; other names are stored and reported for review. A price file listed for several locations, or for any unmatched location, is not assigned to a single facility; the facility mapping happens per file when it is downloaded and read (Phase 2 step 2). Federally owned hospitals are marked exempt rather than searched.

## 2026-11-05 — D-017: Table 5 correction notice supersedes the final rule
When the IPPS Table 5 workbook contains both the final-rule table and a correction-notice table, the correction notice is loaded and the differences are counted in the load summary. If several tables exist and exactly one is not marked as a correction, the load is refused rather than guessing.

## 2026-11-04 — D-016: Reference loads are idempotent upserts with lineage
Every reference load writes a `src.reference_load` row (source URL or file, SHA-256, size, source modified date, counts) and its rejects to `src.reference_reject`. Data changes run in one transaction; a failed load leaves only its `failed` lineage row. Facilities absent from a newer CMS file are not deleted or marked closed automatically (`source_last_seen_at` records when they were last seen); closing a facility needs evidence.

## 2026-11-04 — D-015: Codes are versioned by code-set year (HCPCS) and grouper version (MS-DRG)
HCPCS rows use version = HCPCS year ("2026"); each quarterly file updates that year's descriptors and termination dates. MS-DRG rows use version = grouper ("v44") with effective dates from the fiscal year (FY2027 = 2026-10-01 to 2027-09-30). Only Level II HCPCS codes (letter + 4 digits) are stored; numeric five-character codes in any HCPCS file are skipped so no AMA text can enter (D-002). Modifiers are skipped for now. MS-DRG codes read from spreadsheet cells as 1–99 are restored to three digits ("001"); ZIPs and CCNs that lost leading zeros are refused instead, because those come from text files where a short value signals corruption.

## 2026-11-04 — D-014: Geocoding preference and validation
Address-level coordinates come only from the Census Geocoder (public, no key; batch endpoint first, one-address endpoint if the batch endpoint fails), and only when the match's state and county agree with the facility's published state and county; ties are never used. Otherwise the facility gets its ZCTA internal point, labeled `zcta_centroid`; otherwise no location. Precision is stored and the database requires it whenever `geom` is set. Search-time ZIP lookups use the local `ref.zcta` table only.

## 2026-11-04 — D-013: Facility and health-system identity by identifier, never by name
Facilities are keyed by CCN (6 characters for hospitals, 10 for ASCs, e.g. 29C0001035); NPIs link ASCs to NPPES. Names become aliases: identifier-linked aliases are usable at once, other aliases need a named reviewer. A name shared by two facilities resolves to *ambiguous*, never to one of them. Health systems are keyed by (source, source id); `UNIQUE(name)` on `ref.health_system` was dropped because a name match must not merge two systems. AHRQ links never overwrite a link entered by a person. Campus relationships are never inferred; only reviewed rows with evidence count.

## 2026-11-04 — D-012: CMS Provider Data Catalog via the datastore API, filtered by state
Hospitals (`xubh-q36u`) and ASCs (`4jcv-atw7`) are read through the PDC datastore query API for one state, paged, and refused if the received count differs from the API's count. A downloaded CSV is accepted too; its column titles normalize to the API's machine names. The dataset's `modified` date dates the star rating. Unknown CMS hospital types are rejected, not mapped to "other"; VA and DoD acute-care hospitals map to `acute_care_hospital` with the raw type kept; Rural Emergency Hospitals map to `other`.

## 2026-11-04 — D-011: Real reference data verified in CI, not in the build workspace
The cloud build workspace cannot reach government data hosts. Loaders are tested on synthetic fixtures modeled on the official layouts, and a manual GitHub Actions workflow (`reference-nv.yml`) performs the real Nevada load on a throwaway database and publishes its report. Nothing from that run is kept.

## 2026-11-04 — D-010: Price table partitioned by LIST(state_code)
Rollout is state by state; most consumer searches are within one region; a state partition can be loaded, vacuumed, reindexed or detached independently. Facility-level replacement uses `dataset_version` pointers, not partition swaps. Consequence: PK is (state_code, id); a state partition can be sub-partitioned by hash later if one state grows too large.

## 2026-11-04 — D-009: Long-format price rows
One row per published amount, typed by `price_type`, instead of one wide row with gross/cash/negotiated columns. Reason: makes it structurally impossible to rank a cash price against a negotiated rate by accident, and lets constraints differ per type. Cost: roughly 1.5–3× more rows than wide format; acceptable for Nevada, revisit with measurements before national scale. Supersedes the wide layout sketched in the Phase 0 plan.

## 2026-11-04 — D-008: Amounts stored as NUMERIC(16,4), not NUMERIC(14,2)
Per-unit drug prices and some fee schedules are published with sub-cent precision. Two decimal places would round source values. The parser refuses values with more than 4 decimal places instead of rounding. Display rounding happens only in presentation.

## 2026-11-04 — D-007: Code systems match CMS v3.0 exactly
`ref.code_system` uses the 21 CMS v3.0 `code_information.type` values. An earlier draft had 10 values and would have rejected valid files (APC, HIPPS, CDT, etc.).

## 2026-11-04 — D-006: v2 `estimated_amount` kept as its own price type
v2.0/v2.2 files contain an estimated allowed amount that v3.0 removed. Stored as `estimated_allowed`, never shown as a negotiated rate.

## 2026-11-04 — D-005: Allowed-amount count stored as published text
CMS defines `count` as "0", "1 through 10", or a whole number ≥ 11. Stored verbatim in `allowed_count_raw` with a CHECK, because "1 through 10" has no integer value.

## 2026-11-04 — D-004: API reads only `price.published_price`
The restricted role has no grant on `price.price` or `fixture`. Staged or failed imports and synthetic data are unreachable from the API by database permissions, not just by query filters (the legacy app relied on ~30 separate `is_sample` filters).

## 2026-11-04 — D-003: Import transitions enforced in the database
A BEFORE trigger validates transitions against `src.import_transition`; an AFTER trigger logs them. The Python state machine uses the same list; a test checks they match.

## 2026-11-04 — D-002: CPT without an AMA license at launch
Store and show CPT code numbers as hospitals publish them, our own plain-English names, and hospital-published descriptions labeled as such. AMA descriptor text is refused by a DB constraint unless `descriptor_licensed` is true. Legal review before public launch.

## 2026-11-04 — D-001: Rebuild, don't migrate, the legacy app
Legacy MongoDB data (17.3M rows) is not migrated; procedurescout.com is taken down during the rebuild; all hospital files are downloaded fresh. See `LEGACY_AUDIT.md`.
