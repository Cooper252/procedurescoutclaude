# Cost estimator spec

Rules for estimating what a patient might owe. Phase 5.

## Principles

- Versioned rules engine, Decimal arithmetic, documented rounding.
- Inputs: allowed amount source, deductible remaining, copay, coinsurance, remaining out-of-pocket max, network assumption, individual/family context.
- Missing essentials → "cannot estimate", never a guess.
- Output always shows the posted amount, the allowed amount used, the user's assumptions, the estimated share, the calculation, what is missing, and a non-guarantee statement.

## TODO

- Formal calculation order (deductible → coinsurance/copay → OOP cap).
- 30+ worked numerical examples as test cases.
