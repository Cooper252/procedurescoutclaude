# Provider pages, provider dashboard, reviews and payments readiness

Status: **sections 1–3 and the boost preview are built (D-050, 2026-11-08); payments (section 4) are not.** Built code: `db/migrations/versions/0018_provider_portal.py`, `procedurescout_core/portal_auth.py`, `provider_pages.py`, `reviews.py`, `provider_stats.py`, `apps/api/procedurescout_api/portal_routes.py`, `admin_portal_routes.py`, website `app/providers/account`, `app/review`, `components/ProviderHome.tsx`. This builds on
`SITE_DESIGN.md` §6 and requirements PRV-01 to PRV-06. Choices that Cooper still
has to make are listed as Q30–Q32 in `OPEN_QUESTIONS.md`.

Cooper's request: each provider gets its own account page with analytics (listing
views, how many people searched for what they offer nearby, what a boost would do),
and a public homepage on ProcedureScout with more than prices: website links, logo,
reviews and more, so an interested patient can click through and learn about the
facility.

## 1. Public provider homepage (`/facility/<id>`, extends today's page)

Every hospital, surgery center, clinic, dentist, chiropractor and so on gets a page,
whether or not it has claimed its account. Unclaimed pages show only public-record
data and published prices, plus a "Claim this page" link.

| Section | Source | Notes |
|---|---|---|
| Name, type, address, map, phone | Public records (CMS, NPPES, HRSA); the provider can correct them | Corrections go to review |
| Logo, photos, "About us" | Provider uploads | Image checks (size, type, no faces of patients); reviewed before showing |
| Website, booking link, social links | Provider | Only http(s) links, checked that they work, `rel="nofollow ugc"` |
| Hours, languages, accessibility, parking | Provider | |
| Insurance accepted | Provider claims, plus plans named in the hospital's own price file | The two are labeled separately; the file is shown as evidence |
| Services and prices | Published hospital file (labeled "From the hospital's price file"), plus provider-entered prices and packages | Never mixed together without a label (rule 8) |
| Specials | Provider (built: new-patient price, % off, $ off) | |
| Ratings | Patient reviews (§3); CMS star ratings for hospitals | Each source labeled; never averaged together |
| Badges | "Claimed by the provider", "Prices updated <date>" | No paid badges |

## 2. Provider account and dashboard (`/providers/account`)

Sign-in follows PRV-01: verified authority to speak for the facility, with MFA.
The sign-in method and email service are still open (Q26).

**Manage:** profile, logo, photos, links, hours, services and prices, packages,
specials, replies to reviews, and team members (roles: owner, editor, viewer).

**Analytics** (counts only, by week and month):

- **Page views:** how many times their homepage was viewed.
- **Shown in searches:** how many times they appeared in results, and the average position.
- **Actions:** clicks to their website, phone, directions and booking link.
- **Demand nearby:** how many searches for each service they offer happened within
  10 / 25 / 50 miles, and how many of those showed them.
- **Missed demand:** services people searched for nearby that they don't list yet.
- **Price position:** where each of their prices sits against the local typical range.
- **Boost preview** (only once paid features are approved, §4): an estimate built
  from the real counts above, e.g. "Sponsored spot on X-ray searches within 25 miles:
  about 1,200 extra views a month." It is labeled as an estimate and explains how it
  was calculated.

**Privacy rules for analytics** (health searches are sensitive):

- Counts only. Providers never see who searched, from where exactly, or anyone's
  IP address, device or account.
- Small numbers are hidden: under 10 shows as "fewer than 10", so a single person's
  search can't be singled out.
- Areas are coarse (distance rings, never a pinpoint location).
- Events are counted on our own servers, with no third-party ad trackers or
  pixels. Raw events are kept for a short time, then only totals are kept.
- Counsel reviews this before launch, including the FTC Health Breach
  Notification Rule and state health-data laws such as Washington's My Health My
  Data Act.

## 3. Reviews

The FTC's rule on consumer reviews and testimonials (16 CFR Part 465, in force
since October 2024) bans fake reviews, buying positive reviews or paying for
removals, and hiding negative reviews while presenting the rest as complete.

Proposed rules:

- **Who can review:** only verified visits, by a one-time link from us (email) or from the provider; no receipts (Cooper, Q31). One review per
  person per provider per visit.
- **No filtering by the provider.** Providers can reply and can report a review
  for breaking the posting rules. A person, not the provider, decides. Removed
  reviews are counted publicly ("2 reviews removed for breaking the rules").
- **No incentives.** No discounts or gifts for reviews, and no asking only happy
  patients ("review gating").
- **Health privacy:** a provider's public reply may never confirm that someone was
  a patient or mention their care (HIPAA). Replies are checked before they post.
- **Posting rules:** no medical details about other people, no hate speech, no
  personal information. Reviews are about the experience: price honesty, wait,
  billing and staff.
- **What's shown:** the average, the number of reviews, the newest reviews first,
  plus a "price matched what I was quoted" yes/no.

## 4. Boosts and payments (monetization: build only after Cooper says go)

This keeps the rules already approved in D-031 and PRV-06: **payment never changes
the order of real results or their labels.**

- A **boost** is a separate **"Sponsored"** spot shown above or beside the results
  for a service and area. It is clearly labeled, limited to one or two per page,
  and only offered to providers with a published price for that service.
- Hospital-file prices are always free to show. Correcting your own information is
  free. A free tier always exists: a claimed page, prices and replies to reviews.
- Possible paid items (prices to decide later): monthly Sponsored spots by service
  and area, a "Pro" dashboard with more history and exports, and extra photos.

**Payments readiness (no code yet):**

- Use **Stripe Checkout** and **Stripe Billing** for subscriptions, plus
  **Stripe's customer portal** for invoices and cancelling. Card numbers never touch
  our servers.
- Fees: Stripe lists 2.9% + 30¢ per US card payment. Billing adds a small
  percentage for subscriptions; confirm the rates at sign-up.
- What we would add when approved:
  - a `billing` schema: accounts, subscriptions, sponsored campaigns;
  - a Stripe webhook endpoint that records payment status;
  - a test proving that billing status can't change search order or labels (PRV-06).
- Before taking money: terms of sale, a refund policy, sales tax on digital
  advertising (varies by state), and counsel review of advertising rules.

## 5. Build order (proposed)

1. Provider sign-in and verified claiming (needs Q26).
2. Profile editing: logo, links, hours, photos, with review.
3. Privacy-safe event counting and the analytics dashboard.
4. Reviews: verified visits, moderation, replies.
5. Boost preview (estimates only, no payment).
6. Payments: Stripe and Sponsored spots, after Cooper's go-ahead.
