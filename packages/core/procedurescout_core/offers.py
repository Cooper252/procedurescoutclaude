"""Provider specials on a regular price (D-042).

A provider lists a regular price for one standard service and may add one or
more specials: a special price, a percent off or a dollar amount off, for new
patients or everyone, with dates and short terms. Specials are always shown as
specials next to the regular price; comparisons, "lowest near you" and the
typical range use regular prices only, so a special can never pass itself off
as the everyday price.

Money is Decimal and never rounded here; the page shows cents.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

KINDS = ("special_price", "percent_off", "amount_off")
WHO = ("new_patients", "everyone")


class OfferError(ValueError):
    """An offer that cannot be shown honestly."""


@dataclass(frozen=True, slots=True)
class Offer:
    kind: str
    who: str
    starts_on: date
    ends_on: date | None = None
    offer_price: Decimal | None = None
    percent_off: Decimal | None = None
    amount_off: Decimal | None = None
    terms: str | None = None


def check(regular: Decimal, offer: Offer) -> None:
    """The same rules the database enforces, for the provider form."""
    if regular <= 0:
        raise OfferError("the regular price must be more than $0")
    if offer.kind not in KINDS:
        raise OfferError("unknown kind of special")
    if offer.who not in WHO:
        raise OfferError("say who the special is for")
    given = [offer.offer_price, offer.percent_off, offer.amount_off]
    if sum(v is not None for v in given) != 1:
        raise OfferError("give exactly one of: special price, percent off, dollars off")
    if offer.kind == "special_price":
        if offer.offer_price is None or not (0 < offer.offer_price < regular):
            raise OfferError("a special price must be more than $0 and less than the regular price")
    elif offer.kind == "percent_off":
        if offer.percent_off is None or not (0 < offer.percent_off < 100):
            raise OfferError("percent off must be between 0 and 100")
    elif offer.amount_off is None or not (0 < offer.amount_off < regular):
        raise OfferError("dollars off must be more than $0 and less than the regular price")
    if offer.ends_on is not None and offer.ends_on < offer.starts_on:
        raise OfferError("the end date is before the start date")
    if offer.terms is not None and len(offer.terms) > 300:
        raise OfferError("keep the terms under 300 characters")


def price_with_offer(regular: Decimal, offer: Offer) -> Decimal:
    """What the patient pays with the special (exact; never rounded here)."""
    check(regular, offer)
    if offer.kind == "special_price":
        assert offer.offer_price is not None
        return offer.offer_price
    if offer.kind == "percent_off":
        assert offer.percent_off is not None
        return regular * (Decimal(100) - offer.percent_off) / Decimal(100)
    assert offer.amount_off is not None
    return regular - offer.amount_off


def active(offer: Offer, today: date) -> bool:
    return offer.starts_on <= today and (offer.ends_on is None or today <= offer.ends_on)


def _d(v: Decimal) -> str:
    q = v.quantize(Decimal("0.01"))
    s = f"{q:,.2f}"
    return "$" + (s[:-3] if s.endswith(".00") else s)


def describe(regular: Decimal, offer: Offer) -> str:
    """'New patients: $79 (regular $129, save $50). Ends Dec 31, 2026.'"""
    pay = price_with_offer(regular, offer)
    who = "New patients" if offer.who == "new_patients" else "Special"
    if offer.kind == "percent_off":
        assert offer.percent_off is not None
        lead = f"{who}: {offer.percent_off.normalize():f}% off, {_d(pay)}"
    else:
        lead = f"{who}: {_d(pay)}"
    text = f"{lead} (regular {_d(regular)}, save {_d(regular - pay)})."
    if offer.ends_on is not None:
        text += f" Ends {offer.ends_on.strftime('%b')} {offer.ends_on.day}, {offer.ends_on.year}."
    if offer.terms:
        text += f" {offer.terms.strip()}"
    return text
