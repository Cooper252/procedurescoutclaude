# Site design: layout, ease of use, better pricing

Written 2026-11-08 at Cooper's request ("look at what I'm missing from every aspect: ease of use, site layout, better pricing, and anything else"). It builds on `PRODUCT_REVIEW.md` (all of which Cooper approved, D-039) and turns it into page-by-page design and the pricing features behind it. Nothing here is built yet unless stated.

Guiding rules for every screen:
1. **Lead with what the person will pay** (their plan's rate or the cash price), in one big number, with what it includes.
2. **Free and reduced-cost care is never more than one glance away.**
3. **One decision per screen** on phones; nothing that needs an account, a popup or an ad to get past.
4. **Every number can be traced** (who published it, when, under which code) and nothing is ever guessed.

---

## 1. Site map

| Page | What it's for |
|---|---|
| Home | Search, the free-care panel, trust |
| Search results | Every nearby option for one service, sorted by the person's cost |
| Service page (per city) | "MRI of the brain in Las Vegas": prices, typical range, free-care limits; what Google lands on |
| Facility page | One hospital/clinic: prices, free-care limits in dollars, quality, how to apply, contact |
| Price details | Where a price came from, every code, the file date, "report a wrong price" |
| Bundle builder | Whole procedure with checkboxes for optional pieces |
| "Can I get help paying?" | The two-question check, Medicaid/marketplace nudges, community health centers, how to apply |
| "Already got a bill?" | Compare, itemized bill, apply after the fact, dispute rights, letter templates |
| Learn | Short plain guides (what a cash price is, Good Faith Estimates, deductibles) |
| For providers | Claim your listing, verification, pricing plans, dashboard |
| About / How we get prices / Privacy / Terms / Contact | Trust and legal |

Every page carries: the free-care banner (in dollars, for the person's state), a language switch (English/Español), "Emergency? Go to the nearest ER", and a footer with the data sources and dates.

## 2. Page layouts

### Home (phone first; desktop puts the panels side by side)
1. **Search box** at the top: "What do you need?" with suggestions as you type (plain names, common words, misspellings, code numbers), and "Where?" pre-filled only if the person allows location; otherwise a ZIP box.
2. **Free-care panel**, as large as the search: "You may qualify for free care at many Nevada hospitals if your household makes under $31,920 (1 person) or $66,000 (family of 4)." Two fields (people in household, yearly income) and "See what I may qualify for". The answers stay in this browser.
3. **Popular searches** as big tappable buttons (MRI, colonoscopy, having a baby, teeth cleaning, Botox, blood work), chosen by real search counts once live.
4. **"Got a bill already?"** button.
5. **Three-line trust strip:** "Prices come straight from hospitals' own government-required files and verified providers. We never sell your information. No account needed."

### Search results
- **Top bar:** service name and unit ("per procedure", "per unit"), location and radius, "Change".
- **Who's paying:** a one-tap switch: *My insurance* (pick the plan from the names on your card) · *Paying cash* · *Show list prices*.
- **Each result card:**
  - name, distance, provider type, quality stars where they exist;
  - **one big number:** your plan's rate or the cash price, with "includes facility; doctor billed separately" or "everything included (bundle)";
  - badges: **Lowest near you**, **Cash cheaper than insurance**, **Free for you: likely**, **Below typical price**, **Price from Sept 2026 file**;
  - buttons: *Details*, *Call*, *Directions*, *Compare*.
- **Sort:** lowest cost for me (default), nearest, most free-care help, best rated. **Filters:** provider type, distance, "takes my plan", open now (later), Spanish spoken (later).
- **"Typical price" line** above the list: "Typical cash price for this near you: $410–$1,250 (middle half of 14 published prices)."
- **Facilities with no published price** are listed at the bottom with their status, never hidden and never estimated.
- **Compare tray:** pick up to 3 cards and see them side by side (price pieces, distance, quality, free-care limits).
- **Share/print:** a link that recreates the search (no personal data in the link) and a one-page printable "price sheet" with the code numbers to ask about.

### Facility page
Header (name, address, phone, map, type, quality), then **"Help paying here"** in dollars with the application link and deadline, then searchable prices (by service name or code), plans accepted (as published), "How we got these prices" (file date, link to the hospital's file), and "Is this your facility? Claim it".

### Price details
The amount, price type in plain words, the code(s), setting, the payer and plan exactly as published, the file name and date, other codes on the same item, flags (e.g. "more than 4 decimals, shown rounded"), and **Report a wrong price**.

### Bundle builder
The procedure at the top with the total; below, each piece with a checkbox (required pieces are checked and locked, with "why this is needed"), its price or "not published here — usually billed by the anesthesia group", and a running total that says **complete** or **missing pieces**. Switching facility keeps the checkboxes.

### "Can I get help paying?"
The two questions, then for each nearby hospital "Free for you: likely / 50% off likely / Ask them", in dollars; then "You may also qualify for Nevada Medicaid" or "marketplace insurance with savings" when the income fits (from reviewed official limits); then nearby community health centers with sliding fees and free clinics; then "How to apply" checklists.

### "Already got a bill?"
Step-by-step: (1) enter the hospital and service, see their own published price; (2) request an itemized bill (letter template); (3) check free-care limits and apply after the fact (most nonprofit hospitals accept applications up to 240 days after the first bill); (4) if uninsured/self-pay and the bill is $400+ over your Good Faith Estimate, how to dispute it; (5) ask for a payment plan, interest-free where offered.

## 3. Ease of use

1. **Search that understands people:** synonyms and misspellings (reviewed), body-part words ("knee", "back"), code numbers for people who have them from a doctor's order, and "not sure what it's called?" browsing by category. No symptom checker or medical advice.
2. **Insurance picker by the name on the card,** with a photo hint of where the plan name appears; "I don't know my plan" falls back to cash and list prices with an explanation.
3. **Defaults that save time:** remember location, plan and the free-care answers in the browser (with a "forget me" button); open the most useful sort.
4. **Speed:** first screen in under 2 seconds on a phone on 4G; results stream in nearest-first.
5. **No dead ends:** every empty result explains why and offers the next step (wider radius, related service, call the facility, community health center).
6. **Plain words with a tap-to-explain** for every term (deductible, coinsurance, list price, facility fee).
7. **Large tap targets, readable type, works with screen readers and zoom** (WCAG 2.2 AA).
8. **Spanish** for every page, message and template; Tagalog later.
9. **Human help:** a contact form and, later, a call-back line or chat for people stuck applying for assistance.

## 4. Better pricing

1. **Your number first.** Compute one headline per facility: the plan's dollar rate when a plan is chosen; otherwise the cash price; list price only when nothing else exists, labeled. Never mix types in a comparison or a sort.
2. **Typical local price.** For each service and area, the middle half (25th–75th percentile) of published prices of the same type and unit, with the count ("14 prices"). Badges like "35% below typical" come from this. Shown only when there are enough prices (e.g. at least 5) to mean something.
3. **Price confidence.** Each headline carries how complete and fresh it is: file date, whether all bundle pieces are priced, whether it came from a hospital file, a verified provider or a provider correction. Older than 12 months is flagged.
4. **Catch file errors before people see them.** Prices that are almost certainly mistakes ($0.01 for surgery, $9,999,999, cash 50× list) are held for review instead of shown as "lowest". Today's checks flag zero amounts and decimals; add statistical outlier checks per service.
5. **Settings and pieces made clear.** Inpatient vs outpatient shown separately; "facility fee" vs "doctor's fee" labeled; per-unit, per-day and per-month prices never compared with per-procedure ones.
6. **Several prices for one service at one place** (e.g. different codes or settings) shown as a range with "why there's more than one".
7. **Medicare reference price** (public CMS fee schedules) as a labeled anchor: "Medicare pays about $X here."
8. **Price history.** Each refresh is kept, so cards can say "price up 12% since March" and service pages can show trends.
9. **Nevada's uninsured discount.** North Vista's policy cites a Nevada law (NRS 439B.260) giving uninsured patients 30% off billed charges at certain hospitals. If verified, show it on qualifying hospitals' list prices ("uninsured? by Nevada law you may pay at least 30% less").
10. **Ways to pay less on any bill:** ask for the cash price, prompt-pay discounts, interest-free payment plans, HSA/FSA eligibility, financial assistance, as a short checklist on every price page.
11. **Plan rates done right.** Map the hospitals' many spellings of each plan to the names on people's cards through reviewed aliases (rule 9); show "your plan" rates first and other plans from the same insurer separately, labeled.
12. **Provider prices on equal footing, clearly labeled** "set by the provider" with verified date, compared only with the same service and unit.

## 5. Trust and transparency
- "How we get prices" page: sources, how often refreshed, what "not published" means, how corrections work, how providers are verified, how we make money (listings) and what money can't buy (rank, labels).
- Every price traceable to its file and date; every provider shows verification details.
- Visible corrections log for prices fixed after reports.
- No ads from third parties, no tracking pixels, no selling data.

## 6. Providers (adds to `PRODUCT_REVIEW.md` §4)
- **Five-minute start:** claim from public records → verify → pick services from our list with units → enter prices or upload the spreadsheet → preview exactly how patients will see it → submit for review.
- **Plans:** free trial months, then one simple monthly price per location (to be set, Q17); never charge to correct errors.
- **Useful dashboard:** views, calls, direction requests, how their prices sit against the local typical range, which searched services they don't list yet, reviews of their CMS file (hospitals).
- **Booking and contact links** only to the provider's verified website or phone.
- **Clear rules page** (no deposits through listings, prices must be honored, removal policy).

## 7. Getting found and growing
- Service-by-city pages with structured data for search engines; plain answers to common questions ("How much is an MRI in Reno?").
- Partners who reach people needing help: Nevada 211, community health centers, unions (e.g. Culinary Health Fund members), employers with high-deductible plans, benefits brokers, social workers and hospital financial counselors (a printable flyer and a simple link they can share).
- Local news and consumer reporters love "same MRI, $400 vs $3,000" stories; a monthly Nevada price report could earn coverage.

## 8. Operations behind the scenes
- Weekly automatic refreshes with the auto-publish rule (D-035) and alerts when a hospital's file vanishes, goes stale or changes a lot.
- A review queue for prices, provider applications, reports, synonyms, plan aliases and assistance policies, with a target time for each (e.g. reports looked at within 2 business days).
- Yearly update of the poverty guidelines and Medicaid limits each January, and of hospital policies.
- Backups, monitoring and an outage page.

## 9. Measuring whether it helps (privacy-friendly, no personal data)
- Searches with a result; share of results with a "your price"; assistance checks run and "free likely" results shown; "already got a bill?" flows completed; provider listings verified; wrong-price reports and time to fix.
- A simple "Did this help? Yes / No" on results and bill tools.

## 10. Build order (proposed)
1. Plan-name review queue and plan picker; typical-price and outlier checks; price history.
2. The website: home, results, service-by-city, facility, price details, help-paying, bill tools, Learn; English + Spanish; accessibility.
3. Community health centers and free clinics; Medicaid/marketplace limits; Medicare reference prices.
4. Provider portal with verification, price entry, dashboard; then billing.
5. Hosting decision and launch (needs Cooper's approval of costs), then the other states.
