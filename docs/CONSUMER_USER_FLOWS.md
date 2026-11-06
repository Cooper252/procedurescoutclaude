# Consumer user flows

The guided search and results experience. Phase 3.

## Guided search

1. Location (ZIP, city, or opt-in geolocation; radius or statewide).
2. How you'll pay (insurance, cash/self-pay, uninsured, Medicare, Medicaid, not sure).
3. Insurance company (only payers published nearby; "I don't know", "Not listed").
4. Plan (published plans, labeled by type; skip shows all as separate rows).
5. Procedure (plain-English autocomplete, disambiguation when a term covers several services).
6. Financial help (optional; household size and income range, kept in the browser session).

State lives in the URL so Back and sharing work. Counts appear only when computed from published data.

## Results

One card per facility; inside, one row per distinct payer/plan/price type with amount, price-type label, match label, source date, freshness, and a "where this number comes from" link. Facilities without a usable price stay listed with a specific reason. "Lowest price" sort only after choosing one comparison basis.

## TODO

- Wireframes, empty/error/stale states, accessibility review.

## Facilities without usable prices (D-022)

A facility is always listed (name, address, distance) even when no prices can be shown, with one plain status instead of prices:

| Status | Shown when | Text (draft) |
|---|---|---|
| `coming_soon` | A price file exists but could not be read automatically this run (e.g. the site refuses automated requests) | "Prices coming soon" |
| `not_published` | No standard machine-readable price file found (no cms-hpt.txt entry, PDF only, file not listed) | "This hospital doesn't publish a standard price file" |
| `exempt` | Federally owned hospital (`hpt_exempt_reason` set) | "Federal hospital — not required to publish prices" |
| `unknown` | No website known | "Price information not available" |

No estimate, average or neighbouring hospital's price is ever shown in their place. Statuses come from the latest discovery run, never from memory.
