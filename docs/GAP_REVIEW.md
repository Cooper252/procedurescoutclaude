# Gap review: what ProcedureScout is still missing (2026-11-11)

Cooper asked for a full list across every area. Each item says **what**, **why
it matters**, and a rough **size** (S = hours, M = a day or two, L = a week+).
"Have" notes what already exists so nothing is rebuilt. Priorities: **P1** before
or right after launch, **P2** first months, **P3** later.

## 1. Providers and listings

| # | Item | Why | Size | Pri |
|---|---|---|---|---|
| 1.1 | **Individual clinicians add themselves** by NPI (doctors, therapists, psychiatrists, dentists, PTs). The national provider list (NPPES) is checked live when they sign up; their listing stays **hidden until they add prices** (Cooper, 2026-11-11). Not preloaded: about 3 million people nationally would bloat the database. | Most therapists and many specialists work alone. | M | P1 |
| 1.2 | **Psychiatrists** and **all common specialties**: cardiology, orthopedics, OB-GYN, ENT, gastroenterology, urology, allergy, neurology, endocrinology, rheumatology, pulmonology, oncology, nephrology, pain medicine, sleep medicine, plastic surgery, fertility (REI), sports medicine. Have: family, internal, pediatrics, dermatology only. | Specialists are where prices vary most. | S | done (2026-11-11, migration 0022) |
| 1.3 | **"Usually needs a referral"** label by specialty and plan type (HMO vs PPO), explained in plain words. | People don't know if they can go directly. | S | done (shown on specialist pages) |
| 1.4 | **Offices without prices out of the way**: search shows priced places first; unpriced ones collapse under "N more nearby that haven't posted prices (ask them)". | Thousands of unpriced pins drown 12 real prices. | S | done (search page) |
| 1.5 | More kinds of places: dialysis, home health, hospice, nursing homes (CMS directories, free), ambulance, medical equipment suppliers, birthing centers and midwives, addiction treatment (SAMHSA locator), sleep centers, fertility/IVF clinics, LASIK centers, hair restoration, IV hydration, hormone/TRT and weight-loss clinics, acupuncture, dietitians, speech and occupational therapy, retail clinics (MinuteClinic etc.), pharmacies. | Each is a real "what does it cost" search. | M | P2 |
| 1.6 | **Chains and multi-location groups**: one account, many locations, one price list applied to all or per location. Have: memberships per facility. | Labs, urgent care, imaging and dental chains will only join if it's easy. | M | P1 |
| 1.7 | **Telehealth companies** as national listings (Teladoc, Amwell, MDLive, Sesame, Hims/Hers, etc.), shown in every state they serve, prices only from what they publish or enter themselves. | People compare online visits by price. | S | P1 |
| 1.8 | **Labs** (Quest, Labcorp) and imaging chains invited to claim national listings and post cash prices. Their website prices are not copied without permission. | Often the cheapest option for lab work. | S | P1 |

## 2. Services and prices

| # | Item | Why | Size | Pri |
|---|---|---|---|---|
| 2.1 | **Mental health services**. Have (since 2026-11-08): therapy 45/60 min, first visit (90791), couples, group. **Added 2026-11-11**: psychiatric evaluation with a psychiatrist (90792), medication follow-up, TMS, Spravato, ketamine infusion. | Mental health is a top cash-pay category. | S | done |
| 2.2 | **Cosmetic surgery**. Have: injectables, fillers, peels, microneedling, laser hair removal, fat freezing, PRP. **Added 2026-11-11**: breast augmentation, lift, reduction, male breast reduction, liposuction (per area), tummy tuck, BBL, rhinoplasty, facelift, eyelid surgery, brow lift, ear pinning, mommy makeover, hair transplant, lip filler. Still to do: what each price includes (surgeon, anesthesia, facility) as separate tick boxes. | Cosmetic is almost all cash, the likeliest paying providers. | S | mostly done |
| 2.3 | **Specialist visits and procedures**. Have: colonoscopy, endoscopy, sleep study, vasectomy, echo, stress test, allergy testing, GLP-1 programs. **Added 2026-11-11**: new specialist visit, full skin check, IUD insertion, IUI, IVF cycle, egg freezing, hearing aids. | Covers "referral" searches end to end. | S | done |
| 2.4 | **In-person vs telehealth** on every provider price (in person / online / both) and an **"Online visits" filter**. Hospital files: telehealth modifiers (95, GT) shown as "online". Have: a telehealth badge on provider pages only. | Asked for directly. | M | P1 |
| 2.5 | **Medicare's price** for each service as a fair-price yardstick (Medicare Physician Fee Schedule + hospital outpatient rates, public domain), adjusted for the area. | Gives every price context, even with no other prices nearby. | M | P1 |
| 2.6 | **Prescription drugs**: pharmacy acquisition cost (NADAC, public), drug names in plain English; pharmacy cash prices only through partners. | Drugs are a top cost question. | M | P3 |
| 2.7 | **Package prices** clearly split from single items, and "what's included" (facility, surgeon, anesthesia) on cosmetic and surgery prices. Have: packages and bundles. | Cosmetic quotes are packages. | S | P2 |

## 3. Insurance and what you'll pay

| # | Item | Why | Size | Pri |
|---|---|---|---|---|
| 3.1 | **Copays**: on provider prices, "With insurance: standard copay applies" or the copay they list; on searches, "Your plan's copay for a specialist visit is $__" for marketplace plans (CMS plan attribute files, public). | Asked for directly. | M | P1 |
| 3.2 | **"What will I pay?" estimator**: deductible left, coinsurance %, out-of-pocket max, then the estimate on each result, saved only in the browser. Have: explanations only (learn pages). | The question most insured people actually have. | M | P1 |
| 3.3 | **Insurance names for every state**: matched automatically when certain, researched with evidence otherwise (D-047). Have: Nevada (500 approved spellings). | Without it the plan picker is Nevada-only. | L | P1 |
| 3.4 | **Insurance accepted** and **taking new patients** as fields providers fill in, searchable and filterable. Have: a free-text insurance note. | People filter on these first. | S | P1 |
| 3.5 | **Insurers' own price files** (Transparency in Coverage): what each plan pays each doctor. | The real answer for in-network doctor visits; terabytes, so a later project. | L | P3 |
| 3.6 | **Medicare and Medicaid patients**: show "Medicare patients usually pay 20% of $__" using 2.5. | Large audience. | S | P2 |

## 4. Payments and billing (providers paying us)

| # | Item | Why | Size | Pri |
|---|---|---|---|---|
| 4.1 | Have: Stripe checkout, customer portal, plans by provider type, Sponsored spots, webhooks (off until Cooper charges). | — | — | — |
| 4.2 | **Founding-member offer and free period** recorded per provider (e.g. free until a date, then a discount for early joiners). | Gets the first providers in. | S | P2 |
| 4.3 | **Annual billing, coupons, taxes (Stripe Tax), receipts and failed-payment emails** (mostly Stripe settings). | Standard for subscriptions. | S | P2 |
| 4.4 | **Pay per lead** as an alternative to a monthly fee (only charged when a patient contacts them through us). | Small practices with few visitors (Cooper's concern). | M | P3 |
| 4.5 | Patients paying through the site (deposits, booking). Not recommended now: money handling, refunds, liability. | — | L | P3 |

## 5. Getting providers to sign up and add prices

| # | Item | Why | Size | Pri |
|---|---|---|---|---|
| 5.1 | **"Patients are asking" requests**: a button on unpriced listings, "Ask for prices"; we count requests and tell the provider ("14 people asked for your MRI price this month"). | The strongest reason for a provider to log in. | M | P1 |
| 5.2 | **Outreach emails** to hospitals' price-transparency contacts (listed in every cms-hpt.txt) and to practices that publish an email, with their page link and real counts; unsubscribe link; CAN-SPAM compliant. | No one claims a page they don't know exists. | M | P1 |
| 5.3 | **Price-list templates by kind of practice** (Cooper, 2026-11-11). At sign-up a practice downloads a spreadsheet made for its kind of care, with our services, codes and units already filled in, so all price lists look the same. Combined practices tick more than one (dental + orthodontics + oral surgery) and get those sections in one file. On **upload** every line is checked: matched to our services by code (CPT, HCPCS, CDT numbers with our own plain names, no ADA text, Q16) or by name. Prices are checked for format, units and impossible values. Each problem is shown on its line, and nothing goes live until they confirm. Lines we don't have yet are kept as the practice's own items under its own wording and added to our list after review (D-047-style evidence). Also: typing prices in the portal, starting from the same list; **upload of an existing price sheet (PDF/photo)** read into the same template for them to confirm. | Typing 50 prices by hand stops most practices; uniform lists make prices comparable. | M | P1 |
| 5.4 | **Monthly stats email** to claimed providers (views, searches nearby, requests, reviews). Have: dashboard counts. | Keeps them coming back and updating prices. | S | P2 |
| 5.5 | **"Prices on ProcedureScout" badge** and a small price widget for their own website (links back to us). | Free advertising and backlinks. | S | P2 |
| 5.6 | Referral reward: a provider who invites another gets a free month (once billing is on). | Cheap growth. | S | P3 |

## 6. Front end (what visitors see)

| # | Item | Why | Size | Pri |
|---|---|---|---|---|
| 6.1 | **Map view** of results. Have: list only. | People think by location. | M | P2 |
| 6.2 | **Filters**: open now, evenings/weekends, online visits, language, insurance accepted, new patients, rating, distance. Have: provider type, distance. | Narrowing is half of shopping. | M | P1 |
| 6.3 | **Compare side by side** (2–4 places) and **save/share** a result. | Decision support. | S | P2 |
| 6.4 | **Price alerts** by email ("tell me when a cheaper MRI appears near 89123"). | Return visits; needs email consent. | M | P3 |
| 6.5 | **Good Faith Estimate helper**: a ready letter for uninsured patients to request one (No Surprises Act). Have: explained on learn pages. | Practical protection. | S | P2 |
| 6.6 | Screen-reader check by a person; Spanish read by a native speaker. | Already on the go-live list. | — | P1 |
| 6.7 | Installable on phones (PWA). | Cheap, feels like an app. | S | P3 |

## 7. Back end and operations

| # | Item | Why | Size | Pri |
|---|---|---|---|---|
| 7.1 | **Error alerts and uptime check**: Sentry (free tier) for errors; an uptime monitor (free) that emails Cooper. | Know about outages before users do. | S | P1 |
| 7.2 | **Scheduled housekeeping** (free, GitHub Actions): email retries, daily stats rollups, deleting expired sign-in links and old sent emails, code-index refresh. | Some of these only happen when someone uses the site today. | S | P1 |
| 7.3 | **Off-site backups**: weekly database copy to R2 (Render Hobby keeps only 3 days). | Recovery from mistakes. | S | P1 |
| 7.4 | **Cloudflare in front of the site** (free; move DNS from IONOS, keep IONOS email): caching, bot and scraping protection, attack protection. | Cheaper bandwidth, safer. | S | P2 |
| 7.5 | **Data freshness dashboard**: per state, hospitals with prices, files published, files set aside and why, last load date, sites that block us. | Run the national data without reading logs. | M | P1 |
| 7.6 | **Home-computer fetch for blocked hospital sites** in the live run (optional, when Cooper's computer is on). | About 1 in 6 hospital sites refuse GitHub's computers. | S | P2 |
| 7.7 | **More hospitals**: the 1,900 hospitals in the Medicare enrollment list but not CMS's hospital list (DoltHub has 7,231 vs our 5,306), and DoltHub's 4,205 price-file links checked by header address (D-058). | Coverage is 41% today. | M | P1 |
| 7.8 | Support inbox and contact form; provider dispute/takedown process; a public status page. | Required once real people rely on it. | S | P1 |

## 8. Statistics and dashboards

| # | Item | Why | Size | Pri |
|---|---|---|---|---|
| 8.1 | **Owner dashboard for Cooper**: visitors, searches, top services, searches with no results (what to add next), providers claimed, prices added, requests, reviews, revenue. Have: provider dashboards and review queues only. | Run the business. | M | P1 |
| 8.2 | **Price reports by state** from the data ("MRI prices in Nevada range from $X to $Y"): public pages and press material. | Free press and SEO. | M | P2 |

## 9. Advertising and growth

| # | Item | Why | Size | Pri |
|---|---|---|---|---|
| 9.1 | Have: city and service pages, sitemap. Add **structured data** (schema.org MedicalBusiness / Offer) so Google shows prices. | Search traffic is the main free channel. | S | P1 |
| 9.2 | **Google Search Console and Bing** set up after launch. | See what people search to find us. | S | P1 |
| 9.3 | Partners: HR/benefits brokers, patient advocates, cash-pay surgery centers, health-sharing ministries, cosmetic marketplaces. | Distribution. | — | P2 |
| 9.4 | Data API or licensing for employers and researchers (paid). | Second revenue line. | L | P3 |

## 10. Legal and policy

| # | Item | Why | Size | Pri |
|---|---|---|---|---|
| 10.1 | Lawyer review (Q25), now also: provider listing agreement, outreach emails (CAN-SPAM), the FTC's 2024 rule on fake reviews, medical advertising rules for cosmetic specials. | Before charging and before outreach. | — | P1 |
| 10.2 | Data credits: CC BY-SA 4.0 credit for the DoltHub list. **Done 2026-11-11** on "How it works". | License requires it. | S | done |
| 10.3 | Privacy: no ad trackers; if analytics are added, cookieless (e.g. Plausible) to avoid a cookie banner. | Trust; health searches are sensitive. | S | P1 |

## 11. Making it easier for everyone

| # | Item | Who it helps | Size | Pri |
|---|---|---|---|---|
| 11.1 | **"Prices still correct?" one click**: every 6 months we email the practice; one click re-confirms all prices. Each price shows "confirmed on [date]". Prices not confirmed for 12 months are marked "may be out of date". | Providers, patients | S | P1 |
| 11.2 | **Change all prices by a percentage** (yearly increases) and **copy a price list to another location**. | Providers, chains | S | P1 |
| 11.3 | **Plain-English names and a short "what is this?"** on every service, plus "what's usually included". Have: plain names. | Patients | S | P1 |
| 11.4 | **Search understands everyday words** ("tooth cleaning", "boob job", "nose job", "Ozempic", "therapy"). Have: synonyms list; grow it from searches with no results. | Patients | S | P1 |
| 11.5 | **Review queue shortcuts for staff**: approve many at once, filters by kind and state, reasons pre-written. | Cooper, staff | S | P2 |
| 11.6 | **Guided setup** for a new provider: claim, then logo and hours, then template, then done, with a progress bar. Have: separate tabs. | Providers | S | P1 |
| 11.7 | **"Message the practice"** from a listing (goes to their email; no patient health details asked). | Patients, providers | M | P2 |
| 11.8 | **Help pages for providers**: how prices are shown, how to fix a wrong hospital price, how billing works. | Providers, Cooper (fewer support emails) | S | P1 |
