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
from procedurescout_core import provider_prices as prices
from procedurescout_core import reviews

from .admin_routes import AdminConn, AdminStore, Reviewer, _esc, _form, form_token

router = APIRouter(prefix="/admin/providers", tags=["admin"], include_in_schema=False)
KINDS = (
    "listingrequest",
    "suggestion",
    "pricereport",
    "claim",
    "profile",
    "media",
    "review",
    "reply",
    "report",
    "listing",
    "offer",
    "package",
)
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
<h2>Practices asking to be added</h2>
<p class="muted">Check the practice is real (website, phone, state license) before approving.
Approving creates its page and makes the requester its owner.</p>{listingrequests}
<h2>New services from price lists</h2>
<p class="muted">A practice priced something we don't list. Add it to the service list
(data/reference/service_catalog.csv) if it's a real, common service, then mark it added;
otherwise decline with a reason.</p>{suggestions}
<h2>Wrong-price reports</h2>{pricereports}
<h2>People asking to manage a page</h2>{claims}
<h2>Provider prices</h2>
<p class="muted">New prices and changes to live prices (the live price stays until you approve).
Check that the price is believable for the service.</p>{listings}
<h2>Specials</h2>{offers}
<h2>Packages</h2>{packages}
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


def _report_buttons(item: str) -> str:
    token = form_token(f"pricereport:{item}")
    return (
        f"<form method=post action='/admin/providers/pricereport/{item}/approve'>"
        f"<input type=hidden name=form_token value='{token}'>"
        "<select name=reason><option value=fixed>fixed</option>"
        "<option value=sent_to_provider>sent to provider</option>"
        "<option value=no_change>no change needed</option></select> "
        "<button>Done</button></form>"
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

    def dollars(v: object) -> str:
        return "" if v is None else f"${v:,.2f}"

    listings = []
    for r in conn.execute(
        text(
            "SELECT lp.id, f.name, "
            "coalesce(p.consumer_name, lp.code_system::text || ' ' || lp.code), "
            "lp.quantity, lp.regular_price, lp.proposed_price, lp.status "
            "FROM prov.listing_price lp "
            "JOIN ref.facility f ON f.id = lp.facility_id LEFT JOIN ref.procedure p "
            "ON p.id = lp.procedure_id WHERE lp.status = 'pending_review' "
            "OR lp.proposed_price IS NOT NULL ORDER BY coalesce(lp.proposed_at, lp.updated_at)"
        )
    ).all():
        if r[5] is not None:
            big = r[4] and (r[5] > r[4] * 2 or r[5] * 2 < r[4])
            what = f"Change: {dollars(r[4])} → <strong>{dollars(r[5])}</strong>" + (
                " <span class=warn>(more than doubles or halves)</span>" if big else ""
            )
        else:
            what = f"New: <strong>{dollars(r[4])}</strong>"
        sessions = f" · {r[3]} sessions" if r[3] > 1 else ""
        listings.append(
            f"<tr><td>{_esc(r[1])}</td><td>{_esc(r[2])}{sessions}</td><td>{what}</td>"
            f"<td>{_buttons('listing', str(r[0]))}</td></tr>"
        )
    offers = [
        f"<tr><td>{_esc(r[1])}</td><td>{_esc(r[2])}</td><td>Regular {dollars(r[3])} · "
        f"{_esc(r[4].replace('_', ' '))} {dollars(r[5]) or ''}{'' if r[6] is None else f'{r[6]}%'}"
        f"{dollars(r[7])} · {_esc(r[8].replace('_', ' '))} · {r[9]} to {r[10] or 'no end'}"
        f"<br><span class=muted>{_esc(r[11])}</span></td>"
        f"<td>{_buttons('offer', str(r[0]))}</td></tr>"
        for r in conn.execute(
            text(
                "SELECT o.id, f.name, coalesce(p.consumer_name, lp.code), lp.regular_price, "
                "o.kind, o.offer_price, o.percent_off, o.amount_off, o.who, o.starts_on, "
                "o.ends_on, o.terms "
                "FROM prov.offer o JOIN prov.listing_price lp ON lp.id = o.listing_price_id "
                "JOIN ref.facility f ON f.id = lp.facility_id LEFT JOIN ref.procedure p "
                "ON p.id = lp.procedure_id WHERE o.status = 'pending_review' ORDER BY o.created_at"
            )
        ).all()
    ]
    packages = []
    for r in conn.execute(
        text(
            "SELECT k.id, f.name, k.name, k.price, k.description FROM prov.package k "
            "JOIN ref.facility f ON f.id = k.facility_id WHERE k.status = 'pending_review' "
            "ORDER BY k.created_at"
        )
    ).all():
        items = ", ".join(
            f"{_esc(i[0])}{' x' + str(i[1]) if i[1] > 1 else ''}"
            for i in conn.execute(
                text(
                    "SELECT coalesce(p.consumer_name, i.code_system::text || ' ' || i.code), "
                    "i.quantity FROM prov.package_item i LEFT JOIN ref.procedure p "
                    "ON p.id = i.procedure_id WHERE i.package_id = :k"
                ),
                {"k": r[0]},
            ).all()
        )
        packages.append(
            f"<tr><td>{_esc(r[1])}</td><td><strong>{_esc(r[2])}</strong> {dollars(r[3])}"
            f"<br>{items}<br><span class=muted>{_esc(r[4])}</span></td>"
            f"<td>{_buttons('package', str(r[0]))}</td></tr>"
        )
    listingrequests = [
        f"<tr><td><strong>{_esc(r[1])}</strong><br>{_esc(r[2])}, {_esc(r[3])}, {_esc(r[4])} "
        f"{_esc(r[5])}<br><span class=muted>{_esc(r[6])} · {_esc(r[7])} · NPI {_esc(r[8] or '—')}"
        f"</span></td><td>{_esc(r[9])}<br><span class=muted>{_esc(r[10])} · {_esc(r[11])}</span>"
        f"</td><td>{_buttons('listingrequest', str(r[0]))}</td></tr>"
        for r in conn.execute(
            text(
                "SELECT q.id, q.name, q.address_line1, q.city, q.state_code, q.zip5, q.phone, "
                "q.website, q.npi, t.name, a.email, q.note FROM prov.listing_request q "
                "JOIN ref.provider_type t ON t.code = q.provider_type "
                "JOIN prov.account a ON a.id = q.account_id WHERE q.status = 'pending' "
                "ORDER BY q.created_at"
            )
        ).all()
    ]
    pricereports = [
        f"<tr><td>{_esc(r[1])}</td><td>{_esc(r[2].replace('_', ' '))}"
        f"{' · ' + _esc(r[3]) if r[3] else ''}{' · shown $' + _esc(r[4]) if r[4] else ''}"
        f"<br><span class=muted>{_esc(r[5])}</span></td>"
        f"<td>{_report_buttons(str(r[0]))}</td></tr>"
        for r in conn.execute(
            text(
                "SELECT p.id, f.name, p.problem, p.service_key, p.price_shown, p.details "
                "FROM prov.price_report p JOIN ref.facility f ON f.id = p.facility_id "
                "WHERE p.resolved_at IS NULL ORDER BY p.created_at LIMIT 200"
            )
        ).all()
    ]
    suggestions = [
        f"<tr><td>{_esc(r[1])}</td><td><strong>{_esc(r[2])}</strong>"
        f"{' · ' + _esc(r[3]) + ' ' + _esc(r[4]) if r[3] else ''} · ${_esc(r[5])}</td>"
        f"<td>{_buttons('suggestion', str(r[0]), 'Added to our list', 'Decline')}</td></tr>"
        for r in conn.execute(
            text(
                "SELECT s.id, f.name, s.name, s.code_system, s.code, s.price "
                "FROM prov.service_suggestion s JOIN ref.facility f ON f.id = s.facility_id "
                "WHERE s.status = 'proposed' ORDER BY s.created_at LIMIT 200"
            )
        ).all()
    ]
    return HTMLResponse(
        PAGE.format(
            suggestions=_table(["Provider", "Service and price", "Decision"], suggestions),
            listingrequests=_table(["Practice", "Type and requester", "Decision"], listingrequests),
            pricereports=_table(["Provider", "Report", "Decision"], pricereports),
            listings=_table(["Provider", "Service", "Price", "Decision"], listings),
            offers=_table(["Provider", "Service", "Special", "Decision"], offers),
            packages=_table(["Provider", "Package", "Decision"], packages),
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
        if kind == "listingrequest":
            from procedurescout_core import listing_requests

            listing_requests.decide(conn, item, who, ok, reason)
        elif kind == "suggestion":
            if not ok and not reason:
                raise ValueError("a reason is needed to decline")
            conn.execute(
                text(
                    "UPDATE prov.service_suggestion SET status = :s, review_note = :n, "
                    "reviewed_at = now() WHERE id = CAST(:i AS uuid) AND status = 'proposed'"
                ),
                {"s": "added" if ok else "declined", "n": reason, "i": item},
            )
        elif kind == "pricereport":
            from procedurescout_core import price_reports

            price_reports.resolve(conn, item, who, reason or "no_change")
        elif kind == "claim":
            account_id, facility_id = item.split(".")
            auth.decide_membership(conn, account_id, facility_id, who, ok)
        elif kind == "profile":
            pages.review_profile(conn, item, who, ok, reason)
        elif kind == "media":
            pages.review_media(conn, item, who, ok)
        elif kind == "review":
            reviews.moderate(conn, item, who, publish=ok, reason=reason)
        elif kind == "listing":
            prices.review_listing(conn, item, who, ok, reason)
        elif kind == "offer":
            prices.review_offer(conn, item, who, ok, reason)
        elif kind == "package":
            prices.review_package(conn, item, who, ok, reason)
        elif kind == "reply":
            reviews.review_reply(conn, item, who, ok)
        else:
            reviews.resolve_report(conn, item, who, None if ok else reason)
    except (pages.PageError, reviews.ReviewError, prices.ProviderPriceError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse(
        f"/admin/providers?done={kind}+{'approved' if ok else 'rejected'}", status_code=303
    )
