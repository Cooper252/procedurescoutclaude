# Bundled pricing

What a person actually pays for a procedure is usually several bills: the procedure and facility, the doctor, anesthesia, pathology, a newborn's care. A **bundle** groups them (D-036, `procedurescout_core/bundles.py`).

## Data
- A bundle is a catalog entry with `kind = 'bundle'` in `ref.procedure`; its pieces are `ref.bundle_component` rows: label, role (procedure, facility, physician, anesthesia, pathology, imaging, lab, newborn, supplies, other), **required** or **optional**, included by default or not, and the code the piece is billed under.
- Bundles come from `data/reference/bundles.csv`. A bundle is approved only when every piece is approved. Bundle contents are clinical judgments: the starting three (upper endoscopy, colonoscopy, vaginal birth) are AI suggestions and stay proposed until a clinical reviewer approves them (Q4).

## Pricing rules
1. Required pieces are always included; optional pieces follow the person's checkboxes (e.g. epidural on/off), starting from their defaults.
2. Payment mode: **cash** (discounted cash), **list** (gross charge), or **one insurance plan** exactly as the facility publishes it. A plan the facility does not publish is refused, never matched to a look-alike.
3. A piece with no published dollar amount at that facility is shown as **not published** and never counted as $0 (doctors' and anesthesia fees are often billed separately and missing from hospital files).
4. A percentage-of-charges or formula rate is shown as published and not added.
5. A piece with several different published amounts (e.g. by setting) shows all of them and is not added.
6. The total adds only priced pieces and says whether it is **complete**.

## API
`GET /v1/bundles`, `GET /v1/facilities/{id}/plans`, `POST /v1/bundles/{slug}/estimate` (see `API_CONTRACTS.md`).

## Not yet
Packaged items (supplies included in a facility fee) are not separately added because bundles list only billable pieces; anesthesia priced by time units, and provider-entered bundle prices (D-030), come later.
