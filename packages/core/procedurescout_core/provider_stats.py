"""Privacy-safe counts for provider dashboards (D-050).

What is stored: daily totals per facility (page views, times shown in search
results with the sum of positions, clicks to website, phone, directions and
booking), daily totals per facility and service shown, and daily search totals
per service on a 0.1-degree grid (about 7 miles). Nothing else: no IP address,
device, account, exact location or search text.

What providers see: totals over a period. Any number under 10 is shown as
"fewer than 10", so one person's search can never be singled out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import Connection, text

SMALL = 10
METRICS = (
    "page_view",
    "search_impression",
    "website_click",
    "phone_click",
    "directions_click",
    "booking_click",
)
CLICKS = ("website_click", "phone_click", "directions_click", "booking_click")
RINGS_MILES = (10, 25, 50)
METERS_PER_MILE = Decimal("1609.344")
# A Sponsored spot is shared by at most this many providers per search page (PRV-06).
SPONSORS_PER_PAGE = 2
_SERVICE_KEY = re.compile(r"^(svc:[a-z0-9-]{1,80}|code:[A-Z_]{2,12}:[0-9A-Za-z.-]{1,12})$")


@dataclass(frozen=True, slots=True)
class Count:
    value: int | None  # None when hidden (fewer than SMALL)
    previous: int | None

    @property
    def label(self) -> str:
        return f"fewer than {SMALL}" if self.value is None else f"{self.value:,}"


def _hide(n: int) -> int | None:
    return None if n < SMALL else n


def service_key(service_slug: str | None, code_system: str | None, code: str | None) -> str | None:
    if service_slug:
        key = f"svc:{service_slug}"
    elif code_system and code:
        key = f"code:{code_system.upper()}:{code}"
    else:
        return None
    return key if _SERVICE_KEY.match(key) else None


def grid(lat: Decimal, lng: Decimal) -> tuple[str, Decimal, Decimal]:
    """Round a searched point down to its 0.1-degree cell and use the cell centre."""
    tenth = Decimal("0.1")
    la = (lat / tenth).to_integral_value(rounding=ROUND_FLOOR) * tenth
    lo = (lng / tenth).to_integral_value(rounding=ROUND_FLOOR) * tenth
    key = f"grid:{la:.1f},{lo:.1f}"
    return key, la + Decimal("0.05"), lo + Decimal("0.05")


def record_event(conn: Connection, facility_id: str, metric: str) -> None:
    if metric not in METRICS or metric == "search_impression":
        raise ValueError(f"not a countable event: {metric}")
    conn.execute(
        text(
            """
            INSERT INTO stats.facility_daily (day, facility_id, metric, count)
            SELECT current_date, f.id, :m, 1 FROM ref.facility f WHERE f.id = CAST(:f AS uuid)
            ON CONFLICT (day, facility_id, metric)
            DO UPDATE SET count = stats.facility_daily.count + 1
            """
        ),
        {"f": facility_id, "m": metric},
    )


def record_search(
    conn: Connection,
    key: str,
    lat: Decimal,
    lng: Decimal,
    shown: list[str],
) -> None:
    """Count one search and the facilities shown (in order, first = position 1)."""
    if not _SERVICE_KEY.match(key):
        return
    place, clat, clng = grid(lat, lng)
    conn.execute(
        text(
            """
            INSERT INTO stats.search_daily (day, service_key, place_key, geom, count)
            VALUES (current_date, :k, :p,
                    ST_SetSRID(ST_MakePoint(CAST(:lng AS float8), CAST(:lat AS float8)),
                               4326)::geography, 1)
            ON CONFLICT (day, service_key, place_key)
            DO UPDATE SET count = stats.search_daily.count + 1
            """
        ),
        {"k": key, "p": place, "lat": str(clat), "lng": str(clng)},
    )
    # Two set-based statements (not two per place shown): one search used to make
    # 100 round trips that queued behind other searches' row locks (2026-11-12).
    # Rows are written in facility order so concurrent searches can't deadlock.
    seen: dict[str, int] = {}
    for position, fid in enumerate(shown[:100], start=1):
        seen.setdefault(fid, position)
    if not seen:
        return
    ids = sorted(seen)
    params = {"f": ids, "pos": [seen[f] for f in ids], "k": key}
    conn.execute(
        text(
            """
            INSERT INTO stats.facility_daily (day, facility_id, metric, count, position_sum)
            SELECT current_date, CAST(f AS uuid), 'search_impression', 1, pos
            FROM unnest(CAST(:f AS text[]), CAST(:pos AS int[])) AS t(f, pos)
            ORDER BY f
            ON CONFLICT (day, facility_id, metric) DO UPDATE SET
                count = stats.facility_daily.count + 1,
                position_sum = stats.facility_daily.position_sum + EXCLUDED.position_sum
            """
        ),
        params,
    )
    conn.execute(
        text(
            """
            INSERT INTO stats.facility_service_daily (day, facility_id, service_key,
                impressions)
            SELECT current_date, CAST(f AS uuid), :k, 1
            FROM unnest(CAST(:f AS text[])) AS t(f)
            ORDER BY f
            ON CONFLICT (day, facility_id, service_key) DO UPDATE SET
                impressions = stats.facility_service_daily.impressions + 1
            """
        ),
        {"f": ids, "k": key},
    )


@dataclass(frozen=True, slots=True)
class ServiceDemand:
    service_key: str
    name: str
    searches: tuple[int | None, int | None, int | None]  # within 10 / 25 / 50 miles
    shown: int | None
    offered: bool


@dataclass(frozen=True, slots=True)
class Boost:
    service_key: str
    name: str
    ring_miles: int
    searches: int | None
    estimated_views: int | None
    current_views: int | None


@dataclass(frozen=True, slots=True)
class Dashboard:
    days: int
    counts: dict[str, Count]
    average_position: Decimal | None
    services: tuple[ServiceDemand, ...]
    missed: tuple[ServiceDemand, ...]
    boosts: tuple[Boost, ...]
    has_location: bool


def _names(conn: Connection, keys: list[str]) -> dict[str, str]:
    slugs = [k[4:] for k in keys if k.startswith("svc:")]
    names: dict[str, str] = {}
    if slugs:
        for slug, name in conn.execute(
            text("SELECT slug, consumer_name FROM ref.procedure WHERE slug = ANY(:s)"), {"s": slugs}
        ).all():
            names[f"svc:{slug}"] = str(name)
    for k in keys:
        if k.startswith("code:") and k not in names:
            _, system, code = k.split(":", 2)
            names[k] = f"{system.replace('_', ' ')} code {code}"
        names.setdefault(k, k[4:].replace("-", " "))
    return names


def dashboard(conn: Connection, facility_id: str, days: int = 30) -> Dashboard:
    if days not in (7, 30, 90):
        raise ValueError("period must be 7, 30 or 90 days")
    rows = conn.execute(
        text(
            """
            SELECT metric,
                   coalesce(sum(count) FILTER (WHERE day > current_date - :d), 0),
                   coalesce(sum(count) FILTER (WHERE day <= current_date - :d), 0),
                   coalesce(sum(position_sum) FILTER (WHERE day > current_date - :d), 0)
            FROM stats.facility_daily
            WHERE facility_id = CAST(:f AS uuid) AND day > current_date - 2 * :d
            GROUP BY metric
            """
        ),
        {"f": facility_id, "d": days},
    ).all()
    raw = {str(r[0]): (int(r[1]), int(r[2]), int(r[3])) for r in rows}
    counts = {
        m: Count(_hide(raw.get(m, (0, 0, 0))[0]), _hide(raw.get(m, (0, 0, 0))[1])) for m in METRICS
    }
    impressions, _, pos_sum = raw.get("search_impression", (0, 0, 0))
    average_position = (
        (Decimal(pos_sum) / Decimal(impressions)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        if impressions >= SMALL
        else None
    )
    has_location = (
        conn.execute(
            text("SELECT geom IS NOT NULL FROM ref.facility WHERE id = CAST(:f AS uuid)"),
            {"f": facility_id},
        ).scalar()
        is True
    )
    shown = {
        str(r[0]): int(r[1])
        for r in conn.execute(
            text(
                "SELECT service_key, sum(impressions) FROM stats.facility_service_daily "
                "WHERE facility_id = CAST(:f AS uuid) AND day > current_date - :d GROUP BY 1"
            ),
            {"f": facility_id, "d": days},
        ).all()
    }
    listed = {
        f"svc:{r[0]}"
        for r in conn.execute(
            text(
                "SELECT p.slug FROM prov.listing_price lp JOIN ref.procedure p "
                "ON p.id = lp.procedure_id WHERE lp.facility_id = CAST(:f AS uuid) "
                "AND lp.status = 'published'"
            ),
            {"f": facility_id},
        ).all()
    } | {
        f"code:{r[0]}:{r[1]}"
        for r in conn.execute(
            text(
                "SELECT code_system, code FROM prov.listing_price WHERE "
                "facility_id = CAST(:f AS uuid) AND status = 'published' AND code IS NOT NULL"
            ),
            {"f": facility_id},
        ).all()
    }
    demand: dict[str, list[int]] = {}
    if has_location:
        meters = [str(Decimal(m) * METERS_PER_MILE) for m in RINGS_MILES]
        for r in conn.execute(
            text(
                """
                SELECT s.service_key,
                       sum(s.count) FILTER (WHERE ST_DWithin(s.geom, f.geom, CAST(:m10 AS float8))),
                       sum(s.count) FILTER (WHERE ST_DWithin(s.geom, f.geom, CAST(:m25 AS float8))),
                       sum(s.count)
                FROM stats.search_daily s, ref.facility f
                WHERE f.id = CAST(:f AS uuid) AND s.day > current_date - :d
                  AND ST_DWithin(s.geom, f.geom, CAST(:m50 AS float8))
                GROUP BY s.service_key
                ORDER BY 4 DESC LIMIT 200
                """
            ),
            {"f": facility_id, "d": days, "m10": meters[0], "m25": meters[1], "m50": meters[2]},
        ).all():
            demand[str(r[0])] = [int(r[1] or 0), int(r[2] or 0), int(r[3] or 0)]
    offered = listed | {k for k, n in shown.items() if n > 0}
    keys = sorted(set(demand) | offered)
    names = _names(conn, keys)

    def item(k: str) -> ServiceDemand:
        d = demand.get(k, [0, 0, 0])
        return ServiceDemand(
            service_key=k,
            name=names[k],
            searches=(_hide(d[0]), _hide(d[1]), _hide(d[2])),
            shown=_hide(shown.get(k, 0)),
            offered=k in offered,
        )

    services = tuple(
        sorted((item(k) for k in offered), key=lambda s: -(demand.get(s.service_key, [0, 0, 0])[2]))
    )
    missed = tuple(
        item(k)
        for k in sorted(demand, key=lambda k: -demand[k][1])
        if k not in offered and demand[k][1] >= SMALL
    )[:10]
    boosts: list[Boost] = []
    if days == 30:
        for s in services[:10]:
            d = demand.get(s.service_key, [0, 0, 0])
            for ring_index, ring in enumerate(RINGS_MILES):
                n = d[ring_index]
                boosts.append(
                    Boost(
                        service_key=s.service_key,
                        name=s.name,
                        ring_miles=ring,
                        searches=_hide(n),
                        estimated_views=_hide(n // SPONSORS_PER_PAGE),
                        current_views=s.shown,
                    )
                )
    return Dashboard(
        days=days,
        counts=counts,
        average_position=average_position,
        services=services,
        missed=missed,
        boosts=tuple(boosts),
        has_location=has_location,
    )


def as_dict(d: Dashboard) -> dict[str, Any]:
    return {
        "days": d.days,
        "has_location": d.has_location,
        "small_number": SMALL,
        "counts": {k: {"value": c.value, "previous": c.previous} for k, c in d.counts.items()},
        "average_position": None if d.average_position is None else str(d.average_position),
        "services": [_svc(s) for s in d.services],
        "missed": [_svc(s) for s in d.missed],
        "boosts": [
            {
                "service_key": b.service_key,
                "name": b.name,
                "ring_miles": b.ring_miles,
                "searches": b.searches,
                "estimated_views": b.estimated_views,
                "current_views": b.current_views,
            }
            for b in d.boosts
        ],
        "sponsors_per_page": SPONSORS_PER_PAGE,
    }


def _svc(s: ServiceDemand) -> dict[str, Any]:
    return {
        "service_key": s.service_key,
        "name": s.name,
        "searches_10": s.searches[0],
        "searches_25": s.searches[1],
        "searches_50": s.searches[2],
        "shown": s.shown,
        "offered": s.offered,
    }
