"""Review page for provider pages (D-050): claims, homepage changes, images,
reviews, replies and reports. Same sign-in as the price review page (interim,
ADM-02). Every decision records who made it."""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import text

from procedurescout_core import portal_auth as auth
from procedurescout_core import provider_pages as pages
from procedurescout_core import reviews

from .admin_routes import AdminConn, AdminStore, Reviewer, _esc, _form, form_token

router = APIRouter(prefix="/admin/providers", tags=["admin"], include_in_schema=False)
KINDS = ("claim", "profile", "media", "review", "reply", "report")
_ID = re.compile(r"^[0-9a-f-]{36}(\.[0-9a-f-]{36})?$")

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Provider page review</title>
<style>
body{{font-family:system-ui,sans-serif;margin:16px;max-width:1100px;color:#1a1a1a}}
table{{border-collapse:collapse;width:100%;margin:12px 0}}
th,td{{border-bottom:1px solid #ddd;padding:8px;text-align:left;vertical-align:top}}
.warn{{color:#9a3412;font-weight:600}} .muted{{color:#666}}
form{{display:inline-block;margin:2px 0}}
input[type=text]{{width:200px}} button{{padding:4px 10px}} img{{max-width:160px;max-height:120px}}
pre{{white-space:pre-wrap;margin:0;font:inherit}}
</style></head><body>
<h1>Provider pages waiting for review</h1>
<p class="muted">Signed in as {who}. Nothing here shows on the site until approved.
<a href="/admin/reviews">Hospital price review</a></p>
{message}
<h2>People asking to manage a page</h2>{claims}
<h2>Homepage changes</h2>{profiles}
<h2>Logos and photos</h2>{media}
<h2>New reviews</h2>
<p class="muted">Publish unless it breaks a posting rule. Never remove a review only because
it is negative (FTC rule, 16 CFR Part 465).</p>{reviews}
<h2>Provider replies</h2>
<p class="muted">Replies must not confirm that someone was a patient or mention their
care.</p>{replies}
<h2>Reports from providers</h2>{reports}
</body></html>"""

REASONS = "".join(
    f"<option value='{r}'>{r.replace('_', ' ')}</option>" for r in reviews.REMOVAL_REASONS
)


def _buttons(
    kind: str, item: str, approve: str = "Approve", reject: str = "Reject", reason: str = "text"
) -> str:
    token = form_token(f"{kind}:{item}")
    hidden = f"<input type=hidden name=form_token value='{token}'>"
    if reason == "select":
        field = f"<select name=reason>{REASONS}</select>"
    elif reason == "text":
        field = "<input type=text name=reason placeholder='Reason (needed to reject)'>"
    else:
        field = ""
    return (
        f"<form method=post action='/admin/providers/{kind}/{item}/approve'>{hidden}"
        f"<button>{approve}</button></form> "
        f"<form method=post action='/admin/providers/{kind}/{item}/reject'>{hidden}{field} "
        f"<button>{reject}</button></form>"
    )


def _table(head: list[str], rows: list[str]) -> str:
    if not rows:
        return "<p>Nothing waiting.</p>"
    return (
        "<table><tr>"
        + "".join(f"<th>{h}</th>" for h in head)
        + "</tr>"
        + "".join(rows)
        + "</table>"
    )


@router.get("", response_class=HTMLResponse)
def page(who: Reviewer, conn: AdminConn, done: str | None = None) -> HTMLResponse:
    claims = [
        f"<tr><td>{_esc(r[2])}</td><td>{_esc(r[3])}<br><span class=muted>website: "
        f"{_esc(r[4] or 'none on file')}</span></td><td>{_esc(r[5])}</td><td>{_esc(r[6])}</td>"
        f"<td>{_buttons('claim', f'{r[0]}.{r[1]}', reason='none')}</td></tr>"
        for r in conn.execute(
            text(
                "SELECT m.account_id, m.facility_id, a.email, f.name, f.website, m.role, m.note "
                "FROM prov.membership m JOIN prov.account a ON a.id = m.account_id "
                "JOIN ref.facility f ON f.id = m.facility_id WHERE m.status = 'pending' "
                "ORDER BY m.created_at"
            )
        ).all()
    ]
    profiles = []
    for r in conn.execute(
        text(
            "SELECT p.id, f.name, p.about, p.website_url, p.booking_url, p.phone, p.hours, "
            "p.languages, p.accessibility, p.insurance_note, p.social_urls FROM prov.profile p "
            "JOIN ref.facility f ON f.id = p.facility_id WHERE p.status = 'pending_review' "
            "ORDER BY p.submitted_at"
        )
    ).all():
        detail = (
            f"<pre>{_esc(r[2])}</pre><span class=muted>Website {_esc(r[3])} · Booking {_esc(r[4])}"
            f" · Phone {_esc(r[5])} · Hours {_esc(json.dumps(r[6]))} · Languages "
            f"{_esc(', '.join(r[7] or []))} · Access {_esc(', '.join(r[8] or []))} · Insurance "
            f"{_esc(r[9])} · Social {_esc(', '.join(r[10] or []))}</span>"
        )
        profiles.append(
            f"<tr><td>{_esc(r[1])}</td><td>{detail}</td>"
            f"<td>{_buttons('profile', str(r[0]))}</td></tr>"
        )
    media = [
        f"<tr><td>{_esc(r[1])}</td><td>{_esc(r[2])}</td>"
        f"<td><img src='/admin/providers/media/{r[0]}' alt=''><br>{_esc(r[3])}</td>"
        f"<td>{_buttons('media', str(r[0]), reason='none')}</td></tr>"
        for r in conn.execute(
            text(
                "SELECT m.id, f.name, m.kind, m.alt_text FROM prov.media m JOIN ref.facility f "
                "ON f.id = m.facility_id WHERE m.status = 'pending_review' ORDER BY m.created_at"
            )
        ).all()
    ]
    review_rows = [
        f"<tr><td>{_esc(r[1])}</td><td>{'★' * int(r[2])} <strong>{_esc(r[3])}</strong>"
        f"<pre>{_esc(r[4])}</pre><span class=muted>{_esc(r[5])} · "
        f"{'email confirmed' if r[6] == 'email' else 'invited by provider'}</span></td>"
        f"<td>{_buttons('review', str(r[0]), 'Publish', 'Remove', 'select')}</td></tr>"
        for r in conn.execute(
            text(
                "SELECT r.id, f.name, r.rating, r.title, r.body, r.display_name, r.verification "
                "FROM prov.review r JOIN ref.facility f ON f.id = r.facility_id "
                "WHERE r.status = 'pending_moderation' ORDER BY r.created_at"
            )
        ).all()
    ]
    replies = [
        f"<tr><td>{_esc(r[1])}</td><td><span class=muted>Review: {_esc(r[2][:200])}</span>"
        f"<pre>{_esc(r[3])}</pre>"
        + (
            "<p class=warn>May confirm someone was a patient. Check carefully.</p>"
            if reviews.phi_warning(str(r[3]))
            else ""
        )
        + f"</td><td>{_buttons('reply', str(r[0]), reason='none')}</td></tr>"
        for r in conn.execute(
            text(
                "SELECT rr.review_id, f.name, r.body, rr.body FROM prov.review_reply rr "
                "JOIN prov.review r ON r.id = rr.review_id JOIN ref.facility f "
                "ON f.id = r.facility_id WHERE rr.status = 'pending_review' ORDER BY rr.created_at"
            )
        ).all()
    ]
    reports = [
        f"<tr><td>{_esc(r[1])}</td><td><pre>{_esc(r[2])}</pre></td><td>{_esc(r[3])}</td>"
        f"<td>{_buttons('report', str(r[0]), 'Keep review', 'Remove review', 'select')}</td></tr>"
        for r in conn.execute(
            text(
                "SELECT p.id, f.name, r.body, p.reason FROM prov.review_report p "
                "JOIN prov.review r ON r.id = p.review_id JOIN ref.facility f "
                "ON f.id = r.facility_id WHERE p.resolved_at IS NULL ORDER BY p.created_at"
            )
        ).all()
    ]
    return HTMLResponse(
        PAGE.format(
            who=_esc(who),
            message=f"<p><strong>{_esc(done)}</strong></p>" if done else "",
            claims=_table(["Email", "Page", "Role", "Note", "Decision"], claims),
            profiles=_table(["Provider", "Change", "Decision"], profiles),
            media=_table(["Provider", "Kind", "Image", "Decision"], media),
            reviews=_table(["Provider", "Review", "Decision"], review_rows),
            replies=_table(["Provider", "Reply", "Decision"], replies),
            reports=_table(["Provider", "Review", "Reason given", "Decision"], reports),
        )
    )


@router.get("/media/{media_id}")
def media_file(media_id: str, who: Reviewer, conn: AdminConn, store: AdminStore) -> Response:
    if not _ID.match(media_id) or "." in media_id:
        raise HTTPException(status_code=404)
    row = conn.execute(
        text("SELECT object_key, content_type FROM prov.media WHERE id = CAST(:m AS uuid)"),
        {"m": media_id},
    ).first()
    data = store.get_media(str(row[0])) if row else None
    if row is None or data is None:
        raise HTTPException(status_code=404)
    return Response(
        content=data,
        media_type=str(row[1]),
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/{kind}/{item}/{action}")
async def decide(
    kind: str, item: str, action: str, request: Request, who: Reviewer, conn: AdminConn
) -> RedirectResponse:
    if kind not in KINDS or action not in ("approve", "reject") or not _ID.match(item):
        raise HTTPException(status_code=404)
    form = await _form(request)
    import hmac

    if not hmac.compare_digest(form.get("form_token", ""), form_token(f"{kind}:{item}")):
        raise HTTPException(status_code=403, detail="form expired; reload the page")
    ok = action == "approve"
    reason = (form.get("reason") or "").strip() or None
    try:
        if kind == "claim":
            account_id, facility_id = item.split(".")
            auth.decide_membership(conn, account_id, facility_id, who, ok)
        elif kind == "profile":
            pages.review_profile(conn, item, who, ok, reason)
        elif kind == "media":
            pages.review_media(conn, item, who, ok)
        elif kind == "review":
            reviews.moderate(conn, item, who, publish=ok, reason=reason)
        elif kind == "reply":
            reviews.review_reply(conn, item, who, ok)
        else:
            reviews.resolve_report(conn, item, who, None if ok else reason)
    except (pages.PageError, reviews.ReviewError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse(
        f"/admin/providers?done={kind}+{'approved' if ok else 'rejected'}", status_code=303
    )
