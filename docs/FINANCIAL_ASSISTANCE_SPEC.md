# Financial assistance

Telling people they may qualify for free or reduced-cost care is central to ProcedureScout (Cooper, 2026-11-08, D-037).

## On every page
- A site-wide message (`procedurescout_core/assistance.py: SITE_MESSAGE`, served by `GET /v1/assistance/message`) appears on **every page**, and **prominently on the home page** (a large panel above or beside the search, not a footer line), with a link to the check below and to each hospital's policy.
- Every facility result and every price shows a "You may qualify for free or reduced-cost care here" link.
- Wording rules: say "may qualify", never "eligible" or "approved"; never imply that insurance rules someone out; always say only the hospital can confirm; **state limits in dollars** ("under $31,920 for 1 person or $66,000 for a family of 4"), never as a percent of the poverty guideline (D-038).

## Data
- `ref.poverty_guideline`: HHS poverty guidelines exactly as published (2026 loaded from the HHS/ASPE detailed guidelines; 48 states + DC, Alaska, Hawaii; sizes 1–8 plus the per-person amount).
- `ref.assistance_policy` + `ref.assistance_tier`: each hospital's policy URL, application, phone, and income limits as a percent of the guideline (free up to N%, discount up to M%, with the discount percent or the policy's own description). Entered by a person from the hospital's own policy, with evidence and a check date, in `data/reference/assistance_policies.csv` (empty until collected; Q20).

## The check (`POST /v1/assistance/check`)
Household size, annual income and state; income is sent in the request body, never a URL, and is not stored or logged. Result per hospital: `may_qualify_free`, `may_qualify_discount` (with the discount), `above_published_limits` (with "apply anyway; hospitals can consider other circumstances"), or `policy_not_reviewed` ("ask the hospital"), plus the policy and application links.

## Not yet
Collecting the Nevada hospitals' policies (Q20), asset tests and residency rules, presumptive eligibility, and the website panels themselves (Phase 3).
