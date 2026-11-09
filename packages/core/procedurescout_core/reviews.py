"""Patient reviews (D-050), following the FTC rule on consumer reviews and
testimonials (16 CFR Part 465).

- Who can review: someone who confirmed their visit through a link. Either we
  email them ("Did you visit ...?", label "Email confirmed"), or the provider
  gives them a one-time link ("Invited by the provider"). No receipts (Cooper,
  Q31). Unclaimed providers can be reviewed too (Q32).
- One review per person per provider. Reviewers confirm they visited and are
  not staff, family or paid.
- Providers can reply and report, never remove. A person decides on reports.
  Removed reviews are counted publicly.
- A person checks every review and reply before it shows (personal health
  details, hate, spam). Replies must not confirm someone was a patient (HIPAA).
"""

from __future__ import annotations

import hashlib
import hmac
import re
import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import Connection, text

from .portal_auth import AuthError, new_token, normalize_email, token_hash

EMAIL_LINK_DAYS = 14
INVITE_LINK_DAYS = 60
MAX_EMAIL_LINKS_PER_DAY = 3
MAX_INVITES_PER_DAY = 200
REMOVAL_REASONS = (
    "off_topic",
    "personal_information",
    "hateful",
    "spam",
    "conflict_of_interest",
    "not_a_patient",
    "other",
)
# Phrases that suggest a reply confirms someone was a patient; the moderator is warned.
_PHI_HINTS = re.compile(
    r"\b(your (visit|appointment|procedure|surgery|treatment|test|results|chart|records)|"
    r"we (saw|treated) you|our records show|on (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",
    re.I,
)


class ReviewError(ValueError):
    """A review action that can't be done (message is safe to show)."""


@dataclass(frozen=True, slots=True)
class ReviewOut:
    id: str
    rating: int
    title: str | None
    body: str
    price_matched: bool | None
    display_name: str
    verification: str
    published_at: str
    reply_body: str | None
    reply_at: str | None


@dataclass(frozen=True, slots=True)
class Summary:
    average: Decimal | None
    count: int
    removed: int
    price_matched_yes: int
    price_matched_answered: int
    stars: tuple[int, int, int, int, int]


def _reviewer_hash(secret: str, facility_id: str, who: str) -> bytes:
    return hmac.new(secret.encode(), f"{facility_id}|{who}".encode(), hashlib.sha256).digest()


def _facility_name(conn: Connection, facility_id: str) -> str:
    try:
        fid = str(uuid.UUID(facility_id))
    except ValueError as exc:
        raise ReviewError("Unknown provider.") from exc
    name = conn.execute(text("SELECT name FROM ref.facility WHERE id = :f"), {"f": fid}).scalar()
    if name is None:
        raise ReviewError("Unknown provider.")
    return str(name)


def start_email_review(
    conn: Connection, facility_id: str, email: str, site_url: str, secret: str
) -> str | None:
    """Email a 'Did you visit?' link. Returns the token (shown only in
    development) or None when limits are reached; the caller answers the same
    either way."""
    name = _facility_name(conn, facility_id)
    try:
        e = normalize_email(email)
    except AuthError as exc:
        raise ReviewError(str(exc)) from exc
    who = _reviewer_hash(secret, facility_id, e)
    already = conn.execute(
        text("SELECT 1 FROM prov.review WHERE facility_id = :f AND reviewer_hash = :h"),
        {"f": facility_id, "h": who},
    ).first()
    recent = conn.execute(
        text(
            "SELECT count(*) FROM prov.outbox WHERE to_email = :e AND purpose = 'review_confirm' "
            "AND created_at > now() - interval '1 day'"
        ),
        {"e": e},
    ).scalar_one()
    if already is not None or int(recent) >= MAX_EMAIL_LINKS_PER_DAY:
        return None
    token, digest = new_token()
    conn.execute(
        text(
            "INSERT INTO prov.review_token (token_hash, facility_id, kind, reviewer_hash, "
            "expires_at) VALUES (:h, :f, 'email', :w, now() + make_interval(days => :d))"
        ),
        {"h": digest, "f": facility_id, "w": who, "d": EMAIL_LINK_DAYS},
    )
    link = f"{site_url.rstrip('/')}/review#{token}"
    conn.execute(
        text(
            "INSERT INTO prov.outbox (to_email, purpose, subject, body) "
            "VALUES (:e, 'review_confirm', :s, :b)"
        ),
        {
            "e": e,
            "s": f"Did you visit {name}?",
            "b": (
                f"You asked to review {name} on ProcedureScout.\n\n"
                f"If you visited, use this link to write your review:\n{link}\n\n"
                f"It works once and expires in {EMAIL_LINK_DAYS} days. If you didn't ask, "
                "ignore this email."
            ),
        },
    )
    return token


def create_invite(conn: Connection, facility_id: str, account_id: str) -> str:
    """A one-time review link the provider gives a patient. The FTC rule means
    providers should invite every patient, not only happy ones; the page says so."""
    _facility_name(conn, facility_id)
    today = conn.execute(
        text(
            "SELECT count(*) FROM prov.review_token WHERE facility_id = :f "
            "AND kind = 'provider_invite' AND created_at > now() - interval '1 day'"
        ),
        {"f": facility_id},
    ).scalar_one()
    if int(today) >= MAX_INVITES_PER_DAY:
        raise ReviewError(f"Up to {MAX_INVITES_PER_DAY} invite links a day.")
    token, digest = new_token()
    conn.execute(
        text(
            "INSERT INTO prov.review_token (token_hash, facility_id, kind, reviewer_hash, "
            "created_by, expires_at) VALUES (:h, :f, 'provider_invite', :w, :a, "
            "now() + make_interval(days => :d))"
        ),
        {"h": digest, "f": facility_id, "w": digest, "a": account_id, "d": INVITE_LINK_DAYS},
    )
    return token


def token_facility(conn: Connection, token: str) -> tuple[str, str, str]:
    """(facility id, name, kind) for a valid, unused review link."""
    row = conn.execute(
        text(
            "SELECT t.facility_id, f.name, t.kind FROM prov.review_token t "
            "JOIN ref.facility f ON f.id = t.facility_id "
            "WHERE t.token_hash = :h AND t.used_at IS NULL AND t.expires_at > now()"
        ),
        {"h": token_hash(token)},
    ).first()
    if row is None:
        raise ReviewError("This review link has expired or was already used.")
    return str(row[0]), str(row[1]), str(row[2])


def submit_review(
    conn: Connection,
    token: str,
    *,
    rating: int,
    body: str,
    display_name: str,
    title: str | None = None,
    price_matched: bool | None = None,
    visited: bool,
    independent: bool,
) -> str:
    if not visited:
        raise ReviewError("Only people who visited can leave a review.")
    if not independent:
        raise ReviewError(
            "Reviews can't come from staff, owners, their families, or anyone paid or "
            "rewarded for a review."
        )
    if not 1 <= rating <= 5:
        raise ReviewError("Choose 1 to 5 stars.")
    body = body.strip()
    if not 20 <= len(body) <= 3000:
        raise ReviewError("Write between 20 and 3,000 characters.")
    name = display_name.strip()
    if not 1 <= len(name) <= 40:
        raise ReviewError("Add a first name or initials (up to 40 characters).")
    t = (title or "").strip() or None
    if t is not None and len(t) > 120:
        raise ReviewError("Keep the title under 120 characters.")
    row = conn.execute(
        text(
            "UPDATE prov.review_token SET used_at = now() WHERE token_hash = :h "
            "AND used_at IS NULL AND expires_at > now() "
            "RETURNING facility_id, kind, reviewer_hash"
        ),
        {"h": token_hash(token)},
    ).first()
    if row is None:
        raise ReviewError("This review link has expired or was already used.")
    exists = conn.execute(
        text("SELECT 1 FROM prov.review WHERE facility_id = :f AND reviewer_hash = :w"),
        {"f": row[0], "w": row[2]},
    ).first()
    if exists is not None:
        raise ReviewError("You've already reviewed this provider.")
    rid = conn.execute(
        text(
            """
            INSERT INTO prov.review (facility_id, rating, title, body, price_matched,
                display_name, verification, reviewer_hash)
            VALUES (:f, :r, :t, :b, :pm, :n, :v, :w) RETURNING id
            """
        ),
        {
            "f": row[0],
            "r": rating,
            "t": t,
            "b": body,
            "pm": price_matched,
            "n": name,
            "v": row[1],
            "w": row[2],
        },
    ).scalar_one()
    return str(rid)


def moderate(
    conn: Connection, review_id: str, moderator: str, publish: bool, reason: str | None = None
) -> None:
    if not publish and reason not in REMOVAL_REASONS:
        raise ReviewError("Choose a reason from the posting rules.")
    done = conn.execute(
        text(
            """
            UPDATE prov.review SET status = :s, removal_reason = :reason,
                moderated_by = :m, moderated_at = now(),
                published_at = CASE WHEN :s = 'published' THEN now() END
            WHERE id = CAST(:id AS uuid) AND status IN ('pending_moderation', 'published')
            RETURNING id
            """
        ),
        {
            "s": "published" if publish else "removed",
            "reason": None if publish else reason,
            "m": moderator,
            "id": review_id,
        },
    ).first()
    if done is None:
        raise ReviewError("That review can't be changed.")


def reply(conn: Connection, review_id: str, facility_id: str, account_id: str, body: str) -> bool:
    """Save a provider reply for review. Returns True when it looks like it may
    confirm someone was a patient (the moderator is warned)."""
    b = body.strip()
    if not 2 <= len(b) <= 1500:
        raise ReviewError("Replies are 2 to 1,500 characters.")
    ok = conn.execute(
        text(
            "SELECT 1 FROM prov.review WHERE id = CAST(:r AS uuid) "
            "AND facility_id = CAST(:f AS uuid) AND status = 'published'"
        ),
        {"r": review_id, "f": facility_id},
    ).first()
    if ok is None:
        raise ReviewError("Unknown review.")
    conn.execute(
        text(
            """
            INSERT INTO prov.review_reply (review_id, body, account_id)
            VALUES (CAST(:r AS uuid), :b, :a)
            ON CONFLICT (review_id) DO UPDATE SET body = EXCLUDED.body,
                account_id = EXCLUDED.account_id, status = 'pending_review',
                reviewed_by = NULL, reviewed_at = NULL, created_at = now()
            """
        ),
        {"r": review_id, "b": b, "a": account_id},
    )
    return bool(_PHI_HINTS.search(b))


def phi_warning(body: str) -> bool:
    return bool(_PHI_HINTS.search(body))


def review_reply(conn: Connection, review_id: str, moderator: str, approve: bool) -> None:
    conn.execute(
        text(
            "UPDATE prov.review_reply SET status = :s, reviewed_by = :m, reviewed_at = now() "
            "WHERE review_id = CAST(:r AS uuid) AND status = 'pending_review'"
        ),
        {"s": "published" if approve else "rejected", "m": moderator, "r": review_id},
    )


def report(
    conn: Connection, review_id: str, facility_id: str, account_id: str, reason: str
) -> None:
    r = reason.strip()
    if not 3 <= len(r) <= 500:
        raise ReviewError("Say which posting rule the review breaks (3 to 500 characters).")
    ok = conn.execute(
        text(
            "SELECT 1 FROM prov.review WHERE id = CAST(:r AS uuid) "
            "AND facility_id = CAST(:f AS uuid) AND status = 'published'"
        ),
        {"r": review_id, "f": facility_id},
    ).first()
    if ok is None:
        raise ReviewError("Unknown review.")
    conn.execute(
        text(
            "INSERT INTO prov.review_report (review_id, reason, account_id) "
            "VALUES (CAST(:r AS uuid), :why, :a)"
        ),
        {"r": review_id, "why": r, "a": account_id},
    )


def resolve_report(
    conn: Connection, report_id: str, moderator: str, remove_reason: str | None
) -> None:
    row = conn.execute(
        text(
            "SELECT review_id FROM prov.review_report WHERE id = CAST(:p AS uuid) "
            "AND resolved_at IS NULL"
        ),
        {"p": report_id},
    ).first()
    if row is None:
        raise ReviewError("That report was already handled.")
    if remove_reason is not None:
        moderate(conn, str(row[0]), moderator, publish=False, reason=remove_reason)
    conn.execute(
        text(
            "UPDATE prov.review_report SET resolved_by = :m, resolved_at = now(), outcome = :o "
            "WHERE id = CAST(:p AS uuid)"
        ),
        {"m": moderator, "o": "kept" if remove_reason is None else "removed", "p": report_id},
    )


# ------------------------------------------------------------------- reading
def _row(r: Any) -> ReviewOut:
    return ReviewOut(
        id=str(r[0]),
        rating=int(r[1]),
        title=r[2],
        body=str(r[3]),
        price_matched=r[4],
        display_name=str(r[5]),
        verification=str(r[6]),
        published_at=r[7].date().isoformat(),
        reply_body=r[8],
        reply_at=None if r[9] is None else r[9].date().isoformat(),
    )


def published(
    conn: Connection, facility_id: str, limit: int = 20, offset: int = 0
) -> list[ReviewOut]:
    rows = conn.execute(
        text(
            "SELECT id, rating, title, body, price_matched, display_name, verification, "
            "published_at, reply_body, reply_at FROM prov.published_review "
            "WHERE facility_id = CAST(:f AS uuid) ORDER BY published_at DESC, id "
            "LIMIT :l OFFSET :o"
        ),
        {"f": facility_id, "l": max(1, min(limit, 50)), "o": max(0, offset)},
    ).all()
    return [_row(r) for r in rows]


def summary(conn: Connection, facility_id: str) -> Summary:
    row = conn.execute(
        text(
            """
            SELECT count(*), sum(rating),
                   count(*) FILTER (WHERE price_matched),
                   count(*) FILTER (WHERE price_matched IS NOT NULL),
                   count(*) FILTER (WHERE rating = 1), count(*) FILTER (WHERE rating = 2),
                   count(*) FILTER (WHERE rating = 3), count(*) FILTER (WHERE rating = 4),
                   count(*) FILTER (WHERE rating = 5),
                   (SELECT removed FROM prov.review_counts WHERE facility_id = CAST(:f AS uuid))
            FROM prov.published_review WHERE facility_id = CAST(:f AS uuid)
            """
        ),
        {"f": facility_id},
    ).one()
    count = int(row[0])
    average = (
        (Decimal(int(row[1])) / Decimal(count)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        if count
        else None
    )
    return Summary(
        average=average,
        count=count,
        removed=int(row[9] or 0),
        price_matched_yes=int(row[2]),
        price_matched_answered=int(row[3]),
        stars=(int(row[4]), int(row[5]), int(row[6]), int(row[7]), int(row[8])),
    )


def for_provider(conn: Connection, facility_id: str) -> list[dict[str, Any]]:
    """Every published review with its reply status, for the provider's page."""
    rows = conn.execute(
        text(
            """
            SELECT r.id, r.rating, r.title, r.body, r.display_name, r.verification,
                   r.published_at, rr.body, rr.status
            FROM prov.review r LEFT JOIN prov.review_reply rr ON rr.review_id = r.id
            WHERE r.facility_id = CAST(:f AS uuid) AND r.status = 'published'
            ORDER BY r.published_at DESC LIMIT 200
            """
        ),
        {"f": facility_id},
    ).all()
    return [
        {
            "id": str(r[0]),
            "rating": int(r[1]),
            "title": r[2],
            "body": r[3],
            "display_name": r[4],
            "verification": r[5],
            "published_at": r[6].date().isoformat(),
            "reply_body": r[7],
            "reply_status": r[8],
        }
        for r in rows
    ]
