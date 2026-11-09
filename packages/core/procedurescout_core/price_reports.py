"""Report a wrong price (PRODUCT_REVIEW §Launch 5).

Anyone can say a price looks wrong, a service isn't offered, or a place has
closed. Nothing about the person is stored. A person looks at each report;
reports about a claimed provider are also shown to that provider.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import Connection, text

PROBLEMS = ("price_different", "not_offered", "closed_or_moved", "insurance_wrong", "other")
OUTCOMES = ("fixed", "no_change", "sent_to_provider")
MAX_PER_FACILITY_PER_DAY = 50
_SERVICE = re.compile(r"^[A-Za-z0-9:_. -]{1,120}$")
_AMOUNT = re.compile(r"^[0-9]{1,9}(\.[0-9]{1,15})?$")


class ReportError(ValueError):
    """A report that can't be saved (message is safe to show)."""


def submit(
    conn: Connection,
    facility_id: str,
    problem: str,
    service_key: str | None = None,
    price_shown: str | None = None,
    details: str | None = None,
) -> str:
    try:
        fid = str(uuid.UUID(facility_id))
    except ValueError as exc:
        raise ReportError("Unknown provider.") from exc
    if problem not in PROBLEMS:
        raise ReportError("Choose what's wrong.")
    if service_key is not None and not _SERVICE.match(service_key):
        service_key = None
    if price_shown is not None and not _AMOUNT.match(price_shown):
        price_shown = None
    d = (details or "").strip() or None
    if d is not None and len(d) > 500:
        raise ReportError("Keep it under 500 characters.")
    if conn.execute(text("SELECT 1 FROM ref.facility WHERE id = :f"), {"f": fid}).first() is None:
        raise ReportError("Unknown provider.")
    today = conn.execute(
        text(
            "SELECT count(*) FROM prov.price_report WHERE facility_id = :f "
            "AND created_at > now() - interval '1 day'"
        ),
        {"f": fid},
    ).scalar_one()
    if int(today) >= MAX_PER_FACILITY_PER_DAY:
        raise ReportError("We already have many reports about this place today. Thank you.")
    rid = conn.execute(
        text(
            "INSERT INTO prov.price_report (facility_id, service_key, price_shown, problem, "
            "details) VALUES (:f, :s, :p, :k, :d) RETURNING id"
        ),
        {"f": fid, "s": service_key, "p": price_shown, "k": problem, "d": d},
    ).scalar_one()
    return str(rid)


def resolve(conn: Connection, report_id: str, reviewer: str, outcome: str) -> None:
    if outcome not in OUTCOMES:
        raise ReportError("Choose an outcome.")
    done = conn.execute(
        text(
            "UPDATE prov.price_report SET resolved_by = :r, resolved_at = now(), outcome = :o "
            "WHERE id = CAST(:i AS uuid) AND resolved_at IS NULL RETURNING id"
        ),
        {"r": reviewer, "o": outcome, "i": report_id},
    ).first()
    if done is None:
        raise ReportError("That report was already handled.")


def for_facility(conn: Connection, facility_id: str) -> list[dict[str, Any]]:
    """Recent reports about one facility, for its provider."""
    return [
        {
            "id": str(r[0]),
            "problem": r[1],
            "service_key": r[2],
            "price_shown": r[3],
            "details": r[4],
            "created_at": r[5].date().isoformat(),
            "outcome": r[6],
        }
        for r in conn.execute(
            text(
                "SELECT id, problem, service_key, price_shown, details, created_at, outcome "
                "FROM prov.price_report WHERE facility_id = CAST(:f AS uuid) "
                "AND created_at > now() - interval '90 days' ORDER BY created_at DESC LIMIT 100"
            ),
            {"f": facility_id},
        ).all()
    ]
