"""Places people search from: cities with facilities (for service-by-city pages).

A city's center is the center of its active, geocoded facilities, so a
"near Las Vegas" search starts where the care is. Nothing here reads prices.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import Connection, text

_STATE = re.compile(r"^[A-Za-z]{2}$")
_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class PlaceError(ValueError):
    """Unknown state or city."""


@dataclass(frozen=True, slots=True)
class City:
    state_code: str
    name: str
    slug: str
    lat: str
    lng: str
    facilities: int


def city_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def cities(conn: Connection, state_code: str) -> list[City]:
    """Cities in a state with at least one active, geocoded facility, largest first."""
    if not _STATE.match(state_code):
        raise PlaceError("not a state code")
    rows = conn.execute(
        text(
            """
            SELECT initcap(lower(f.city)) AS city, f.state_code,
                   round(CAST(ST_Y(ST_Centroid(ST_Collect(f.geom::geometry))) AS numeric), 4)::text,
                   round(CAST(ST_X(ST_Centroid(ST_Collect(f.geom::geometry))) AS numeric), 4)::text,
                   count(*) AS n
            FROM ref.facility f
            WHERE f.state_code = :s AND f.status = 'active' AND f.geom IS NOT NULL
              AND f.city IS NOT NULL AND btrim(f.city) <> ''
            GROUP BY 1, 2
            ORDER BY n DESC, city
            """
        ),
        {"s": state_code.upper()},
    ).all()
    out: list[City] = []
    seen: set[str] = set()
    for r in rows:
        slug = city_slug(str(r[0]))
        if not slug or slug in seen:
            continue
        seen.add(slug)
        out.append(City(str(r[1]), str(r[0]), slug, str(r[2]), str(r[3]), int(r[4])))
    return out


def city(conn: Connection, state_code: str, slug: str) -> City:
    if not _SLUG.match(slug):
        raise PlaceError("not a city")
    for c in cities(conn, state_code):
        if c.slug == slug:
            return c
    raise PlaceError("unknown city")
