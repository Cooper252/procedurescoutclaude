"""Listing fee and Sponsored spots (D-051, off by default), wrong-price reports,
and review stars in search. Synthetic data, rolled back."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Connection, text

from procedurescout_core import billing, price_reports
from procedurescout_core import provider_prices as pp
from tests.test_provider_prices import SLUG, fac  # noqa: F401  (fixture)

TODAY = datetime.now(UTC).date()


def _publish_price(conn: Connection, fid: str) -> None:
    a = conn.execute(
        text("INSERT INTO prov.account (email) VALUES ('b@synthetic.test') RETURNING id")
    ).scalar_one()
    lid = pp.save_listing(conn, fid, str(a), service_slug=SLUG, regular_price="129")
    pp.review_listing(conn, lid, "R", approve=True, note=None)


def _signed(payload: bytes, secret: str, at: int | None = None) -> str:
    t = at or int(time.time())
    sig = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={t},v1={sig}"


def _event(eid: str, etype: str, fid: str, plan: str, status: str) -> dict[str, object]:
    return {
        "id": eid,
        "type": etype,
        "data": {
            "object": {
                "id": "sub_synthetic_1",
                "customer": "cus_synthetic",
                "status": status,
                "current_period_end": int(time.time()) + 86400 * 30,
                "metadata": {"facility_id": fid, "plan_code": plan},
            }
        },
    }


def test_free_until_a_fee_date_then_only_paid_content_shows(conn: Connection, fac: str) -> None:  # noqa: F811
    _publish_price(conn, fac)
    assert len(pp.public_prices(conn, fac, TODAY)["listings"]) == 1  # free: shown
    billing.set_fee_start(conn, TODAY + timedelta(days=30), "Cooper")
    assert len(pp.public_prices(conn, fac, TODAY)["listings"]) == 1  # future date: still free
    billing.set_fee_start(conn, TODAY - timedelta(days=1), "Cooper")
    assert pp.public_prices(conn, fac, TODAY)["listings"] == []  # in force, unpaid: hidden
    billing.set_plan(
        conn,
        code="dental_listing",
        name="Dental listing",
        kind="listing",
        amount=Decimal("250"),
        provider_type=None,
        stripe_price_id="price_x",
        approved_by="Cooper",
    )
    billing.handle_event(
        conn, _event("evt_1", "customer.subscription.created", fac, "dental_listing", "active")
    )
    assert len(pp.public_prices(conn, fac, TODAY)["listings"]) == 1  # paid: shown again
    assert (
        billing.handle_event(  # the same event is applied once
            conn, _event("evt_1", "customer.subscription.created", fac, "dental_listing", "active")
        )
        is False
    )
    billing.handle_event(
        conn, _event("evt_2", "customer.subscription.deleted", fac, "dental_listing", "active")
    )
    assert pp.public_prices(conn, fac, TODAY)["listings"] == []
    st = billing.status(conn, fac, TODAY)
    assert st.fee_in_force and st.listing_status == "canceled" and not st.content_shown
    billing.set_fee_start(conn, None, "Cooper")
    assert billing.status(conn, fac, TODAY).content_shown


def test_webhook_signature() -> None:
    body = json.dumps({"id": "evt"}).encode()
    billing.verify_webhook(body, _signed(body, "whsec_test"), "whsec_test")
    with pytest.raises(billing.BillingError):
        billing.verify_webhook(body, _signed(body, "other"), "whsec_test")
    with pytest.raises(billing.BillingError):
        billing.verify_webhook(
            body, _signed(body, "whsec_test", int(time.time()) - 3600), "whsec_test"
        )
    with pytest.raises(billing.BillingError):
        billing.verify_webhook(body + b"x", _signed(body, "whsec_test"), "whsec_test")


def test_sponsored_spot_needs_plan_and_price_and_stays_apart(conn: Connection, fac: str) -> None:  # noqa: F811
    with pytest.raises(billing.BillingError):
        billing.set_slot(conn, fac, f"svc:{SLUG}", 25)  # no plan
    billing.set_plan(
        conn,
        code="sponsored_basic",
        name="Sponsored",
        kind="sponsored",
        amount=Decimal("99"),
        provider_type=None,
        stripe_price_id="price_y",
        approved_by="Cooper",
    )
    billing.handle_event(
        conn, _event("evt_s", "customer.subscription.created", fac, "sponsored_basic", "active")
    )
    with pytest.raises(billing.BillingError):
        billing.set_slot(conn, fac, f"svc:{SLUG}", 25)  # no published price for it
    _publish_price(conn, fac)
    billing.set_slot(conn, fac, f"svc:{SLUG}", 25)
    near = (
        conn.execute(
            text("SELECT facility_id FROM bill.sponsored_for(:k, 36.2, -115.1)"),
            {"k": f"svc:{SLUG}"},
        )
        .scalars()
        .all()
    )
    far = (
        conn.execute(
            text("SELECT facility_id FROM bill.sponsored_for(:k, 39.5, -119.8)"),
            {"k": f"svc:{SLUG}"},
        )
        .scalars()
        .all()
    )
    assert [str(x) for x in near] == [fac] and far == []


def test_wrong_price_reports(conn: Connection, fac: str) -> None:  # noqa: F811
    rid = price_reports.submit(conn, fac, "price_different", f"svc:{SLUG}", "129", "Charged $180")
    with pytest.raises(price_reports.ReportError):
        price_reports.submit(conn, fac, "made_up_problem")
    with pytest.raises(price_reports.ReportError):
        price_reports.submit(conn, "not-a-uuid", "other")
    assert price_reports.for_facility(conn, fac)[0]["details"] == "Charged $180"
    price_reports.resolve(conn, rid, "Synthetic Reviewer", "sent_to_provider")
    with pytest.raises(price_reports.ReportError):
        price_reports.resolve(conn, rid, "Synthetic Reviewer", "fixed")
    # junk in optional fields is dropped, not stored
    price_reports.submit(conn, fac, "other", "<script>", "12; DROP", None)
    row = conn.execute(
        text("SELECT service_key, price_shown FROM prov.price_report WHERE problem = 'other'")
    ).one()
    assert row == (None, None)
