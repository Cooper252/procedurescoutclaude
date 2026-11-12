"""Provider-entered prices, specials and packages: portal entry, review, search
and the facility page (PRV-02, PRV-08, PRV-09). Synthetic data, rolled back."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Connection, text

from procedurescout_core import provider_prices as pp
from procedurescout_core.object_store import LocalStore
from procedurescout_core.search import search
from tests.test_catalog_offers import load_all
from tests.test_discovery import setup_hospitals

TODAY = datetime.now(UTC).date()
LV = (Decimal("36.17"), Decimal("-115.14"))
SLUG = "teeth-cleaning-adult"


@pytest.fixture()
def fac(conn: Connection) -> str:
    setup_hospitals(conn)
    load_all(conn)
    conn.execute(
        text(
            "UPDATE ref.facility SET geom = CAST(ST_SetSRID(ST_MakePoint(-115.14, 36.17), 4326) "
            "AS geography), geocode_source = 'synthetic', geocode_precision = 'address' "
            "WHERE ccn = 'SYN501'"
        )
    )
    return str(conn.execute(text("SELECT id FROM ref.facility WHERE ccn = 'SYN501'")).scalar())


def _acct(conn: Connection) -> str:
    return str(
        conn.execute(
            text("INSERT INTO prov.account (email) VALUES ('p@synthetic.test') RETURNING id")
        ).scalar_one()
    )


def _search(conn: Connection, tmp_path: Path, **kw: object):  # type: ignore[no-untyped-def]
    return search(
        conn,
        LocalStore(tmp_path),
        latitude=LV[0],
        longitude=LV[1],
        radius_miles=Decimal(10),
        **kw,  # type: ignore[arg-type]
    )


def _mine(result, fid: str):  # type: ignore[no-untyped-def]
    return next(f for f in result.facilities if f.facility_id == fid)


def test_money_is_exact_and_refuses_fractions_of_cents() -> None:
    assert pp.money("129.50") == Decimal("129.50")
    assert pp.money("$1,200") == Decimal("1200")
    for bad in ("0", "-5", "12.345", "abc", ""):
        with pytest.raises(pp.ProviderPriceError):
            pp.money(bad)


def test_price_is_reviewed_then_shown_in_search(conn: Connection, fac: str, tmp_path: Path) -> None:
    a = _acct(conn)
    lid = pp.save_listing(conn, fac, a, service_slug=SLUG, regular_price="129")
    assert _mine(_search(conn, tmp_path, service_slug=SLUG), fac).status == "no_published_prices"
    with pytest.raises(pp.ProviderPriceError):  # rejecting needs a reason
        pp.review_listing(conn, lid, "Synthetic Reviewer", approve=False, note="")
    pp.review_listing(conn, lid, "Synthetic Reviewer", approve=True, note=None)
    r = _mine(_search(conn, tmp_path, service_slug=SLUG), fac)
    assert r.status == "prices"
    assert r.headline is not None and r.headline.amount == Decimal("129")
    assert r.prices[0].price_source == "provider_entered"
    assert r.special is None


def test_changing_a_live_price_keeps_it_live_until_approved(
    conn: Connection, fac: str, tmp_path: Path
) -> None:
    a = _acct(conn)
    lid = pp.save_listing(conn, fac, a, service_slug=SLUG, regular_price="129")
    pp.review_listing(conn, lid, "R", approve=True, note=None)
    assert pp.save_listing(conn, fac, a, service_slug=SLUG, regular_price="149") == lid
    mine = pp.for_provider(conn, fac)["listings"][0]
    assert (mine["regular_price"], mine["proposed_price"], mine["status"]) == (
        "129",
        "149",
        "published",
    )
    assert _mine(_search(conn, tmp_path, service_slug=SLUG), fac).headline.amount == 129  # type: ignore[union-attr]
    pp.review_listing(conn, lid, "R", approve=True, note=None)
    assert _mine(_search(conn, tmp_path, service_slug=SLUG), fac).headline.amount == 149  # type: ignore[union-attr]


def test_specials_show_apart_and_never_change_the_regular_price(
    conn: Connection, fac: str, tmp_path: Path
) -> None:
    a = _acct(conn)
    lid = pp.save_listing(conn, fac, a, service_slug=SLUG, regular_price="129")
    pp.review_listing(conn, lid, "R", approve=True, note=None)
    with pytest.raises(pp.ProviderPriceError):  # must be lower than the regular price
        pp.add_offer(
            conn,
            fac,
            lid,
            kind="special_price",
            who="new_patients",
            value="150",
            starts_on=TODAY,
            ends_on=None,
            terms=None,
        )
    oid = pp.add_offer(
        conn,
        fac,
        lid,
        kind="percent_off",
        who="new_patients",
        value="20",
        starts_on=TODAY,
        ends_on=TODAY + timedelta(days=30),
        terms="First visit",
    )
    assert _mine(_search(conn, tmp_path, service_slug=SLUG), fac).special is None  # not reviewed
    pp.review_offer(conn, oid, "R", approve=True, note=None)
    r = _mine(_search(conn, tmp_path, service_slug=SLUG), fac)
    assert r.special is not None
    assert (r.special.price, r.special.regular, r.special.who) == (
        Decimal("103.2"),
        Decimal("129"),
        "new_patients",
    )
    assert r.headline.amount == Decimal("129")  # type: ignore[union-attr]
    # a future special isn't active yet
    later = pp.add_offer(
        conn,
        fac,
        lid,
        kind="special_price",
        who="everyone",
        value="99",
        starts_on=TODAY + timedelta(days=10),
        ends_on=None,
        terms=None,
    )
    pp.review_offer(conn, later, "R", approve=True, note=None)
    assert _mine(_search(conn, tmp_path, service_slug=SLUG), fac).special.price == Decimal("103.2")  # type: ignore[union-attr]
    # raising the regular price above nothing breaks; lowering it below a special withdraws it
    pp.save_listing(conn, fac, a, service_slug=SLUG, regular_price="90")
    pp.review_listing(conn, lid, "R", approve=True, note=None)
    left = conn.execute(
        text("SELECT status FROM prov.offer WHERE id = :o"), {"o": later}
    ).scalar_one()
    assert left == "withdrawn"


def test_sessions_codes_packages_and_public_page(conn: Connection, fac: str) -> None:
    a = _acct(conn)
    conn.execute(
        text(
            "INSERT INTO ref.code (system, code, version) VALUES ('CDT', 'D1110', '2026') "
            "ON CONFLICT DO NOTHING"
        )
    )
    with pytest.raises(pp.ProviderPriceError):
        pp.save_listing(conn, fac, a, code_system="CDT", code="D9999", regular_price="50")
    with pytest.raises(pp.ProviderPriceError):
        pp.save_listing(conn, fac, a, service_slug="not-a-service", regular_price="50")
    one = pp.save_listing(conn, fac, a, code_system="cdt", code="d1110", regular_price="95")
    five = pp.save_listing(conn, fac, a, service_slug=SLUG, quantity=5, regular_price="500")
    pkg = pp.save_package(
        conn,
        fac,
        name="Synthetic cleaning plan",
        description="Two visits",
        price="180",
        items=[{"service_slug": SLUG, "quantity": 2}],
    )
    for lid in (one, five):
        pp.review_listing(conn, lid, "R", approve=True, note=None)
    pp.review_package(conn, pkg, "R", approve=True, note=None)
    page = pp.public_prices(conn, fac, TODAY)
    got = {(x["code"], x["quantity"], x["regular_price"]) for x in page["listings"]}
    assert got == {("CDT D1110", 1, "95"), (None, 5, "500")}
    assert page["packages"][0]["items"][0]["quantity"] == 2
    pp.withdraw_listing(conn, fac, one)
    assert len(pp.public_prices(conn, fac, TODAY)["listings"]) == 1


def test_public_api_role_reads_published_price_views_only(api_engine) -> None:  # type: ignore[no-untyped-def]
    with api_engine.connect() as c:
        c.execute(text("SELECT count(*) FROM prov.published_listing")).scalar_one()
        c.execute(text("SELECT count(*) FROM prov.published_offer")).scalar_one()
        c.execute(text("SELECT count(*) FROM prov.published_package_item")).scalar_one()


def test_online_and_in_person_prices_and_copay(conn: Connection, fac: str, tmp_path: Path) -> None:
    """Cooper (2026-11-11): in-person AND telehealth pricing, and copays."""
    a = _acct(conn)
    slug = "therapy-session-60"
    office = pp.save_listing(conn, fac, a, service_slug=slug, regular_price="160")
    video = pp.save_listing(
        conn,
        fac,
        a,
        service_slug=slug,
        regular_price="120",
        delivery="online",
        copay_kind="amount",
        copay_amount="30",
    )
    assert office != video  # the same service once in person and once online
    with pytest.raises(pp.ProviderPriceError):
        pp.save_listing(conn, fac, a, service_slug=slug, regular_price="1", delivery="phone")
    with pytest.raises(pp.ProviderPriceError):
        pp.save_listing(conn, fac, a, service_slug=slug, regular_price="160", copay_kind="free")
    for lid in (office, video):
        pp.review_listing(conn, lid, "Synthetic Reviewer", approve=True, note=None)
    anywhere = _mine(_search(conn, tmp_path, service_slug=slug), fac)
    assert anywhere.headline is not None and anywhere.headline.amount == 120  # lowest
    online = _search(conn, tmp_path, service_slug=slug, online_only=True)
    assert [f.facility_id for f in online.facilities] == [fac]
    assert online.facilities[0].delivery == "online"
    page = pp.public_prices(conn, fac, date(2026, 11, 11))
    shown = {(x["delivery"], x["copay_kind"], x["copay_amount"]) for x in page["listings"]}
    assert shown == {("in_person", None, None), ("online", "amount", "30")}
    # only the in-person price: nobody shows up for "online visits"
    pp.withdraw_listing(conn, fac, video)
    assert _search(conn, tmp_path, service_slug=slug, online_only=True).facilities == ()
