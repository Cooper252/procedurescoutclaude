"""Owner analytics (Cooper, 2026-11-12): daily totals, no cookies, no addresses."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from procedurescout_core import site_stats
from tests.conftest import as_role
from tests.test_portal_api import ADMIN, client  # noqa: F401  (fixture)


def test_visits_are_counted_once_per_visitor_per_day_without_addresses(conn: Connection) -> None:
    a = site_stats.visitor_code("synthetic-secret-123456", date(2026, 11, 12), "203.0.113.5", "UA")
    b = site_stats.visitor_code("synthetic-secret-123456", date(2026, 11, 13), "203.0.113.5", "UA")
    assert a != b and len(a) == 64  # a different code the next day: no following people
    phone = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile"
    with as_role(conn, "ps_portal") as c:  # what the live site uses
        for page in ("home", "search", "search"):
            site_stats.record_visit(
                c, page=page, lang="es", user_agent=phone, referrer="https://www.google.com/x?q=1",
                own_host="procedurescout.com", visitor=a,
            )  # fmt: skip
        site_stats.record_visit(
            c, page="facility", lang="en", user_agent="Desktop", referrer=None,
            own_host="procedurescout.com", visitor=None,
        )  # fmt: skip
        site_stats.bump(c, "search", "insurance")
    got = {
        (str(m), str(k)): int(n)
        for m, k, n in conn.execute(
            text("SELECT metric, key, count FROM stats.site_daily WHERE day = current_date")
        ).all()
    }
    assert got[("page_view", "search")] == 2 and got[("page_view", "home")] == 1
    assert got[("visitor", "")] == 1  # one person, three pages
    assert got[("device", "phone")] == 1 and got[("language", "es")] == 1
    assert got[("referrer", "google.com")] == 3  # the site's name only, never the address
    assert site_stats.referrer_host("https://procedurescout.com/search", "procedurescout.com") == ""
    stored = conn.execute(text("SELECT count(*) FROM stats.visitor_seen")).scalar()
    assert stored == 1  # a one-day code, not an address


def test_owner_sees_the_analytics_page(client: TestClient, conn: Connection) -> None:  # noqa: F811
    with as_role(conn, "ps_portal") as c:
        site_stats.bump(c, "search", "cash", by=3)
    r = client.get("/admin/analytics?days=7", headers=ADMIN)
    assert r.status_code == 200, r.text
    for words in ("Visitors", "Most searched", "Price files published", "Provider accounts"):
        assert words in r.text
    d = site_stats.dashboard(conn, 7)
    assert d["site"]["search"] == [("cash", 3)]
