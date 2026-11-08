"""Price a bundle at one facility (BUN-01, D-036).

A bundle is everything a person actually needs (e.g. an endoscopy plus the
anesthesia, plus the biopsy review if one is taken). Required pieces are
always included; optional ones follow the person's checkboxes, starting from
their defaults.

Rules (no price is better than a false price):
- each piece is priced from the facility's published prices for its code, in
  the chosen payment mode: cash (discounted cash), list (gross charge), or one
  insurance plan (the facility's negotiated rate for exactly that payer and
  plan as published);
- a piece with no published dollar amount is listed as "not published"
  (doctors' and anesthesia fees are often billed separately and missing from
  hospital files) and is never counted as $0; a percentage-of-charges or
  formula rate is shown, not added;
- a piece with several different published amounts (e.g. by setting) is shown
  with all of them and not added;
- the total adds only priced pieces, and says whether it is complete.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import Connection, text

from .object_store import ObjectStore
from .price_store import PublishedPrice, facility_payer_plans, find_prices

MODES = ("cash", "list", "insurance")


class BundleError(ValueError):
    """Bad input; nothing was priced."""


@dataclass(frozen=True, slots=True)
class Component:
    component_id: str
    position: int
    label: str
    role: str
    requirement: str
    included_by_default: bool
    code_system: str
    code: str
    notes: str | None


@dataclass(frozen=True, slots=True)
class Line:
    component: Component
    included: bool
    status: str  # "priced", "not_published", "not_a_dollar_amount", "several_prices", "left_out"
    amount: Decimal | None = None
    other_amounts: tuple[Decimal, ...] = field(default_factory=tuple)
    rate_text: str | None = None


@dataclass(frozen=True, slots=True)
class BundleEstimate:
    bundle_slug: str
    bundle_name: str
    facility_id: str
    mode: str
    payer: str | None
    plan: str | None
    lines: tuple[Line, ...]
    total_of_priced: Decimal | None
    complete: bool


def bundle_components(conn: Connection, slug: str) -> tuple[str, list[Component]]:
    row = conn.execute(
        text(
            "SELECT id, consumer_name FROM ref.procedure "
            "WHERE slug = :s AND kind = 'bundle' AND review_state = 'approved'"
        ),
        {"s": slug},
    ).first()
    if row is None:
        raise BundleError(f"unknown bundle: {slug!r}")
    comps = conn.execute(
        text(
            """
            SELECT id, position, label, role, requirement, included_by_default,
                   code_system::text, code, notes
            FROM ref.bundle_component
            WHERE bundle_id = :b AND review_state = 'approved' ORDER BY position
            """
        ),
        {"b": row[0]},
    ).all()
    return str(row[1]), [
        Component(
            str(c[0]),
            int(c[1]),
            str(c[2]),
            str(c[3]),
            str(c[4]),
            bool(c[5]),
            str(c[6]),
            str(c[7]),
            None if c[8] is None else str(c[8]),
        )
        for c in comps
    ]


def _price_line(
    component: Component,
    prices: list[PublishedPrice],
    mode: str,
    payer: str | None,
    plan: str | None,
) -> Line:
    if mode == "cash":
        rows = [p for p in prices if p.price_type == "discounted_cash"]
    elif mode == "list":
        rows = [p for p in prices if p.price_type == "gross"]
    else:
        rows = [
            p
            for p in prices
            if p.price_type == "negotiated"
            and p.payer_name_raw == payer
            and p.plan_name_raw == plan
        ]
    if not rows:
        return Line(component, True, "not_published")
    amounts = sorted({p.amount for p in rows if p.amount is not None})
    if not amounts:
        r = rows[0]
        rate = (
            f"{r.percentage.normalize():f}% of charges" if r.percentage is not None else r.algorithm
        )
        return Line(component, True, "not_a_dollar_amount", rate_text=rate)
    if len(amounts) > 1:
        return Line(component, True, "several_prices", other_amounts=tuple(amounts))
    return Line(component, True, "priced", amount=amounts[0])


def estimate(
    conn: Connection,
    store: ObjectStore,
    *,
    bundle_slug: str,
    facility_id: uuid.UUID | str,
    mode: str,
    include_optional: Collection[str] | None = None,
    payer: str | None = None,
    plan: str | None = None,
) -> BundleEstimate:
    if mode not in MODES:
        raise BundleError(f"payment must be one of {', '.join(MODES)}")
    if (mode == "insurance") != (payer is not None and plan is not None):
        raise BundleError("insurance needs a payer and a plan (and only insurance does)")
    try:
        fid = uuid.UUID(str(facility_id))
    except ValueError as exc:
        raise BundleError(str(exc)) from exc
    name, components = bundle_components(conn, bundle_slug)
    if mode == "insurance" and (payer, plan) not in facility_payer_plans(conn, store, fid):
        # only plans this facility actually publishes; never a similar-looking one
        raise BundleError("this facility does not publish prices for that payer and plan")
    known_ids = {c.component_id for c in components}
    chosen = None if include_optional is None else set(include_optional)
    if chosen is not None and not chosen <= known_ids:
        raise BundleError("unknown component in the selection")
    lines = []
    for comp in components:
        included = comp.requirement == "required" or (
            comp.included_by_default if chosen is None else comp.component_id in chosen
        )
        if not included:
            lines.append(Line(comp, False, "left_out"))
            continue
        prices = find_prices(conn, store, [fid], comp.code_system, comp.code)
        lines.append(_price_line(comp, prices, mode, payer, plan))
    priced = [ln.amount for ln in lines if ln.status == "priced" and ln.amount is not None]
    included_lines = [ln for ln in lines if ln.included]
    complete = bool(included_lines) and all(ln.status == "priced" for ln in included_lines)
    return BundleEstimate(
        bundle_slug=bundle_slug,
        bundle_name=name,
        facility_id=str(fid),
        mode=mode,
        payer=payer,
        plan=plan,
        lines=tuple(lines),
        total_of_priced=sum(priced, Decimal(0)) if priced else None,
        complete=complete,
    )
