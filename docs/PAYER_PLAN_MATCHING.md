# Payer and plan matching

How raw payer and plan names become canonical payers and plans.

## Layers

raw payer text → normalized key → `ref.payer_alias` (approved?) → `ref.payer`; likewise raw (payer, plan) → `ref.plan_alias` → `ref.plan` with product type and segment.

## Rules (implemented as guards in Phase 0)

- `normalize_name` removes only case, accents, extra whitespace and stray punctuation. Words are never dropped or reordered.
- `resolve_payer` returns a payer only for an **approved** alias with an exact normalized match. Otherwise None.
- Unseen names are recorded as `unmapped` for review; recording never overwrites a mapping.
- One normalized raw name maps to at most one payer (unique constraint).
- No fuzzy auto-merge: "Anthem Blue Cross Blue Shield" ≠ "BCBS BlueCard" ≠ "Blue Cross Blue Shield" (tested).
- PPO, HMO, exchange, Medicare Advantage and Medicaid managed care plans are never combined without an explicit documented rule.

## Consumer-facing match labels (Phase 3)

Exact plan · Normalized match · Other plan from your insurer (shown separately) · Not published.

## TODO

- Review queue UI and audit trail (Phase 2).
- Seed list from legacy union/employer/casino plan names, each reviewed.
