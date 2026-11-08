# Product review: what would make ProcedureScout more helpful

Written 2026-11-08 at Cooper's request ("think about every single aspect ... see what I'm missing"). Nothing here is built or decided yet unless it says so; each item names who it helps, why it matters, and a priority: **Launch** (should be there on day one), **Soon** (first months), **Later**.

The test for every item: does it help a person pay less, get free or reduced care they are entitled to, or understand what they are buying, without ever showing a false price?

---

## 1. Finding the lowest cost

1. **Search in everyday words (Launch).** People type "knee scope", "MRI back", "colonoscopy", "getting tubes tied", often misspelled. Each service gets reviewed synonyms and common misspellings (the `ref.procedure_synonym` table already exists), plus "Did you mean …?". Never silently swap one procedure for another (rule 8): show "Showing results for MRI of the lower back. Not it? See MRI of the upper back."
2. **One question at a time (Launch).** Location → "Do you have insurance?" → plan (from the plans the nearby hospitals actually publish) → procedure. The answer screen leads with the person's real cost type: their plan's rate, or the cash price.
3. **Cash can beat insurance (Launch).** Hospital files often show a cash price below what a plan pays (and the person may owe all of it before their deductible). Flag it plainly: "Cash price here is $640; your plan's rate is $1,180. Ask for the cash price."
4. **Worth the drive (Launch).** "Drive 38 miles to Carson Valley and save about $2,100" with a map. Many people will travel for a big saving; few know they can.
5. **What you'll actually owe (Soon, EST-01).** Enter deductible left, coinsurance, copay, out-of-pocket max; we do the arithmetic on the published rate and show every step. If the plan rate is a percentage or formula, say "cannot estimate" rather than guess (EST-02).
6. **Medicare reference price (Soon).** CMS publishes what Medicare pays for most procedures (public data, no license issue). Showing "Medicare pays about $X here" gives people a fair anchor and a negotiating point, and fills gaps where hospital files lack doctor fees. Always labeled as a reference, never as a price anyone will charge.
7. **Bundles show the whole bill (built, needs clinical review).** Include "What's usually billed separately" so nobody is surprised by the anesthesiologist's bill.
8. **Quality next to price (Launch).** CMS star ratings are already loaded for hospitals; show them with the price so the cheapest isn't mistaken for the best value. Later: surgery-center quality measures.
9. **Price alerts (Later).** "Tell me if the MRI price near me drops", by email only, no account.

## 2. Free and reduced-cost care (the heart of it)

1. **Dollars, not poverty levels (built 2026-11-08).** "You may qualify for free care here if your household makes under $31,920 (1 person) or $66,000 (family of 4)."
2. **Ask once, show everywhere (Launch).** A two-question check on the home page (household size, yearly income), kept only in the person's own browser, never sent to us except for the check itself and never stored. After that, every result shows "Free for you here: likely" or "50% off likely", and results can be sorted by it.
3. **Medicaid and marketplace nudges (Launch).** Many people below the free-care limits also qualify for Nevada Medicaid (adults up to 138% of the poverty guideline, about $22,000 for one person in 2026) or subsidized marketplace insurance. "You may also qualify for Nevada Medicaid, which can cover this at no cost," with a link to the state's application. These numbers must come from the official sources and be reviewed.
4. **Community health centers and free clinics (Launch).** Federally qualified health centers must offer a sliding fee scale to everyone under 200% of the guideline, insured or not, and free clinics serve people with no money at all. They are a huge source of free and reduced care that hospital policies miss. Add them as a provider type, from the public HRSA list, with their sliding-fee information.
5. **Help applying (Soon).** Hospital applications are long. A plain checklist per hospital (what documents, where to send, deadline), pre-filled where possible, and the reminder that people can apply up to 240 days after their first bill at nonprofit hospitals and should apply even if unsure.
6. **"Already got a bill?" (Soon).** Many people find us after the bill arrives. Tools: (a) compare your bill with the hospital's own published price; (b) ask for an itemized bill (template letter); (c) apply for financial assistance retroactively; (d) if you were uninsured or paid cash and the bill is $400 or more above the Good Faith Estimate you were given, you can dispute it under the No Surprises Act (link to the federal process). This is where the site can save people the most money.
7. **Good Faith Estimate rights (Launch, one paragraph).** Uninsured and self-pay patients have a legal right to a written estimate before scheduled care. Tell people, and give them a printable "price sheet" with the code numbers to ask about.

## 3. Easy to understand and search

1. **Plain language everywhere (Launch).** Write for a 6th-grade reading level. "List price" instead of "gross charge", "cash price" instead of "discounted cash", "your plan's rate" instead of "negotiated rate". Every number has a one-line "what this means".
2. **Spanish from day one (Launch).** Nevada has a large Spanish-speaking population, and Tagalog is common in Clark County; hospital assistance applications already come in these languages.
3. **Mobile first (Launch).** Most people will search on a phone, often in a waiting room or after a doctor's visit.
4. **Honest gaps (built).** "This hospital doesn't publish a standard price file", "Prices coming soon", never a blank or a guess. Show how fresh each price is ("from the hospital's file dated Sept 1, 2026").
5. **Report a wrong price (Launch).** One button on every price; reports go to the review queue and, when providers can sign in, to the provider.
6. **Emergency notice (Launch).** "In an emergency, go to the nearest ER. Emergency care can't be refused because you can't pay." Price shopping is for planned care.
7. **Pages people can find on Google (Launch).** One page per service per city ("MRI cost in Las Vegas") with real published prices and the free-care message. This is likely the biggest source of visitors and costs nothing per visit.
8. **Accessibility (Launch, A11Y-01).** Keyboard, screen readers, large text, color contrast.

## 4. Providers: easy to join, impossible to abuse

### Easy setup
1. **Claim, don't create (Launch of provider portal).** Most providers already exist in public registries (CMS for hospitals and surgery centers; the national NPI registry for every licensed clinician and practice). A provider searches for itself, claims the listing, and everything public (address, phone, NPI) is pre-filled.
2. **Three ways to add prices.** A simple form for a handful of services; a spreadsheet template for many; or "use my CMS price file" for hospitals (we already read those). Prices are entered against our service list with units (per unit, per syringe, per month), so Botox per unit is never compared with Botox per area.
3. **A dashboard worth paying for.** Views, clicks, calls, how their prices compare with nearby providers, and (for hospitals) the problems we found in their CMS file (old date, wrong format, missing columns), which CMS can fine them for. This makes the listing fee easy to justify.

### Keeping scammers out (the "fake med spa with a $500 deposit" problem)
1. **Verified before anything is public.** Every provider account must pass, before a single price shows:
   - an active **NPI** for the business or its medical director (public NPI registry);
   - an active **state license** for the responsible clinician (e.g. Nevada State Board of Medical Examiners, Nursing, Dental Examiners), checked against the state's public lookup; medical spas must name a licensed medical director;
   - a registered **business** (Nevada Secretary of State business search) whose name and address match;
   - **contact verification**: email at the business's own website domain, and a phone call or code to the number in the public record (not a number the applicant types in);
   - the **listing fee paid** with a card or bank account in the business's name (payment processors verify the business identity).
   A person approves each new provider; the first price list is reviewed too.
2. **No money changes hands through us for care.** Listings never take deposits, payments or card details, and may not link to payment pages. A listing that requires a large upfront deposit to "hold" a discounted price is not allowed; the rule and the reason are shown to patients ("Legitimate providers don't need a deposit to give you a price").
3. **Too-good-to-be-true checks.** A new provider's price far below the local range (for example less than half the lowest published price nearby) is held for review and, if published, shown with "Unusually low price — confirm with the provider." New accounts can't change many prices at once without review (PRV-05).
4. **Visible trust signals.** "Verified Nov 8, 2026: NPI 1234567890, Nevada license #…, business registered since 2019", linked to the public lookups, plus how long the provider has listed with us.
5. **Fast takedown.** Patient reports and anomaly flags go to a queue; a listing can be suspended in one click, and suspensions are logged. Repeat bait-and-switch (refusing to honor a listed price) means removal.
6. **Prices must be honored.** Providers agree that listed prices are their real prices for the stated service and unit (and match their Good Faith Estimates). An optional "price guarantee" badge for providers who commit to it in writing.

### Fair advertising (rules confirmed 2026-11-08)
Payment buys a listing, never a better rank or different labels; paid placements say "Sponsored"; hospital-file prices stay free to show; fixing your own errors is free.

## 5. Things that protect the business

1. **Health privacy laws (before launch, counsel).** Nevada's consumer health data law (SB 370, 2023) and the FTC Health Breach Notification Rule can apply to sites that collect health-related information, even without HIPAA. Keep the site account-free for patients, collect nothing about a person's health or income on our servers, and use no advertising trackers (already SEC-01).
2. **Advertising and reviews rules.** The FTC's rules on endorsements and fake reviews apply to provider listings and any patient reviews. If reviews are added, only from verified visits, and never paid or filtered.
3. **Terms and attestations** for providers (prices honored, accurate, licensed), and a clear disclaimer for patients (prices come from providers; only the provider can confirm). Counsel review (Q1).
4. **Medical codes.** CPT (AMA) and CDT (ADA) descriptions need licences; we show code numbers with our own names (D-002, Q16).
5. **Data that stays current.** Automatic weekly refreshes with the automatic publishing rule (D-035), alerts when a hospital's file disappears or goes stale, and the emails to Renown and Tahoe Forest (Q13).

## 6. Local knowledge that matters in Nevada

1. **Plan names people recognize.** In Las Vegas the Culinary Health Fund (a large union plan), the Medicaid managed-care plans, and Medicare Advantage plans cover a large share of people. The plan picker must use the names on people's cards, which needs the payer and plan name review queue (rule 9) that is not built yet. This is the biggest missing piece for insured people.
2. **Low-cost options beyond hospitals.** UNLV's dental school clinic, community health centers (e.g. Nevada Health Centers), and county programs (UMC's program is for Clark County residents). These belong in results for "teeth cleaning" or "checkup".
3. **Rural Nevada.** Several hospitals are hours apart; distance and "worth the drive" matter more than in cities.

## 7. Suggested order

**Before launch (in this order):** payer/plan name review queue and plan picker → free-care check shown on every result → plain-language website with Spanish → service and city pages for search engines → report-a-wrong-price → community health centers → emergency and Good Faith Estimate notices → counsel review of privacy, terms and advertising.

**Provider portal (next):** claim listing → verification steps above → price entry with units → anomaly checks and takedown → dashboard → billing.

**After:** out-of-pocket estimator, Medicare reference prices, "already got a bill?" tools, price alerts.

## Open choices for Cooper
- Which of the "before launch" items to keep, drop or reorder.
- Whether community health centers and free clinics should be listed at launch (recommended).
- Whether to show Medicare reference prices (recommended, clearly labeled).
- Provider verification: are all five checks required for every provider type, or lighter for some (e.g. a solo chiropractor)?
