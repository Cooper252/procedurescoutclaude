"""Headline prices, typical local range and badges (SITE_DESIGN §4, PRC-01/02).

- **Headline** per facility: the lowest published dollar amount of exactly one
  price type (cash, list, or the chosen plan's negotiated rate). Several
  different amounts are reported as a range. Price types are never mixed.
- **Typical range**: one value per facility (its headline), then the 25th,
  50th and 75th percentiles *as actually published* (nearest published value,
  never an interpolated number), only when at least MIN_FOR_TYPICAL facilities
  have a price. Prices flagged as possible errors are left out.
- **Badges**: lowest near you; below typical (under the 25th percentile);
  cash cheaper than your plan.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from .price_store import PublishedPrice

MIN_FOR_TYPICAL = 5
POSSIBLE_ERROR_FLAGS = frozenset({"under_one_dollar", "over_ten_million"})
MODE_PRICE_TYPE = {"cash": "discounted_cash", "list": "gross", "plan": "negotiated"}


@dataclass(frozen=True, slots=True)
class Headline:
    amount: Decimal  # the lowest amount of that type at the facility
    highest: Decimal  # equal to amount unless several were published
    price_type: str
    possible_error: bool = False


@dataclass(frozen=True, slots=True)
class Typical:
    low: Decimal  # 25th percentile (a published value)
    middle: Decimal
    high: Decimal  # 75th percentile
    count: int


@dataclass(frozen=True, slots=True)
class Badges:
    lowest_near_you: bool = False
    below_typical: bool = False
    cash_cheaper_than_plan: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)


def _parts(
    prices: Sequence[PublishedPrice], mode: str
) -> tuple[list[PublishedPrice], list[PublishedPrice]]:
    """(main rows, doctor's rows) of one price type. Where a hospital published
    both its own part (facility) and the doctor's part (professional) of a
    service, the headline is the hospital's part and the doctor's part is shown
    beside it, never mixed into one "lowest" number (Cooper, 2026-11-12: a
    radiologist's $66 fee was shown as the MRI's price)."""
    ptype = MODE_PRICE_TYPE[mode]
    rows = [p for p in prices if p.price_type == ptype and p.amount is not None]
    doctor = [p for p in rows if p.billing_class == "professional"]
    main = [p for p in rows if p.billing_class != "professional"]
    return (main, doctor) if main and doctor else (rows, [])


def doctor_fee(prices: Sequence[PublishedPrice], mode: str) -> Headline | None:
    """The doctor's part, when published separately from the hospital's part."""
    _, doctor = _parts(prices, mode)
    if not doctor:
        return None
    clean = [p for p in doctor if not (set(p.quality_flags) & POSSIBLE_ERROR_FLAGS)]
    use = clean or doctor
    amounts = sorted(p.amount for p in use if p.amount is not None)
    return Headline(amounts[0], amounts[-1], MODE_PRICE_TYPE[mode], possible_error=not clean)


def headline(prices: Sequence[PublishedPrice], mode: str) -> Headline | None:
    rows, _ = _parts(prices, mode)
    if not rows:
        return None
    clean = [p for p in rows if not (set(p.quality_flags) & POSSIBLE_ERROR_FLAGS)]
    use = clean or rows
    amounts = sorted(p.amount for p in use if p.amount is not None)
    return Headline(amounts[0], amounts[-1], MODE_PRICE_TYPE[mode], possible_error=not clean)


def _nearest_rank(sorted_values: Sequence[Decimal], percentile: int) -> Decimal:
    """Nearest-rank percentile: always one of the published values."""
    n = len(sorted_values)
    rank = max(1, -(-percentile * n // 100))  # ceil(p * n / 100)
    return sorted_values[rank - 1]


def typical(headlines: Sequence[Headline]) -> Typical | None:
    values = sorted(h.amount for h in headlines if not h.possible_error)
    if len(values) < MIN_FOR_TYPICAL:
        return None
    return Typical(
        _nearest_rank(values, 25),
        _nearest_rank(values, 50),
        _nearest_rank(values, 75),
        len(values),
    )


def badges(
    mine: Headline | None,
    all_headlines: Sequence[Headline],
    typ: Typical | None,
    cash: Headline | None = None,
) -> Badges:
    if mine is None or mine.possible_error:
        return Badges()
    clean = [h.amount for h in all_headlines if not h.possible_error]
    notes = []
    lowest = bool(clean) and mine.amount == min(clean) and len(clean) > 1
    below = typ is not None and mine.amount < typ.low
    cheaper = (
        mine.price_type == "negotiated"
        and cash is not None
        and not cash.possible_error
        and cash.amount < mine.amount
    )
    if cheaper and cash is not None:
        notes.append(
            f"Cash price ${cash.amount.normalize():f} is lower than your plan's rate "
            f"${mine.amount.normalize():f}"
        )
    return Badges(lowest, below, cheaper, tuple(notes))


def percent_change(old: Decimal, new: Decimal) -> Decimal:
    """Whole-percent change for display (rounded toward zero)."""
    if old == 0:
        raise ValueError("no change from zero")
    return ((new - old) * 100 / old).to_integral_value(rounding="ROUND_DOWN")
