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
- the total adds only priced pieces, and says whether it is complete;
- (2026-11-12) a piece with several amounts adds its lowest and highest to a
  total range; a doctor's piece is priced from rows the hospital labeled as the
  doctor's part (professional) and a hospital piece from its own part, when the
  hospital labeled them; insurance can be one card-name plan (approved
  spellings, rule 9) or "not sure which plan" (all of an insurer's work and
  individual plans).
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Connection, text

if TYPE_CHECKING:
    from .plans import Spellings
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
    total_low: Decimal | None = None  # with several-price pieces at their lowest
    total_high: Decimal | None = None  # ... and at their highest


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


DOCTOR_ROLES = frozenset({"physician", "anesthesia", "pathology"})


def _price_line(
    component: Component,
    prices: list[PublishedPrice],
    mode: str,
    payer: str | None,
    plan: str | None,
    spellings: Spellings | None = None,
    state: str = "",
) -> Line:
    if mode == "cash":
        rows = [p for p in prices if p.price_type == "discounted_cash"]
    elif mode == "list":
        rows = [p for p in prices if p.price_type == "gross"]
    elif spellings is not None:
        from .plans import matches

        rows = [p for p in prices if p.price_type == "negotiated" and matches(p, spellings, state)]
    else:
        rows = [
            p
            for p in prices
            if p.price_type == "negotiated"
            and p.payer_name_raw == payer
            and p.plan_name_raw == plan
        ]
    # the doctor's piece from the doctor's part, the hospital's piece from its own
    # part, when the hospital labeled them (otherwise every row, as before)
    doctor = [p for p in rows if p.billing_class == "professional"]
    own = [p for p in rows if p.billing_class in ("facility", "both")]
    if component.role in DOCTOR_ROLES and doctor:
        rows = doctor
    elif component.role not in DOCTOR_ROLES and own:
        rows = own
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
    plan_id: str | None = None,
    payer_id: str | None = None,
) -> BundleEstimate:
    if mode not in MODES:
        raise BundleError(f"payment must be one of {', '.join(MODES)}")
    by_id = plan_id is not None or payer_id is not None
    if plan_id is not None and payer_id is not None:
        raise BundleError("give a plan or an insurer, not both")
    if (mode == "insurance") != (by_id or (payer is not None and plan is not None)):
        raise BundleError("insurance needs a payer and a plan (and only insurance does)")
    spellings: Spellings | None = None
    if by_id:
        from .plans import PlanError, approved_spellings, insurer_spellings

        try:
            spellings = (
                approved_spellings(conn, plan_id)
                if plan_id is not None
                else insurer_spellings(conn, str(payer_id))[1]
            )
        except PlanError as exc:
            raise BundleError(str(exc)) from exc
    try:
        fid = uuid.UUID(str(facility_id))
    except ValueError as exc:
        raise BundleError(str(exc)) from exc
    name, components = bundle_components(conn, bundle_slug)
    from .plans import facility_states

    state = facility_states(conn, [str(fid)]).get(str(fid), "")
    if (
        mode == "insurance"
        and not by_id
        and (payer, plan) not in facility_payer_plans(conn, store, fid)
    ):
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
        lines.append(_price_line(comp, prices, mode, payer, plan, spellings, state))
    priced = [ln.amount for ln in lines if ln.status == "priced" and ln.amount is not None]
    included_lines = [ln for ln in lines if ln.included]
    complete = bool(included_lines) and all(ln.status == "priced" for ln in included_lines)
    lows = [ln.amount for ln in lines if ln.status == "priced" and ln.amount is not None]
    highs = list(lows)
    for ln in lines:
        if ln.status == "several_prices" and ln.other_amounts:
            lows.append(min(ln.other_amounts))
            highs.append(max(ln.other_amounts))
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
        total_low=sum(lows, Decimal(0)) if lows else None,
        total_high=sum(highs, Decimal(0)) if highs else None,
    )
