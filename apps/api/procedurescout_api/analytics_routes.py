"""The owner's analytics page at /admin/analytics (Cooper, 2026-11-12: "how many
visitors, how many searches, most searched ... and everything about the
providers"). Admins only. Numbers come from daily totals (site_stats.py); no
visitor is identifiable."""

from __future__ import annotations

import html
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from procedurescout_core import site_stats

from .admin_routes import AdminConn, Reviewer

router = APIRouter(prefix="/admin", tags=["admin"])

PERIODS = ((1, "Today"), (7, "7 days"), (30, "30 days"), (90, "90 days"), (3650, "All time"))


def _esc(v: object) -> str:
    return html.escape("" if v is None else str(v))


def _n(v: Any) -> str:
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return _esc(v)


def _table(headers: list[str], rows: list[list[Any]], empty: str = "Nothing yet.") -> str:
    if not rows:
        return f"<p class=muted>{_esc(empty)}</p>"
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def _tile(label: str, value: Any, note: str = "") -> str:
    return (
        f"<div class=tile><span class=label>{_esc(label)}</span>"
        f"<span class=value>{_n(value)}</span>"
        + (f"<span class=muted>{_esc(note)}</span>" if note else "")
        + "</div>"
    )


@router.get("/analytics", response_class=HTMLResponse)
def analytics(who: Reviewer, conn: AdminConn, request: Request, days: int = 30) -> HTMLResponse:
    role = conn.execute(
        text(
            "SELECT s.role FROM prov.staff s JOIN prov.account a ON a.id = s.account_id "
            "WHERE lower(a.email) = lower(:e)"
        ),
        {"e": who},
    ).scalar()
    if "@" in who and role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can see the analytics.")
    d = site_stats.dashboard(conn, days)
    site: dict[str, list[tuple[str, int]]] = d["site"]

    def total(metric: str) -> int:
        return sum(n for _, n in site.get(metric, []))

    def keyed(metric: str, limit: int = 20) -> list[list[Any]]:
        return [[_esc(k or "-"), _n(n)] for k, n in site.get(metric, [])[:limit]]

    period_links = " · ".join(
        f"<strong>{label}</strong>" if n == d["days"] else f"<a href='?days={n}'>{label}</a>"
        for n, label in PERIODS
    )
    places, files, prov = d["places"], d["files"], d["providers"]
    searches = total("search")
    no_prices = total("search_no_prices")
    tiles_people = "".join(
        [
            _tile("Visitors", total("visitor"), "unique per day, added up"),
            _tile("Page views", total("page_view")),
            _tile("Searches", searches),
            _tile(
                "Searches with no prices",
                no_prices,
                f"{round(100 * no_prices / searches)}% of searches" if searches else "",
            ),
            _tile("Price emails sent", total("email_sent")),
            _tile("Whole-cost panels opened", total("whole_cost")),
        ]
    )
    tiles_data = "".join(
        [
            _tile("Places listed", places[0]),
            _tile("Hospitals", places[1]),
            _tile("Places with published prices", places[2]),
            _tile("States with places", places[3]),
            _tile("Price files published", files[0], f"{_n(d['files_new'])} new in this period"),
            _tile("Prices in published files", files[1]),
            _tile("States with prices", files[2]),
        ]
    )
    tiles_prov = "".join(
        [
            _tile("Provider accounts", prov[0], f"{_n(prov[1])} new in this period"),
            _tile("Claimed pages", prov[2], f"{_n(prov[3])} waiting for approval"),
            _tile("Published provider pages", prov[4], f"{_n(prov[5])} waiting for review"),
            _tile("Provider prices live", prov[6], f"{_n(prov[7])} waiting for review"),
            _tile("Provider prices added", prov[8], "in this period"),
            _tile("Specials live", prov[9]),
            _tile("Reviews live", prov[10], f"{_n(prov[11])} waiting for moderation"),
            _tile("Practices asking to be added", prov[12], "waiting"),
            _tile("Wrong-price reports open", prov[13]),
        ]
    )
    daily = _table(
        ["Day", "Visitors", "Page views", "Searches"],
        [[_esc(r[0]), _n(r[1]), _n(r[2]), _n(r[3])] for r in d["daily"][:31]],
    )
    top = _table(
        ["Service or code", "Searches"],
        [[_esc(r[1]), _n(r[2])] for r in d["top_services"]],
    )
    states = _table(["State", "Searches"], [[_esc(r[0]), _n(r[1])] for r in d["top_states"]])
    by_state = _table(
        ["State", "Price files", "Prices"],
        [[_esc(r[0]), _n(r[1]), _n(r[2])] for r in d["files_by_state"]],
    )
    by_type = _table(["Kind of place", "Places"], [[_esc(r[1]), _n(r[2])] for r in d["by_type"]])
    last = files[3].strftime("%Y-%m-%d %H:%M UTC") if files[3] else "never"
    body = f"""
<h1>ProcedureScout analytics</h1>
<p class=muted>Signed in as {_esc(who)}. Period: {period_links}. Counts are daily totals;
no cookies or addresses are stored, so a person who visits on 3 days counts 3 times.</p>
<h2>People using the site</h2><div class=tiles>{tiles_people}</div>
<div class=cols>
<div><h3>Pages</h3>{_table(["Page", "Views"], keyed("page_view"))}</div>
<div><h3>Devices</h3>{_table(["Device", "Visitors"], keyed("device"))}
<h3>Language</h3>{_table(["Language", "Visitors"], keyed("language"))}</div>
<div><h3>Where visitors came from</h3>{_table(["Site", "Visits"], keyed("referrer"))}</div>
</div>
<div class=cols>
<div><h3>Most searched</h3>{top}</div>
<div><h3>Searches by kind</h3>{_table(["Kind", "Searches"], keyed("search"))}
<h3>Searches by state</h3>{states}</div>
<div><h3>Searched, but no prices found</h3>
{_table(["Service or code", "Searches"], keyed("search_no_prices"))}</div>
</div>
<h3>By day</h3>{daily}
<h2>Prices and places</h2><div class=tiles>{tiles_data}</div>
<p class=muted>Last price file published: {_esc(last)}.</p>
<div class=cols><div><h3>Prices by state</h3>{by_state}</div>
<div><h3>Places by kind</h3>{by_type}</div></div>
<h2>Providers</h2><div class=tiles>{tiles_prov}</div>
<p><a href="/admin/reviews">Price review</a> · <a href="/admin/providers">Provider review</a></p>
"""
    return HTMLResponse(PAGE.replace("{body}", body))


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Analytics</title>
<style>
body{font-family:system-ui,sans-serif;margin:16px;max-width:1200px;color:#1a1a1a}
h2{margin-top:32px;border-bottom:2px solid #0b6e75;padding-bottom:4px}
table{border-collapse:collapse;width:100%;margin:8px 0}
th,td{border-bottom:1px solid #ddd;padding:6px 8px;text-align:left}
td:last-child,th:last-child{text-align:right}
.muted{color:#666;font-size:14px}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px}
.tile{border:1px solid #ddd;border-radius:10px;padding:10px 12px;display:grid;gap:2px}
.tile .label{font-size:13px;color:#555}
.tile .value{font-size:26px;font-weight:700}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}
a{color:#0b6e75}
</style></head><body>{body}</body></html>"""
