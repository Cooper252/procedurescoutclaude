"""Service catalog, search by service near a place, the public API and the review page."""

import base64
import uuid
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, text

from procedurescout_api import admin_routes, search_routes
from procedurescout_api.main import app
from procedurescout_api.settings import get_settings
from procedurescout_core.object_store import LocalStore
from procedurescout_core.search import SearchError, search
from procedurescout_ingest import publish
from procedurescout_ingest.discovery import discover
from procedurescout_ingest.reference import catalog
from procedurescout_ingest.reference.websites import load_websites
from tests.test_discovery import fake_fetcher, setup_hospitals, websites_csv
from tests.test_publish import stage, syn501

ROOT = Path(__file__).resolve().parent.parent
SERVICE_CSV = (
    "slug,name,category,unit,codes,source,reviewed_by,reviewed_at,notes\n"
    "synthetic-service,Synthetic service,Tests,per_service,CPT:99999@2026,human,tester,"
    "2026-11-08,\n"
    "synthetic-proposed,Synthetic proposed,Tests,per_service,CPT:99998@2026,ai_suggested,,,\n"
)
LAS_VEGAS = (Decimal("36.17"), Decimal("-115.14"))


def place(conn: Connection, ccn: str, lat: str, lng: str) -> None:
    conn.execute(
        text(
            "UPDATE ref.facility SET geom = CAST(ST_SetSRID(ST_MakePoint(:lng, :lat), 4326) "
            "AS geography), geocode_source = 'synthetic', geocode_precision = 'address' "
            "WHERE ccn = :c"
        ),
        {"lat": lat, "lng": lng, "c": ccn},
    )


@pytest.fixture()
def world(conn: Connection, tmp_path: Path) -> LocalStore:
    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    catalog.load_provider_types(conn, (ROOT / "data/reference/provider_types.csv").read_text())
    catalog.assign_cms_provider_types(conn)
    services = catalog.load_services(conn, SERVICE_CSV)
    assert services.summary == {"approved": 1, "proposed": 1}
    place(conn, "SYN501", "36.17", "-115.14")  # Las Vegas
    place(conn, "SYN503", "36.20", "-115.10")  # a few miles away, nothing published
    place(conn, "SYN504", "39.53", "-119.81")  # Reno, far outside 25 miles
    discover(conn, "NV", fake_fetcher)
    stage(conn, tmp_path)
    store = LocalStore(tmp_path / "store")
    publish.approve(conn, uuid.UUID(syn501(conn)[0].dataset_version_id), "Tester", store)
    return store


def test_committed_catalog_files_load_with_review_state(conn: Connection) -> None:
    types = catalog.load_provider_types(
        conn, (ROOT / "data/reference/provider_types.csv").read_text()
    )
    services = catalog.load_services(
        conn, (ROOT / "data/reference/service_catalog.csv").read_text()
    )
    assert types.rejects == [] and services.rejects == []
    assert types.summary == {"approved": 16}  # Cooper approved the full list (2026-11-08)
    assert services.summary == {"approved": services.rows_in}  # Cooper (D-042)
    no_descriptor = conn.execute(
        text("SELECT count(*) FROM ref.code WHERE system = 'CPT' AND descriptor IS NOT NULL")
    ).scalar()
    assert no_descriptor == 0  # code numbers only (D-002)


def test_search_by_service_near_a_place(conn: Connection, world: LocalStore) -> None:
    result = search(
        conn,
        world,
        latitude=LAS_VEGAS[0],
        longitude=LAS_VEGAS[1],
        radius_miles=Decimal(25),
        service_slug="synthetic-service",
    )
    assert result.codes == ("CPT 99999",) and result.unit == "per_service"
    names = [f.name for f in result.facilities]
    assert names == ["SYNTHETIC VALLEY MEDICAL CENTER", "SYNTHETIC DESERT HOSPITAL"]
    near, other = result.facilities
    assert near.status == "prices" and near.distance_miles == Decimal("0.0")
    assert {(p.price_type, p.amount) for p in near.prices} >= {("gross", Decimal("100.10"))}
    assert other.status == "no_published_prices" and other.prices == ()
    assert "hospital" in near.provider_types
    only_spas = search(
        conn,
        world,
        latitude=LAS_VEGAS[0],
        longitude=LAS_VEGAS[1],
        radius_miles=Decimal(25),
        service_slug="synthetic-service",
        provider_type="medical_spa",
    )
    assert only_spas.facilities == ()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"service_slug": "synthetic-proposed"},  # not approved: refused, not used
        {"service_slug": "no-such-service"},
        {"service_slug": "synthetic-service", "code": "99999", "code_system": "CPT"},
        {"service_slug": "synthetic-service", "provider_type": "no_such_type"},
        {"code_system": "CPT", "code": "12345"},  # not in ref.code
        {"service_slug": "synthetic-service", "radius": Decimal(500)},
    ],
)
def test_search_refuses_unknown_or_unapproved_filters(
    conn: Connection, world: LocalStore, kwargs: dict[str, object]
) -> None:
    radius = kwargs.pop("radius", Decimal(25))
    with pytest.raises(SearchError):
        search(
            conn,
            world,
            latitude=LAS_VEGAS[0],
            longitude=LAS_VEGAS[1],
            radius_miles=radius,  # type: ignore[arg-type]
            **kwargs,  # type: ignore[arg-type]
        )


@pytest.fixture()
def client(
    conn: Connection, world: LocalStore, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    def test_conn() -> Iterator[Connection]:
        yield conn

    monkeypatch.setenv("ADMIN_TOKEN", "synthetic-admin-password")
    monkeypatch.setenv("ADMIN_DATABASE_URL", "postgresql+psycopg://unused")
    get_settings.cache_clear()
    app.dependency_overrides[search_routes.get_conn] = test_conn
    app.dependency_overrides[search_routes.get_store] = lambda: world
    app.dependency_overrides[admin_routes.get_admin_conn] = test_conn
    app.dependency_overrides[admin_routes.get_admin_store] = lambda: world
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def test_api_search_returns_amounts_as_strings(client: TestClient) -> None:
    r = client.get(
        "/v1/search",
        params={"lat": "36.17", "lng": "-115.14", "service": "synthetic-service"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    first = body["facilities"][0]
    gross = [p for p in first["prices"] if p["price_type"] == "gross"]
    assert gross[0]["amount"] == "100.1"  # exact value as a string, never a float
    assert gross[0]["price_source"] == "hospital_file" and gross[0]["code"] == "CPT 99999"
    assert body["facilities"][1]["status"] == "no_published_prices"
    assert (
        client.get("/v1/search", params={"lat": "36", "lng": "-115", "service": "nope"}).status_code
        == 422
    )
    services = client.get("/v1/services").json()
    assert [s["slug"] for s in services] == ["synthetic-service"]
    assert "medical_spa" in [t["code"] for t in client.get("/v1/provider-types").json()]


def auth(name: str, password: str = "synthetic-admin-password") -> dict[str, str]:
    return {"Authorization": "Basic " + base64.b64encode(f"{name}:{password}".encode()).decode()}


def test_review_page_approves_with_the_signed_in_name(
    client: TestClient, conn: Connection, tmp_path: Path
) -> None:
    assert client.get("/admin/reviews").status_code == 401
    assert client.get("/admin/reviews", headers=auth("Cooper", "wrong")).status_code == 401
    stage(conn, tmp_path)  # a new file for the same hospital waits for review
    pending = syn501(conn)[0]
    page = client.get("/admin/reviews", headers=auth("Cooper"))
    assert page.status_code == 200 and "SYNTHETIC VALLEY MEDICAL CENTER" in page.text
    assert "Synthetic proposed" in page.text  # proposals listed, not approvable here
    url = f"/admin/reviews/{pending.dataset_version_id}/approve"
    forged = client.post(
        url, headers=auth("Cooper"), content="form_token=nope&note=x", follow_redirects=False
    )
    assert forged.status_code == 403
    token = admin_routes.form_token(pending.dataset_version_id)
    ok = client.post(
        url,
        headers={**auth("Cooper"), "Content-Type": "application/x-www-form-urlencoded"},
        content=f"form_token={token}&note=checked+totals",
        follow_redirects=False,
    )
    assert ok.status_code == 303
    row = conn.execute(
        text(
            "SELECT status::text, reviewed_by, review_note FROM src.dataset_version WHERE id = :d"
        ),
        {"d": pending.dataset_version_id},
    ).one()
    assert tuple(row) == ("published", "Cooper", "checked totals")


def test_review_page_is_off_without_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    monkeypatch.setenv("ADMIN_TOKEN", "")
    get_settings.cache_clear()
    try:
        assert TestClient(app).get("/admin/reviews", headers=auth("Cooper")).status_code == 404
    finally:
        get_settings.cache_clear()


def test_api_role_can_read_catalog_tables(api_engine: Engine) -> None:
    with api_engine.connect() as c:
        c.execute(text("SELECT count(*) FROM ref.provider_type"))
        c.execute(text("SELECT count(*) FROM ref.facility_provider_type"))
        c.execute(text("SELECT count(*) FROM ref.procedure_code"))


def test_search_box_suggestions_use_names_and_approved_words(
    conn: Connection, world: LocalStore
) -> None:
    from procedurescout_core.search import suggest

    stats = catalog.load_synonyms(
        conn,
        "slug,term,source,reviewed_by,reviewed_at\n"
        "synthetic-service,synthetic scope,human,tester,2026-11-08\n"
        "synthetic-service,synthtic typo,ai_suggested,,\n",
    )
    assert stats.summary == {"approved": 1, "proposed": 1}
    assert [s.slug for s in suggest(conn, "SCOPE")] == ["synthetic-service"]
    assert suggest(conn, "synthtic typo") == []  # proposed words are not used
    assert [s.slug for s in suggest(conn, "synthetic s")] == ["synthetic-service"]
    assert suggest(conn, "x") == []  # too short
    assert "synthetic-proposed" not in [s.slug for s in suggest(conn, "synthetic")]


def test_committed_synonyms_load_approved(conn: Connection) -> None:
    catalog.load_provider_types(conn, (ROOT / "data/reference/provider_types.csv").read_text())
    catalog.load_services(conn, (ROOT / "data/reference/service_catalog.csv").read_text())
    stats = catalog.load_synonyms(conn, (ROOT / "data/reference/service_synonyms.csv").read_text())
    assert stats.rejects == [] and stats.summary == {"approved": stats.rows_in}  # Cooper


def test_zip_lookup(client: TestClient, conn: Connection) -> None:
    conn.execute(
        text(
            "INSERT INTO ref.county (county_fips, state_code, name, source) "
            "VALUES ('32003', 'NV', 'Synthetic County', 'synthetic') ON CONFLICT DO NOTHING"
        )
    )
    conn.execute(
        text(
            "INSERT INTO ref.zcta (zcta5, state_code, county_fips, crosses_counties, aland_m2, "
            "geom, gazetteer_year, source) VALUES ('89999', 'NV', '32003', false, 1, "
            "CAST(ST_SetSRID(ST_MakePoint(-115.14, 36.17), 4326) AS geography), 2026, 'synthetic')"
        )
    )
    r = client.get("/v1/places/zip/89999").json()
    assert (r["state"], r["lat"][:5], r["lng"][:7]) == ("NV", "36.17", "-115.14")
    assert client.get("/v1/places/zip/00000").status_code == 404
    assert client.get("/v1/places/zip/abc").status_code == 422


def test_facilities_near(client: TestClient) -> None:
    r = client.get(
        "/v1/facilities/near",
        params={"lat": "36.17", "lng": "-115.14", "provider_type": "hospital"},
    )
    assert r.status_code == 200, r.text
    names = [f["name"] for f in r.json()]
    assert names == ["SYNTHETIC VALLEY MEDICAL CENTER", "SYNTHETIC DESERT HOSPITAL"]  # Reno is out
    assert r.json()[0]["distance_miles"] == "0.0" and "prices" not in r.json()[0]
    bad = {"lat": "36.17", "lng": "-115.14", "provider_type": "no_such_type"}
    assert client.get("/v1/facilities/near", params=bad).status_code == 422
    far = {"lat": "36.17", "lng": "-115.14", "radius_miles": "500"}
    assert client.get("/v1/facilities/near", params=far).status_code == 422


def test_facility_page_endpoints(client: TestClient, conn: Connection) -> None:
    near = client.get("/v1/facilities/near", params={"lat": "36.17", "lng": "-115.14"}).json()
    fid = near[0]["facility_id"]
    d = client.get(f"/v1/facilities/{fid}")
    assert d.status_code == 200, d.text
    assert d.json()["name"] == "SYNTHETIC VALLEY MEDICAL CENTER"
    assert d.json()["prices_published_at"] is not None
    p = client.get(f"/v1/facilities/{fid}/prices", params={"service": "synthetic-service"})
    assert p.status_code == 200, p.text
    body = p.json()
    assert body["codes"] == ["CPT 99999"] and body["unit"] == "per_service"
    assert ("gross", "100.1") in {(x["price_type"], x["amount"]) for x in body["prices"]}
    other = near[1]["facility_id"]  # nearby, nothing published: no prices, never guessed
    assert (
        client.get(
            f"/v1/facilities/{other}/prices", params={"service": "synthetic-service"}
        ).json()["prices"]
        == []
    )
    bad = client.get(f"/v1/facilities/{fid}/prices", params={"service": "synthetic-proposed"})
    assert bad.status_code == 422  # unapproved service refused
    assert client.get("/v1/facilities/not-a-uuid").status_code == 404
    assert client.get("/v1/facilities/00000000-0000-4000-8000-000000000000").status_code == 404


def test_city_places(client: TestClient) -> None:
    rows = client.get("/v1/places/cities", params={"state": "NV"}).json()
    assert rows and all(r["state"] == "NV" and r["facilities"] >= 1 for r in rows)
    first = rows[0]
    one = client.get(f"/v1/places/city/nv/{first['slug']}")
    assert one.status_code == 200 and one.json()["city"] == first["city"]
    assert client.get("/v1/places/city/nv/no-such-town").status_code == 404
    assert client.get("/v1/places/city/nv/Bad Slug!").status_code == 404
    assert client.get("/v1/places/cities", params={"state": "N1"}).status_code == 422
