"""One facility's public page: who it is and its published prices for a service.

The facility id and the service are validated before any price file is read
(CLAUDE.md rule 12). Prices come only from published files (rule 7). A
website is shown only when a person reviewed it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import Connection, text

from .object_store import ObjectStore
from .price_store import PublishedPrice, find_prices
from .search import SearchError, _codes_for_service


@dataclass(frozen=True, slots=True)
class FacilityDetail:
    facility_id: str
    name: str
    address: str | None
    city: str | None
    state_code: str
    zip5: str | None
    phone: str | None
    website: str | None  # only a reviewed website
    emergency_services: bool | None
    cms_rating: int | None
    cms_rating_as_of: str | None
    provider_types: tuple[str, ...]
    prices_published_at: str | None
    lat: str | None
    lng: str | None


@dataclass(frozen=True, slots=True)
class FacilityPrices:
    facility_id: str
    service_slug: str
    service_name: str
    unit: str
    codes: tuple[str, ...]
    published_at: str | None
    prices: tuple[PublishedPrice, ...] = field(default_factory=tuple)


def _id(facility_id: str) -> str:
    try:
        return str(uuid.UUID(facility_id))
    except ValueError as exc:
        raise SearchError("not a facility id") from exc


def facility_detail(conn: Connection, facility_id: str) -> FacilityDetail:
    fid = _id(facility_id)
    row = conn.execute(
        text(
            """
            SELECT f.id, f.name, f.address_line1, f.city, f.state_code, f.zip5, f.phone,
                   CASE WHEN f.website_reviewed_at IS NOT NULL THEN f.website END,
                   f.er_services, f.cms_overall_rating, f.cms_rating_as_of,
                   coalesce((SELECT array_agg(provider_type ORDER BY provider_type)
                             FROM ref.facility_provider_type WHERE facility_id = f.id), '{}'),
                   (SELECT max(published_at) FROM price.published_file WHERE facility_id = f.id),
                   ST_Y(f.geom::geometry)::text, ST_X(f.geom::geometry)::text
            FROM ref.facility f
            WHERE f.id = :f AND f.status = 'active'
            """
        ),
        {"f": fid},
    ).first()
    if row is None:
        raise SearchError("unknown facility")
    return FacilityDetail(
        facility_id=str(row[0]),
        name=str(row[1]),
        address=row[2],
        city=row[3],
        state_code=str(row[4]),
        zip5=row[5],
        phone=row[6],
        website=row[7],
        emergency_services=row[8],
        cms_rating=row[9],
        cms_rating_as_of=None if row[10] is None else row[10].isoformat(),
        provider_types=tuple(row[11]),
        prices_published_at=None if row[12] is None else row[12].isoformat(),
        lat=row[13],
        lng=row[14],
    )


def facility_prices(
    conn: Connection, store: ObjectStore, facility_id: str, service_slug: str
) -> FacilityPrices:
    """Every published price at one facility under the service's approved codes."""
    detail = facility_detail(conn, facility_id)
    name, unit, codes = _codes_for_service(conn, service_slug)
    prices: list[PublishedPrice] = []
    if detail.prices_published_at is not None:
        for system, value in codes:
            prices.extend(find_prices(conn, store, [detail.facility_id], system, value))
    return FacilityPrices(
        facility_id=detail.facility_id,
        service_slug=service_slug,
        service_name=name,
        unit=unit or "",
        codes=tuple(f"{s} {c}" for s, c in codes),
        published_at=detail.prices_published_at,
        prices=tuple(prices),
    )
