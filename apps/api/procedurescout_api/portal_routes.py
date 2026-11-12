"""Provider homepages, reviews, counts and the provider portal (D-050).

Public reads (homepage, reviews, images) use the public API role, which sees
only published views. Everything that writes (sign-in, edits, reviews, counts)
uses the portal role (PORTAL_DATABASE_URL); without it those routes answer 404
and counting is skipped.

Portal sessions are an HttpOnly cookie. Every portal change must carry the
header `X-ProcedureScout: 1`, which other sites cannot add (no CORS), so a
form on another site can't act for a signed-in provider.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi import Path as PathParam
from pydantic import BaseModel, Field
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import Engine

from procedurescout_core import portal_auth as auth
from procedurescout_core import price_templates as templates
from procedurescout_core import provider_pages as pages
from procedurescout_core import provider_prices as prices
from procedurescout_core import provider_stats as stats
from procedurescout_core import reviews
from procedurescout_core.db_url import sqlalchemy_url

from .search_routes import Conn, Store
from .settings import get_settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["providers"])
COOKIE = "ps_session"
_engine: Engine | None = None
_UUID = "^[0-9a-fA-F-]{36}$"
_BOT = re.compile(r"bot|crawl|spider|slurp|preview|monitor|curl|wget|python", re.I)


def portal_engine() -> Engine | None:
    global _engine
    url = get_settings().portal_database_url
    if not url:
        return None
    if _engine is None:
        _engine = create_engine(sqlalchemy_url(url), pool_pre_ping=True)
    return _engine


def get_portal_conn() -> Iterator[Connection]:
    engine = portal_engine()
    if engine is None:
        raise HTTPException(status_code=404, detail="The provider portal is not turned on.")
    with engine.begin() as conn:
        yield conn


PortalConn = Annotated[Connection, Depends(get_portal_conn)]


def require_header(x_procedurescout: Annotated[str | None, Header()] = None) -> None:
    if x_procedurescout != "1":
        raise HTTPException(status_code=403, detail="Missing request header.")


Guard = Annotated[None, Depends(require_header)]


def current(request: Request, conn: PortalConn) -> auth.Account:
    account = auth.session_account(conn, request.cookies.get(COOKIE))
    if account is None:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return account


Me = Annotated[auth.Account, Depends(current)]


def _role(conn: Connection, account: auth.Account, fid: str, roles: tuple[str, ...]) -> None:
    try:
        auth.require_role(conn, account, fid, roles)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


EDIT = ("owner", "editor")
VIEW = ("owner", "editor", "viewer")


def _secret() -> str:
    s = get_settings().portal_secret
    if len(s) < 16:
        raise HTTPException(status_code=503, detail="Reviews are not turned on yet.")
    return s


# ======================================================== public: homepage
class ProfileOut(BaseModel):
    about: str | None
    website_url: str | None
    booking_url: str | None
    phone: str | None
    hours: dict[str, str]
    languages: list[str]
    accessibility: list[str]
    insurance_note: str | None
    social_urls: list[str]
    updated_at: str | None


class ReviewOut(BaseModel):
    id: str
    rating: int
    title: str | None
    body: str
    price_matched: bool | None
    display_name: str
    verification: str
    published_at: str
    reply_body: str | None
    reply_at: str | None


class ReviewSummaryOut(BaseModel):
    average: str | None
    count: int
    removed: int
    price_matched_yes: int
    price_matched_answered: int
    stars: list[int]


class PageOut(BaseModel):
    facility_id: str
    claimed: bool
    profile: ProfileOut | None
    logo_url: str | None
    photos: list[dict[str, str | None]]
    reviews: ReviewSummaryOut
    latest_reviews: list[ReviewOut]
    reviews_enabled: bool


def _media_url(key: str) -> str:
    return f"/api/v1/media/{key}"


def _review(r: reviews.ReviewOut) -> ReviewOut:
    return ReviewOut(**{f: getattr(r, f) for f in ReviewOut.model_fields})


@router.get("/facilities/{facility_id}/page", response_model=PageOut)
def facility_page(facility_id: Annotated[str, PathParam(pattern=_UUID)], conn: Conn) -> PageOut:
    """A provider's homepage: published profile, logo, photos and reviews."""
    exists = conn.execute(
        text("SELECT 1 FROM ref.facility WHERE id = CAST(:f AS uuid)"), {"f": facility_id}
    ).first()
    if exists is None:
        raise HTTPException(status_code=404, detail="Unknown provider.")
    page = pages.public_page(conn, facility_id)
    s = reviews.summary(conn, facility_id)
    p = page.profile
    return PageOut(
        facility_id=facility_id,
        claimed=page.claimed,
        profile=None
        if p is None
        else ProfileOut(
            about=p.about,
            website_url=p.website_url,
            booking_url=p.booking_url,
            phone=p.phone,
            hours=p.hours,
            languages=list(p.languages),
            accessibility=list(p.accessibility),
            insurance_note=p.insurance_note,
            social_urls=list(p.social_urls),
            updated_at=page.profile_updated_at,
        ),
        logo_url=_media_url(page.logo_key) if page.logo_key else None,
        photos=[{"url": _media_url(k), "alt": alt} for k, alt in page.photos],
        reviews=ReviewSummaryOut(
            average=None if s.average is None else str(s.average),
            count=s.count,
            removed=s.removed,
            price_matched_yes=s.price_matched_yes,
            price_matched_answered=s.price_matched_answered,
            stars=list(s.stars),
        ),
        latest_reviews=[_review(r) for r in reviews.published(conn, facility_id, 10)],
        reviews_enabled=portal_engine() is not None and len(get_settings().portal_secret) >= 16,
    )


@router.get("/facilities/{facility_id}/reviews", response_model=list[ReviewOut])
def facility_reviews(
    facility_id: Annotated[str, PathParam(pattern=_UUID)],
    conn: Conn,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> list[ReviewOut]:
    return [_review(r) for r in reviews.published(conn, facility_id, 20, offset)]


@router.get("/media/{key:path}")
def media(key: str, conn: Conn, store: Store) -> Response:
    """A reviewed, published logo or photo."""
    if not re.fullmatch(r"media/[0-9a-f-]{36}/[0-9a-f-]{36}\.(png|jpg|webp)", key):
        raise HTTPException(status_code=404)
    content_type = pages.media_is_published(conn, key)
    data = store.get_media(key) if content_type else None
    if data is None or content_type is None:
        raise HTTPException(status_code=404)
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
        },
    )


# ============================================================ public: counts
class EventIn(BaseModel):
    facility_id: str = Field(pattern=_UUID)
    kind: str = Field(
        pattern="^(page_view|website_click|phone_click|directions_click|booking_click)$"
    )


@router.post("/events", status_code=204)
def event(body: EventIn, request: Request) -> Response:
    """Count a page view or click. Stores only today's total for the facility."""
    engine = portal_engine()
    ua = request.headers.get("user-agent", "")
    if engine is None or not ua or _BOT.search(ua) or request.headers.get("dnt") == "1":
        return Response(status_code=204)
    try:
        with engine.begin() as conn:
            stats.record_event(conn, body.facility_id, body.kind)
    except Exception:  # counting must never break the page
        log.exception("could not count an event")
    return Response(status_code=204)


def count_search(
    key: str | None, lat: Decimal, lng: Decimal, shown: list[str], user_agent: str
) -> None:
    """Called after a search answers (background); never raises."""
    engine = portal_engine()
    if engine is None or key is None or not user_agent or _BOT.search(user_agent):
        return
    try:
        with engine.begin() as conn:
            stats.record_search(conn, key, lat, lng, shown)
    except Exception:
        log.exception("could not count a search")


def send_mail_soon() -> None:
    """Send waiting emails right after a request (background); never raises.
    The `send-email` command retries anything left over."""
    engine = portal_engine()
    sender = get_settings().mail_sender()
    if engine is None or sender is None:
        return
    from procedurescout_core.mailer import send_pending

    try:
        with engine.begin() as conn:
            send_pending(conn, sender, limit=10)
    except Exception:
        log.exception("could not send email")


# =========================================================== public: reviews
class ReviewRequestIn(BaseModel):
    facility_id: str = Field(pattern=_UUID)
    email: str = Field(max_length=254)


class LinkOut(BaseModel):
    ok: bool
    dev_link: str | None = None


@router.post("/reviews/request", response_model=LinkOut, status_code=202)
def review_request(body: ReviewRequestIn, conn: PortalConn, background: BackgroundTasks) -> LinkOut:
    """Email a 'Did you visit?' link. The answer is the same whether or not an
    email was queued."""
    settings = get_settings()
    try:
        token = reviews.start_email_review(
            conn, body.facility_id, body.email, settings.site_url, _secret()
        )
    except reviews.ReviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    dev = f"{settings.site_url}/review#{token}" if token and settings.show_dev_links else None
    if token:
        background.add_task(send_mail_soon)
    return LinkOut(ok=True, dev_link=dev)


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=100)


class TokenInfoOut(BaseModel):
    facility_id: str
    facility_name: str
    kind: str


@router.post("/reviews/check", response_model=TokenInfoOut)
def review_check(body: TokenIn, conn: PortalConn) -> TokenInfoOut:
    try:
        fid, name, kind = reviews.token_facility(conn, body.token)
    except reviews.ReviewError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    return TokenInfoOut(facility_id=fid, facility_name=name, kind=kind)


class ReviewIn(BaseModel):
    token: str = Field(min_length=20, max_length=100)
    rating: int = Field(ge=1, le=5)
    title: str | None = Field(default=None, max_length=120)
    body: str = Field(max_length=3000)
    price_matched: bool | None = None
    display_name: str = Field(max_length=40)
    visited: bool
    independent: bool


@router.post("/reviews", status_code=201)
def review_submit(body: ReviewIn, conn: PortalConn) -> dict[str, str]:
    try:
        rid = reviews.submit_review(
            conn,
            body.token,
            rating=body.rating,
            title=body.title,
            body=body.body,
            price_matched=body.price_matched,
            display_name=body.display_name,
            visited=body.visited,
            independent=body.independent,
        )
    except reviews.ReviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": rid, "status": "pending_moderation"}


# ============================================================ portal: sign-in
class EmailIn(BaseModel):
    email: str = Field(max_length=254)


@router.post("/portal/sign-in", response_model=LinkOut, status_code=202)
def sign_in(body: EmailIn, conn: PortalConn, _: Guard, background: BackgroundTasks) -> LinkOut:
    settings = get_settings()
    try:
        token = auth.request_sign_in(conn, body.email, settings.site_url)
    except auth.AuthError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    dev = (
        f"{settings.site_url}/providers/sign-in/verify#{token}"
        if token and settings.show_dev_links
        else None
    )
    if token:
        background.add_task(send_mail_soon)
    return LinkOut(ok=True, dev_link=dev)


class MembershipOut(BaseModel):
    facility_id: str
    facility_name: str
    role: str
    status: str


class MeOut(BaseModel):
    email: str
    display_name: str | None
    mfa_enabled: bool
    mfa_passed: bool
    memberships: list[MembershipOut]


def _me(conn: Connection, a: auth.Account) -> MeOut:
    return MeOut(
        email=a.email,
        display_name=a.display_name,
        mfa_enabled=a.mfa_enabled,
        mfa_passed=a.mfa_passed,
        memberships=[
            MembershipOut(
                facility_id=m.facility_id,
                facility_name=m.facility_name,
                role=m.role,
                status=m.status,
            )
            for m in auth.memberships(conn, a.id)
        ],
    )


@router.post("/portal/sign-in/verify", response_model=MeOut)
def sign_in_verify(body: TokenIn, conn: PortalConn, response: Response, _: Guard) -> MeOut:
    try:
        session, account = auth.complete_sign_in(conn, body.token)
    except auth.AuthError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    response.set_cookie(
        COOKIE,
        session,
        max_age=auth.SESSION_DAYS * 86400,
        httponly=True,
        secure=get_settings().environment == "production",
        samesite="lax",
        path="/",
    )
    return _me(conn, account)


@router.post("/portal/sign-out", status_code=204)
def portal_sign_out(request: Request, conn: PortalConn, _: Guard) -> Response:
    token = request.cookies.get(COOKIE)
    if token:
        auth.sign_out(conn, token)
    out = Response(status_code=204)
    out.delete_cookie(COOKIE, path="/")
    return out


@router.get("/portal/me", response_model=MeOut)
def me(conn: PortalConn, account: Me) -> MeOut:
    return _me(conn, account)


class MfaSetupOut(BaseModel):
    secret: str
    otpauth_uri: str


@router.post("/portal/mfa/setup", response_model=MfaSetupOut)
def mfa_setup(conn: PortalConn, account: Me, _: Guard) -> MfaSetupOut:
    try:
        secret, uri = auth.totp_setup(conn, account)
    except auth.AuthError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return MfaSetupOut(secret=secret, otpauth_uri=uri)


class CodeIn(BaseModel):
    code: str = Field(max_length=12)


@router.post("/portal/mfa/verify", response_model=MeOut)
def mfa_verify(body: CodeIn, request: Request, conn: PortalConn, _: Guard) -> MeOut:
    session = request.cookies.get(COOKIE) or ""
    try:
        auth.totp_verify(conn, session, body.code)
    except auth.AuthError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    account = auth.session_account(conn, session)
    if account is None:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return _me(conn, account)


# ============================================================ portal: claims
class FacilityHit(BaseModel):
    facility_id: str
    name: str
    city: str | None
    state: str
    claimed: bool


@router.get("/portal/facilities/search", response_model=list[FacilityHit])
def facility_search(
    conn: PortalConn, account: Me, q: Annotated[str, Query(min_length=3, max_length=80)]
) -> list[FacilityHit]:
    like = "%" + q.replace("\\", "").replace("%", "").replace("_", " ") + "%"
    rows = conn.execute(
        text(
            "SELECT f.id, f.name, f.city, f.state_code, c.facility_id IS NOT NULL "
            "FROM ref.facility f LEFT JOIN prov.claimed_facility c ON c.facility_id = f.id "
            "WHERE f.name ILIKE :q ORDER BY f.name LIMIT 20"
        ),
        {"q": like},
    ).all()
    return [
        FacilityHit(facility_id=str(r[0]), name=r[1], city=r[2], state=r[3], claimed=r[4])
        for r in rows
    ]


class ClaimIn(BaseModel):
    facility_id: str = Field(pattern=_UUID)
    note: str | None = Field(default=None, max_length=500)


@router.post("/portal/claims", response_model=MembershipOut)
def portal_claim(body: ClaimIn, conn: PortalConn, account: Me, _: Guard) -> MembershipOut:
    try:
        m = auth.claim(conn, account, body.facility_id, body.note)
    except auth.AuthError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return MembershipOut(
        facility_id=m.facility_id, facility_name=m.facility_name, role=m.role, status=m.status
    )


# ======================================================== portal: homepage
class ProfileIn(BaseModel):
    about: str | None = None
    website_url: str | None = None
    booking_url: str | None = None
    phone: str | None = None
    hours: dict[str, str] = Field(default_factory=dict)
    languages: list[str] = Field(default_factory=list)
    accessibility: list[str] = Field(default_factory=list)
    insurance_note: str | None = None
    social_urls: list[str] = Field(default_factory=list)


class ProfileEditOut(BaseModel):
    status: str
    profile: ProfileIn
    rejected_note: str | None
    media: list[dict[str, Any]]
    languages: list[str]
    accessibility: list[str]


def _edit_out(conn: Connection, fid: str, p: pages.Profile) -> ProfileEditOut:
    return ProfileEditOut(
        status=p.status,
        profile=ProfileIn(
            about=p.about,
            website_url=p.website_url,
            booking_url=p.booking_url,
            phone=p.phone,
            hours=p.hours,
            languages=list(p.languages),
            accessibility=list(p.accessibility),
            insurance_note=p.insurance_note,
            social_urls=list(p.social_urls),
        ),
        rejected_note=pages.last_rejected_note(conn, fid),
        media=[
            {**m, "url": f"/api/v1/portal/facilities/{fid}/media/{m['id']}"}
            for m in pages.media_list(conn, fid)
        ],
        languages=list(pages.LANGUAGES),
        accessibility=list(pages.ACCESSIBILITY),
    )


FID = Annotated[str, PathParam(pattern=_UUID)]


@router.get("/portal/facilities/{facility_id}/profile", response_model=ProfileEditOut)
def profile_get(facility_id: FID, conn: PortalConn, account: Me) -> ProfileEditOut:
    _role(conn, account, facility_id, VIEW)
    return _edit_out(conn, facility_id, pages.editable(conn, facility_id))


class ProfileSaveIn(BaseModel):
    profile: ProfileIn
    submit: bool = False


@router.put("/portal/facilities/{facility_id}/profile", response_model=ProfileEditOut)
def profile_put(
    facility_id: FID, body: ProfileSaveIn, conn: PortalConn, account: Me, _: Guard
) -> ProfileEditOut:
    _role(conn, account, facility_id, EDIT)
    try:
        p = pages.save_draft(conn, facility_id, account.id, body.profile.model_dump(), body.submit)
    except pages.PageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _edit_out(conn, facility_id, p)


@router.post("/portal/facilities/{facility_id}/media", status_code=201)
async def media_upload(
    facility_id: FID,
    request: Request,
    conn: PortalConn,
    store: Store,
    account: Me,
    _: Guard,
    kind: Annotated[str, Query(pattern="^(logo|photo)$")],
    alt: Annotated[str | None, Query(max_length=200)] = None,
) -> dict[str, str]:
    """Upload one image as the raw request body (PNG, JPEG or WebP, 2 MB max)."""
    _role(conn, account, facility_id, EDIT)
    data = b""
    async for chunk in request.stream():
        data += chunk
        if len(data) > pages.MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Images must be 2 MB or smaller.")
    try:
        mid = pages.upload_media(conn, store, facility_id, account.id, kind, data, alt)
    except pages.PageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": mid, "status": "pending_review"}


@router.get("/portal/facilities/{facility_id}/media/{media_id}")
def media_preview(
    facility_id: FID,
    media_id: Annotated[str, PathParam(pattern=_UUID)],
    conn: PortalConn,
    store: Store,
    account: Me,
) -> Response:
    """The provider's own image, including ones waiting for review."""
    _role(conn, account, facility_id, VIEW)
    row = conn.execute(
        text(
            "SELECT object_key, content_type FROM prov.media WHERE id = CAST(:m AS uuid) "
            "AND facility_id = CAST(:f AS uuid)"
        ),
        {"m": media_id, "f": facility_id},
    ).first()
    data = store.get_media(str(row[0])) if row else None
    if row is None or data is None:
        raise HTTPException(status_code=404)
    return Response(
        content=data,
        media_type=str(row[1]),
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/portal/facilities/{facility_id}/media/{media_id}", status_code=204)
def media_delete(
    facility_id: FID,
    media_id: Annotated[str, PathParam(pattern=_UUID)],
    conn: PortalConn,
    account: Me,
    _: Guard,
) -> Response:
    _role(conn, account, facility_id, EDIT)
    pages.remove_media(conn, facility_id, media_id)
    return Response(status_code=204)


# =========================================================== portal: numbers
@router.get("/portal/facilities/{facility_id}/stats")
def portal_stats(
    facility_id: FID,
    conn: PortalConn,
    account: Me,
    days: Annotated[int, Query()] = 30,
) -> dict[str, Any]:
    _role(conn, account, facility_id, VIEW)
    if days not in (7, 30, 90):
        raise HTTPException(status_code=422, detail="days must be 7, 30 or 90")
    return stats.as_dict(stats.dashboard(conn, facility_id, days))


# =========================================================== portal: reviews
@router.get("/portal/facilities/{facility_id}/reviews")
def portal_reviews(facility_id: FID, conn: PortalConn, account: Me) -> dict[str, Any]:
    _role(conn, account, facility_id, VIEW)
    s = reviews.summary(conn, facility_id)
    return {
        "summary": {
            "average": None if s.average is None else str(s.average),
            "count": s.count,
            "removed": s.removed,
        },
        "reviews": reviews.for_provider(conn, facility_id),
    }


class InviteOut(BaseModel):
    link: str
    expires_in_days: int


@router.post("/portal/facilities/{facility_id}/invites", response_model=InviteOut)
def portal_invite(facility_id: FID, conn: PortalConn, account: Me, _: Guard) -> InviteOut:
    """A one-time review link for the provider to give a patient."""
    _role(conn, account, facility_id, EDIT)
    try:
        token = reviews.create_invite(conn, facility_id, account.id)
    except reviews.ReviewError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return InviteOut(
        link=f"{get_settings().site_url}/review#{token}", expires_in_days=reviews.INVITE_LINK_DAYS
    )


class ReplyIn(BaseModel):
    body: str = Field(max_length=1500)


@router.post("/portal/facilities/{facility_id}/reviews/{review_id}/reply")
def portal_reply(
    facility_id: FID,
    review_id: Annotated[str, PathParam(pattern=_UUID)],
    body: ReplyIn,
    conn: PortalConn,
    account: Me,
    _: Guard,
) -> dict[str, Any]:
    _role(conn, account, facility_id, EDIT)
    try:
        warn = reviews.reply(conn, review_id, facility_id, account.id, body.body)
    except reviews.ReviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "pending_review", "privacy_warning": warn}


class ReportIn(BaseModel):
    reason: str = Field(max_length=500)


@router.post("/portal/facilities/{facility_id}/reviews/{review_id}/report", status_code=202)
def portal_report(
    facility_id: FID,
    review_id: Annotated[str, PathParam(pattern=_UUID)],
    body: ReportIn,
    conn: PortalConn,
    account: Me,
    _: Guard,
) -> dict[str, str]:
    _role(conn, account, facility_id, EDIT)
    try:
        reviews.report(conn, review_id, facility_id, account.id, body.reason)
    except reviews.ReviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "received"}


# ============================================== provider prices (PRV-02/08/09)
@router.get("/facilities/{facility_id}/provider-prices")
def facility_provider_prices(
    facility_id: Annotated[str, PathParam(pattern=_UUID)], conn: Conn
) -> dict[str, Any]:
    """Reviewed prices, active specials and packages entered by the provider."""
    try:
        return prices.public_prices(conn, facility_id, _today())
    except prices.ProviderPriceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _today() -> date:
    return datetime.now(UTC).date()


@router.get("/portal/facilities/{facility_id}/prices")
def portal_prices(facility_id: FID, conn: PortalConn, account: Me) -> dict[str, Any]:
    _role(conn, account, facility_id, VIEW)
    return prices.for_provider(conn, facility_id)


class ListingIn(BaseModel):
    service_slug: str | None = Field(default=None, max_length=80)
    code_system: str | None = Field(default=None, max_length=20)
    code: str | None = Field(default=None, max_length=12)
    quantity: int = Field(default=1, ge=1, le=100)
    regular_price: str = Field(max_length=20)
    delivery: str = Field(default="in_person", pattern="^(in_person|online|both)$")
    copay_kind: str | None = Field(default=None, pattern="^(standard|amount)$")
    copay_amount: str | None = Field(default=None, max_length=20)


@router.post("/portal/facilities/{facility_id}/prices", status_code=201)
def portal_price_save(
    facility_id: FID, body: ListingIn, conn: PortalConn, account: Me, _: Guard
) -> dict[str, str]:
    _role(conn, account, facility_id, EDIT)
    try:
        lid = prices.save_listing(
            conn,
            facility_id,
            account.id,
            service_slug=body.service_slug or None,
            code_system=body.code_system or None,
            code=body.code or None,
            quantity=body.quantity,
            regular_price=body.regular_price,
            delivery=body.delivery,
            copay_kind=body.copay_kind,
            copay_amount=body.copay_amount,
        )
    except prices.ProviderPriceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": lid}


@router.get("/portal/price-template")
def portal_price_template(
    conn: PortalConn,
    account: Me,
    types: Annotated[str, Query(min_length=2, max_length=400)],
) -> Response:
    """Download the price list for these kinds of care (comma-separated codes)."""
    try:
        body = templates.template_csv(conn, types.split(","))
    except templates.TemplateError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content="\ufeff" + body,  # so Excel opens it as UTF-8
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="procedurescout-price-list.csv"'},
    )


class UploadIn(BaseModel):
    csv: str = Field(max_length=templates.MAX_BYTES)
    confirm: bool = False


@router.post("/portal/facilities/{facility_id}/price-upload")
def portal_price_upload(
    facility_id: FID, body: UploadIn, conn: PortalConn, account: Me, _: Guard
) -> dict[str, Any]:
    """Check a filled-in price list line by line; with confirm, send the ready
    lines to price review and keep the practice's own services as suggestions."""
    _role(conn, account, facility_id, EDIT)
    try:
        check = templates.check_upload(conn, body.csv)
        applied = (
            templates.apply_upload(conn, facility_id, account.id, check) if body.confirm else None
        )
    except (templates.TemplateError, prices.ProviderPriceError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "lines": [
            {
                "line": x.line,
                "status": x.status,
                "message": x.message,
                "service": x.service,
                "price": x.price,
                "sessions": x.sessions,
            }
            for x in check.lines
            if x.status != "skipped"
        ],
        "counts": {s: check.count(s) for s in ("ready", "skipped", "error", "suggestion")},
        "applied": applied,
    }


@router.delete("/portal/facilities/{facility_id}/prices/{listing_id}", status_code=204)
def portal_price_withdraw(
    facility_id: FID,
    listing_id: Annotated[str, PathParam(pattern=_UUID)],
    conn: PortalConn,
    account: Me,
    _: Guard,
) -> Response:
    _role(conn, account, facility_id, EDIT)
    try:
        prices.withdraw_listing(conn, facility_id, listing_id)
    except prices.ProviderPriceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


class OfferIn(BaseModel):
    kind: str = Field(pattern="^(special_price|percent_off|amount_off)$")
    who: str = Field(pattern="^(new_patients|everyone)$")
    value: str = Field(max_length=20)
    starts_on: date
    ends_on: date | None = None
    terms: str | None = Field(default=None, max_length=300)


@router.post("/portal/facilities/{facility_id}/prices/{listing_id}/specials", status_code=201)
def portal_offer_add(
    facility_id: FID,
    listing_id: Annotated[str, PathParam(pattern=_UUID)],
    body: OfferIn,
    conn: PortalConn,
    account: Me,
    _: Guard,
) -> dict[str, str]:
    _role(conn, account, facility_id, EDIT)
    try:
        oid = prices.add_offer(
            conn,
            facility_id,
            listing_id,
            kind=body.kind,
            who=body.who,
            value=body.value,
            starts_on=body.starts_on,
            ends_on=body.ends_on,
            terms=body.terms,
        )
    except prices.ProviderPriceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": oid}


@router.delete("/portal/facilities/{facility_id}/specials/{offer_id}", status_code=204)
def portal_offer_withdraw(
    facility_id: FID,
    offer_id: Annotated[str, PathParam(pattern=_UUID)],
    conn: PortalConn,
    account: Me,
    _: Guard,
) -> Response:
    _role(conn, account, facility_id, EDIT)
    try:
        prices.withdraw_offer(conn, facility_id, offer_id)
    except prices.ProviderPriceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


class PackageItemIn(BaseModel):
    service_slug: str | None = Field(default=None, max_length=80)
    code_system: str | None = Field(default=None, max_length=20)
    code: str | None = Field(default=None, max_length=12)
    quantity: int = Field(default=1, ge=1, le=100)


class PackageIn(BaseModel):
    name: str = Field(max_length=80)
    description: str | None = Field(default=None, max_length=500)
    price: str = Field(max_length=20)
    items: list[PackageItemIn] = Field(max_length=12)


@router.post("/portal/facilities/{facility_id}/packages", status_code=201)
def portal_package_add(
    facility_id: FID, body: PackageIn, conn: PortalConn, account: Me, _: Guard
) -> dict[str, str]:
    _role(conn, account, facility_id, EDIT)
    try:
        pid = prices.save_package(
            conn,
            facility_id,
            name=body.name,
            description=body.description,
            price=body.price,
            items=[i.model_dump() for i in body.items],
        )
    except prices.ProviderPriceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": pid}


@router.delete("/portal/facilities/{facility_id}/packages/{package_id}", status_code=204)
def portal_package_withdraw(
    facility_id: FID,
    package_id: Annotated[str, PathParam(pattern=_UUID)],
    conn: PortalConn,
    account: Me,
    _: Guard,
) -> Response:
    _role(conn, account, facility_id, EDIT)
    try:
        prices.withdraw_package(conn, facility_id, package_id)
    except prices.ProviderPriceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


# ========================================================= wrong-price reports
class PriceReportIn(BaseModel):
    facility_id: str = Field(pattern=_UUID)
    problem: str = Field(max_length=30)
    service_key: str | None = Field(default=None, max_length=120)
    price_shown: str | None = Field(default=None, max_length=30)
    details: str | None = Field(default=None, max_length=500)


@router.post("/price-reports", status_code=202)
def price_report(body: PriceReportIn, conn: PortalConn) -> dict[str, str]:
    """Report a wrong price. Nothing about the person is stored."""
    from procedurescout_core import price_reports

    try:
        price_reports.submit(
            conn, body.facility_id, body.problem, body.service_key, body.price_shown, body.details
        )
    except price_reports.ReportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "received"}


@router.get("/portal/facilities/{facility_id}/price-reports")
def portal_price_reports(facility_id: FID, conn: PortalConn, account: Me) -> list[dict[str, Any]]:
    from procedurescout_core import price_reports

    _role(conn, account, facility_id, VIEW)
    return price_reports.for_facility(conn, facility_id)


# ================================================================ billing (D-051)
@router.get("/portal/facilities/{facility_id}/billing")
def portal_billing(facility_id: FID, conn: PortalConn, account: Me) -> dict[str, Any]:
    from procedurescout_core import billing

    _role(conn, account, facility_id, VIEW)
    st = billing.status(conn, facility_id)
    return {
        "payments_on": bool(get_settings().stripe_secret_key),
        "fee_starts_on": None if st.fee_starts_on is None else st.fee_starts_on.isoformat(),
        "fee_in_force": st.fee_in_force,
        "content_shown": st.content_shown,
        "listing_status": st.listing_status,
        "sponsored_status": st.sponsored_status,
        "plans": [
            {
                "code": p.code,
                "name": p.name,
                "kind": p.kind,
                "amount": format(p.amount.normalize(), "f"),
                "interval": p.interval,
                "can_buy": p.can_buy and bool(get_settings().stripe_secret_key),
            }
            for p in st.plans
        ],
        "slots": [{"service_key": k, "ring_miles": r} for k, r in st.slots],
    }


class CheckoutIn(BaseModel):
    plan_code: str = Field(pattern="^[a-z0-9_]{2,40}$")


@router.post("/portal/facilities/{facility_id}/billing/checkout")
def portal_checkout(
    facility_id: FID, body: CheckoutIn, conn: PortalConn, account: Me, _: Guard
) -> dict[str, str]:
    from procedurescout_core import billing

    _role(conn, account, facility_id, ("owner",))
    s = get_settings()
    try:
        url = billing.checkout_url(
            conn,
            s.stripe_secret_key,
            facility_id=facility_id,
            account_id=account.id,
            email=account.email,
            plan_code=body.plan_code,
            site_url=s.site_url,
        )
    except billing.BillingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"url": url}


@router.post("/portal/facilities/{facility_id}/billing/portal")
def portal_billing_portal(
    facility_id: FID, conn: PortalConn, account: Me, _: Guard
) -> dict[str, str]:
    from procedurescout_core import billing

    _role(conn, account, facility_id, ("owner",))
    s = get_settings()
    try:
        return {"url": billing.portal_url(conn, s.stripe_secret_key, facility_id, s.site_url)}
    except billing.BillingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


class SlotIn(BaseModel):
    service_key: str = Field(max_length=120)
    ring_miles: int


@router.put("/portal/facilities/{facility_id}/billing/sponsored")
def portal_sponsored(
    facility_id: FID, body: SlotIn, conn: PortalConn, account: Me, _: Guard
) -> dict[str, str]:
    from procedurescout_core import billing

    _role(conn, account, facility_id, EDIT)
    try:
        billing.set_slot(conn, facility_id, body.service_key, body.ring_miles)
    except billing.BillingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "saved"}


@router.post("/stripe/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, conn: PortalConn) -> dict[str, bool]:
    """Stripe tells us about subscription changes. Signed; applied once."""
    import json

    from procedurescout_core import billing

    payload = await request.body()
    try:
        billing.verify_webhook(
            payload,
            request.headers.get("stripe-signature", ""),
            get_settings().stripe_webhook_secret,
        )
        event = json.loads(payload)
        if not isinstance(event, dict):
            raise billing.BillingError("bad event")
        fresh = billing.handle_event(conn, event)
    except (billing.BillingError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="invalid webhook") from exc
    return {"received": True, "applied": fresh}


# ================================================== practices not in public records
class ListingRequestIn(BaseModel):
    name: str = Field(max_length=120)
    address_line1: str = Field(max_length=120)
    city: str = Field(max_length=60)
    state_code: str = Field(max_length=2)
    zip5: str = Field(max_length=5)
    phone: str | None = Field(default=None, max_length=25)
    website: str | None = Field(default=None, max_length=300)
    provider_type: str = Field(max_length=40)
    npi: str | None = Field(default=None, max_length=10)
    note: str | None = Field(default=None, max_length=500)


@router.post("/portal/listing-requests", status_code=201)
def listing_request(
    body: ListingRequestIn, conn: PortalConn, account: Me, _: Guard
) -> dict[str, str]:
    from procedurescout_core import listing_requests

    if not account.mfa_passed:
        raise HTTPException(
            status_code=403, detail="Enter the code from your authenticator app first."
        )
    try:
        rid = listing_requests.request(conn, account.id, body.model_dump())
    except listing_requests.ListingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": rid, "status": "pending"}


@router.get("/portal/listing-requests")
def listing_requests_mine(conn: PortalConn, account: Me) -> list[dict[str, Any]]:
    from procedurescout_core import listing_requests

    return listing_requests.mine(conn, account.id)


@router.get("/provider-types/all")
def provider_types_all(conn: Conn) -> list[dict[str, str]]:
    """Approved kinds of practice, for the 'add your practice' form."""
    return [
        {"code": str(r[0]), "name": str(r[1])}
        for r in conn.execute(
            text(
                "SELECT code, name FROM ref.provider_type WHERE review_state = 'approved' "
                "ORDER BY name"
            )
        ).all()
    ]
