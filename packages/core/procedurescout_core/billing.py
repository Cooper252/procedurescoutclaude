"""Monthly listing fee and Sponsored spots, through Stripe (D-051).

Off by default: listing is free for now (Cooper, 2026-11-08), and nothing is
charged until a start date is set (bill.setting 'listing_fee_starts_on'),
plans with prices are approved, and Stripe keys are configured.

- Prices differ by kind of business (bill.plan.provider_type).
- Card details never touch our servers: Stripe Checkout takes payment and its
  customer portal handles invoices and cancelling. Stripe tells us about
  changes through a signed webhook; we store only status and ids.
- Paying never changes search order or labels (PRV-06). Once the fee is in
  force, an unpaid provider's own content (prices, specials, packages,
  homepage, photos) is hidden; public-record listings, hospital price files
  and reviews always show.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import Connection, text

STRIPE_API = "https://api.stripe.com/v1"
WEBHOOK_TOLERANCE_SECONDS = 300
STATUSES = (
    "incomplete",
    "trialing",
    "active",
    "past_due",
    "canceled",
    "unpaid",
    "incomplete_expired",
    "paused",
)
RINGS = (10, 25, 50)
SLOTS_PER_SPONSORED_PLAN = 1


class BillingError(ValueError):
    """Message is safe to show."""


# ------------------------------------------------------------------ settings
def fee_starts_on(conn: Connection) -> date | None:
    v = conn.execute(
        text("SELECT value FROM bill.setting WHERE key = 'listing_fee_starts_on'")
    ).scalar()
    return None if v is None else date.fromisoformat(str(v))


def set_fee_start(conn: Connection, starts_on: date | None, by: str) -> None:
    """Cooper's decision only. None = free (the default)."""
    if starts_on is None:
        conn.execute(text("DELETE FROM bill.setting WHERE key = 'listing_fee_starts_on'"))
        return
    conn.execute(
        text(
            "INSERT INTO bill.setting (key, value, set_by) "
            "VALUES ('listing_fee_starts_on', :v, :b) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, set_by = EXCLUDED.set_by, "
            "set_at = now()"
        ),
        {"v": starts_on.isoformat(), "b": by},
    )


def set_plan(
    conn: Connection,
    *,
    code: str,
    name: str,
    kind: str,
    amount: Decimal,
    provider_type: str | None,
    stripe_price_id: str | None,
    approved_by: str,
) -> None:
    if kind not in ("listing", "sponsored"):
        raise BillingError("kind must be listing or sponsored")
    if amount <= 0 or amount != amount.quantize(Decimal("0.01")):
        raise BillingError("amount must be dollars and cents, more than $0")
    conn.execute(
        text(
            """
            INSERT INTO bill.plan (code, name, kind, provider_type, amount, stripe_price_id,
                approved_by)
            VALUES (:c, :n, :k, :t, :a, :s, :b)
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, kind = EXCLUDED.kind,
                provider_type = EXCLUDED.provider_type, amount = EXCLUDED.amount,
                stripe_price_id = EXCLUDED.stripe_price_id, approved_by = EXCLUDED.approved_by,
                active = true
            """
        ),
        {
            "c": code,
            "n": name,
            "k": kind,
            "t": provider_type,
            "a": amount,
            "s": stripe_price_id,
            "b": approved_by,
        },
    )


# -------------------------------------------------------------------- status
@dataclass(frozen=True, slots=True)
class PlanOut:
    code: str
    name: str
    kind: str
    amount: Decimal
    interval: str
    can_buy: bool


@dataclass(frozen=True, slots=True)
class Status:
    fee_starts_on: date | None
    fee_in_force: bool
    content_shown: bool
    listing_status: str | None
    sponsored_status: str | None
    plans: tuple[PlanOut, ...]
    slots: tuple[tuple[str, int], ...]


def status(conn: Connection, facility_id: str, today: date | None = None) -> Status:
    day = today or datetime.now(UTC).date()
    starts = fee_starts_on(conn)
    subs = {
        str(r[0]): str(r[1])
        for r in conn.execute(
            text(
                """
                SELECT DISTINCT ON (p.kind) p.kind, s.status FROM bill.subscription s
                JOIN bill.plan p ON p.code = s.plan_code
                WHERE s.facility_id = CAST(:f AS uuid)
                ORDER BY p.kind, (s.status IN ('active', 'trialing')) DESC, s.updated_at DESC
                """
            ),
            {"f": facility_id},
        ).all()
    }
    types = [
        str(r[0])
        for r in conn.execute(
            text(
                "SELECT provider_type FROM ref.facility_provider_type "
                "WHERE facility_id = CAST(:f AS uuid)"
            ),
            {"f": facility_id},
        ).all()
    ]
    plans = tuple(
        PlanOut(str(r[0]), str(r[1]), str(r[2]), Decimal(r[3]), str(r[4]), bool(r[5]))
        for r in conn.execute(
            text(
                """
                SELECT code, name, kind, amount, interval, stripe_price_id IS NOT NULL
                FROM bill.plan WHERE active
                  AND (provider_type IS NULL OR provider_type = ANY(:t))
                ORDER BY kind, amount
                """
            ),
            {"t": types},
        ).all()
    )
    shown = bool(
        conn.execute(
            text("SELECT bill.listing_shown(CAST(:f AS uuid))"), {"f": facility_id}
        ).scalar()
    )
    slots = tuple(
        (str(r[0]), int(r[1]))
        for r in conn.execute(
            text(
                "SELECT service_key, ring_miles FROM bill.sponsored_slot "
                "WHERE facility_id = CAST(:f AS uuid) ORDER BY service_key"
            ),
            {"f": facility_id},
        ).all()
    )
    return Status(
        fee_starts_on=starts,
        fee_in_force=starts is not None and starts <= day,
        content_shown=shown,
        listing_status=subs.get("listing"),
        sponsored_status=subs.get("sponsored"),
        plans=plans,
        slots=slots,
    )


# -------------------------------------------------------------------- stripe
def _stripe(secret_key: str, path: str, data: dict[str, str]) -> dict[str, Any]:
    r = httpx.post(f"{STRIPE_API}{path}", auth=(secret_key, ""), data=data, timeout=20)
    if r.status_code >= 300:
        raise BillingError("The payment service could not start. Please try again later.")
    out = r.json()
    if not isinstance(out, dict):
        raise BillingError("Unexpected answer from the payment service.")
    return out


def checkout_url(
    conn: Connection,
    secret_key: str,
    *,
    facility_id: str,
    account_id: str,
    email: str,
    plan_code: str,
    site_url: str,
) -> str:
    """A Stripe Checkout page for one plan (subscription)."""
    if not secret_key:
        raise BillingError("Payments are not turned on yet.")
    row = conn.execute(
        text("SELECT stripe_price_id, kind FROM bill.plan WHERE code = :c AND active"),
        {"c": plan_code},
    ).first()
    if row is None or not row[0]:
        raise BillingError("That plan isn't available.")
    base = site_url.rstrip("/")
    session = _stripe(
        secret_key,
        "/checkout/sessions",
        {
            "mode": "subscription",
            "line_items[0][price]": str(row[0]),
            "line_items[0][quantity]": "1",
            "customer_email": email,
            "client_reference_id": facility_id,
            "subscription_data[metadata][facility_id]": facility_id,
            "subscription_data[metadata][account_id]": account_id,
            "subscription_data[metadata][plan_code]": plan_code,
            "success_url": f"{base}/providers/account?billing=done",
            "cancel_url": f"{base}/providers/account?billing=cancelled",
        },
    )
    url = session.get("url")
    if not isinstance(url, str):
        raise BillingError("The payment service did not return a page.")
    return url


def portal_url(conn: Connection, secret_key: str, facility_id: str, site_url: str) -> str:
    """Stripe's customer portal (invoices, card, cancel)."""
    customer = conn.execute(
        text(
            "SELECT stripe_customer_id FROM bill.subscription WHERE facility_id = CAST(:f AS uuid) "
            "AND stripe_customer_id IS NOT NULL ORDER BY updated_at DESC LIMIT 1"
        ),
        {"f": facility_id},
    ).scalar()
    if not secret_key or customer is None:
        raise BillingError("There is no billing account for this page yet.")
    session = _stripe(
        secret_key,
        "/billing_portal/sessions",
        {"customer": str(customer), "return_url": f"{site_url.rstrip('/')}/providers/account"},
    )
    url = session.get("url")
    if not isinstance(url, str):
        raise BillingError("The payment service did not return a page.")
    return url


def verify_webhook(
    payload: bytes, signature_header: str, secret: str, now: int | None = None
) -> None:
    """Stripe's signature check: HMAC-SHA256 of 't.payload' with the endpoint secret."""
    if not secret:
        raise BillingError("webhook secret not set")
    parts = dict(p.split("=", 1) for p in signature_header.split(",") if "=" in p)
    signatures = [
        v
        for k, v in (p.split("=", 1) for p in signature_header.split(",") if "=" in p)
        if k == "v1"
    ]
    try:
        stamp = int(parts.get("t", ""))
    except ValueError as exc:
        raise BillingError("bad signature") from exc
    if abs((now if now is not None else int(time.time())) - stamp) > WEBHOOK_TOLERANCE_SECONDS:
        raise BillingError("signature too old")
    expected = hmac.new(secret.encode(), f"{stamp}.".encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in signatures):
        raise BillingError("bad signature")


def handle_event(conn: Connection, event: dict[str, Any]) -> bool:
    """Apply one Stripe event once. Returns False if it was already handled."""
    eid = str(event.get("id", ""))
    etype = str(event.get("type", ""))
    if not eid:
        raise BillingError("event without id")
    fresh = conn.execute(
        text(
            "INSERT INTO bill.stripe_event (id, type) VALUES (:i, :t) "
            "ON CONFLICT (id) DO NOTHING RETURNING id"
        ),
        {"i": eid, "t": etype},
    ).first()
    if fresh is None:
        return False
    obj = (event.get("data") or {}).get("object") or {}
    if etype.startswith("customer.subscription."):
        meta = obj.get("metadata") or {}
        fid, plan = meta.get("facility_id"), meta.get("plan_code")
        state = str(obj.get("status", ""))
        if etype == "customer.subscription.deleted":
            state = "canceled"
        try:
            fid = str(uuid.UUID(str(fid)))
        except ValueError:
            fid = None
        if fid and plan and state in STATUSES:
            end = obj.get("current_period_end")
            if end is None:
                items = (obj.get("items") or {}).get("data") or [{}]
                end = items[0].get("current_period_end") if items else None
            conn.execute(
                text(
                    """
                    INSERT INTO bill.subscription (facility_id, account_id, plan_code, status,
                        stripe_customer_id, stripe_subscription_id, current_period_end)
                    VALUES (CAST(:f AS uuid), CAST(:a AS uuid), :p, :s, :c, :sid,
                            to_timestamp(CAST(:end AS bigint)))
                    ON CONFLICT (stripe_subscription_id) DO UPDATE SET status = EXCLUDED.status,
                        plan_code = EXCLUDED.plan_code,
                        current_period_end = EXCLUDED.current_period_end, updated_at = now()
                    """
                ),
                {
                    "f": fid,
                    "a": meta.get("account_id") or None,
                    "p": plan,
                    "s": state,
                    "c": obj.get("customer"),
                    "sid": obj.get("id"),
                    "end": end,
                },
            )
    conn.execute(text("UPDATE bill.stripe_event SET handled = true WHERE id = :i"), {"i": eid})
    return True


# ----------------------------------------------------------------- sponsored
def set_slot(conn: Connection, facility_id: str, service_key: str, ring_miles: int) -> None:
    """Choose what a Sponsored spot shows for (one service, one distance)."""
    if ring_miles not in RINGS:
        raise BillingError("Choose 10, 25 or 50 miles.")
    sub = conn.execute(
        text(
            """
            SELECT s.id FROM bill.subscription s JOIN bill.plan p ON p.code = s.plan_code
            WHERE s.facility_id = CAST(:f AS uuid) AND p.kind = 'sponsored'
              AND s.status IN ('active', 'trialing') ORDER BY s.updated_at DESC LIMIT 1
            """
        ),
        {"f": facility_id},
    ).scalar()
    if sub is None:
        raise BillingError("A Sponsored spot needs an active Sponsored plan.")
    has_price = conn.execute(
        text(
            "SELECT 1 FROM prov.published_listing WHERE facility_id = CAST(:f AS uuid) AND "
            "(('svc:' || service_slug) = :k OR ('code:' || code_system || ':' || code) = :k)"
        ),
        {"f": facility_id, "k": service_key},
    ).first()
    if has_price is None:
        raise BillingError("Sponsored spots are only for services you have a published price for.")
    conn.execute(text("DELETE FROM bill.sponsored_slot WHERE subscription_id = :s"), {"s": sub})
    conn.execute(
        text(
            "INSERT INTO bill.sponsored_slot (subscription_id, facility_id, service_key, "
            "ring_miles) "
            "VALUES (:s, CAST(:f AS uuid), :k, :r)"
        ),
        {"s": sub, "f": facility_id, "k": service_key, "r": ring_miles},
    )
