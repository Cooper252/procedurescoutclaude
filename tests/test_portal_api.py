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
from sqlalchemy import Connection, Engine, text

from procedurescout_api import admin_routes, portal_routes, search_routes
from procedurescout_api.main import app
from procedurescout_api.settings import get_settings
from procedurescout_core import portal_auth as auth
from procedurescout_core.object_store import LocalStore

from .conftest import as_role, make_facility

H = {"X-ProcedureScout": "1", "User-Agent": "Mozilla/5.0 synthetic test"}
ADMIN = {
    "Authorization": "Basic " + base64.b64encode(b"Synthetic Reviewer:synthetic-admin").decode()
}


class _FakeEngine:
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    @contextlib.contextmanager
    def begin(self) -> Iterator[Connection]:
        with as_role(self.conn, "ps_portal") as c:
            yield c


@pytest.fixture()
def client(
    conn: Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    store = LocalStore(tmp_path)

    def test_conn() -> Iterator[Connection]:  # the review pages: owner, as hosted
        yield conn

    def api_conn() -> Iterator[Connection]:
        with as_role(conn, "ps_api") as c:
            yield c

    def portal_conn() -> Iterator[Connection]:
        with as_role(conn, "ps_portal") as c:
            yield c

    monkeypatch.setenv("PORTAL_SECRET", "synthetic-portal-secret-123")
    monkeypatch.setenv("PORTAL_DEV_LINKS", "true")
    monkeypatch.setenv("SITE_URL", "https://example.test")
    monkeypatch.setenv("ADMIN_TOKEN", "synthetic-admin")
    monkeypatch.setenv("ADMIN_DATABASE_URL", "postgresql+psycopg://unused")
    get_settings.cache_clear()
    monkeypatch.setattr(portal_routes, "portal_engine", lambda: _FakeEngine(conn))
    app.dependency_overrides[search_routes.get_conn] = api_conn
    app.dependency_overrides[search_routes.get_store] = lambda: store
    app.dependency_overrides[portal_routes.get_portal_conn] = portal_conn
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


def test_owner_email_becomes_admin_on_first_sign_in(
    client: TestClient, conn: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Go-live check (2026-11-12): no command line needed to make Cooper a
    reviewer; the review pages also use the hosting's owner connection."""
    _sign_in(client, "someone@synthetic.test")
    monkeypatch.setenv("OWNER_EMAILS", "Owner@Synthetic.test, other@synthetic.test")
    get_settings.cache_clear()
    staff = _admin()
    assert staff.get("/admin/providers").status_code == 401  # not signed in
    # a browser goes to the account page (sign-in / authenticator) instead of JSON
    r = staff.get("/admin/providers", headers={"Accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/providers/account"
    me = _sign_in(staff, "owner@synthetic.test")
    assert me["staff"] is True  # the account page shows the review links
    page = staff.get("/admin/providers")
    assert page.status_code == 200 and "owner@synthetic.test" in page.text
    role = conn.execute(
        text(
            "SELECT s.role FROM prov.staff s JOIN prov.account a ON a.id = s.account_id "
            "WHERE a.email = 'owner@synthetic.test'"
        )
    ).scalar_one()
    assert role == "admin"
    other = _admin()
    assert _sign_in(other, "stranger@synthetic.test")["staff"] is False
    assert other.get("/admin/providers").status_code == 403  # not on the list
    page = other.get("/admin/providers", headers={"Accept": "text/html"})
    assert page.status_code == 403 and "can't use the review pages" in page.text
    from procedurescout_api.settings import Settings

    monkeypatch.delenv("ADMIN_DATABASE_URL", raising=False)
    s = Settings(database_url="postgres://o:p@h:5432/db", _env_file=None)  # type: ignore[call-arg]
    assert s.admin_database_url == "postgresql+psycopg://o:p@h:5432/db"


def test_price_list_template_and_upload(client: TestClient, conn: Connection) -> None:
    """Cooper (2026-11-11): one template for dental + orthodontics + oral surgery,
    and an upload that checks every line before anything goes to review."""
    import csv
    import io

    from tests.test_catalog_offers import load_all

    load_all(conn)
    fid = _facility(conn)
    _sign_in(client, "owner@synthetic-clinic.test")
    client.post("/v1/portal/claims", json={"facility_id": fid}, headers=H)
    r = client.get("/v1/portal/price-template?types=dental_office,orthodontics,oral_surgery")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text.lstrip("﻿"))))
    sections = {x["section"] for x in rows}
    assert {"Dental office", "Orthodontist (braces and aligners)", "Oral surgeon"} <= sections
    slugs = [x["service_id"] for x in rows if x["service_id"]]
    assert len(slugs) == len(set(slugs))  # a shared service appears once
    assert "braces-full-adult" in slugs and "wisdom-tooth-full-bony" in slugs
    # fill in a few lines, one mistake, one of their own services
    for x in rows:
        if x["service_id"] == "teeth-cleaning-adult":
            x["your_price"] = "$129.50"
            x["copay"] = "standard"
        if x["service_id"] == "ortho-consultation":
            x.update(your_price="75", in_person_or_online="online")
        if x["service_id"] == "braces-full-adult":
            x["your_price"] = "5,900"
        if x["service_id"] == "night-guard":
            x["your_price"] = "12.345"
    own = [x for x in rows if x["section"] == "Your own services"]
    own[0].update(service="Smile makeover consultation", your_price="0.01")
    own[1].update(service="Exam", codes="CDT D0120", your_price="60")
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
    url = f"/v1/portal/facilities/{fid}/price-upload"
    first = client.post(url, json={"csv": out.getvalue()}, headers=H).json()
    assert first["counts"]["ready"] == 4  # cleaning, braces, online consult, exam by its code
    assert first["counts"]["suggestion"] == 1 and first["counts"]["error"] == 1
    bad = next(x for x in first["lines"] if x["status"] == "error")
    assert "2 decimal places" in bad["message"]
    refused = client.post(url, json={"csv": out.getvalue(), "confirm": True}, headers=H)
    assert refused.status_code == 422  # problems must be fixed first
    for x in rows:
        if x["service_id"] == "night-guard":
            x["your_price"] = "350"
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
    done = client.post(url, json={"csv": out.getvalue(), "confirm": True}, headers=H).json()
    assert done["applied"] == {"sent_for_review": 5, "suggestions": 1}
    mine = client.get(f"/v1/portal/facilities/{fid}/prices").json()["listings"]
    assert {x["status"] for x in mine} == {"pending_review"} and len(mine) == 5
    by = {x["service_slug"]: x for x in mine}
    assert by["teeth-cleaning-adult"]["copay_kind"] == "standard"
    assert by["ortho-consultation"]["delivery"] == "online"
    assert client.get(f"/v1/facilities/{fid}/provider-prices").json()["listings"] == []
    kept = conn.execute(text("SELECT name, price FROM prov.service_suggestion")).all()
    assert [(k[0], str(k[1])) for k in kept] == [("Smile makeover consultation", "0.01")]
    sid = conn.execute(text("SELECT id FROM prov.service_suggestion")).scalar_one()
    assert "Smile makeover consultation" in _admin().get("/admin/providers", headers=ADMIN).text
    tok = admin_routes.form_token(f"suggestion:{sid}")
    r = _admin().post(
        f"/admin/providers/suggestion/{sid}/approve",
        data={"form_token": tok},
        headers=ADMIN,
        follow_redirects=False,
    )
    assert r.status_code == 303
    status = conn.execute(text("SELECT status FROM prov.service_suggestion")).scalar_one()
    assert status == "added"


def test_sign_in_email_is_really_sent_after_the_row_is_saved(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First live sign-in (2026-11-11): FastAPI runs background tasks before the
    request's connection closes, so the queued email wasn't saved yet and was
    never sent. This uses real commits (no rolled-back test connection)."""
    sent: list[tuple[str, str]] = []

    class Capture:
        def send(self, to: str, subject: str, body: str) -> None:
            sent.append((to, subject))

    monkeypatch.setenv("PORTAL_SECRET", "synthetic-portal-secret-123")
    monkeypatch.setenv("SITE_URL", "https://example.test")
    get_settings.cache_clear()
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    # the portal role, as hosted (2026-11-12: owner-only tests hid a
    # "permission denied" that made every email go out again every 5 minutes)
    portal = create_engine(
        make_url(str(engine.url.render_as_string(hide_password=False))).set(
            username="ps_portal", password="ps_portal_dev"
        )
    )
    monkeypatch.setattr(portal_routes, "portal_engine", lambda: portal)
    monkeypatch.setattr(type(get_settings()), "mail_sender", lambda self: Capture())
    email = "commit-check@synthetic-clinic.test"
    try:
        r = TestClient(app, base_url="https://testserver").post(
            "/v1/portal/sign-in", json={"email": email}, headers=H
        )
        assert r.status_code == 202, r.text
        with engine.connect() as c:
            rows = c.execute(
                text("SELECT to_email, sent_at FROM prov.outbox WHERE to_email = :e"),
                {"e": email},
            ).all()
        assert sent and sent[0][0] == email, (r.json(), rows)
        assert rows[0][1] is not None  # marked sent, so it is never sent again
        portal_routes.send_mail_soon()  # the 5-minute retry
        assert len(sent) == 1
    finally:
        portal.dispose()
        with engine.begin() as c:
            c.execute(text("DELETE FROM prov.outbox WHERE to_email = :e"), {"e": email})
            c.execute(
                text(
                    "DELETE FROM prov.login_token WHERE account_id IN "
                    "(SELECT id FROM prov.account WHERE email = :e)"
                ),
                {"e": email},
            )
            c.execute(text("DELETE FROM prov.account WHERE email = :e"), {"e": email})
        get_settings.cache_clear()


def test_waiting_emails_are_retried_every_few_minutes(monkeypatch: pytest.MonkeyPatch) -> None:
    """An email that couldn't go out at once is tried again by the API itself."""
    from procedurescout_api import main

    calls: list[int] = []
    monkeypatch.setattr(main, "MAIL_RETRY_SECONDS", 0)
    monkeypatch.setattr(main, "send_mail_soon", lambda: calls.append(1))
    with TestClient(main.app) as c:
        deadline = __import__("time").monotonic_ns() + 2_000_000_000
        while not calls and __import__("time").monotonic_ns() < deadline:
            c.get("/healthz")
    assert calls
