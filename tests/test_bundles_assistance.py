"""Bundles, financial assistance and automatic publishing of clean refreshes."""

import uuid
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from procedurescout_api import search_routes
from procedurescout_api.main import app
from procedurescout_core import assistance, bundles
from procedurescout_core.object_store import LocalStore
from procedurescout_ingest import publish
from procedurescout_ingest.discovery import discover
from procedurescout_ingest.reference import catalog
from procedurescout_ingest.reference.websites import load_websites
from tests.conftest import api_conn_for
from tests.test_discovery import fake_fetcher, setup_hospitals, websites_csv
from tests.test_publish import JSON_FILE, stage, syn501

ROOT = Path(__file__).resolve().parent.parent
REVIEWED = "human,tester,2026-11-08"
BUNDLE_CSV = (
    "bundle_slug,bundle_name,category,setting,position,label,role,requirement,"
    "included_by_default,code,notes,source,reviewed_by,reviewed_at\n"
    f"synthetic-bundle,Synthetic bundle,Tests,outpatient,0,The procedure,procedure,required,true,"
    f"CPT:99999@2026,,{REVIEWED}\n"
    f"synthetic-bundle,Synthetic bundle,Tests,outpatient,1,Anesthesia,anesthesia,optional,true,"
    f"CPT:99998@2026,billed separately,{REVIEWED}\n"
    f"synthetic-bundle,Synthetic bundle,Tests,outpatient,2,Hospital stay,facility,optional,false,"
    f"MS-DRG:999@v44,,{REVIEWED}\n"
)
POLICY_CSV = (
    ",".join(catalog.POLICY_COLUMNS) + "\n"
    "SYN501,https://synthetic-health.example/fap.pdf,https://synthetic-health.example/apply,,"
    "555-0100,2026,2026-01-01,2026-11-08,synthetic policy text,free<=200;discount<=400:50,,"
    f"{REVIEWED}\n"
)


def test_committed_files_load(conn: Connection) -> None:
    setup_hospitals(conn)
    b = catalog.load_bundles(conn, (ROOT / "data/reference/bundles.csv").read_text())
    g = catalog.load_poverty_guidelines(
        conn, (ROOT / "data/reference/poverty_guidelines.csv").read_text()
    )
    a = catalog.load_assistance_policies(
        conn, (ROOT / "data/reference/assistance_policies.csv").read_text()
    )
    assert b.rejects == [] and b.summary == {
        "bundles_proposed": 3,
        "bundles_approved": 2,
    }  # 3 medical need a clinician
    assert g.rows_loaded == 24
    # proposed policies name real CCNs (not in this synthetic database); check their syntax
    assert {r.rule for r in a.rejects} == {"facility_not_found"}
    import csv
    import io

    for row in csv.DictReader(
        io.StringIO((ROOT / "data/reference/assistance_policies.csv").read_text())
    ):
        # unreviewed, or approved by Claude from the hospital's own document (D-060)
        if row["reviewed_by"]:
            assert row["reviewed_by"] == "Claude (delegated by Cooper, D-060)"
            assert row["reviewed_at"] and "Checked" in row["evidence"]
        else:
            assert row["reviewed_at"] == "" and row["source"] == "ai_suggested"
        assert row["policy_url"].startswith("https://") and row["evidence"]
        for part in row["tiers"].split(";"):
            assert catalog._TIER.match(part), part
    assert assistance.guideline(conn, 2026, "NV", 4) == Decimal("33000")
    assert assistance.guideline(conn, 2026, "NV", 10) == Decimal("55720") + 2 * Decimal("5680")
    assert assistance.guideline(conn, 2026, "AK", 1) == Decimal("19950")
    with pytest.raises(assistance.AssistanceError):
        assistance.guideline(conn, 2026, "NV", 0)


@pytest.fixture()
def world(conn: Connection, tmp_path: Path) -> LocalStore:
    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    catalog.load_poverty_guidelines(
        conn, (ROOT / "data/reference/poverty_guidelines.csv").read_text()
    )
    assert catalog.load_assistance_policies(conn, POLICY_CSV).rows_loaded == 1
    assert catalog.load_bundles(conn, BUNDLE_CSV).summary == {"bundles_approved": 1}
    discover(conn, "NV", fake_fetcher)
    stage(conn, tmp_path)
    store = LocalStore(tmp_path / "store")
    publish.approve(conn, uuid.UUID(syn501(conn)[0].dataset_version_id), "Tester", store)
    return store


def _ids(conn: Connection, *ccns: str) -> list[str]:
    return [
        str(conn.execute(text("SELECT id FROM ref.facility WHERE ccn = :c"), {"c": c}).scalar())
        for c in ccns
    ]


def test_assistance_check_says_may_qualify_never_eligible(
    conn: Connection, world: LocalStore
) -> None:
    ids = _ids(conn, "SYN501", "SYN503")

    def run(income: str) -> dict[str, assistance.FacilityAssistance]:
        res = assistance.check(
            conn, facility_ids=ids, household_size=4, annual_income=Decimal(income), state_code="NV"
        )
        return {f.name: f for f in res.facilities}

    low = run("50000")  # 151.5% of $33,000
    assert low["SYNTHETIC VALLEY MEDICAL CENTER"].status == "may_qualify_free"
    assert low["SYNTHETIC DESERT HOSPITAL"].status == "policy_not_reviewed"  # never "no help"
    mid = run("100000")["SYNTHETIC VALLEY MEDICAL CENTER"]
    assert mid.status == "may_qualify_discount" and mid.best_tier is not None
    assert mid.best_tier.discount_percent == Decimal("50")
    assert run("200000")["SYNTHETIC VALLEY MEDICAL CENTER"].status == "above_published_limits"
    assert "eligible" not in assistance.SITE_MESSAGE.lower()
    # dollars, never poverty-level percentages (Cooper, 2026-11-08)
    assert low["SYNTHETIC VALLEY MEDICAL CENTER"].plain_message == (
        "You may qualify for free care at SYNTHETIC VALLEY MEDICAL CENTER if your household "
        "makes under $31,920 (1 person) or $66,000 (family of 4). Discounts may be available "
        "up to $63,840 (1 person) or $132,000 (family of 4)."
    )
    assert "poverty" not in low["SYNTHETIC VALLEY MEDICAL CENTER"].plain_message.lower()
    assert low["SYNTHETIC DESERT HOSPITAL"].plain_message.startswith("Ask SYNTHETIC DESERT")
    assert assistance.site_message(conn, "NV") == (
        "At many hospitals you may qualify for free care if your household makes under "
        "$31,920 (1 person) or $66,000 (family of 4), and for reduced-cost care up to $63,840 "
        "or $132,000. Even with insurance. Check before you pay."
    )


def test_bundle_estimate_never_counts_missing_pieces_as_zero(
    conn: Connection, world: LocalStore
) -> None:
    (fid,) = _ids(conn, "SYN501")
    cash = bundles.estimate(
        conn, world, bundle_slug="synthetic-bundle", facility_id=fid, mode="cash"
    )
    status = {ln.component.label: (ln.status, ln.amount) for ln in cash.lines}
    assert status == {
        "The procedure": ("priced", Decimal("80.00")),
        "Anesthesia": ("not_published", None),  # included by default, not in the file
        "Hospital stay": ("left_out", None),  # optional, off by default
    }
    assert cash.total_of_priced == Decimal("80.00") and cash.complete is False
    comps = {
        c.label: c.component_id for c in bundles.bundle_components(conn, "synthetic-bundle")[1]
    }
    listed = bundles.estimate(
        conn,
        world,
        bundle_slug="synthetic-bundle",
        facility_id=fid,
        mode="list",
        include_optional=[comps["Hospital stay"]],  # anesthesia unchecked, stay checked
    )
    assert listed.total_of_priced == Decimal("100.10") + Decimal("25000")
    assert listed.complete is True
    ins = bundles.estimate(
        conn,
        world,
        bundle_slug="synthetic-bundle",
        facility_id=fid,
        mode="insurance",
        payer="Synthetic Payer Two",
        plan="HMO",
        include_optional=[],
    )
    proc = ins.lines[0]
    assert (proc.status, proc.rate_text) == ("not_a_dollar_amount", "60% of charges")
    with pytest.raises(bundles.BundleError):
        bundles.estimate(
            conn,
            world,
            bundle_slug="synthetic-bundle",
            facility_id=fid,
            mode="insurance",
            payer="Synthetic Payer",
            plan="PPO",
        )  # not published
    with pytest.raises(bundles.BundleError):
        bundles.estimate(
            conn,
            world,
            bundle_slug="synthetic-bundle",
            facility_id=fid,
            mode="cash",
            include_optional=[str(uuid.uuid4())],
        )


def test_clean_refresh_publishes_automatically_others_wait(
    conn: Connection, world: LocalStore, tmp_path: Path
) -> None:
    stage(conn, tmp_path)  # same file again: nothing got worse
    decisions = {d.facility_name: d for d in publish.auto_publish_pending(conn, world)}
    same = decisions["SYNTHETIC VALLEY MEDICAL CENTER"]
    assert same.published and same.reasons == ()
    who = conn.execute(
        text("SELECT reviewed_by FROM src.dataset_version WHERE id = :d"),
        {"d": same.dataset_version_id},
    ).scalar()
    assert who == publish.AUTO_REVIEWER
    # a refresh with far fewer prices waits for a person
    import json

    doc = json.loads(JSON_FILE.read_text())
    doc["standard_charge_information"] = doc["standard_charge_information"][:1]
    doc["standard_charge_information"][0]["standard_charges"][0]["payers_information"] = []
    smaller = json.dumps(doc).encode()  # 2 prices instead of 6
    stage(conn, tmp_path, smaller)
    held = {d.facility_name: d for d in publish.auto_publish_pending(conn, world)}
    assert held["SYNTHETIC VALLEY MEDICAL CENTER"].published is False
    assert "price count changed" in held["SYNTHETIC VALLEY MEDICAL CENTER"].reasons[0]


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


def test_api_bundles_and_assistance(client: TestClient, conn: Connection) -> None:
    (fid,) = _ids(conn, "SYN501")
    msg = client.get("/v1/assistance/message").json()
    assert "free or reduced-cost care" in msg["message"]
    nv = client.get("/v1/assistance/message", params={"state": "NV"}).json()
    assert "$31,920" in nv["message"]
    one = client.get(f"/v1/facilities/{fid}/assistance").json()
    assert "$66,000 (family of 4)" in one["message"]
    r = client.post(
        "/v1/assistance/check",
        json={"facility_ids": [fid], "household_size": 4, "annual_income": "50000", "state": "NV"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["facilities"][0]["status"] == "may_qualify_free"
    assert r.json()["income_percent_of_guideline"] == "151"
    assert client.get("/v1/bundles").json()[0]["slug"] == "synthetic-bundle"
    plans = client.get(f"/v1/facilities/{fid}/plans").json()
    assert {"payer": "Synthetic Payer One", "plan": "PPO"} in plans
    est = client.post(
        "/v1/bundles/synthetic-bundle/estimate", json={"facility_id": fid, "payment": "cash"}
    ).json()
    assert est["total_of_priced_pieces"] == "80" and est["complete"] is False
    assert (
        client.post(
            "/v1/bundles/nope/estimate", json={"facility_id": fid, "payment": "cash"}
        ).status_code
        == 422
    )
