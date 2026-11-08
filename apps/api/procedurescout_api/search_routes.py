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
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import Engine

from procedurescout_core.object_store import LocalStore, ObjectStore
from procedurescout_core.plans import list_plans
from procedurescout_core.search import SearchError, search, suggest

from .settings import get_settings

router = APIRouter(prefix="/v1", tags=["search"])
_engine: Engine | None = None


def get_conn() -> Iterator[Connection]:
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().api_database_url)
    with _engine.connect() as conn:
        yield conn


def get_store() -> ObjectStore:
    return LocalStore(Path(get_settings().price_store_dir))


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
    prices: list[Price]


class TypicalOut(BaseModel):
    low: str
    middle: str
    high: str
    count: int


class SearchOut(BaseModel):
    service: str | None
    service_name: str | None
    unit: str | None
    codes: list[str]
    note: str | None
    mode: str
    typical: TypicalOut | None
    facilities: list[FacilityOut]


class SuggestionOut(BaseModel):
    slug: str
    name: str
    unit: str
    matched: str


@router.get("/services/suggest", response_model=list[SuggestionOut])
def services_suggest(
    conn: Conn, q: Annotated[str, Query(min_length=1, max_length=60)]
) -> list[SuggestionOut]:
    """Search-box suggestions from service names and approved everyday words."""
    return [
        SuggestionOut(slug=s.slug, name=s.name, unit=s.unit, matched=s.matched)
        for s in suggest(conn, q)
    ]


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
            "SELECT code, name FROM ref.provider_type WHERE review_state = 'approved' ORDER BY name"
        )
    ).all()
    return [ProviderType(code=r[0], name=r[1]) for r in rows]


@router.get("/search", response_model=SearchOut)
def search_endpoint(
    conn: Conn,
    store: Store,
    lat: Annotated[Decimal, Query(ge=-90, le=90)],
    lng: Annotated[Decimal, Query(ge=-180, le=180)],
    radius_miles: Annotated[Decimal, Query(ge=1, le=100)] = Decimal(25),
    service: Annotated[str | None, Query(max_length=80)] = None,
    code_system: Annotated[str | None, Query(max_length=20)] = None,
    code: Annotated[str | None, Query(max_length=20)] = None,
    provider_type: Annotated[str | None, Query(max_length=40)] = None,
    mode: Annotated[str, Query(pattern="^(cash|list|plan)$")] = "cash",
    plan_id: Annotated[str | None, Query(max_length=36)] = None,
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
        )
    except SearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SearchOut(
        service=result.service_slug,
        service_name=result.service_name,
        unit=result.unit,
        codes=list(result.codes),
        note=result.note,
        mode=result.mode,
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
                prices=[
                    Price(
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
                    for p in f.prices
                ],
            )
            for f in result.facilities
        ],
    )
