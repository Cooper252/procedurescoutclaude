"""Exact money and percentage parsing for hospital price files.

Rules (see docs/DATA_NORMALIZATION.md):
- Blank or missing values return None. They never become 0.
- Values are parsed with Decimal and are never rounded. A value with more
  decimal places than the database can hold raises instead of being rounded.
- Python floats are rejected outright: they cannot represent cents exactly.
- A percentage passed to the dollar parser (e.g. "65%") raises.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# Database columns: NUMERIC(16,4) for dollars, NUMERIC(9,4) for percentages.
DOLLAR_MAX_PLACES = 4
DOLLAR_MAX = Decimal("999999999999.9999")
PERCENT_MAX_PLACES = 4
PERCENT_MAX = Decimal("1000")

_BLANK_TOKENS = frozenset({"", "na", "n/a", "nan", "null", "none", "-", "--"})
_NUMBER_RE = re.compile(r"^\d+(\.\d+)?$|^\.\d+$")


class MoneyParseError(ValueError):
    """Raised when a source value cannot be read as an exact amount."""


def _is_blank(text: str) -> bool:
    return text.strip().lower() in _BLANK_TOKENS


def _to_decimal(text: str, original: object) -> Decimal:
    if not _NUMBER_RE.match(text):
        raise MoneyParseError(f"not a plain non-negative number: {original!r}")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - regex already guards this
        raise MoneyParseError(f"not a number: {original!r}") from exc
    return value


def _check_places(value: Decimal, max_places: int, original: object) -> None:
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and -exponent > max_places:
        raise MoneyParseError(
            f"{original!r} has more than {max_places} decimal places; refusing to round"
        )


def parse_dollar(raw: object) -> Decimal | None:
    """Parse a dollar amount such as "$1,234.50" into Decimal("1234.50").

    Returns None for blank/missing values. Raises MoneyParseError for anything
    that is not an exact, non-negative dollar amount.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise MoneyParseError(f"boolean is not an amount: {raw!r}")
    if isinstance(raw, Decimal):
        if raw.is_nan():
            return None
        text = format(raw, "f")
    elif isinstance(raw, int):
        text = str(raw)
    elif isinstance(raw, str):
        if _is_blank(raw):
            return None
        text = raw.strip()
        if "%" in text:
            raise MoneyParseError(f"percentage passed to dollar parser: {raw!r}")
        text = text.replace("$", "", 1).replace(",", "").strip()
        if text.startswith("(") or text.startswith("-"):
            raise MoneyParseError(f"negative amounts are not valid prices: {raw!r}")
    else:
        raise MoneyParseError(
            f"unsupported type {type(raw).__name__}; floats are not allowed for money"
        )
    value = _to_decimal(text, raw)
    _check_places(value, DOLLAR_MAX_PLACES, raw)
    if value > DOLLAR_MAX:
        raise MoneyParseError(f"amount too large: {raw!r}")
    return value


def parse_percentage(raw: object) -> Decimal | None:
    """Parse a percentage such as "65", "65%" or "65.5 %" into Decimal("65.5").

    The number is the percentage itself (65 means 65%), matching CMS
    standard_charge_percentage. Valid range is 0 to 1000.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise MoneyParseError(f"boolean is not a percentage: {raw!r}")
    if isinstance(raw, Decimal):
        if raw.is_nan():
            return None
        text = format(raw, "f")
    elif isinstance(raw, int):
        text = str(raw)
    elif isinstance(raw, str):
        if _is_blank(raw):
            return None
        text = raw.strip().removesuffix("%").strip()
        if "$" in text:
            raise MoneyParseError(f"dollar amount passed to percentage parser: {raw!r}")
    else:
        raise MoneyParseError(
            f"unsupported type {type(raw).__name__}; floats are not allowed for percentages"
        )
    value = _to_decimal(text, raw)
    _check_places(value, PERCENT_MAX_PLACES, raw)
    if value > PERCENT_MAX:
        raise MoneyParseError(f"percentage outside 0-1000: {raw!r}")
    return value
