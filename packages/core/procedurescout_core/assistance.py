"""Financial assistance: the site-wide message and the "you may qualify" check
(FA-01, FA-02, D-037).

The check never says "eligible": hospitals decide. It compares the household's
income with the HHS poverty guideline for its size (exactly as published) and
each hospital's reviewed income limits, and says which help the person *may*
qualify for. Hospitals without a reviewed policy are listed as "ask the
hospital", never as "no help". Nothing about the person is stored or logged.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import Connection, text

# Shown on every page of the site and prominently on the home page.
SITE_MESSAGE = (
    "You may qualify for free or reduced-cost care. Most hospitals must offer "
    "financial assistance, and many people with low or middle incomes qualify, "
    "even with insurance. Check what you may qualify for before you pay."
)
SITE_MESSAGE_DETAIL = (
    "Nonprofit hospitals are required by federal law to have a written financial "
    "assistance policy, and many other hospitals offer one. Each hospital sets its "
    "own rules, usually based on household income compared with the federal "
    "poverty guidelines. Only the hospital can confirm what you will receive."
)
MAX_HOUSEHOLD = 20


class AssistanceError(ValueError):
    """Bad input; nothing was checked."""


def region_for_state(state_code: str) -> str:
    return {"AK": "alaska", "HI": "hawaii"}.get(state_code.upper(), "contiguous")


def guideline(conn: Connection, year: int, state_code: str, household_size: int) -> Decimal:
    """HHS poverty guideline for a household: the published amount for sizes
    1-8, plus the published per-person amount for each person beyond 8."""
    if not 1 <= household_size <= MAX_HOUSEHOLD:
        raise AssistanceError(f"household size must be 1 to {MAX_HOUSEHOLD}")
    size = min(household_size, 8)
    row = conn.execute(
        text(
            "SELECT amount, per_additional FROM ref.poverty_guideline "
            "WHERE year = :y AND region = :r AND household_size = :h"
        ),
        {"y": year, "r": region_for_state(state_code), "h": size},
    ).first()
    if row is None:
        raise AssistanceError(f"no poverty guideline loaded for {year}")
    amount, extra = Decimal(row[0]), Decimal(row[1])
    return amount + extra * (household_size - size)


def latest_guideline_year(conn: Connection) -> int:
    year = conn.execute(text("SELECT max(year) FROM ref.poverty_guideline")).scalar()
    if year is None:
        raise AssistanceError("no poverty guidelines loaded")
    return int(year)


@dataclass(frozen=True, slots=True)
class Tier:
    benefit: str  # "free" or "discount"
    max_percent_fpg: Decimal
    discount_percent: Decimal | None
    description: str | None


def dollars(amount: Decimal) -> str:
    """Whole dollars for display ("$31,920"); a limit is shown rounded down so
    nobody is told they are under it when they are not."""
    return f"${int(amount.quantize(Decimal(1), rounding=ROUND_DOWN)):,}"


def income_limit(fpg: Decimal, percent: Decimal) -> Decimal:
    return fpg * percent / 100


def plain_message(
    name: str, tiers: Sequence[Tier], single_fpg: Decimal, family4_fpg: Decimal
) -> str:
    """'You may qualify for free care at X if your household makes under $31,920
    (1 person) or $66,000 (family of 4).' Dollar amounts, never poverty-level
    percentages (Cooper, 2026-11-08)."""
    if not tiers:
        return f"Ask {name} about financial assistance; we have not reviewed its policy yet."
    parts = []
    free = [t for t in tiers if t.benefit == "free"]
    discounts = [t for t in tiers if t.benefit == "discount"]
    if free:
        top = max(free, key=lambda t: t.max_percent_fpg)
        parts.append(
            f"You may qualify for free care at {name} if your household makes under "
            f"{dollars(income_limit(single_fpg, top.max_percent_fpg))} (1 person) or "
            f"{dollars(income_limit(family4_fpg, top.max_percent_fpg))} (family of 4)."
        )
    if discounts:
        top = max(discounts, key=lambda t: t.max_percent_fpg)
        lead = "Discounts may be available" if free else f"You may qualify for help at {name}"
        parts.append(
            f"{lead} up to {dollars(income_limit(single_fpg, top.max_percent_fpg))} "
            f"(1 person) or {dollars(income_limit(family4_fpg, top.max_percent_fpg))} "
            "(family of 4)."
        )
    return " ".join(parts)


def facility_policy(conn: Connection, facility_id: uuid.UUID | str, state_code: str) -> str:
    """The plain-dollar message for one facility (no personal data needed)."""
    fid = str(uuid.UUID(str(facility_id)))
    row = conn.execute(text("SELECT name FROM ref.facility WHERE id = :f"), {"f": fid}).first()
    if row is None:
        raise AssistanceError("unknown facility")
    tiers = [
        Tier(
            str(r[0]),
            Decimal(str(r[1])),
            None if r[2] is None else Decimal(str(r[2])),
            None if r[3] is None else str(r[3]),
        )
        for r in conn.execute(
            text(
                """
                SELECT t.benefit, t.max_percent_fpg, t.discount_percent, t.description
                FROM ref.assistance_policy p JOIN ref.assistance_tier t ON t.policy_id = p.id
                WHERE p.facility_id = :f AND p.review_state = 'approved'
                """
            ),
            {"f": fid},
        ).all()
    ]
    year = latest_guideline_year(conn)
    return plain_message(
        str(row[0]),
        tiers,
        guideline(conn, year, state_code, 1),
        guideline(conn, year, state_code, 4),
    )


def site_message(conn: Connection, state_code: str) -> str:
    """Home-page headline in dollars: the free-care and help limits most common
    among the state's reviewed hospital policies ("at many hospitals")."""
    rows = conn.execute(
        text(
            """
            SELECT t.benefit, t.max_percent_fpg, count(DISTINCT p.facility_id) AS n
            FROM ref.assistance_policy p
            JOIN ref.assistance_tier t ON t.policy_id = p.id
            JOIN ref.facility f ON f.id = p.facility_id
            WHERE p.review_state = 'approved' AND f.state_code = :s
            GROUP BY 1, 2 ORDER BY n DESC, t.max_percent_fpg DESC
            """
        ),
        {"s": state_code.upper()},
    ).all()
    if not rows:
        return SITE_MESSAGE
    year = latest_guideline_year(conn)
    single = guideline(conn, year, state_code, 1)
    family = guideline(conn, year, state_code, 4)
    free = [r for r in rows if r[0] == "free"]
    help_ = [Decimal(str(r[1])) for r in rows]
    parts = []
    if free:
        pct = Decimal(str(free[0][1]))
        parts.append(
            f"At many hospitals you may qualify for free care if your household makes under "
            f"{dollars(income_limit(single, pct))} (1 person) or "
            f"{dollars(income_limit(family, pct))} (family of 4)"
        )
    top = max(help_)
    parts.append(
        f"and for reduced-cost care up to {dollars(income_limit(single, top))} or "
        f"{dollars(income_limit(family, top))}"
        if free
        else f"At many hospitals you may qualify for free or reduced-cost care if your household "
        f"makes under {dollars(income_limit(single, top))} (1 person) or "
        f"{dollars(income_limit(family, top))} (family of 4)"
    )
    return ", ".join(parts) + ". Even with insurance. Check before you pay."


@dataclass(frozen=True, slots=True)
class FacilityAssistance:
    facility_id: str
    name: str
    status: str  # "may_qualify_free", "may_qualify_discount", "above_published_limits",
    #              "policy_not_reviewed"
    best_tier: Tier | None
    policy_url: str | None
    application_url: str | None
    phone: str | None
    tiers: tuple[Tier, ...] = field(default_factory=tuple)
    plain_message: str = ""


@dataclass(frozen=True, slots=True)
class AssistanceCheck:
    guideline_year: int
    guideline_amount: Decimal
    percent_of_guideline: Decimal  # rounded down to a whole percent, for display only
    facilities: tuple[FacilityAssistance, ...]
    message: str = SITE_MESSAGE


def check(
    conn: Connection,
    *,
    facility_ids: Sequence[uuid.UUID | str],
    household_size: int,
    annual_income: Decimal,
    state_code: str,
) -> AssistanceCheck:
    if not facility_ids or len(facility_ids) > 50:
        raise AssistanceError("give 1 to 50 facilities")
    if annual_income < 0 or annual_income > Decimal("100000000"):
        raise AssistanceError("income out of range")
    if len(state_code) != 2 or not state_code.isalpha():
        raise AssistanceError("state must be a two-letter code")
    try:
        ids = sorted({str(uuid.UUID(str(f))) for f in facility_ids})
    except ValueError as exc:
        raise AssistanceError(str(exc)) from exc
    year = latest_guideline_year(conn)
    fpg = guideline(conn, year, state_code, household_size)
    percent = annual_income * 100 / fpg  # exact comparison below; display rounds down
    rows = conn.execute(
        text(
            """
            SELECT f.id, f.name, p.policy_url, p.application_url, p.phone,
                   t.benefit, t.max_percent_fpg, t.discount_percent, t.description
            FROM ref.facility f
            LEFT JOIN ref.assistance_policy p
                   ON p.facility_id = f.id AND p.review_state = 'approved'
            LEFT JOIN ref.assistance_tier t ON t.policy_id = p.id
            WHERE f.id = ANY(CAST(:ids AS uuid[]))
            ORDER BY f.name, t.max_percent_fpg
            """
        ),
        {"ids": ids},
    ).all()
    grouped: dict[str, list[tuple[object, ...]]] = {}
    for r in rows:
        grouped.setdefault(str(r[0]), []).append(tuple(r))
    results = []
    for fid, items in grouped.items():
        first = items[0]
        tiers = tuple(
            Tier(
                str(r[5]),
                Decimal(str(r[6])),
                None if r[7] is None else Decimal(str(r[7])),
                None if r[8] is None else str(r[8]),
            )
            for r in items
            if r[5] is not None
        )
        if first[2] is None or not tiers:
            status, best = "policy_not_reviewed", None
        else:
            matching = [t for t in tiers if percent <= t.max_percent_fpg]
            free = [t for t in matching if t.benefit == "free"]
            if free:
                status, best = "may_qualify_free", free[0]
            elif matching:
                status, best = "may_qualify_discount", matching[0]
            else:
                status, best = "above_published_limits", None
        results.append(
            FacilityAssistance(
                facility_id=fid,
                name=str(first[1]),
                status=status,
                best_tier=best,
                policy_url=None if first[2] is None else str(first[2]),
                application_url=None if first[3] is None else str(first[3]),
                phone=None if first[4] is None else str(first[4]),
                tiers=tiers,
                plain_message=plain_message(
                    str(first[1]),
                    tiers if first[2] is not None else (),
                    guideline(conn, year, state_code, 1),
                    guideline(conn, year, state_code, 4),
                ),
            )
        )
    return AssistanceCheck(
        guideline_year=year,
        guideline_amount=fpg,
        percent_of_guideline=percent.quantize(Decimal(1), rounding=ROUND_DOWN),
        facilities=tuple(results),
    )
