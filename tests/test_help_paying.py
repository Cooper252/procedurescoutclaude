"""Community health centers and public coverage limits for "Help paying" (HELP-01)."""

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from procedurescout_api import search_routes
from procedurescout_api.main import app
from procedurescout_core import assistance
from procedurescout_ingest.reference import catalog
from procedurescout_ingest.reference.health_centers import HealthCenterError, load_health_centers

ROOT = Path(__file__).resolve().parent.parent / "data/reference"
HRSA_CSV = (
    "Site Name,Health Center Name,Site Address,Site City,Site State Abbreviation,"
    "Site Postal Code,Site Telephone Number,Site Web Address,"
    "Geocoding Artifact Address Primary X Coordinate,"
    "Geocoding Artifact Address Primary Y Coordinate,Site Status Description,BPHC Assigned Number\n"
    "Synthetic Clinic A,Synthetic Health Org,1 Test St,Las Vegas,NV,89101-1234,555-0101,"
    "https://synthetic.example,-115.14,36.17,Active,SYN-1\n"
    "Synthetic Clinic B,Synthetic Health Org,2 Test St,Reno,NV,89501,555-0102,,-119.81,39.53,"
    "Active,SYN-2\n"
    "Synthetic Clinic Closed,Synthetic Health Org,3 Test St,Las Vegas,NV,89101,,,-115.15,36.18,"
    "Inactive,SYN-3\n"
    "Synthetic Clinic Elsewhere,Other,4 Test St,Phoenix,AZ,85001,,,-112.07,33.45,Active,SYN-4\n"
)


def test_health_center_sites_load_for_one_state(conn: Connection) -> None:
    stats = load_health_centers(conn, HRSA_CSV, "NV")
    assert stats.rows_loaded == 2 and stats.summary["not_active"] == 1
    near = assistance.health_centers_near(
        conn, latitude=Decimal("36.17"), longitude=Decimal("-115.14"), radius_miles=Decimal(25)
    )
    assert [h.name for h in near] == ["Synthetic Clinic A"]  # Reno is far; closed site left out
    assert near[0].zip5 == "89101" and near[0].distance_miles == Decimal("0.0")


def test_health_center_file_with_unknown_columns_is_refused(conn: Connection) -> None:
    with pytest.raises(HealthCenterError, match="headers seen"):
        load_health_centers(conn, "Name,Town\nX,Y\n", "NV")


def _guidelines(conn: Connection) -> None:
    catalog.load_poverty_guidelines(conn, (ROOT / "poverty_guidelines.csv").read_text())


def test_coverage_limits_say_may_qualify_only_when_approved(conn: Connection) -> None:
    _guidelines(conn)
    stats = catalog.load_coverage_limits(conn, (ROOT / "coverage_limits.csv").read_text())
    assert stats.rejects == [] and stats.summary == {"approved": stats.rows_in}  # Cooper
    kw = {"state_code": "NV", "household_size": 2, "annual_income": Decimal(25000)}
    conn.execute(
        text(
            "UPDATE ref.coverage_limit SET review_state = 'proposed', reviewed_by = NULL, "
            "reviewed_at = NULL"
        )
    )
    assert assistance.coverage(conn, **kw) == []  # proposed limits are not used (rule 10)
    catalog.load_coverage_limits(conn, (ROOT / "coverage_limits.csv").read_text())
    found = {(m.program, m.group) for m in assistance.coverage(conn, **kw)}
    # 2026 guideline for 2 people is $21,640; $25,000 is about 116%
    assert found == {("medicaid", "adults"), ("medicaid", "children"), ("medicaid", "pregnant")}
    middle = assistance.coverage(
        conn, state_code="NV", household_size=1, annual_income=Decimal(40000)
    )
    assert [(m.program, m.limit_text) for m in middle] == [
        ("marketplace_savings", "about $22,024 to $63,840 a year for 1 person")
    ]
    assert (
        assistance.coverage(conn, state_code="NV", household_size=1, annual_income=Decimal(90000))
        == []
    )


@pytest.fixture()
def client(conn: Connection) -> Iterator[TestClient]:
    def test_conn() -> Iterator[Connection]:
        yield conn

    app.dependency_overrides[search_routes.get_conn] = test_conn
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_api_health_centers_near(client: TestClient, conn: Connection) -> None:
    load_health_centers(conn, HRSA_CSV, "NV")
    r = client.get("/v1/health-centers/near", params={"lat": "36.17", "lng": "-115.14"})
    assert r.status_code == 200, r.text
    assert [h["name"] for h in r.json()] == ["Synthetic Clinic A"]
    bad = client.get(
        "/v1/health-centers/near", params={"lat": "36", "lng": "-115", "radius_miles": "500"}
    )
    assert bad.status_code == 422
