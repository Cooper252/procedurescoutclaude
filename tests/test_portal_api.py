"""Provider portal over HTTP (D-050): sign-in cookie, authenticator, claiming,
homepage edits, images, reviews, counts and the review page. Synthetic data,
rolled back after each test."""

from __future__ import annotations

import base64
import contextlib
import struct
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from procedurescout_api import admin_routes, portal_routes, search_routes
from procedurescout_api.main import app
from procedurescout_api.settings import get_settings
from procedurescout_core import portal_auth as auth
from procedurescout_core.object_store import LocalStore

from .conftest import make_facility

H = {"X-ProcedureScout": "1", "User-Agent": "Mozilla/5.0 synthetic test"}
ADMIN = {
    "Authorization": "Basic " + base64.b64encode(b"Synthetic Reviewer:synthetic-admin").decode()
}


class _FakeEngine:
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    @contextlib.contextmanager
    def begin(self) -> Iterator[Connection]:
        yield self.conn


@pytest.fixture()
def client(
    conn: Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    store = LocalStore(tmp_path)

    def test_conn() -> Iterator[Connection]:
        yield conn

    monkeypatch.setenv("PORTAL_SECRET", "synthetic-portal-secret-123")
    monkeypatch.setenv("PORTAL_DEV_LINKS", "true")
    monkeypatch.setenv("SITE_URL", "https://example.test")
    monkeypatch.setenv("ADMIN_TOKEN", "synthetic-admin")
    monkeypatch.setenv("ADMIN_DATABASE_URL", "postgresql+psycopg://unused")
    get_settings.cache_clear()
    monkeypatch.setattr(portal_routes, "portal_engine", lambda: _FakeEngine(conn))
    app.dependency_overrides[search_routes.get_conn] = test_conn
    app.dependency_overrides[search_routes.get_store] = lambda: store
    app.dependency_overrides[portal_routes.get_portal_conn] = test_conn
    app.dependency_overrides[admin_routes.get_admin_conn] = test_conn
    app.dependency_overrides[admin_routes.get_admin_store] = lambda: store
    try:
        yield TestClient(app, base_url="https://testserver")
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def _admin() -> TestClient:
    """A separate browser for the review page (shared password, development only)."""
    return TestClient(app, base_url="https://testserver")


def _facility(conn: Connection) -> str:
    fid = make_facility(conn, "Synthetic Portal Clinic")
    conn.execute(
        text(
            "UPDATE ref.facility SET website = 'https://synthetic-clinic.test', "
            "website_reviewed_by = 'test', website_reviewed_at = now() WHERE id = :f"
        ),
        {"f": fid},
    )
    return str(fid)


def _sign_in(client: TestClient, email: str) -> dict[str, Any]:
    r = client.post("/v1/portal/sign-in", json={"email": email}, headers=H)
    assert r.status_code == 202, r.text
    token = r.json()["dev_link"].split("#", 1)[1]
    r = client.post("/v1/portal/sign-in/verify", json={"token": token}, headers=H)
    assert r.status_code == 200, r.text
    assert "httponly" in r.headers["set-cookie"].lower()
    setup = client.post("/v1/portal/mfa/setup", headers=H).json()
    r = client.post(
        "/v1/portal/mfa/verify", json={"code": auth.totp_code(setup["secret"])}, headers=H
    )
    assert r.status_code == 200 and r.json()["mfa_passed"], r.text
    return dict(r.json())


def test_changes_need_the_custom_header_and_a_session(client: TestClient, conn: Connection) -> None:
    fid = _facility(conn)
    assert client.post("/v1/portal/sign-in", json={"email": "a@b.test"}).status_code == 403
    assert client.get("/v1/portal/me").status_code == 401
    r = client.put(f"/v1/portal/facilities/{fid}/profile", json={"profile": {}}, headers=H)
    assert r.status_code == 401


def test_full_provider_journey(client: TestClient, conn: Connection) -> None:
    fid = _facility(conn)
    _sign_in(client, "owner@synthetic-clinic.test")
    hits = client.get("/v1/portal/facilities/search", params={"q": "Synthetic Portal"}).json()
    assert any(h["facility_id"] == fid for h in hits)
    claim = client.post("/v1/portal/claims", json={"facility_id": fid}, headers=H).json()
    assert claim["status"] == "active" and claim["role"] == "owner"

    body = {
        "profile": {
            "about": "Synthetic clinic.",
            "website_url": "synthetic-clinic.test",
            "hours": {"mon": "08:00-17:00"},
            "languages": ["Spanish"],
        },
        "submit": True,
    }
    r = client.put(f"/v1/portal/facilities/{fid}/profile", json=body, headers=H)
    assert r.status_code == 200 and r.json()["status"] == "pending_review", r.text
    assert client.get(f"/v1/facilities/{fid}/page").json()["profile"] is None

    png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + struct.pack(">II", 4, 4) + b"\x08\x06"
    r = client.post(
        f"/v1/portal/facilities/{fid}/media",
        params={"kind": "logo"},
        content=png,
        headers={**H, "Content-Type": "image/png"},
    )
    assert r.status_code == 201, r.text
    media_id = r.json()["id"]
    assert client.get(f"/v1/portal/facilities/{fid}/media/{media_id}").content == png
    bad = client.post(
        f"/v1/portal/facilities/{fid}/media",
        params={"kind": "logo"},
        content=b"<svg onload=alert(1)>",
        headers=H,
    )
    assert bad.status_code == 422

    # a person approves on the review page
    admin = _admin().get("/admin/providers", headers=ADMIN)
    assert admin.status_code == 200 and "Synthetic clinic." in admin.text
    pid = conn.execute(
        text("SELECT id FROM prov.profile WHERE facility_id = :f"), {"f": fid}
    ).scalar_one()
    for kind, item in (("profile", str(pid)), ("media", media_id)):
        tok = admin_routes.form_token(f"{kind}:{item}")
        r = _admin().post(
            f"/admin/providers/{kind}/{item}/approve",
            data={"form_token": tok},
            headers=ADMIN,
            follow_redirects=False,
        )
        assert r.status_code == 303, r.text
    page = client.get(f"/v1/facilities/{fid}/page").json()
    assert page["claimed"] and page["profile"]["about"] == "Synthetic clinic."
    logo = client.get(page["logo_url"].removeprefix("/api"))
    assert logo.status_code == 200 and logo.content == png
    assert logo.headers["content-type"] == "image/png"

    # invite a patient; they review; a person publishes; the owner replies
    link = client.post(f"/v1/portal/facilities/{fid}/invites", headers=H).json()["link"]
    token = link.split("#", 1)[1]
    assert (
        client.post("/v1/reviews/check", json={"token": token}).json()["kind"] == "provider_invite"
    )
    r = client.post(
        "/v1/reviews",
        json={
            "token": token,
            "rating": 5,
            "body": "Clear prices and the bill matched the quote.",
            "display_name": "R.",
            "price_matched": True,
            "visited": True,
            "independent": True,
        },
    )
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    tok = admin_routes.form_token(f"review:{rid}")
    _admin().post(f"/admin/providers/review/{rid}/approve", data={"form_token": tok}, headers=ADMIN)
    page = client.get(f"/v1/facilities/{fid}/page").json()
    assert page["reviews"]["count"] == 1 and page["reviews"]["average"] == "5.0"
    r = client.post(
        f"/v1/portal/facilities/{fid}/reviews/{rid}/reply",
        json={"body": "Thank you for the kind words."},
        headers=H,
    )
    assert r.json() == {"status": "pending_review", "privacy_warning": False}

    # counts: a page view and a click; dashboard hides small numbers
    for kind in ("page_view", "website_click"):
        assert (
            client.post(
                "/v1/events", json={"facility_id": fid, "kind": kind}, headers=H
            ).status_code
            == 204
        )
    dash = client.get(f"/v1/portal/facilities/{fid}/stats", params={"days": 30}).json()
    assert dash["counts"]["page_view"]["value"] is None and dash["small_number"] == 10


def test_email_review_request_and_bad_tokens(client: TestClient, conn: Connection) -> None:
    fid = _facility(conn)
    r = client.post("/v1/reviews/request", json={"facility_id": fid, "email": "p@synthetic.test"})
    assert r.status_code == 202 and r.json()["dev_link"].startswith("https://example.test/review#")
    again = client.post(
        "/v1/reviews/request", json={"facility_id": fid, "email": "p@synthetic.test"}
    )
    assert again.status_code == 202  # same answer either way
    assert client.post("/v1/reviews/check", json={"token": "x" * 40}).status_code == 410


def test_dev_links_never_shown_in_production(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    r = client.post("/v1/portal/sign-in", json={"email": "prod@synthetic.test"}, headers=H)
    assert r.status_code == 202 and r.json()["dev_link"] is None


def test_unpublished_images_are_not_served(client: TestClient, conn: Connection) -> None:
    fid = _facility(conn)
    r = client.get(f"/v1/media/media/{fid}/{fid}.png")
    assert r.status_code == 404
    assert client.get("/v1/media/../../etc/passwd").status_code == 404


def test_provider_prices_over_http(client: TestClient, conn: Connection) -> None:
    from tests.test_catalog_offers import load_all

    load_all(conn)
    fid = _facility(conn)
    _sign_in(client, "owner@synthetic-clinic.test")
    client.post("/v1/portal/claims", json={"facility_id": fid}, headers=H)
    r = client.post(
        f"/v1/portal/facilities/{fid}/prices",
        json={"service_slug": "teeth-cleaning-adult", "regular_price": "129.5"},
        headers=H,
    )
    assert r.status_code == 201, r.text
    lid = r.json()["id"]
    bad = client.post(
        f"/v1/portal/facilities/{fid}/prices",
        json={"service_slug": "teeth-cleaning-adult", "regular_price": "1.234"},
        headers=H,
    )
    assert bad.status_code == 422
    r = client.post(
        f"/v1/portal/facilities/{fid}/prices/{lid}/specials",
        json={
            "kind": "amount_off",
            "who": "new_patients",
            "value": "30",
            "starts_on": "2026-01-01",
            "ends_on": None,
            "terms": None,
        },
        headers=H,
    )
    assert r.status_code == 201, r.text
    oid = r.json()["id"]
    assert client.get(f"/v1/facilities/{fid}/provider-prices").json()["listings"] == []
    page = _admin().get("/admin/providers", headers=ADMIN).text
    assert "New: <strong>$129.50</strong>" in page
    for kind, item in (("listing", lid), ("offer", oid)):
        tok = admin_routes.form_token(f"{kind}:{item}")
        r = _admin().post(
            f"/admin/providers/{kind}/{item}/approve",
            data={"form_token": tok},
            headers=ADMIN,
            follow_redirects=False,
        )
        assert r.status_code == 303, r.text
    pub = client.get(f"/v1/facilities/{fid}/provider-prices").json()["listings"]
    assert pub[0]["regular_price"] == "129.5" and pub[0]["special"]["price"] == "99.5"
    mine = client.get(f"/v1/portal/facilities/{fid}/prices").json()
    assert mine["listings"][0]["status"] == "published"
    assert client.delete(f"/v1/portal/facilities/{fid}/prices/{lid}", headers=H).status_code == 204
    assert client.get(f"/v1/facilities/{fid}/provider-prices").json()["listings"] == []


def test_review_pages_need_staff_with_authenticator(
    client: TestClient, conn: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    from procedurescout_core.portal_auth import add_staff

    _sign_in(client, "notstaff@synthetic.test")
    assert client.get("/admin/providers").status_code == 403  # signed in, not staff
    staff = _admin()
    add_staff(conn, "reviewer@synthetic.test", "reviewer", "Synthetic Admin")
    _sign_in(staff, "reviewer@synthetic.test")
    page = staff.get("/admin/providers")
    assert page.status_code == 200 and "reviewer@synthetic.test" in page.text
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    assert _admin().get("/admin/providers", headers=ADMIN).status_code == 401  # no shared password
