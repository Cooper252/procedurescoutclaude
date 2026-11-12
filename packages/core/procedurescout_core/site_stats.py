"""Site analytics: daily totals only, no cookies, no addresses (migration 0026).

Cooper (2026-11-12) wants to see visitors, searches, the most searched
services and everything about providers. Unique visitors are counted with a
code that is only good for one day (see visitor_code), so nobody can be
followed across days.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import date
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import Connection, text

PAGES = frozenset(
    {
        "home", "search", "facility", "help_paying", "bill", "bundles", "learn", "prices",
        "providers", "provider_portal", "how_it_works", "legal", "review", "other",
    }
)  # fmt: skip
METRICS = frozenset(
    {
        "page_view", "visitor", "device", "language", "referrer", "search",
        "search_no_prices", "email_sent", "whole_cost",
    }
)  # fmt: skip
_KEY_OK = re.compile(r"^[a-z0-9:._-]{0,120}$")


def bump(conn: Connection, metric: str, key: str = "", by: int = 1) -> None:
    if metric not in METRICS:
        raise ValueError(f"not a site metric: {metric}")
    key = key.lower()[:120]
    if not _KEY_OK.match(key):
        key = "other"
    conn.execute(
        text(
            """
            INSERT INTO stats.site_daily (day, metric, key, count)
            VALUES (current_date, :m, :k, :n)
            ON CONFLICT (day, metric, key) DO UPDATE SET count = stats.site_daily.count + :n
            """
        ),
        {"m": metric, "k": key, "n": by},
    )


def visitor_code(secret: str, day: date, ip: str, user_agent: str) -> str:
    """A one-way code for one visitor on one day. The key includes the date, so
    the same visitor gets an unrelated code tomorrow."""
    daily_key = hmac.new(secret.encode(), f"visitors:{day.isoformat()}".encode(), "sha256")
    return hmac.new(daily_key.digest(), f"{ip}|{user_agent}".encode(), hashlib.sha256).hexdigest()


def device_of(user_agent: str) -> str:
    ua = user_agent.lower()
    if "ipad" in ua or "tablet" in ua:
        return "tablet"
    if "mobi" in ua or "iphone" in ua or "android" in ua:
        return "phone"
    return "computer"


def referrer_host(referrer: str | None, own_host: str) -> str:
    """The referring site's name only ('google.com'), 'direct' when none, and
    nothing at all for links inside our own site."""
    if not referrer:
        return "direct"
    host = (urlparse(referrer).hostname or "").lower()
    if not host:
        return "direct"
    if own_host and (host == own_host or host.endswith("." + own_host)):
        return ""
    return host[4:] if host.startswith("www.") else host


def record_visit(
    conn: Connection,
    *,
    page: str,
    lang: str,
    user_agent: str,
    referrer: str | None,
    own_host: str,
    visitor: str | None,
) -> None:
    page = page if page in PAGES else "other"
    bump(conn, "page_view", page)
    new_today = False
    if visitor:
        new_today = (
            conn.execute(
                text(
                    "INSERT INTO stats.visitor_seen (day, visitor) VALUES (current_date, :v) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"v": visitor},
            ).rowcount
            == 1
        )
    if new_today:  # once per visitor per day
        prune_visitors(conn)
        bump(conn, "visitor")
        bump(conn, "device", device_of(user_agent))
        bump(conn, "language", "es" if lang == "es" else "en")
    ref = referrer_host(referrer, own_host)
    if ref and (new_today or ref != "direct"):
        bump(conn, "referrer", ref)


def prune_visitors(conn: Connection) -> int:
    """Forget the day codes from before yesterday."""
    return conn.execute(
        text("DELETE FROM stats.visitor_seen WHERE day < current_date - 1")
    ).rowcount


def _rows(conn: Connection, sql: str, **kw: Any) -> list[tuple[Any, ...]]:
    return [tuple(r) for r in conn.execute(text(sql), kw).all()]


def dashboard(conn: Connection, days: int) -> dict[str, Any]:
    """Everything on the owner's analytics page, for the last `days` days."""
    days = max(1, min(days, 3650))
    since = {"d": days}
    site = _rows(
        conn,
        "SELECT metric, key, sum(count) FROM stats.site_daily "
        "WHERE day > current_date - :d GROUP BY metric, key ORDER BY 3 DESC",
        **since,
    )
    by: dict[str, list[tuple[str, int]]] = {}
    for metric, key, n in site:
        by.setdefault(str(metric), []).append((str(key), int(n)))
    daily = _rows(
        conn,
        """
        SELECT day,
               coalesce(sum(count) FILTER (WHERE metric = 'visitor'), 0),
               coalesce(sum(count) FILTER (WHERE metric = 'page_view'), 0),
               coalesce(sum(count) FILTER (WHERE metric = 'search'), 0)
        FROM stats.site_daily WHERE day > current_date - :d GROUP BY day ORDER BY day DESC
        """,
        **since,
    )
    top_services = _rows(
        conn,
        """
        SELECT s.service_key, coalesce(p.consumer_name, s.service_key), sum(s.count)
        FROM stats.search_daily s
        LEFT JOIN ref.procedure p ON 'svc:' || p.slug = s.service_key
        WHERE s.day > current_date - :d
        GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 25
        """,
        **since,
    )
    top_states = _rows(
        conn,
        """
        SELECT z.state_code, sum(s.count)
        FROM stats.search_daily s
        CROSS JOIN LATERAL (SELECT state_code FROM ref.zcta ORDER BY geom <-> s.geom LIMIT 1) z
        WHERE s.day > current_date - :d
        GROUP BY 1 ORDER BY 2 DESC LIMIT 15
        """,
        **since,
    )
    places = _rows(
        conn,
        """
        SELECT count(*),
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM ref.facility_provider_type t
                                WHERE t.facility_id = f.id AND t.provider_type = 'hospital')),
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM price.published_file p
                                WHERE p.facility_id = f.id)),
               count(DISTINCT f.state_code)
        FROM ref.facility f WHERE f.status = 'active'
        """,
    )[0]
    files = _rows(
        conn,
        "SELECT count(*), coalesce(sum(rows), 0), count(DISTINCT state_code), max(published_at) "
        "FROM price.published_file",
    )[0]
    files_new = _rows(
        conn,
        "SELECT count(*) FROM price.published_file "
        "WHERE published_at > now() - make_interval(days => :d)",
        **since,
    )[0][0]
    by_state = _rows(
        conn,
        "SELECT state_code, count(*), sum(rows) FROM price.published_file "
        "GROUP BY 1 ORDER BY 2 DESC",
    )
    by_type = _rows(
        conn,
        """
        SELECT t.provider_type, coalesce(pt.name, t.provider_type), count(DISTINCT t.facility_id)
        FROM ref.facility_provider_type t
        LEFT JOIN ref.provider_type pt ON pt.code = t.provider_type
        GROUP BY 1, 2 ORDER BY 3 DESC
        """,
    )
    providers = _rows(
        conn,
        """
        SELECT
          (SELECT count(*) FROM prov.account WHERE disabled_at IS NULL),
          (SELECT count(*) FROM prov.account WHERE created_at > now() - make_interval(days => :d)),
          (SELECT count(DISTINCT facility_id) FROM prov.membership WHERE status = 'active'),
          (SELECT count(*) FROM prov.membership WHERE status = 'pending'),
          (SELECT count(*) FROM prov.profile WHERE status = 'published'),
          (SELECT count(*) FROM prov.profile WHERE status = 'pending_review'),
          (SELECT count(*) FROM prov.listing_price WHERE status = 'published'),
          (SELECT count(*) FROM prov.listing_price WHERE status = 'pending_review'),
          (SELECT count(*) FROM prov.listing_price
            WHERE created_at > now() - make_interval(days => :d)),
          (SELECT count(*) FROM prov.offer WHERE status = 'published'),
          (SELECT count(*) FROM prov.review WHERE status = 'published'),
          (SELECT count(*) FROM prov.review WHERE status = 'pending_moderation'),
          (SELECT count(*) FROM prov.listing_request WHERE status = 'pending'),
          (SELECT count(*) FROM prov.price_report WHERE resolved_at IS NULL)
        """,
        **since,
    )[0]
    return {
        "days": days,
        "site": by,
        "daily": daily,
        "top_services": top_services,
        "top_states": top_states,
        "places": places,
        "files": files,
        "files_new": files_new,
        "files_by_state": by_state,
        "by_type": by_type,
        "providers": providers,
    }
