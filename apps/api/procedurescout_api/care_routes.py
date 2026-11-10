"""Bundles and financial assistance endpoints (BUN-01, FA-01, FA-02).

GET  /v1/assistance/message          the site-wide "you may qualify" message (dollars by state)
GET  /v1/facilities/{id}/assistance  one hospital's help limits in dollars
POST /v1/assistance/check            what a household may qualify for at chosen hospitals
                                     (POST so income never appears in a URL or log)
GET  /v1/bundles                     approved bundles and their pieces
GET  /v1/facilities/{id}/plans       insurance plans a facility publishes prices for
POST /v1/bundles/{slug}/estimate     a bundle priced at one facility
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from procedurescout_core import assistance, bundles
from procedurescout_core.price_store import facility_payer_plans

from .search_routes import Conn, Store

router = APIRouter(prefix="/v1", tags=["bundles and assistance"])


def _s(value: Decimal | None) -> str | None:
    return None if value is None else format(value.normalize(), "f")


class Message(BaseModel):
    message: str
    detail: str


@router.get("/assistance/message", response_model=Message)
def assistance_message(
    conn: Conn, state: Annotated[str | None, Query(min_length=2, max_length=2)] = None
) -> Message:
    """The banner for every page; with a state, in dollars from that state's
    reviewed hospital policies (never poverty-level percentages)."""
    message = assistance.SITE_MESSAGE
    if state is not None and state.isalpha():
        try:
            message = assistance.site_message(conn, state)
        except assistance.AssistanceError:
            message = assistance.SITE_MESSAGE
    return Message(message=message, detail=assistance.SITE_MESSAGE_DETAIL)


class FacilityMessage(BaseModel):
    facility_id: str
    message: str


@router.get("/facilities/{facility_id}/assistance", response_model=FacilityMessage)
def facility_assistance(
    facility_id: Annotated[str, Path(max_length=36)],
    conn: Conn,
    state: Annotated[str, Query(min_length=2, max_length=2)] = "US",
) -> FacilityMessage:
    try:
        message = assistance.facility_policy(conn, facility_id, state)
    except (assistance.AssistanceError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FacilityMessage(facility_id=facility_id, message=message)


class CheckIn(BaseModel):
    facility_ids: list[str] = Field(min_length=1, max_length=50)
    household_size: int = Field(ge=1, le=20)
    annual_income: Decimal = Field(ge=0, le=100_000_000)
    state: str = Field(min_length=2, max_length=2)


class TierOut(BaseModel):
    benefit: str
    up_to_percent_of_poverty_guideline: str
    discount_percent: str | None
    description: str | None


class FacilityAssistanceOut(BaseModel):
    facility_id: str
    name: str
    status: str
    best: TierOut | None
    policy_url: str | None
    application_url: str | None
    phone: str | None
    message: str


class CoverageOut(BaseModel):
    program: str
    group: str
    label: str
    limit: str
    apply_url: str
    source_url: str


class CheckOut(BaseModel):
    coverage: list[CoverageOut] = []
    message: str
    guideline_year: int
    guideline_amount: str
    income_percent_of_guideline: str
    facilities: list[FacilityAssistanceOut]
    reminder: str


def _tier(t: assistance.Tier | None) -> TierOut | None:
    if t is None:
        return None
    return TierOut(
        benefit=t.benefit,
        up_to_percent_of_poverty_guideline=format(t.max_percent_fpg.normalize(), "f"),
        discount_percent=_s(t.discount_percent),
        description=t.description,
    )


@router.post("/assistance/check", response_model=CheckOut)
def assistance_check(body: CheckIn, conn: Conn) -> CheckOut:
    try:
        result = assistance.check(
            conn,
            facility_ids=body.facility_ids,
            household_size=body.household_size,
            annual_income=body.annual_income,
            state_code=body.state.upper(),
        )
    except assistance.AssistanceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        matches = assistance.coverage(
            conn,
            state_code=body.state.upper(),
            household_size=body.household_size,
            annual_income=body.annual_income,
        )
    except assistance.AssistanceError:
        matches = []
    return CheckOut(
        coverage=[
            CoverageOut(
                program=m.program,
                group=m.group,
                label=m.label,
                limit=m.limit_text,
                apply_url=m.apply_url,
                source_url=m.source_url,
            )
            for m in matches
        ],
        message=result.message,
        guideline_year=result.guideline_year,
        guideline_amount=format(result.guideline_amount, "f"),
        income_percent_of_guideline=format(result.percent_of_guideline, "f"),
        facilities=[
            FacilityAssistanceOut(
                facility_id=f.facility_id,
                name=f.name,
                status=f.status,
                best=_tier(f.best_tier),
                policy_url=f.policy_url,
                application_url=f.application_url,
                phone=f.phone,
                message=f.plain_message,
            )
            for f in result.facilities
        ],
        reminder="Only the hospital can confirm what you will receive. Apply even if unsure.",
    )


class ComponentOut(BaseModel):
    component_id: str
    label: str
    role: str
    requirement: str
    included_by_default: bool
    code: str
    notes: str | None


class BundleOut(BaseModel):
    slug: str
    name: str
    components: list[ComponentOut]


@router.get("/bundles", response_model=list[BundleOut])
def list_bundles(conn: Conn) -> list[BundleOut]:
    slugs = (
        conn.execute(
            text(
                "SELECT slug FROM ref.procedure "
                "WHERE kind = 'bundle' AND review_state = 'approved' "
                "ORDER BY category, consumer_name"
            )
        )
        .scalars()
        .all()
    )
    out = []
    for slug in slugs:
        name, comps = bundles.bundle_components(conn, str(slug))
        out.append(
            BundleOut(
                slug=str(slug),
                name=name,
                components=[
                    ComponentOut(
                        component_id=c.component_id,
                        label=c.label,
                        role=c.role,
                        requirement=c.requirement,
                        included_by_default=c.included_by_default,
                        code=f"{c.code_system} {c.code}",
                        notes=c.notes,
                    )
                    for c in comps
                ],
            )
        )
    return out


class PlanOut(BaseModel):
    payer: str
    plan: str


@router.get("/facilities/{facility_id}/plans", response_model=list[PlanOut])
def plans(
    facility_id: Annotated[str, Path(max_length=36)], conn: Conn, store: Store
) -> list[PlanOut]:
    try:
        rows = facility_payer_plans(conn, store, facility_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="not a facility id") from exc
    return [PlanOut(payer=p, plan=q) for p, q in rows]


class EstimateIn(BaseModel):
    facility_id: str
    payment: str = Field(pattern="^(cash|list|insurance)$")
    payer: str | None = Field(default=None, max_length=300)
    plan: str | None = Field(default=None, max_length=300)
    include_optional: list[str] | None = Field(default=None, max_length=50)


class LineOut(BaseModel):
    component_id: str
    label: str
    role: str
    requirement: str
    included: bool
    status: str
    amount: str | None
    amounts_published: list[str]
    rate: str | None
    notes: str | None


class EstimateOut(BaseModel):
    bundle: str
    name: str
    facility_id: str
    payment: str
    payer: str | None
    plan: str | None
    lines: list[LineOut]
    total_of_priced_pieces: str | None
    complete: bool
    explanation: str


@router.post("/bundles/{slug}/estimate", response_model=EstimateOut)
def bundle_estimate(
    slug: Annotated[str, Path(max_length=80)], body: EstimateIn, conn: Conn, store: Store
) -> EstimateOut:
    try:
        est = bundles.estimate(
            conn,
            store,
            bundle_slug=slug,
            facility_id=body.facility_id,
            mode=body.payment,
            include_optional=body.include_optional,
            payer=body.payer,
            plan=body.plan,
        )
    except bundles.BundleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    explanation = (
        "Every included piece has a published price."
        if est.complete
        else "Some included pieces have no published dollar price here (often doctors' or "
        "anesthesia fees billed separately); the total covers only the priced pieces."
    )
    return EstimateOut(
        bundle=est.bundle_slug,
        name=est.bundle_name,
        facility_id=est.facility_id,
        payment=est.mode,
        payer=est.payer,
        plan=est.plan,
        lines=[
            LineOut(
                component_id=ln.component.component_id,
                label=ln.component.label,
                role=ln.component.role,
                requirement=ln.component.requirement,
                included=ln.included,
                status=ln.status,
                amount=_s(ln.amount),
                amounts_published=[format(a.normalize(), "f") for a in ln.other_amounts],
                rate=ln.rate_text,
                notes=ln.component.notes,
            )
            for ln in est.lines
        ],
        total_of_priced_pieces=_s(est.total_of_priced),
        complete=est.complete,
        explanation=explanation,
    )


class HealthCenterOut(BaseModel):
    name: str
    organization: str | None
    address: str | None
    city: str | None
    state: str
    zip: str | None
    phone: str | None
    website: str | None
    distance_miles: str


@router.get("/health-centers/near", response_model=list[HealthCenterOut])
def health_centers_near(
    conn: Conn,
    lat: Annotated[Decimal, Query(ge=-90, le=90)],
    lng: Annotated[Decimal, Query(ge=-180, le=180)],
    radius_miles: Annotated[Decimal, Query(ge=1, le=100)] = Decimal(25),
) -> list[HealthCenterOut]:
    """Community health centers (HRSA) near a place; they charge by income."""
    try:
        rows = assistance.health_centers_near(
            conn, latitude=lat, longitude=lng, radius_miles=radius_miles
        )
    except assistance.AssistanceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [
        HealthCenterOut(
            name=h.name,
            organization=h.organization,
            address=h.address,
            city=h.city,
            state=h.state_code,
            zip=h.zip5,
            phone=h.phone,
            website=h.website,
            distance_miles=format(h.distance_miles, "f"),
        )
        for h in rows
    ]
