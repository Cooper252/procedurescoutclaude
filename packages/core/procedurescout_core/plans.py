"""Insurance plans by the names on people's cards (rule 9, SITE_DESIGN §4.11).

Hospitals spell plans their own way ("CIGNA - PPO", "Cigna Open Access Plus").
A person picks a plan by the name on their card (ref.plan under ref.payer);
only *approved* alias rows connect that plan to the raw payer/plan spellings
in hospital files. Nothing is matched fuzzily, and prices of other plans from
the same insurer are never substituted.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import Connection, text

from .matching import normalize_name
from .price_store import PublishedPrice


class PlanError(ValueError):
    """Unknown or unapproved plan."""


@dataclass(frozen=True, slots=True)
class Plan:
    plan_id: str
    payer: str
    plan: str
    product_type: str
    segment: str


def list_plans(conn: Connection) -> list[Plan]:
    """Plans that have at least one approved hospital spelling."""
    rows = conn.execute(
        text(
            """
            SELECT DISTINCT pl.id, py.canonical_name, pl.canonical_name,
                   pl.product_type::text, pl.segment::text
            FROM ref.plan pl
            JOIN ref.payer py ON py.id = pl.payer_id
            JOIN ref.plan_alias a ON a.plan_id = pl.id AND a.review_state = 'approved'
            ORDER BY 2, 3
            """
        )
    ).all()
    return [Plan(str(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4])) for r in rows]


def approved_spellings(conn: Connection, plan_id: uuid.UUID | str) -> set[tuple[str, str]]:
    """(normalized payer, normalized plan) spellings approved for this plan."""
    try:
        pid = str(uuid.UUID(str(plan_id)))
    except ValueError as exc:
        raise PlanError("not a plan id") from exc
    rows = conn.execute(
        text(
            "SELECT raw_payer_normalized, raw_plan_normalized FROM ref.plan_alias "
            "WHERE plan_id = CAST(:p AS uuid) AND review_state = 'approved'"
        ),
        {"p": pid},
    ).all()
    if not rows:
        raise PlanError("unknown plan, or no hospital spelling of it is approved yet")
    return {(str(r[0]), str(r[1])) for r in rows}


def matches(price: PublishedPrice, spellings: set[tuple[str, str]]) -> bool:
    if price.payer_name_raw is None or price.plan_name_raw is None:
        return False
    return (normalize_name(price.payer_name_raw), normalize_name(price.plan_name_raw)) in spellings
