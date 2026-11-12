"""'Email this to me' (Cooper, 2026-11-12).

POST /v1/email-prices   one place's prices for one service, emailed to the person
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from procedurescout_core import price_email

from .portal_routes import portal_engine, send_mail_soon
from .search_routes import Conn, Store
from .settings import get_settings

router = APIRouter(prefix="/v1", tags=["email"])


class EmailPricesIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    facility_id: str = Field(max_length=36)
    service: str | None = Field(default=None, max_length=80)
    code_system: str | None = Field(default=None, max_length=20)
    code: str | None = Field(default=None, max_length=20)
    mode: str = Field(default="cash", pattern="^(cash|plan)$")
    plan_id: str | None = Field(default=None, max_length=36)
    payer_id: str | None = Field(default=None, max_length=36)
    payer: str | None = Field(default=None, max_length=200)  # insurer name as written
    plan_label: str | None = Field(default=None, max_length=200)
    lang: Annotated[str, Field(pattern="^(en|es)$")] = "en"


class EmailPricesOut(BaseModel):
    ok: bool


@router.post("/email-prices", response_model=EmailPricesOut)
def email_prices(
    body: EmailPricesIn,
    conn: Conn,
    store: Store,
    background: BackgroundTasks,
) -> EmailPricesOut:
    """Builds the email from the same search the site shows, queues it and sends
    it right away. The address is used only for this email."""
    try:
        mail = price_email.compose(
            conn,
            store,
            facility_id=body.facility_id,
            service_slug=body.service,
            code_system=body.code_system,
            code=body.code,
            mode=body.mode,
            plan_id=body.plan_id if body.mode == "plan" else None,
            payer_id=body.payer_id if body.mode == "plan" and not body.plan_id else None,
            payer_raw=body.payer
            if body.mode == "plan" and not body.plan_id and not body.payer_id
            else None,
            plan_label=body.plan_label,
            lang=body.lang,
            site_url=get_settings().site_url,
        )
        engine = portal_engine()
        if engine is None:
            raise HTTPException(status_code=404, detail="Email is not turned on.")
        # its own short transaction, saved before the background send starts
        with engine.begin() as portal:
            price_email.queue(portal, body.email, mail)
            from procedurescout_core import site_stats

            site_stats.bump(portal, "email_sent")
    except price_email.PriceEmailError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    background.add_task(send_mail_soon)
    return EmailPricesOut(ok=True)
