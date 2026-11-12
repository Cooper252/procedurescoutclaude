"""Public search endpoints (SRCH-06).

GET /v1/services          approved services for the home search box
GET /v1/provider-types    approved provider types for the filter
GET /v1/search            published prices for one service (or code) near a place

Amounts are returned as strings so no client turns them into floating point.
Every price carries its source, the code it was published under and the
publish date of its file.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi import Path as PathParam
from pydantic import BaseModel
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import Engine

from procedurescout_core.db_url import sqlalchemy_url
from procedurescout_core.facilities import facility_detail, facility_prices
from procedurescout_core.object_store import ObjectStore, open_store
from procedurescout_core.places import City, PlaceError, cities, city
from procedurescout_core.plans import list_plans, matches
from procedurescout_core.price_store import PriceQueryError, PublishedPrice
from procedurescout_core.search import (
    SearchError,
    SearchResult,
    nearby,
    payer_suggestions,
    search,
    suggest,
)

from .settings import get_settings

router = APIRouter(prefix="/v1", tags=["search"])
_engine: Engine | None = None


def get_conn() -> Iterator[Connection]:
    global _engine
    if _engine is None:
        # 2026-11-12: crawlers on the city pages used up the default 5 + 10
        # connections; waiting callers now fail fast instead of hanging 30 s.
        _engine = create_engine(
            sqlalchemy_url(get_settings().api_database_url),
            pool_size=10,
            max_overflow=15,
            pool_timeout=10,
            pool_pre_ping=True,
        )
    with _engine.connect() as conn:
        yield conn


def get_store() -> ObjectStore:
    return open_store(*get_settings().store_args())


Conn = Annotated[Connection, Depends(get_conn)]
Store = Annotated[ObjectStore, Depends(get_store)]


class Service(BaseModel):
    slug: str
    name: str
    category: str | None
    unit: str


class ProviderType(BaseModel):
    code: str
    name: str
    grouping: str | None = None
    referral: str | None = None  # 'hmo' or 'none' (0022)


class Price(BaseModel):
    price_source: str
    code: str
    description: str | None
    setting: str | None
    price_type: str
    payer: str | None
    plan: str | None
    amount: str | None
    percentage: str | None
    algorithm: str | None
    methodology: str | None
    plan_match: str | None = None  # "plan" or "all_plans" (insurer's one rate for all plans)


class SpecialOut(BaseModel):
    """A provider special on its own regular price; never used in comparisons."""

    price: str
    regular: str
    who: str
    kind: str
    percent_off: str | None
    ends_on: str | None
    terms: str | None


class FacilityOut(BaseModel):
    facility_id: str
    name: str
    city: str | None
    state: str
    distance_miles: str
    provider_types: list[str]
    status: str
    prices_published_at: str | None
    headline: str | None
    headline_highest: str | None
    headline_price_type: str | None
    headline_possible_error: bool
    lowest_near_you: bool
    below_typical: bool
    cash_cheaper_than_plan: bool
    badge_notes: list[str]
    change_percent_since_last_file: str | None
    plan_rate_is_all_plans: bool = False
    special: SpecialOut | None = None
    delivery: str | None = None  # provider price: in_person, online or both
    rating_average: str | None = None  # patient reviews (D-050), never affects order
    rating_count: int = 0
    prices: list[Price]


class TypicalOut(BaseModel):
    low: str
    middle: str
    high: str
    count: int


class SponsoredOut(BaseModel):
    """A paid "Sponsored" spot (D-051). Shown apart from the results and labeled;
    never changes their order or labels (PRV-06)."""

    facility_id: str
    name: str
    city: str | None
    state: str


class SearchOut(BaseModel):
    service: str | None
    service_name: str | None
    unit: str | None
    codes: list[str]
    note: str | None
    mode: str
    code_description: str | None = None
    typical: TypicalOut | None
    facilities: list[FacilityOut]
    sponsored: list[SponsoredOut] = []


class SuggestionOut(BaseModel):
    slug: str
    name: str
    unit: str
    matched: str
    kind: str = "service"
    code_system: str | None = None
    code: str | None = None


@router.get("/services/suggest", response_model=list[SuggestionOut])
def services_suggest(
    conn: Conn, q: Annotated[str, Query(min_length=1, max_length=60)]
) -> list[SuggestionOut]:
    """Search-box suggestions from service names and approved everyday words."""
    return [
        SuggestionOut(
            slug=s.slug,
            name=s.name,
            unit=s.unit,
            matched=s.matched,
            kind=s.kind,
            code_system=s.code_system,
            code=s.code,
        )
        for s in suggest(conn, q)
    ]


class PlaceOut(BaseModel):
    zip: str
    state: str
    lat: str
    lng: str


@router.get("/places/zip/{zip5}", response_model=PlaceOut)
def place_for_zip(zip5: Annotated[str, PathParam(pattern="^[0-9]{5}$")], conn: Conn) -> PlaceOut:
    """The center of a ZIP code area (Census ZCTA), so people can search by ZIP."""
    row = conn.execute(
        text(
            "SELECT zcta5, state_code, ST_Y(geom::geometry)::text, ST_X(geom::geometry)::text "
            "FROM ref.zcta WHERE zcta5 = :z"
        ),
        {"z": zip5},
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="ZIP code not found")
    return PlaceOut(zip=row[0], state=row[1], lat=row[2], lng=row[3])


class NearbyOut(BaseModel):
    facility_id: str
    name: str
    city: str | None
    state: str
    distance_miles: str
    provider_types: list[str]


@router.get("/facilities/near", response_model=list[NearbyOut])
def facilities_near(
    conn: Conn,
    lat: Annotated[Decimal, Query(ge=-90, le=90)],
    lng: Annotated[Decimal, Query(ge=-180, le=180)],
    radius_miles: Annotated[Decimal, Query(ge=1, le=100)] = Decimal(25),
    provider_type: Annotated[str | None, Query(max_length=40)] = None,
) -> list[NearbyOut]:
    """Facilities near a place, nearest first (no prices), for the help-paying check."""
    try:
        rows = nearby(
            conn,
            latitude=lat,
            longitude=lng,
            radius_miles=radius_miles,
            provider_type=provider_type,
        )
    except SearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [
        NearbyOut(
            facility_id=n.facility_id,
            name=n.name,
            city=n.city,
            state=n.state_code,
            distance_miles=format(n.distance_miles, "f"),
            provider_types=list(n.provider_types),
        )
        for n in rows
    ]


class CityOut(BaseModel):
    state: str
    city: str
    slug: str
    lat: str
    lng: str
    facilities: int


def _city(c: City) -> CityOut:
    return CityOut(
        state=c.state_code, city=c.name, slug=c.slug, lat=c.lat, lng=c.lng, facilities=c.facilities
    )


@router.get("/places/cities", response_model=list[CityOut])
def places_cities(
    conn: Conn, state: Annotated[str, Query(min_length=2, max_length=2)]
) -> list[CityOut]:
    """Cities in a state that have facilities (for service-by-city pages)."""
    try:
        return [_city(c) for c in cities(conn, state)]
    except PlaceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/places/city/{state}/{slug}", response_model=CityOut)
def places_city(
    conn: Conn,
    state: Annotated[str, PathParam(min_length=2, max_length=2)],
    slug: Annotated[str, PathParam(max_length=80)],
) -> CityOut:
    try:
        return _city(city(conn, state, slug))
    except PlaceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class PlanOut(BaseModel):
    plan_id: str
    payer: str
    plan: str
    product_type: str
    segment: str


@router.get("/plans", response_model=list[PlanOut])
def plans(conn: Conn) -> list[PlanOut]:
    """Plans by the names on people's cards that have approved hospital spellings."""
    return [
        PlanOut(
            plan_id=p.plan_id,
            payer=p.payer,
            plan=p.plan,
            product_type=p.product_type,
            segment=p.segment,
        )
        for p in list_plans(conn)
    ]


def _price(p: PublishedPrice) -> Price:
    return Price(
        price_source=p.price_source,
        code=f"{p.code_system} {p.code}",
        description=p.description_raw,
        setting=p.setting,
        price_type=p.price_type,
        payer=p.payer_name_raw,
        plan=p.plan_name_raw,
        amount=_s(p.amount),
        percentage=_s(p.percentage),
        algorithm=p.algorithm,
        methodology=p.methodology,
    )


def _plan_match(out: Price, p: PublishedPrice, result: SearchResult) -> Price:
    if result.mode == "plan" and p.price_type == "negotiated":
        out.plan_match = "all_plans" if matches(p, set(result.all_plans_spellings)) else "plan"
    return out


def _s(value: Decimal | None) -> str | None:
    """Exact value as a plain string, without padding zeros ("100.1", not 100.100000...)."""
    return None if value is None else format(value.normalize(), "f")


@router.get("/services", response_model=list[Service])
def services(conn: Conn) -> list[Service]:
    rows = conn.execute(
        text(
            "SELECT slug, consumer_name, category, unit FROM ref.procedure "
            "WHERE review_state = 'approved' AND kind = 'service' ORDER BY category, consumer_name"
        )
    ).all()
    return [Service(slug=r[0], name=r[1], category=r[2], unit=r[3]) for r in rows]


@router.get("/provider-types", response_model=list[ProviderType])
def provider_types(conn: Conn) -> list[ProviderType]:
    rows = conn.execute(
        text(
            "SELECT code, name, grouping, referral FROM ref.provider_type "
            "WHERE review_state = 'approved' ORDER BY grouping NULLS LAST, name"
        )
    ).all()
    return [ProviderType(code=r[0], name=r[1], grouping=r[2], referral=r[3]) for r in rows]


@router.get("/search", response_model=SearchOut)
def search_endpoint(
    conn: Conn,
    store: Store,
    request: Request,
    background: BackgroundTasks,
    lat: Annotated[Decimal, Query(ge=-90, le=90)],
    lng: Annotated[Decimal, Query(ge=-180, le=180)],
    radius_miles: Annotated[Decimal, Query(ge=1, le=100)] = Decimal(25),
    service: Annotated[str | None, Query(max_length=80)] = None,
    code_system: Annotated[str | None, Query(max_length=20)] = None,
    code: Annotated[str | None, Query(max_length=20)] = None,
    provider_type: Annotated[str | None, Query(max_length=40)] = None,
    mode: Annotated[str, Query(pattern="^(cash|list|plan)$")] = "cash",
    plan_id: Annotated[str | None, Query(max_length=36)] = None,
    payer: Annotated[str | None, Query(max_length=200)] = None,
    online: bool = False,
) -> SearchOut:
    try:
        result = search(
            conn,
            store,
            latitude=lat,
            longitude=lng,
            radius_miles=radius_miles,
            service_slug=service,
            code_system=code_system,
            code=code,
            provider_type=provider_type,
            mode=mode,
            plan_id=plan_id,
            payer_raw=payer,
            online_only=online,
        )
    except SearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    from procedurescout_core.provider_stats import service_key

    from .portal_routes import count_search

    ids = [f.facility_id for f in result.facilities]
    ratings = {
        str(r[0]): (format(r[1], "f"), int(r[2]))
        for r in (
            conn.execute(
                text(
                    "SELECT facility_id, round(avg(rating), 1), count(*) "
                    "FROM prov.published_review "
                    "WHERE facility_id = ANY(CAST(:ids AS uuid[])) GROUP BY facility_id"
                ),
                {"ids": ids},
            ).all()
            if ids
            else []
        )
    }
    key = service_key(result.service_slug, code_system, code)
    sponsored = (
        [
            SponsoredOut(facility_id=str(r[0]), name=r[1], city=r[2], state=r[3])
            for r in conn.execute(
                text(
                    "SELECT f.id, f.name, f.city, f.state_code "
                    "FROM bill.sponsored_for(:k, :lat, :lng) s "
                    "JOIN ref.facility f ON f.id = s.facility_id ORDER BY random()"
                ),
                {"k": key, "lat": lat, "lng": lng},
            ).all()
        ]
        if key
        else []
    )
    background.add_task(
        count_search,
        key,
        lat,
        lng,
        [f.facility_id for f in result.facilities],
        request.headers.get("user-agent", ""),
    )
    return SearchOut(
        service=result.service_slug,
        service_name=result.service_name,
        unit=result.unit,
        codes=list(result.codes),
        note=result.note,
        mode=result.mode,
        code_description=result.code_description,
        typical=None
        if result.typical is None
        else TypicalOut(
            low=_s(result.typical.low) or "",
            middle=_s(result.typical.middle) or "",
            high=_s(result.typical.high) or "",
            count=result.typical.count,
        ),
        facilities=[
            FacilityOut(
                facility_id=f.facility_id,
                name=f.name,
                city=f.city,
                state=f.state_code,
                distance_miles=format(f.distance_miles, "f"),
                provider_types=list(f.provider_types),
                status=f.status,
                prices_published_at=f.published_at,
                headline=_s(f.headline.amount) if f.headline else None,
                headline_highest=_s(f.headline.highest) if f.headline else None,
                headline_price_type=f.headline.price_type if f.headline else None,
                headline_possible_error=bool(f.headline and f.headline.possible_error),
                lowest_near_you=f.badges.lowest_near_you,
                below_typical=f.badges.below_typical,
                cash_cheaper_than_plan=f.badges.cash_cheaper_than_plan,
                badge_notes=list(f.badges.notes),
                change_percent_since_last_file=None
                if f.change_percent is None
                else format(f.change_percent, "f"),
                plan_rate_is_all_plans=f.all_plans_rate,
                rating_average=ratings.get(f.facility_id, (None, 0))[0],
                rating_count=ratings.get(f.facility_id, (None, 0))[1],
                special=None
                if f.special is None
                else SpecialOut(
                    price=_s(f.special.price) or "",
                    regular=_s(f.special.regular) or "",
                    who=f.special.who,
                    kind=f.special.kind,
                    percent_off=_s(f.special.percent_off),
                    ends_on=None if f.special.ends_on is None else f.special.ends_on.isoformat(),
                    terms=f.special.terms,
                ),
                prices=[_plan_match(_price(p), p, result) for p in f.prices],
                delivery=f.delivery,
            )
            for f in result.facilities
        ],
        sponsored=sponsored,
    )


class FacilityDetailOut(BaseModel):
    facility_id: str
    name: str
    address: str | None
    city: str | None
    state: str
    zip: str | None
    phone: str | None
    website: str | None
    emergency_services: bool | None
    cms_rating: int | None
    cms_rating_as_of: str | None
    provider_types: list[str]
    prices_published_at: str | None
    lat: str | None
    lng: str | None


@router.get("/facilities/{facility_id}", response_model=FacilityDetailOut)
def facility(
    facility_id: Annotated[str, PathParam(max_length=36)], conn: Conn
) -> FacilityDetailOut:
    """One facility's public details (website only when a person reviewed it)."""
    try:
        d = facility_detail(conn, facility_id)
    except SearchError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FacilityDetailOut(
        facility_id=d.facility_id,
        name=d.name,
        address=d.address,
        city=d.city,
        state=d.state_code,
        zip=d.zip5,
        phone=d.phone,
        website=d.website,
        emergency_services=d.emergency_services,
        cms_rating=d.cms_rating,
        cms_rating_as_of=d.cms_rating_as_of,
        provider_types=list(d.provider_types),
        prices_published_at=d.prices_published_at,
        lat=d.lat,
        lng=d.lng,
    )


class FacilityPricesOut(BaseModel):
    facility_id: str
    service: str
    service_name: str
    unit: str
    codes: list[str]
    prices_published_at: str | None
    prices: list[Price]


@router.get("/facilities/{facility_id}/prices", response_model=FacilityPricesOut)
def facility_service_prices(
    facility_id: Annotated[str, PathParam(max_length=36)],
    conn: Conn,
    store: Store,
    service: Annotated[str, Query(max_length=80)],
) -> FacilityPricesOut:
    """Every published price at one facility for one approved service."""
    try:
        r = facility_prices(conn, store, facility_id, service)
    except (SearchError, PriceQueryError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FacilityPricesOut(
        facility_id=r.facility_id,
        service=r.service_slug,
        service_name=r.service_name,
        unit=r.unit,
        codes=list(r.codes),
        prices_published_at=r.published_at,
        prices=[_price(p) for p in r.prices],
    )


class PayerNameOut(BaseModel):
    name: str
    facilities: int


@router.get("/payers/suggest", response_model=list[PayerNameOut])
def payers_suggest(
    conn: Conn, q: Annotated[str, Query(min_length=2, max_length=60)]
) -> list[PayerNameOut]:
    """Insurer names exactly as hospitals wrote them, for people whose plan is not
    in the card-name list yet (D-046)."""
    return [PayerNameOut(name=n, facilities=f) for n, f in payer_suggestions(conn, q)]
