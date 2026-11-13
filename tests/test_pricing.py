"""Headline prices, typical range, badges, price history and plans by card name."""

import json
import uuid
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from procedurescout_api import search_routes
from procedurescout_api.main import app
from procedurescout_core import pricing
from procedurescout_core.object_store import LocalStore
from procedurescout_core.plans import list_plans
from procedurescout_core.price_store import PublishedPrice
from procedurescout_core.search import SearchError, search
from procedurescout_ingest import publish
from procedurescout_ingest.discovery import discover
from procedurescout_ingest.reference import catalog
from procedurescout_ingest.reference.websites import load_websites
from tests.conftest import api_conn_for
from tests.test_discovery import fake_fetcher, setup_hospitals, websites_csv
from tests.test_publish import JSON_FILE, stage, syn501
from tests.test_search_and_review import LAS_VEGAS, SERVICE_CSV, place


def price(ptype: str, amount: str, flags: tuple[str, ...] = ()) -> PublishedPrice:
    return PublishedPrice(
        "f",
        "hospital_file",
        "CPT",
        "1",
        None,
        None,
        ptype,
        None,
        None,
        Decimal(amount),
        None,
        None,
        None,
        "d",
        flags,
    )


def test_headline_uses_one_price_type_and_skips_likely_errors() -> None:
    rows = [
        price("discounted_cash", "80"),
        price("discounted_cash", "95"),
        price("gross", "50"),
        price("discounted_cash", "0.01", ("under_one_dollar",)),
    ]
    h = pricing.headline(rows, "cash")
    assert h is not None and (h.amount, h.highest, h.possible_error) == (
        Decimal("80"),
        Decimal("95"),
        False,
    )
    only_error = pricing.headline([price("gross", "0.01", ("under_one_dollar",))], "list")
    assert only_error is not None and only_error.possible_error
    assert pricing.headline(rows, "plan") is None


def test_typical_range_is_made_of_published_values() -> None:
    heads = [pricing.Headline(Decimal(v), Decimal(v), "discounted_cash") for v in range(1, 11)]
    t = pricing.typical(heads)
    assert t is not None and (t.low, t.middle, t.high, t.count) == (
        Decimal(3),
        Decimal(5),
        Decimal(8),
        10,
    )
    assert pricing.typical(heads[:4]) is None  # fewer than 5 prices: no "typical"
    b = pricing.badges(heads[0], heads, t)
    assert b.lowest_near_you and b.below_typical
    assert not pricing.badges(heads[5], heads, t).below_typical
    plan = pricing.Headline(Decimal("1180"), Decimal("1180"), "negotiated")
    cash = pricing.Headline(Decimal("640"), Decimal("640"), "discounted_cash")
    cheaper = pricing.badges(plan, [plan], None, cash)
    assert cheaper.cash_cheaper_than_plan
    assert cheaper.notes == ("Cash price $640 is lower than your plan's rate $1180",)
    assert pricing.percent_change(Decimal(80), Decimal(100)) == Decimal(25)
    assert pricing.percent_change(Decimal(100), Decimal(88)) == Decimal(-12)


ALIASES_HEADER = ",".join(catalog.ALIAS_COLUMNS) + "\n"


@pytest.fixture()
def world(conn: Connection, tmp_path: Path) -> LocalStore:
    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    catalog.load_provider_types(
        conn,
        (Path(__file__).resolve().parent.parent / "data/reference/provider_types.csv").read_text(),
    )
    catalog.load_services(conn, SERVICE_CSV)
    place(conn, "SYN501", "36.17", "-115.14")
    catalog.load_payers(
        conn,
        ",".join(catalog.PAYER_COLUMNS) + "\n"
        "Synthetic Health,Gold PPO,ppo,commercial,tester,2026-11-08\n"
        "Synthetic Health,Silver HMO,hmo,commercial,tester,2026-11-08\n",
    )
    aliases = catalog.load_payer_aliases(
        conn,
        ALIASES_HEADER
        + "Synthetic Payer One,PPO,Synthetic Health,Gold PPO,tester,2026-11-08,\n"
        + "Synthetic Payer Two,HMO,Synthetic Health,Silver HMO,,,proposed only\n",
    )
    assert aliases.summary == {"approved": 1, "proposed": 1}
    discover(conn, "NV", fake_fetcher)
    stage(conn, tmp_path)
    store = LocalStore(tmp_path / "store")
    publish.approve(conn, uuid.UUID(syn501(conn)[0].dataset_version_id), "Tester", store)
    return store


def _plan_id(conn: Connection, name: str) -> str:
    return str(
        conn.execute(
            text("SELECT id FROM ref.plan WHERE canonical_name = :n"), {"n": name}
        ).scalar()
    )


def run(conn: Connection, store: LocalStore, **kw: object) -> object:
    return search(
        conn,
        store,
        latitude=LAS_VEGAS[0],
        longitude=LAS_VEGAS[1],
        radius_miles=Decimal(25),
        service_slug="synthetic-service",
        **kw,
    )  # type: ignore[arg-type]


def test_plan_prices_only_through_approved_spellings(conn: Connection, world: LocalStore) -> None:
    assert [p.plan for p in list_plans(conn)] == ["Gold PPO"]  # Silver HMO not approved yet
    res = run(conn, world, mode="plan", plan_id=_plan_id(conn, "Gold PPO"))
    near = res.facilities[0]  # type: ignore[attr-defined]
    assert near.headline.amount == Decimal("75.25")
    negotiated = [p for p in near.prices if p.price_type == "negotiated"]
    assert {p.payer_name_raw for p in negotiated} == {"Synthetic Payer One"}  # no substitutes
    with pytest.raises(SearchError):
        run(conn, world, mode="plan", plan_id=_plan_id(conn, "Silver HMO"))  # unapproved
    with pytest.raises(SearchError):
        run(conn, world, mode="plan")  # plan mode needs a plan
    cash = run(conn, world)
    assert cash.facilities[0].headline.amount == Decimal("80.00")  # type: ignore[attr-defined]


def test_price_history_between_published_files(
    conn: Connection, world: LocalStore, tmp_path: Path
) -> None:
    doc = json.loads(JSON_FILE.read_text())
    doc["standard_charge_information"][0]["standard_charges"][0]["discounted_cash"] = "100.00"
    stage(conn, tmp_path, json.dumps(doc).encode())
    publish.approve(conn, uuid.UUID(syn501(conn)[0].dataset_version_id), "Tester", world)
    res = run(conn, world)
    near = res.facilities[0]  # type: ignore[attr-defined]
    assert near.headline.amount == Decimal("100.00")
    assert near.change_percent == Decimal(25)  # 80 -> 100


def test_unmapped_spellings_go_to_the_review_queue(conn: Connection, world: LocalStore) -> None:
    added = catalog.collect_unmapped_plans(conn)
    assert added >= 0
    queued = conn.execute(
        text("SELECT count(*) FROM ref.plan_alias WHERE raw_plan_text = 'HMO'")
    ).scalar()
    assert queued == 1  # proposed earlier, left untouched (not duplicated)


@pytest.fixture()
def client(conn: Connection, world: LocalStore) -> Iterator[TestClient]:
    def test_conn() -> Iterator[Connection]:
        yield conn

    app.dependency_overrides[search_routes.get_conn] = api_conn_for(conn)
    app.dependency_overrides[search_routes.get_store] = lambda: world
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_api_plans_and_plan_search(client: TestClient, conn: Connection) -> None:
    plans = client.get("/v1/plans").json()
    assert plans == [
        {
            "plan_id": _plan_id(conn, "Gold PPO"),
            "payer": "Synthetic Health",
            "plan": "Gold PPO",
            "product_type": "ppo",
            "segment": "commercial",
            "payer_id": str(
                conn.execute(
                    text("SELECT id FROM ref.payer WHERE canonical_name = 'Synthetic Health'")
                ).scalar()
            ),
        }
    ]
    r = client.get(
        "/v1/search",
        params={
            "lat": "36.17",
            "lng": "-115.14",
            "service": "synthetic-service",
            "mode": "plan",
            "plan_id": plans[0]["plan_id"],
        },
    )
    assert r.status_code == 200, r.text
    first = r.json()["facilities"][0]
    assert first["headline"] == "75.25" and first["headline_price_type"] == "negotiated"
    assert r.json()["typical"] is None  # one facility is not enough for a typical range


def _more_plans(conn: Connection) -> None:
    catalog.load_payers(
        conn,
        ",".join(catalog.PAYER_COLUMNS) + "\n"
        "Synthetic Health,All plans (one rate published for all),unknown,commercial,"
        "tester,2026-11-08\n"
        "Synthetic Health,Bronze EPO,epo,commercial,tester,2026-11-08\n"
        "Synthetic Health,Medicare Gold,other,medicare_advantage,tester,2026-11-08\n",
    )
    stats = catalog.load_payer_aliases(
        conn,
        ALIASES_HEADER
        + "Synthetic Payer Two,HMO,Synthetic Health,All plans (one rate published for all),"
        "tester,2026-11-08,\n"
        + "Synthetic Payer Four,EPO,Synthetic Health,Bronze EPO,tester,2026-11-08,\n"
        + "Synthetic Payer Five,MA,Synthetic Health,Medicare Gold,tester,2026-11-08,\n",
    )
    assert stats.rejects == []


def test_all_plans_rate_is_used_only_when_the_plan_has_none_and_is_labeled(
    conn: Connection, world: LocalStore
) -> None:
    _more_plans(conn)
    epo = run(conn, world, mode="plan", plan_id=_plan_id(conn, "Bronze EPO"))
    near = epo.facilities[0]  # type: ignore[attr-defined]
    assert near.all_plans_rate  # no Bronze EPO rate published; the one-for-all rate, labeled
    assert {p.payer_name_raw for p in near.prices if p.price_type == "negotiated"} == {
        "Synthetic Payer Two"
    }
    gold = run(conn, world, mode="plan", plan_id=_plan_id(conn, "Gold PPO"))
    g = gold.facilities[0]  # type: ignore[attr-defined]
    assert not g.all_plans_rate  # its own rate exists, so the all-plans rate is not mixed in
    assert {p.payer_name_raw for p in g.prices if p.price_type == "negotiated"} == {
        "Synthetic Payer One"
    }
    medicare = run(conn, world, mode="plan", plan_id=_plan_id(conn, "Medicare Gold"))
    m = medicare.facilities[0]  # type: ignore[attr-defined]
    assert not m.all_plans_rate and not [p for p in m.prices if p.price_type == "negotiated"]


def test_api_labels_all_plans_rates(client: TestClient, conn: Connection) -> None:
    _more_plans(conn)
    r = client.get(
        "/v1/search",
        params={
            "lat": "36.17",
            "lng": "-115.14",
            "service": "synthetic-service",
            "mode": "plan",
            "plan_id": _plan_id(conn, "Bronze EPO"),
        },
    )
    assert r.status_code == 200, r.text
    first = r.json()["facilities"][0]
    assert first["plan_rate_is_all_plans"] is True
    neg = [p for p in first["prices"] if p["price_type"] == "negotiated"]
    assert [p["plan_match"] for p in neg] == ["all_plans"]


def test_committed_plan_names_load_approved(conn: Connection) -> None:
    root = Path(__file__).resolve().parent.parent / "data/reference"
    payers = catalog.load_payers(conn, (root / "payers.csv").read_text())
    aliases = catalog.load_payer_aliases(conn, (root / "payer_aliases.csv").read_text())
    assert payers.rows_loaded == payers.rows_in > 100  # Cooper approved (2026-11-08, D-041)
    assert aliases.rejects == []
    assert aliases.summary.get("approved") == aliases.rows_in
    names = {p.payer for p in list_plans(conn)}
    assert "Anthem Blue Cross Blue Shield (Colorado)" not in names  # out-of-state Blues (rule 9)
    assert {"Anthem Blue Cross Blue Shield (Nevada)", "Culinary Health Fund"} <= names


def test_new_spellings_are_matched_only_when_certain(conn: Connection, world: LocalStore) -> None:
    from procedurescout_ingest.plan_resolver import RULE, plan_type, resolve_new_spellings

    assert plan_type("Commercial HMO") == "HMO" and plan_type("MCR") == "Medicare Advantage"
    assert plan_type("Workers Comp PPO") is None and plan_type("Gold Select Network") is None
    # the synthetic file has "Synthetic Payer Two | HMO"; its insurer is not yet known
    res = resolve_new_spellings(conn)
    assert ("Synthetic Payer Two", "HMO", 1) in res.unresolved and res.matched == []
    # once one spelling of that insurer is approved and it has an HMO card name,
    # its plain "HMO" spelling matches by rule
    catalog.load_payers(
        conn,
        ",".join(catalog.PAYER_COLUMNS)
        + "\nSynthetic Health,HMO,hmo,commercial,tester,2026-11-08\n",
    )
    catalog.load_payer_aliases(
        conn,
        ALIASES_HEADER
        + "Synthetic Payer Two,Gold Network,Synthetic Health,Gold PPO,tester,2026-11-08,\n",
    )
    res = resolve_new_spellings(conn)
    assert res.matched == [("Synthetic Payer Two", "HMO", "Synthetic Health", "HMO")]
    who = conn.execute(
        text(
            "SELECT reviewed_by FROM ref.plan_alias "
            "WHERE raw_plan_text = 'HMO' AND review_state = 'approved'"
        )
    ).scalar()
    assert who == RULE


def test_insurance_search_shows_cash_when_no_rate_for_that_insurance(
    conn: Connection, world: LocalStore
) -> None:
    """Cooper (2026-11-12): choose insurance up front; a place that lists no
    rate for it still shows its cash price, labeled, instead of nothing."""
    catalog.load_payers(
        conn,
        ",".join(catalog.PAYER_COLUMNS)
        + "\nOther Synthetic,Basic,ppo,commercial,tester,2026-11-08\n",
    )
    catalog.load_payer_aliases(
        conn, ALIASES_HEADER + "Nobody Synthetic,Basic,Other Synthetic,Basic,tester,2026-11-08,\n"
    )
    res = run(conn, world, mode="plan", plan_id=_plan_id(conn, "Basic"))
    near = res.facilities[0]  # type: ignore[attr-defined]
    assert near.no_plan_rate is True
    assert near.headline.amount == Decimal("80.00")  # the cash price, labeled
    assert near.headline.price_type == "discounted_cash"
    assert res.typical is None  # cash fallbacks never count as insurance rates
    gold = run(conn, world, mode="plan", plan_id=_plan_id(conn, "Gold PPO"))
    assert gold.facilities[0].no_plan_rate is False  # type: ignore[attr-defined]


def test_several_kinds_of_care_in_one_search(conn: Connection, world: LocalStore) -> None:
    conn.execute(
        text(
            "INSERT INTO ref.facility_provider_type (facility_id, provider_type, source) "
            "SELECT id, 'hospital', 'cms_facility_type' FROM ref.facility WHERE ccn = 'SYN501'"
        )
    )
    both = run(conn, world, provider_type="hospital,medical_spa")
    only_spa = run(conn, world, provider_type="medical_spa")
    assert both.facilities and not only_spa.facilities  # type: ignore[attr-defined]
    with pytest.raises(SearchError):
        run(conn, world, provider_type="hospital,not_a_kind")


def test_insurance_picker_lists_only_insurers_near_the_person(
    client: TestClient, conn: Connection
) -> None:
    """Cooper (2026-11-12): typing "Blue Cross" listed ~15 insurers from every
    state. With a location, only plans and insurer names published nearby."""
    near = {"lat": "36.17", "lng": "-115.14"}
    far = {"lat": "40.71", "lng": "-74.00"}  # New York: no synthetic places
    assert [p["plan"] for p in client.get("/v1/plans", params=near).json()] == ["Gold PPO"]
    assert client.get("/v1/plans", params=far).json() == []
    assert client.get("/v1/plans", params={"lat": "36.17"}).status_code == 422
    # names as written: nearby only, and names already on the card list left out
    names = client.get("/v1/payers/suggest", params={"q": "synthetic", **near}).json()
    assert names == [{"name": "Synthetic Payer Two", "facilities": 1}]
    assert client.get("/v1/payers/suggest", params={"q": "synthetic", **far}).json() == []
    everywhere = client.get("/v1/payers/suggest", params={"q": "synthetic"}).status_code
    assert everywhere == 200


def test_not_sure_which_plan_shows_the_insurers_range(
    client: TestClient, conn: Connection, world: LocalStore
) -> None:
    """Cooper (2026-11-12): people who know their insurer but not their plan see
    the range of its work and individual plans, labeled; Medicare and Medicaid
    plans never mix into that range."""
    catalog.load_payers(
        conn,
        ",".join(catalog.PAYER_COLUMNS)
        + "\nSynthetic Health,Synthetic Medicare,hmo,medicare_advantage,tester,2026-11-08\n",
    )
    catalog.load_payer_aliases(
        conn,
        ALIASES_HEADER
        + "Synthetic Payer Two,HMO,Synthetic Health,Synthetic Medicare,tester,2026-11-08,\n",
    )
    payer_id = str(
        conn.execute(
            text("SELECT id FROM ref.payer WHERE canonical_name = 'Synthetic Health'")
        ).scalar()
    )
    res = run(conn, world, mode="plan", payer_id=payer_id)
    first = res.facilities[0]  # type: ignore[attr-defined]
    negotiated = {p.payer_name_raw for p in first.prices if p.price_type == "negotiated"}
    assert negotiated == {"Synthetic Payer One"}  # the Medicare plan's rate is left out
    assert res.insurer_unsure == "Synthetic Health"  # type: ignore[attr-defined]
    medicare = run(conn, world, mode="plan", plan_id=_plan_id(conn, "Synthetic Medicare"))
    assert {
        p.payer_name_raw
        for p in medicare.facilities[0].prices
        if p.price_type == "negotiated"  # type: ignore[attr-defined]
    } == {"Synthetic Payer Two"}  # still findable by choosing that plan
    with pytest.raises(SearchError):
        run(conn, world, mode="plan", payer_id=payer_id, plan_id=_plan_id(conn, "Gold PPO"))
    with pytest.raises(SearchError):
        run(conn, world, mode="plan", payer_id=str(uuid.uuid4()))
    r = client.get(
        "/v1/search",
        params={
            "lat": "36.17",
            "lng": "-115.14",
            "service": "synthetic-service",
            "mode": "plan",
            "payer_id": payer_id,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["insurer_unsure"] == "Synthetic Health"


def test_doctor_part_is_shown_beside_the_hospital_part_not_as_the_price() -> None:
    """Cooper (2026-11-12): a hospital listed its own MRI rates and the
    radiologist's $66.36 fee for the same plan; the lowest of all of them was
    shown as the MRI price. The hospital's part is the headline and the
    doctor's part is reported separately."""
    from dataclasses import replace

    hospital = [
        replace(price("negotiated", a), billing_class="facility") for a in ("128.27", "194.63")
    ]
    doctor = [replace(price("negotiated", "66.36"), billing_class="professional")]
    h = pricing.headline(hospital + doctor, "plan")
    assert h is not None and (h.amount, h.highest) == (Decimal("128.27"), Decimal("194.63"))
    d = pricing.doctor_fee(hospital + doctor, "plan")
    assert d is not None and d.amount == Decimal("66.36")
    # a doctor's office that only publishes its own fee: that fee is the price
    only = pricing.headline(doctor, "plan")
    assert only is not None and only.amount == Decimal("66.36")
    assert pricing.doctor_fee(doctor, "plan") is None
    # not stated by the hospital: unchanged, lowest to highest of everything
    plain = pricing.headline([price("negotiated", "66.36"), price("negotiated", "128.27")], "plan")
    assert plain is not None and (plain.amount, plain.highest) == (
        Decimal("66.36"),
        Decimal("128.27"),
    )


def test_email_this_to_me(client: TestClient, conn: Connection, world: LocalStore) -> None:
    """Cooper (2026-11-12): email the prices, a link to the hospital's own file,
    and how to find the code in it."""
    from procedurescout_core import price_email

    fid = str(conn.execute(text("SELECT id FROM ref.facility WHERE ccn = 'SYN501'")).scalar())
    mail = price_email.compose(
        conn, world, facility_id=fid, service_slug="synthetic-service", site_url="https://x.test"
    )
    assert "Press Ctrl+F" in mail.body and "Billing code(s) to ask about" in mail.body
    assert "https://x.test/facility/" in mail.body
    assert "$80.00" in mail.body  # the cash price, exactly as published
    plan = price_email.compose(
        conn,
        world,
        facility_id=fid,
        service_slug="synthetic-service",
        mode="plan",
        plan_id=_plan_id(conn, "Gold PPO"),
        plan_label="Synthetic Health · Gold PPO",
        lang="es",
    )
    assert "Synthetic Health · Gold PPO" in plan.body and "$75.25" in plan.body
    assert "Ctrl+F" in plan.body and "Precio" in plan.body
    with pytest.raises(price_email.PriceEmailError):
        price_email.queue(conn, "not-an-email", mail)
    for _ in range(price_email.MAX_PER_ADDRESS_PER_DAY):
        price_email.queue(conn, "someone@example.test", mail)
    with pytest.raises(price_email.PriceEmailError):  # no flooding one inbox
        price_email.queue(conn, "someone@example.test", mail)


def test_email_this_to_me_through_the_api(
    client: TestClient, conn: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    from procedurescout_api import email_routes
    from tests.test_portal_api import _FakeEngine

    monkeypatch.setattr(email_routes, "portal_engine", lambda: _FakeEngine(conn))
    monkeypatch.setattr(email_routes, "send_mail_soon", lambda: None)
    fid = str(conn.execute(text("SELECT id FROM ref.facility WHERE ccn = 'SYN501'")).scalar())
    body = {"email": "person@example.test", "facility_id": fid, "service": "synthetic-service"}
    r = client.post("/v1/email-prices", json=body)
    assert r.status_code == 200, r.text
    queued = conn.execute(
        text("SELECT subject FROM prov.outbox WHERE to_email = 'person@example.test'")
    ).scalar()
    assert queued and "Synthetic" in queued
    assert client.post("/v1/email-prices", json={**body, "email": "nope"}).status_code == 422


REAL_SPELLINGS = [
    # (insurer as the hospital wrote it, plan as written, expected card name or None)
    (
        "BlueCross BlueShield of Alabama",
        "Commercial",
        "Blue Cross Blue Shield of Alabama · All plans (one rate published for all)",
    ),
    (
        "BlueCross BlueShield of Alabama",
        "Medicare Advantage",
        "Blue Cross Blue Shield of Alabama · Medicare Advantage",
    ),
    (
        "Blue Cross and Blue Shield of Alabama",
        "Blue Advantage (Medicare Advantage)",
        "Blue Cross Blue Shield of Alabama · Medicare Advantage",
    ),
    (
        "BCBS_Alabama_Exchange",
        "BCALEXCHNG",
        "Blue Cross Blue Shield of Alabama · Marketplace (exchange) plan",
    ),  # the kind of plan is in the insurer text
    (
        "BLUE CROSS OF AL",
        "BLUE CROSS AL COMMERCIAL",
        "Blue Cross Blue Shield of Alabama · All plans (one rate published for all)",
    ),
    (
        "Blue Cross Blue Shield of AL",
        "Default",
        "Blue Cross Blue Shield of Alabama · All plans (one rate published for all)",
    ),
    ("BlueCross BlueShield of Alabama", "Transplant", None),  # not regular coverage
    ("BCBS", "Anthem HMO", None),  # which Blue? never guessed
    ("Medicare A AL JJ", "Default", "Original Medicare · Original Medicare"),
    ("Traditional Medicare", "Traditional Medicare", "Original Medicare · Original Medicare"),
    (
        "MEDICARE",
        "MEDICARE ADVANTAGE",
        None,
    ),  # an Advantage plan of some insurer: not Original Medicare
    (
        "NODE Medicare Traditional",
        "NODE Medicare Traditional",
        "Original Medicare · Original Medicare",
    ),
    ("Aetna", "Medicare Managed Care Plan", "Aetna · Medicare Advantage"),
    ("AETNA", "AETNA COMMERCIAL", "Aetna · All plans (one rate published for all)"),
    ("AETNA HEALTH MANAGEMENT, LLC", "MANAGED MEDICARE", "Aetna · Medicare Advantage"),
    (
        "Connecticut General Life Insurance Company",
        "COMMERCIAL",
        "Cigna · All plans (one rate published for all)",
    ),
    (
        "United Healthcare",
        "All Payor/Commercial",
        "UnitedHealthcare · All plans (one rate published for all)",
    ),
    (
        "UnitedHealthcare",
        "AARP Medicare Managed Care Plan",
        "UnitedHealthcare · Medicare Advantage",
    ),
    ("United Healthcare", "VACCN", None),
    ("Blue Cross & Blue Shield of Rhode Island", "Prime EPO", None),  # "Prime EPO": not plainly EPO
    (
        "Blue Cross & Blue Shield of Rhode Island",
        "PPO",
        "Blue Cross & Blue Shield of Rhode Island · PPO",
    ),
    (
        "Blue Cross & Blue Shield of Rhode Island",
        "MANAGED MEDICARE",
        "Blue Cross & Blue Shield of Rhode Island · Medicare Advantage",
    ),
    ("Blue Cross & Blue Shield of Rhode Island", "OUT OF STATE", None),
    (
        "Neighborhood Health Plan of Rhode Island",
        "Managed Medicaid",
        "Neighborhood Health Plan of Rhode Island · Medicaid plan",
    ),
    ("Tufts Health Public Plans", "Managed Medicaid RI", "Tufts Health Plan · Medicaid plan"),
    (
        "[payer_BCBS DELAWARE ]",
        "[plan_ BLUE CROSS]",
        "Highmark Blue Cross Blue Shield Delaware · All plans (one rate published for all)",
    ),
    ("Bcbs", "Highmark Medicare Managed Care Plan", None),
    ("DELAWARE FIRST HEALTH-MEDICARE", "DELAWARE FIRST HEALTH-MEDICARE", None),
    ("Devoted Health", "Medicare Advantage", "Devoted Health · Medicare Advantage"),
    ("Wellcare", "MANAGED MEDICARE", "Wellcare · Medicare Advantage"),
    ("MVP", "Medicare Advantage", "MVP Health Care · Medicare Advantage"),
    ("BlueCross BlueShield Vermont", "Indemnity", None),
    ("Viva Health", "HMO", "Viva Health · HMO"),
    ("Humana Military", "TRICARE", None),
    ("CorVel", "Workers' Compensation", None),
    # Arkansas and Arizona hospitals (2026-11-12 load reports)
    (
        "BLUE CROSS OF ARKANSAS",
        "BLUE CROSS OF ARKANSAS",
        "Arkansas Blue Cross and Blue Shield · All plans (one rate published for all)",
    ),
    (
        "BLUE CROSS BLUE SHIELD/AR",
        "BLUE CROSS BLUE SHIELD/AR",
        "Arkansas Blue Cross and Blue Shield · All plans (one rate published for all)",
    ),
    ("ARKANSAS_BLUE_MEDICARE", "344_1", "Arkansas Blue Cross and Blue Shield · Medicare Advantage"),
    ("MEDIPAK", "Medicare Advantage", "Arkansas Blue Cross and Blue Shield · Medicare Advantage"),
    ("MEDIPAK", "MEDIPAK", None),  # may be the Medicare supplement
    (
        "HMO MEDIPAK ADV PLAN",
        "HMO MEDIPAK ADV PLAN",
        "Arkansas Blue Cross and Blue Shield · Medicare Advantage",
    ),
    ("HEALTH ADVANTAGE", "HEALTH ADVANTAGE", "Health Advantage (Arkansas Blue Cross) · HMO"),
    (
        "QUALCHOICE EXCHANGE",
        "QUALCHOICE EXCHANGE",
        "QualChoice (Arkansas) · Marketplace (exchange) plan",
    ),
    ("Qualchoice", "Qualchoice", "QualChoice (Arkansas) · All plans (one rate published for all)"),
    ("QUALCHOICE ADV HMO", "QUALCHOICE ADV HMO", None),  # not plainly one kind of plan
    ("Arkansas Total Care", "Medicaid", "Arkansas Total Care (PASSE) · Medicaid plan"),
    ("Summitt", "Medicaid", "Summit Community Care (PASSE) · Medicaid plan"),
    ("Summit", "All Plans", None),  # a short name: only with a Medicaid plan text
    ("Empower", "Medicaid", "Empower Healthcare Solutions (PASSE) · Medicaid plan"),
    ("Care Source", "Medicaid", "CareSource PASSE (Arkansas) · Medicaid plan"),
    ("MEDICAID-ARKANSAS", "MEDICAID-ARKANSAS", "Arkansas Medicaid (fee for service) · Medicaid"),
    ("ARKIDS-MEDICAID", "ARKIDS-MEDICAID", "Arkansas Medicaid (fee for service) · Medicaid"),
    ("Medicaid", "Medicaid", None),  # which state's? never guessed
    ("Blue Cross", "All Plans", None),  # which Blue? never guessed
    ("Ambetter of Arkansas", "Ambetter of Arkansas", "Ambetter · Marketplace (exchange) plan"),
    ("ALLWELL", "ALLWELL", "Wellcare · Medicare Advantage"),
    ("HUMANA GOLD MEDICARE", "HUMANA GOLD MEDICARE", "Humana · Medicare Advantage"),
    ("HMO HUMANA GOLD", "HMO HUMANA GOLD", None),
    (
        "Blue Cross Blue Shield of Arizona",
        "Commercial",
        "Blue Cross Blue Shield of Arizona · All plans (one rate published for all)",
    ),
    (
        "Blue Cross Blue Shield of Arizona",
        "Medicare Advantage",
        "Blue Cross Blue Shield of Arizona · Medicare Advantage",
    ),
    ("Blue Cross Blue Shield of Arizona", "BCBSAZ Workers Comp", None),
    ("Blue Cross Blue Shield of Arizona", "Medicare Supplemental Senior Preferred", None),
    ("Blue Cross Blue Shield", "Medicare Advantage", None),
    (
        "Health Choice Arizona, Inc.",
        "ACA Health Plan",
        "Health Choice Arizona · Marketplace (exchange) plan",
    ),
    ("Health Choice Arizona, Inc.", "Medicaid", "Health Choice Arizona · Medicaid plan"),
    ("Mercy Care", "Mercy Care Advantage", "Mercy Care (Arizona) · Medicare Advantage"),
    ("Mercy Care", "Mercy Medicaid", "Mercy Care (Arizona) · Medicaid plan"),
    (
        "Banner University Health Plan",
        "AZ Medicaid - AHCCCS",
        "Banner University Health Plans · Medicaid plan",
    ),
    (
        "Banner University Health Plan",
        "University Care Advantage",
        "Banner University Health Plans · Medicare Advantage",
    ),
    ("Banner University Health Plan", "University Family Plan", None),
    (
        "Arizona Complete",
        "Arizona Health Care Cost Containment System (AHCCCS)",
        "Arizona Complete Health · Medicaid plan",
    ),
    ("Arizona Physicians IPA", "Medicaid", "UnitedHealthcare · Medicaid plan"),
    (
        "United Healthcare Community Care",
        "Arizona Health Care Cost Containment System (AHCCCS)",
        "UnitedHealthcare · Medicaid plan",
    ),
    (
        "Cigna Healthcare of Arizona, Inc.",
        "HMO Medicare Advantage Plans",
        "Cigna · Medicare Advantage",
    ),
    ("Devoted Health Services", "Medicare Advantage", "Devoted Health · Medicare Advantage"),
    ("Oscar Health Plan", "Commercial", "Oscar Health · All plans (one rate published for all)"),
    (
        "AHCCCS MOLINA COMPLETE CARE",
        "AHCCCS MOLINA COMPLETE CARE",
        "Molina Healthcare · Medicaid plan",
    ),
    ("AHCCCS IHS", "AHCCCS IHS", "Arizona Medicaid (AHCCCS fee for service) · Medicaid"),
]


def test_reviewed_insurer_names_place_real_hospital_spellings(
    conn: Connection, world: LocalStore
) -> None:
    """Cooper (2026-11-12): typing "Medicare" listed "Medicare A AL JJ",
    "Traditional Medicare"... These are spellings from the Alabama, Rhode
    Island, Delaware and Vermont files, placed by Claude's reviewed naming
    rules (D-047) or left for research, never guessed."""
    from procedurescout_ingest.plan_resolver import load_name_rules, resolve_new_spellings

    catalog.load_payers(
        conn, (Path(__file__).resolve().parent.parent / "data/reference/payers.csv").read_text()
    )
    fid, dv = conn.execute(
        text("SELECT facility_id, dataset_version_id FROM src.published_file LIMIT 1")
    ).one()
    for payer, plan, _ in REAL_SPELLINGS:
        conn.execute(
            text(
                "INSERT INTO price.file_payer_summary (dataset_version_id, facility_id, "
                "payer_name_raw, plan_name_raw, prices) VALUES (:d, :f, :p, :pl, 1)"
            ),
            {"d": dv, "f": fid, "p": payer, "pl": plan},
        )
    rules = load_name_rules(
        (Path(__file__).resolve().parent.parent / "data/reference/payer_name_rules.csv").read_text()
    )
    resolve_new_spellings(conn, rules)
    from procedurescout_core.matching import normalize_name

    got = {
        (str(r[0]), str(r[1])): f"{r[2]} · {r[3]}"
        for r in conn.execute(
            text(
                "SELECT a.raw_payer_normalized, a.raw_plan_normalized, py.canonical_name, "
                "pl.canonical_name FROM ref.plan_alias a JOIN ref.plan pl ON pl.id = a.plan_id "
                "JOIN ref.payer py ON py.id = pl.payer_id WHERE a.review_state = 'approved'"
            )
        ).all()
    }
    wrong = [
        (payer, plan, expected, got.get((normalize_name(payer), normalize_name(plan))))
        for payer, plan, expected in REAL_SPELLINGS
        if got.get((normalize_name(payer), normalize_name(plan))) != expected
    ]
    assert wrong == [], wrong


def test_one_state_insurers_are_matched_only_in_their_state(
    conn: Connection, world: LocalStore
) -> None:
    """Found live (2026-11-12): an Alabama hospital's "Centene | Medicare
    Advantage" was matched to Nevada's SilverSummit plan, because Nevada's
    "Centene" spellings are SilverSummit. One-state insurers now get spellings
    automatically only from their own state's hospitals, and wrong automatic
    matches are removed."""
    from procedurescout_ingest.plan_resolver import (
        RULE,
        load_name_rules,
        load_payer_states,
        resolve_new_spellings,
    )

    root = Path(__file__).resolve().parent.parent
    catalog.load_payers(conn, (root / "data/reference/payers.csv").read_text())
    fid, dv = conn.execute(
        text("SELECT facility_id, dataset_version_id FROM src.published_file LIMIT 1")
    ).one()  # a Nevada hospital
    for payer, plan in (
        ("Viva Health", "HMO"),
        ("Medicare A AL JJ", "Default"),
        ("MEDICAID-ARKANSAS", "MEDICAID-ARKANSAS"),
    ):
        conn.execute(
            text(
                "INSERT INTO price.file_payer_summary (dataset_version_id, facility_id, "
                "payer_name_raw, plan_name_raw, prices) VALUES (:d, :f, :p, :pl, 1)"
            ),
            {"d": dv, "f": fid, "p": payer, "pl": plan},
        )
    # an earlier automatic match of Alabama's Viva to a Nevada hospital's spelling
    conn.execute(
        text(
            "INSERT INTO ref.plan_alias (raw_payer_normalized, raw_plan_text, "
            "raw_plan_normalized, plan_id, match_type, review_state, reviewed_by, reviewed_at) "
            "SELECT 'viva health', 'HMO', 'hmo', pl.id, 'normalized', 'approved', :rb, now() "
            "FROM ref.plan pl JOIN ref.payer py ON py.id = pl.payer_id "
            "WHERE py.canonical_name = 'Viva Health' AND pl.canonical_name = 'HMO'"
        ),
        {"rb": RULE},
    )
    res = resolve_new_spellings(
        conn,
        load_name_rules((root / "data/reference/payer_name_rules.csv").read_text()),
        load_payer_states((root / "data/reference/payer_states.csv").read_text()),
    )
    assert ("Viva Health", "HMO", "Viva Health") in res.removed
    still = conn.execute(
        text("SELECT count(*) FROM ref.plan_alias WHERE raw_payer_normalized = 'viva health'")
    ).scalar()
    assert still == 0  # Alabama's Viva is never matched from a Nevada hospital
    medicare = conn.execute(
        text(
            "SELECT py.canonical_name FROM ref.plan_alias a JOIN ref.plan pl ON pl.id = a.plan_id "
            "JOIN ref.payer py ON py.id = pl.payer_id "
            "WHERE a.raw_payer_normalized = 'medicare a al jj'"
        )
    ).scalar()
    assert medicare == "Original Medicare"  # national: matched in any state
    arkansas = conn.execute(
        text("SELECT count(*) FROM ref.plan_alias WHERE raw_payer_normalized = 'medicaid-arkansas'")
    ).scalar()
    assert arkansas == 0  # Arkansas Medicaid by rule, but this hospital is in Nevada
