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

    app.dependency_overrides[search_routes.get_conn] = test_conn
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
