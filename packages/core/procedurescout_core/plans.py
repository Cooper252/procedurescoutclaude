"""Insurance plans by the names on people's cards (rule 9, SITE_DESIGN §4.11).

Hospitals spell plans their own way ("CIGNA - PPO", "Cigna Open Access Plus").
A person picks a plan by the name on their card (ref.plan under ref.payer);
only *approved* alias rows connect that plan to the raw payer/plan spellings
in hospital files. Nothing is matched fuzzily, and prices of other plans from
the same insurer are never substituted.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Connection, text

from .matching import normalize_name
from .price_store import PublishedPrice


class PlanError(ValueError):
    """Unknown or unapproved plan."""


@dataclass(frozen=True, slots=True)
class Spellings:
    """Approved hospital spellings of a plan (or of an insurer's plans), by
    state (migration 0027): ('', ...) rows count in every state unless that
    state has its own row for the same spelling ("Anthem | Commercial" is
    Anthem Nevada in Nevada and Anthem Blue Cross in California)."""

    own: frozenset[tuple[str, str, str]] = frozenset()
    overridden: frozenset[tuple[str, str, str]] = frozenset()

    def __bool__(self) -> bool:
        return bool(self.own)

    def has(self, payer: str, plan: str, state: str) -> bool:
        if (payer, plan, state) in self.own:
            return True
        return (payer, plan, "") in self.own and (payer, plan, state) not in self.overridden


def _state_rows(conn: Connection) -> frozenset[tuple[str, str, str]]:
    """Every spelling that has its own approved row in some state."""
    return frozenset(
        (str(r[0]), str(r[1]), str(r[2]))
        for r in conn.execute(
            text(
                "SELECT raw_payer_normalized, raw_plan_normalized, state_code FROM ref.plan_alias "
                "WHERE review_state = 'approved' AND state_code <> ''"
            )
        ).all()
    )


def _spellings(conn: Connection, rows: Sequence[Sequence[object]]) -> Spellings:
    return Spellings(frozenset((str(r[0]), str(r[1]), str(r[2])) for r in rows), _state_rows(conn))


@dataclass(frozen=True, slots=True)
class Plan:
    plan_id: str
    payer: str
    plan: str
    product_type: str
    segment: str
    payer_id: str = ""


def list_plans(conn: Connection) -> list[Plan]:
    """Plans that have at least one approved hospital spelling."""
    rows = conn.execute(
        text(
            """
            SELECT DISTINCT pl.id, py.canonical_name, pl.canonical_name,
                   pl.product_type::text, pl.segment::text, py.id
            FROM ref.plan pl
            JOIN ref.payer py ON py.id = pl.payer_id
            JOIN ref.plan_alias a ON a.plan_id = pl.id AND a.review_state = 'approved'
            ORDER BY 2, 3
            """
        )
    ).all()
    return [Plan(str(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4]), str(r[5])) for r in rows]


# "Not sure which plan?" (Cooper, 2026-11-12): people who know their insurer but
# not their plan see the range of that insurer's work and individual plans.
# Medicare and Medicaid plans are left out: their rates are far lower and would
# make the range misleading; people with those cards are told to pick them.
UNSURE_LEFT_OUT = ("medicare_advantage", "medicaid_managed_care")


def insurer_spellings(conn: Connection, payer_id: uuid.UUID | str) -> tuple[str, Spellings]:
    """(insurer name, approved spellings of all its work and individual plans)."""
    try:
        pid = str(uuid.UUID(str(payer_id)))
    except ValueError as exc:
        raise PlanError("not an insurer id") from exc
    rows = conn.execute(
        text(
            """
            SELECT py.canonical_name, a.raw_payer_normalized, a.raw_plan_normalized,
                   a.state_code
            FROM ref.payer py
            JOIN ref.plan pl ON pl.payer_id = py.id
            JOIN ref.plan_alias a ON a.plan_id = pl.id AND a.review_state = 'approved'
            WHERE py.id = CAST(:p AS uuid) AND pl.segment::text <> ALL(:out)
            """
        ),
        {"p": pid, "out": list(UNSURE_LEFT_OUT)},
    ).all()
    if not rows:
        raise PlanError("unknown insurer, or none of its plans is approved yet")
    return str(rows[0][0]), _spellings(conn, [(r[1], r[2], r[3]) for r in rows])


def nearby_published(
    conn: Connection, latitude: Decimal, longitude: Decimal, radius_miles: Decimal
) -> list[str]:
    """Places with a published price file within the distance."""
    rows = conn.execute(
        text(
            """
            SELECT DISTINCT f.id FROM ref.facility f
            JOIN price.published_file pf ON pf.facility_id = f.id
            WHERE f.geom IS NOT NULL AND f.status = 'active'
              AND ST_DWithin(f.geom,
                    CAST(ST_SetSRID(ST_MakePoint(:lng, :lat), 4326) AS geography), :m)
            """
        ),
        {"lat": latitude, "lng": longitude, "m": radius_miles * Decimal("1609.344")},
    ).all()
    return [str(r[0]) for r in rows]


def spellings_at(conn: Connection, facility_ids: list[str]) -> set[tuple[str, str, str]]:
    """Normalized (insurer, plan, state) spellings published by these places."""
    if not facility_ids:
        return set()
    rows = conn.execute(
        text(
            "SELECT DISTINCT pp.payer_name_raw, pp.plan_name_raw, f.state_code "
            "FROM price.published_payer pp JOIN ref.facility f ON f.id = pp.facility_id "
            "WHERE pp.facility_id = ANY(CAST(:ids AS uuid[]))"
        ),
        {"ids": facility_ids},
    ).all()
    return {(normalize_name(str(r[0])), normalize_name(str(r[1] or "")), str(r[2])) for r in rows}


def plans_near(conn: Connection, facility_ids: list[str]) -> list[Plan]:
    """Plans with an approved spelling published by one of these places, as
    that spelling is matched in the place's state."""
    found = spellings_at(conn, facility_ids)
    if not found:
        return []
    rows = conn.execute(
        text(
            "SELECT plan_id, raw_payer_normalized, raw_plan_normalized, state_code "
            "FROM ref.plan_alias WHERE review_state = 'approved'"
        )
    ).all()
    by_plan: dict[str, set[tuple[str, str, str]]] = {}
    for r in rows:
        by_plan.setdefault(str(r[0]), set()).add((str(r[1]), str(r[2]), str(r[3])))
    overridden = _state_rows(conn)
    ok = {
        pid
        for pid, own in by_plan.items()
        if any(Spellings(frozenset(own), overridden).has(p, pl, st) for p, pl, st in found)
    }
    return [p for p in list_plans(conn) if p.plan_id in ok]


def approved_spellings(conn: Connection, plan_id: uuid.UUID | str) -> Spellings:
    """Spellings approved for this plan, by state."""
    try:
        pid = str(uuid.UUID(str(plan_id)))
    except ValueError as exc:
        raise PlanError("not a plan id") from exc
    rows = conn.execute(
        text(
            "SELECT raw_payer_normalized, raw_plan_normalized, state_code FROM ref.plan_alias "
            "WHERE plan_id = CAST(:p AS uuid) AND review_state = 'approved'"
        ),
        {"p": pid},
    ).all()
    if not rows:
        raise PlanError("unknown plan, or no hospital spelling of it is approved yet")
    return _spellings(conn, [tuple(r) for r in rows])


ALL_PLANS = "All plans (one rate published for all)"
_FALLBACK_TYPES = ("hmo", "ppo", "epo", "pos", "hdhp")


def all_plans_spellings(conn: Connection, plan_id: uuid.UUID | str) -> Spellings:
    """Approved spellings of the same insurer's "All plans" rate, used for a
    regular employer or individual plan (HMO/PPO/EPO/POS/HDHP, commercial) only
    when a hospital published one rate for all of that insurer's plans (Cooper,
    2026-11-08). Never for Medicare, Medicaid, marketplace or employer plans.
    Prices found this way are labeled, never passed off as the exact plan."""
    pid = str(uuid.UUID(str(plan_id)))
    rows = conn.execute(
        text(
            """
            SELECT a.raw_payer_normalized, a.raw_plan_normalized, a.state_code
            FROM ref.plan me
            JOIN ref.plan allp ON allp.payer_id = me.payer_id AND allp.canonical_name = :all
                              AND allp.id <> me.id
            JOIN ref.plan_alias a ON a.plan_id = allp.id AND a.review_state = 'approved'
            WHERE me.id = CAST(:p AS uuid) AND me.segment = 'commercial'
              AND me.product_type::text = ANY(:types)
            """
        ),
        {"p": pid, "all": ALL_PLANS, "types": list(_FALLBACK_TYPES)},
    ).all()
    return _spellings(conn, [tuple(r) for r in rows]) if rows else Spellings()


def matches(price: PublishedPrice, spellings: Spellings, state: str) -> bool:
    """Is this price published under one of the spellings, as matched in the
    state of the place that published it?"""
    if price.payer_name_raw is None or price.plan_name_raw is None:
        return False
    return spellings.has(
        normalize_name(price.payer_name_raw), normalize_name(price.plan_name_raw), state
    )


def facility_states(conn: Connection, facility_ids: list[str]) -> dict[str, str]:
    if not facility_ids:
        return {}
    return {
        str(r[0]): str(r[1])
        for r in conn.execute(
            text("SELECT id, state_code FROM ref.facility WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": facility_ids},
        ).all()
    }
