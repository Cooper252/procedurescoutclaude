# API contracts

Public endpoints are read-only, need no account, and validate every filter before reading prices (CLAUDE.md rule 12). Amounts are JSON strings holding the exact value (never floats). Implemented in `apps/api/procedurescout_api/search_routes.py`.

## GET /v1/services
Approved services for the home search box: `[{slug, name, category, unit}]`. `unit` is one of `per_service`, `per_unit`, `per_area`, `per_syringe`, `per_session`, `per_visit`, `per_day`, `per_month`; prices with different units are never compared as equal.

## GET /v1/services/suggest?q=
Search-box suggestions: approved services whose name, or an approved everyday word for them, contains the text (`[{slug, name, unit, matched}]`).

## GET /v1/plans
Plans by the names on people's cards that have at least one approved hospital spelling: `[{plan_id, payer, plan, product_type, segment}]`.

## GET /v1/provider-types
Approved provider types for the filter: `[{code, name}]`.

## GET /v1/search
Query: `lat`, `lng` (required), `radius_miles` (1–100, default 25), and either `service` (an approved slug) or `code_system` + `code` (a code present in `ref.code`), optional `provider_type` (an approved code), `mode` (`cash` default | `list` | `plan`) and `plan_id` (required with `plan`).

Response: `{service, service_name, unit, codes, note, facilities: [{facility_id, name, city, state, distance_miles, provider_types, status, prices_published_at, prices: [{price_source, code, description, setting, price_type, payer, plan, amount, percentage, algorithm, methodology}]}]}`. Each facility also has `headline` (lowest amount of the chosen type) and `headline_highest`, `headline_possible_error`, badges `lowest_near_you`, `below_typical`, `cash_cheaper_than_plan` with `badge_notes`, and `change_percent_since_last_file`; the response has `mode` and `typical` `{low, middle, high, count}` (null under 5 prices). Up to 50 nearest facilities. `status` is `prices` or `no_published_prices` (a facility nearby with nothing published is listed, never filled in). `price_source` is `hospital_file` today; `provider_submitted` and `provider_correction` later (D-030). Unknown or unapproved filters return 422 without reading any price.

## Bundles and assistance (`care_routes.py`)
- `GET /v1/assistance/message?state=NV` — `{message, detail}` for the banner on every page; with a state, the message states the common free-care and help limits in dollars from that state's reviewed policies.
- `GET /v1/facilities/{id}/assistance` — one hospital's limits as a plain sentence in dollars.
- `POST /v1/assistance/check` — body `{facility_ids, household_size, annual_income, state}`; returns the guideline used, income as a whole percent of it (display only), and per hospital `status` (`may_qualify_free` | `may_qualify_discount` | `above_published_limits` | `policy_not_reviewed`), the best matching tier, policy and application links, and `message` (the hospital's limits in dollars). Income is never put in a URL or stored.
- `GET /v1/bundles` — approved bundles with their pieces.
- `GET /v1/facilities/{id}/plans` — payer/plan names exactly as the facility publishes them.
- `POST /v1/bundles/{slug}/estimate` — body `{facility_id, payment: cash|list|insurance, payer?, plan?, include_optional?}`; returns each piece's status (`priced` | `not_published` | `not_a_dollar_amount` | `several_prices` | `left_out`), the total of priced pieces and `complete`.

## Review page (not public)
`/admin/reviews` (HTML), `POST /admin/reviews/{dataset}/approve`, `POST /admin/reviews/{dataset}/reject`. Off unless `ADMIN_TOKEN` and `ADMIN_DATABASE_URL` are set; interim name + password sign-in, multi-factor before launch (ADM-02). Implemented in `apps/api/procedurescout_api/admin_routes.py`.
