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
