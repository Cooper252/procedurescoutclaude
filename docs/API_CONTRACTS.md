# API contracts

Public endpoints are read-only, need no account, and validate every filter before reading prices (CLAUDE.md rule 12). Amounts are JSON strings holding the exact value (never floats). Implemented in `apps/api/procedurescout_api/search_routes.py`.

## GET /v1/services
Approved services for the home search box: `[{slug, name, category, unit}]`. `unit` is one of `per_service`, `per_unit`, `per_area`, `per_syringe`, `per_session`, `per_visit`, `per_day`, `per_month`; prices with different units are never compared as equal.

## GET /v1/services/suggest?q=
Search-box suggestions: approved services whose name, or an approved everyday word for them, contains the text, then billing codes from published prices by number or by the hospitals' wording (`[{slug, name, unit, matched, kind, code_system, code}]`; `kind` is `service` or `code`, D-045). A code suggestion is searched with `code_system` + `code`, and the search response then carries `code_description` (the hospitals' wording, to be labeled as theirs).

## GET /v1/plans
Plans by the names on people's cards that have at least one approved hospital spelling: `[{plan_id, payer, plan, product_type, segment}]`.

## GET /v1/provider-types
Approved provider types for the filter: `[{code, name}]`.

## GET /v1/payers/suggest?q=
Insurer names exactly as hospitals wrote them in published prices, most widely used first: `[{name, facilities}]`. A chosen name is searched with `mode=plan&payer=<name>` (instead of `plan_id`); results then contain only negotiated rates published under that spelling, to be labeled as written (D-046).

## GET /v1/places/zip/{zip5}
Centre of a ZIP code area (Census ZCTA) so people can search by ZIP: `{zip, state, lat, lng}` (strings). 404 if unknown, 422 if not 5 digits.

## GET /v1/places/cities?state=
Cities in a state with active, geocoded facilities, most facilities first: `[{state, city, slug, lat, lng, facilities}]`; the center is the center of those facilities. 422 for a bad state code.

## GET /v1/places/city/{state}/{slug}
One city from that list; 404 if unknown.

## GET /v1/facilities/near
Query: `lat`, `lng`, `radius_miles` (1–100, default 25), optional `provider_type` (approved code). Nearest active facilities, up to 50, without prices: `[{facility_id, name, city, state, distance_miles, provider_types}]`. Used by the help-paying check.

## GET /v1/facilities/{facility_id}
One active facility: `{facility_id, name, address, city, state, zip, phone, website, emergency_services, cms_rating, cms_rating_as_of, provider_types, prices_published_at, lat, lng}`. `website` is null unless a person reviewed it. 404 if unknown or not a UUID.

## GET /v1/facilities/{facility_id}/prices?service=
Every published price at that facility under the approved codes of one approved service: `{facility_id, service, service_name, unit, codes, prices_published_at, prices: [...]}` (same price fields as search). Empty `prices` when nothing is published; 422 for an unapproved service.

## GET /v1/search
Query: `lat`, `lng` (required), `radius_miles` (1–100, default 25), and either `service` (an approved slug) or `code_system` + `code` (a code present in `ref.code`), optional `provider_type` (an approved code), `mode` (`cash` default | `list` | `plan`) and `plan_id` (required with `plan`).

Response: `{service, service_name, unit, codes, note, facilities: [{facility_id, name, city, state, distance_miles, provider_types, status, prices_published_at, prices: [{price_source, code, description, setting, price_type, payer, plan, amount, percentage, algorithm, methodology}]}]}`. Each facility also has `headline` (lowest amount of the chosen type) and `headline_highest`, `headline_possible_error`, badges `lowest_near_you`, `below_typical`, `cash_cheaper_than_plan` with `badge_notes`, and `change_percent_since_last_file`, `plan_rate_is_all_plans` (plan mode: the rate is the insurer's one rate for all its plans, D-041), and each price has `plan_match` (`plan` | `all_plans`, plan mode only); the response has `mode` and `typical` `{low, middle, high, count}` (null under 5 prices). Up to 50 nearest facilities. `status` is `prices` or `no_published_prices` (a facility nearby with nothing published is listed, never filled in). `price_source` is `hospital_file` today; `provider_submitted` and `provider_correction` later (D-030). Unknown or unapproved filters return 422 without reading any price.

## Bundles and assistance (`care_routes.py`)
- `GET /v1/assistance/message?state=NV` — `{message, detail}` for the banner on every page; with a state, the message states the common free-care and help limits in dollars from that state's reviewed policies.
- `GET /v1/facilities/{id}/assistance` — one hospital's limits as a plain sentence in dollars.
- `POST /v1/assistance/check` — body `{facility_ids, household_size, annual_income, state}`; returns the guideline used, income as a whole percent of it (display only), and per hospital `status` (`may_qualify_free` | `may_qualify_discount` | `above_published_limits` | `policy_not_reviewed`), the best matching tier, policy and application links, and `message` (the hospital's limits in dollars). Income is never put in a URL or stored.
- `GET /v1/bundles` — approved bundles with their pieces.
- `GET /v1/facilities/{id}/plans` — payer/plan names exactly as the facility publishes them.
- `POST /v1/bundles/{slug}/estimate` — body `{facility_id, payment: cash|list|insurance, payer?, plan?, include_optional?}`; returns each piece's status (`priced` | `not_published` | `not_a_dollar_amount` | `several_prices` | `left_out`), the total of priced pieces and `complete`.

## Review page (not public)
`/admin/reviews` (HTML), `POST /admin/reviews/{dataset}/approve`, `POST /admin/reviews/{dataset}/reject`. Off unless `ADMIN_TOKEN` and `ADMIN_DATABASE_URL` are set; interim name + password sign-in, multi-factor before launch (ADM-02). Implemented in `apps/api/procedurescout_api/admin_routes.py`.

## Provider homepages, reviews and portal (`portal_routes.py`, D-050)
Public (no sign-in): `GET /v1/facilities/{id}/page` (published profile, logo/photo URLs, review summary, latest 10 reviews, `claimed`), `GET /v1/facilities/{id}/reviews?offset=`, `GET /v1/media/{key}` (approved images only), `POST /v1/events` `{facility_id, kind}` (204; page_view, website_click, phone_click, directions_click, booking_click), `POST /v1/reviews/request` `{facility_id, email}` (202, same answer either way), `POST /v1/reviews/check` `{token}`, `POST /v1/reviews` `{token, rating, title, body, price_matched, display_name, visited, independent}` (201, waits for moderation).

Portal (cookie `ps_session`; every change needs header `X-ProcedureScout: 1`): `POST /v1/portal/sign-in` `{email}`, `POST /v1/portal/sign-in/verify` `{token}`, `POST /v1/portal/sign-out`, `GET /v1/portal/me`, `POST /v1/portal/mfa/setup`, `POST /v1/portal/mfa/verify` `{code}`, `GET /v1/portal/facilities/search?q=`, `POST /v1/portal/claims` `{facility_id, note}`, `GET|PUT /v1/portal/facilities/{id}/profile`, `POST /v1/portal/facilities/{id}/media?kind=logo|photo&alt=` (raw image body), `GET|DELETE /v1/portal/facilities/{id}/media/{media_id}`, `GET /v1/portal/facilities/{id}/stats?days=7|30|90`, `GET /v1/portal/facilities/{id}/reviews`, `POST /v1/portal/facilities/{id}/invites`, `POST .../reviews/{review_id}/reply` `{body}` (returns `privacy_warning`), `POST .../reviews/{review_id}/report` `{reason}`. Without `PORTAL_DATABASE_URL` these answer 404. `dev_link` is returned only when `PORTAL_DEV_LINKS=true` and not in production.
