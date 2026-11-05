# CMS schema support

Source: [CMSgov/hospital-price-transparency](https://github.com/CMSgov/hospital-price-transparency), commit `5333564` (2026-06-09). Current schemas live in `documentation/`; older ones in `archive/documentation/`.

## Versions

| Version | Status in CMS repo | Key differences | ProcedureScout support |
|---|---|---|---|
| 3.0.0 | Current. Effective 2026-01-01, enforced 2026-04-01 | Adds `attestation` object (`attestation`, `confirm_attestation`, `attester_name`), `type_2_npi`, `location_name` (was `hospital_location`), and per payer/plan `median_amount`, `10th_percentile`, `90th_percentile`, `count`. Removes `affirmation` and `estimated_amount`. | Schema ready (Phase 0); parser Phase 2 |
| 2.2.1 / 2.2.0 | Archived (added 2025-03) | `estimated_amount` per payer/plan; `affirmation`; `hospital_location` | Schema ready; parser Phase 2 |
| 2.1.0 | Archived | No `estimated_amount` | Schema ready; parser Phase 2 |
| 2.0.0 | Archived | `estimated_amount`; `affirmation` | Schema ready; parser Phase 2 |
| Pre-2.0 / non-CMS layouts | Not a CMS template | Free-form | Rejected as `unsupported_version`; never guessed |

Formats per version: JSON, CSV tall, CSV wide (templates in `documentation/CSV/templates/`).

## v3.0 JSON structure (from `V3.0.0_Hospital_price_transparency_schema.json`)

- Top-level required: `hospital_name`, `standard_charge_information`, `last_updated_on`, `location_name`, `hospital_address`, `type_2_npi`, `license_information`, `attestation`, `version`. Optional: `modifier_information`.
- `standard_charge_information[]` required: `description`, `code_information[]` (`code`, `type`), `standard_charges[]`; optional `drug_information` (`unit`, `type` ∈ GR, ML, ME, UN, F2, GM, EA).
- `standard_charges[]` required: `setting` (inpatient | outpatient | both). Optional: `gross_charge`, `discounted_cash`, `minimum`, `maximum`, `modifier_code`, `payers_information[]`, `additional_generic_notes`.
- `payers_information[]` required: `payer_name`, `plan_name`, `methodology` (case rate | fee schedule | percent of total billed charges | per diem | other). Optional: `standard_charge_dollar`, `standard_charge_percentage`, `standard_charge_algorithm`, `median_amount`, `10th_percentile`, `90th_percentile`, `count`, `additional_payer_notes`.
- `code_information.type` allowed values (21): CPT, HCPCS, ICD, DRG, MS-DRG, R-DRG, S-DRG, APS-DRG, AP-DRG, APR-DRG, TRIS-DRG, APC, NDC, HIPPS, LOCAL, EAPG, CDT, RC, CDM, CMG, MS-LTC-DRG. Our `ref.code_system` enum matches this list exactly.

## v3.0 conditional rules we must validate (JSON README, "conditional requirements")

1. Each item must have at least one of gross charge, discounted cash, negotiated dollar, negotiated percentage, negotiated algorithm.
2. If percentage or algorithm is encoded, `count` is required.
3. If percentage or algorithm is encoded, median/10th/90th are required unless `count` is "0".
4. If `count` is "0", an explanation is required in the notes.
5. `count` is a string: "0", "1 through 10", or a whole number ≥ 11 with no thousands separator (stored verbatim in `price.allowed_count_raw`, DB-checked).
6. Allowed amounts are historical (12–15 month lookback, from 835 remittances, $0 excluded, "next highest observed value" at even n). They are **not** the negotiated rate and are labeled as historical allowed amounts.

## Mapping to `price.price`

| CMS field | price_type | Column |
|---|---|---|
| `gross_charge` | gross | amount |
| `discounted_cash` | discounted_cash | amount |
| `minimum` / `maximum` | deidentified_min / deidentified_max | amount |
| `standard_charge_dollar` | negotiated | amount |
| `standard_charge_percentage` | negotiated | percentage |
| `standard_charge_algorithm` | negotiated | algorithm |
| `methodology` | (all negotiated rows) | methodology |
| `median_amount` / `10th_percentile` / `90th_percentile` | median_allowed / p10_allowed / p90_allowed | amount |
| `count` | on the allowed-amount rows | allowed_count_raw |
| `estimated_amount` (v2 only) | estimated_allowed | amount |

One source payer/plan entry produces one row per published amount, each carrying the same raw payer and plan text.

## Unverified

- CSV v3.0 column naming edge cases beyond the template header (Phase 2 parser work).
- Behaviour of CMS Validator V2.0 on v3.0 files.
