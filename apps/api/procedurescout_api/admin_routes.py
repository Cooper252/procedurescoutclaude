"""Review page (ADM-01): approve or reject staged hospital price datasets.

Off unless ADMIN_TOKEN and ADMIN_DATABASE_URL are set. Interim sign-in: the
browser asks for a name and the admin password (HTTP Basic); the name is the
reviewer recorded on every decision. Multi-factor sign-in replaces this before
the site is public (ADM-02). Each form carries a token derived from the
password and the dataset id, so another site cannot submit a decision on the
reviewer's behalf.

The page shows what the automatic checks found for each hospital (prices,
refusals, flags, the file's own date, problems) and the proposed services and
provider types waiting for approval (those are approved in the catalog files).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import uuid
from collections.abc import Iterator
from typing import Annotated
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import Engine

from procedurescout_core.db_url import sqlalchemy_url
from procedurescout_core.object_store import ObjectStore, open_store
from procedurescout_ingest import publish

from .settings import get_settings

router = APIRouter(prefix="/admin", tags=["admin"], include_in_schema=False)
_engine: Engine | None = None


def get_admin_conn() -> Iterator[Connection]:
    global _engine
    settings = get_settings()
    if not settings.admin_database_url:
        raise HTTPException(status_code=404)
    if _engine is None:
        _engine = create_engine(sqlalchemy_url(settings.admin_database_url))
    with _engine.begin() as conn:
        yield conn


def get_admin_store() -> ObjectStore:
    return open_store(*get_settings().store_args())


def _basic_reviewer(request: Request) -> str:
    """Development only: name + shared password (HTTP Basic). Never in production."""
    settings = get_settings()
    token = settings.admin_token
    challenge = {"WWW-Authenticate": 'Basic realm="ProcedureScout review"'}
    header = request.headers.get("authorization", "")
    if not token or settings.environment == "production":
        raise HTTPException(status_code=401, detail="Sign in at /providers/sign-in first.")
    if not header.lower().startswith("basic "):
        raise HTTPException(status_code=401, headers=challenge)
    try:
        name, _, password = base64.b64decode(header[6:]).decode().partition(":")
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=401, headers=challenge) from exc
    if not hmac.compare_digest(password.encode(), token.encode()) or len(name.strip()) < 2:
        raise HTTPException(status_code=401, headers=challenge)
    return name.strip()


def reviewer(request: Request, conn: Annotated[Connection, Depends(get_admin_conn)]) -> str:
    """The signed-in reviewer (ADM-02): a staff member signed in with the email
    link and authenticator app, recorded by email on every decision. The shared
    password works only outside production, for local development."""
    from procedurescout_core.portal_auth import session_account, staff_role

    account = session_account(conn, request.cookies.get("ps_session"))
    if account is not None:
        role = staff_role(conn, account)
        if role is not None:
            return account.email
        if not account.mfa_passed:
            raise HTTPException(status_code=401, detail="Enter your authenticator code first.")
        raise HTTPException(status_code=403, detail="This account can't use the review pages.")
    return _basic_reviewer(request)


Reviewer = Annotated[str, Depends(reviewer)]
AdminConn = Annotated[Connection, Depends(get_admin_conn)]
AdminStore = Annotated[ObjectStore, Depends(get_admin_store)]


def form_token(dataset_id: str) -> str:
    settings = get_settings()
    key = (settings.portal_secret or settings.admin_token).encode()
    return hmac.new(key, dataset_id.encode(), hashlib.sha256).hexdigest()


async def _form(request: Request) -> dict[str, str]:
    body = (await request.body()).decode()
    return {k: v[0] for k, v in parse_qs(body, keep_blank_values=True).items()}


def _check_form(form: dict[str, str], dataset_id: str) -> None:
    if not hmac.compare_digest(form.get("form_token", ""), form_token(dataset_id)):
        raise HTTPException(status_code=403, detail="form expired; reload the page")


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Price review</title>
<style>
body{{font-family:system-ui,sans-serif;margin:16px;max-width:1100px;color:#1a1a1a}}
table{{border-collapse:collapse;width:100%;margin:12px 0}}
th,td{{border-bottom:1px solid #ddd;padding:8px;text-align:left;vertical-align:top}}
.warn{{color:#9a3412}} .muted{{color:#666}} form{{display:inline-block;margin:2px 0}}
input[type=text]{{width:220px}} button{{padding:4px 10px}}
</style></head><body>
<h1>Hospital prices waiting for review</h1>
<p class="muted">Signed in as {who}. One decision covers a hospital's whole file. Approving
publishes it to the site; rejecting needs a reason. Every decision is recorded.</p>
{message}
{datasets}
<h2>Proposed items waiting for approval</h2>
<p class="muted">Not used until approved. Tell Claude which to approve (they are kept in the
data/reference catalog, bundle and assistance files).</p>
{proposals}
</body></html>"""


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


@router.get("")
@router.get("/")
def admin_home() -> RedirectResponse:
    """Staff typing /admin land on the price review page (sign-in is checked there)."""
    return RedirectResponse("/admin/reviews", status_code=303)


@router.get("/reviews", response_class=HTMLResponse)
def reviews_page(who: Reviewer, conn: AdminConn, done: str | None = None) -> HTMLResponse:
    rows = []
    for p in publish.pending_reviews(conn):
        load = p.summary
        refused = load.get("rows_rejected", 0)
        flags = load.get("quality_flags", {}) or {}
        flag_text = ", ".join(f"{k}: {v:,}" for k, v in sorted(flags.items())) or "none"
        token = form_token(p.dataset_version_id)
        rows.append(
            "<tr>"
            f"<td><strong>{_esc(p.facility_name)}</strong><br><span class=muted>"
            f"CCN {_esc(p.ccn)}</span></td>"
            f"<td>{p.rows:,}</td>"
            f"<td{' class=warn' if refused else ''}>{int(refused):,}</td>"
            f"<td>{_esc(p.last_updated_raw)}</td>"
            f"<td>{_esc(flag_text)}</td>"
            f"<td{' class=warn' if p.file_problems else ''}>{_esc(p.file_problems or 'none')}</td>"
            "<td>"
            f"<form method=post action='/admin/reviews/{p.dataset_version_id}/approve'>"
            f"<input type=hidden name=form_token value='{token}'>"
            "<input type=text name=note placeholder='What you checked (optional)'> "
            "<button>Approve</button></form><br>"
            f"<form method=post action='/admin/reviews/{p.dataset_version_id}/reject'>"
            f"<input type=hidden name=form_token value='{token}'>"
            "<input type=text name=reason placeholder='Reason (required)' required> "
            "<button>Reject</button></form>"
            "</td></tr>"
        )
    datasets = (
        "<table><tr><th>Hospital</th><th>Prices</th><th>Refused</th><th>File date</th>"
        "<th>Flags</th><th>Problems</th><th>Decision</th></tr>" + "".join(rows) + "</table>"
        if rows
        else "<p>Nothing is waiting for review.</p>"
    )
    proposals = conn.execute(
        text(
            "SELECT 'Service', consumer_name || ' (' || unit || ')' FROM ref.procedure "
            "WHERE review_state = 'proposed' UNION ALL "
            "SELECT 'Provider type', name FROM ref.provider_type WHERE review_state = 'proposed' "
            "UNION ALL "
            "SELECT 'Financial assistance', f.name || ': ' || coalesce(string_agg("
            "t.benefit || ' up to ' || t.max_percent_fpg::text || '% of guideline', '; '), '') "
            "|| ' (' || p.policy_url || ')' "
            "FROM ref.assistance_policy p JOIN ref.facility f ON f.id = p.facility_id "
            "LEFT JOIN ref.assistance_tier t ON t.policy_id = p.id "
            "WHERE p.review_state = 'proposed' GROUP BY f.name, p.policy_url "
            "UNION ALL "
            "SELECT 'Bundle', consumer_name FROM ref.procedure "
            "WHERE kind = 'bundle' AND review_state = 'proposed' "
            "ORDER BY 1, 2"
        )
    ).all()
    proposal_html = (
        "<table><tr><th>Kind</th><th>Name</th></tr>"
        + "".join(f"<tr><td>{_esc(k)}</td><td>{_esc(n)}</td></tr>" for k, n in proposals)
        + "</table>"
        if proposals
        else "<p>None.</p>"
    )
    message = f"<p><strong>{_esc(done)}</strong></p>" if done else ""
    return HTMLResponse(
        PAGE.format(who=_esc(who), message=message, datasets=datasets, proposals=proposal_html)
    )


def _dataset(dataset_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(dataset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404) from exc


@router.post("/reviews/{dataset_id}/approve")
async def approve(
    dataset_id: str, request: Request, who: Reviewer, conn: AdminConn, store: AdminStore
) -> RedirectResponse:
    form = await _form(request)
    _check_form(form, dataset_id)
    try:
        publish.approve(conn, _dataset(dataset_id), who, store, note=form.get("note") or None)
    except publish.ReviewError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse("/admin/reviews?done=Published", status_code=303)


@router.post("/reviews/{dataset_id}/reject")
async def reject(
    dataset_id: str, request: Request, who: Reviewer, conn: AdminConn
) -> RedirectResponse:
    form = await _form(request)
    _check_form(form, dataset_id)
    try:
        publish.reject(conn, _dataset(dataset_id), who, form.get("reason", ""))
    except publish.ReviewError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse("/admin/reviews?done=Rejected", status_code=303)
