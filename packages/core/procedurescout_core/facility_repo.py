"""Facility identity: resolve a name or CCN to one facility without false merges.

Rules (docs/DATA_NORMALIZATION.md, "Facilities"):
- A CCN or NPI is an identifier; a name is not. Names resolve only through
  usable alias rows (linked by CCN/NPI, or approved by a named reviewer).
- No fuzzy matching. If a normalized name belongs to more than one facility
  in the state, the result is *ambiguous* and nothing is returned as a match.
- Campus relationships count only when approved.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import Connection, text

from .matching import normalize_name


class FacilityMatchStatus(StrEnum):
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class FacilityMatch:
    status: FacilityMatchStatus
    facility_id: uuid.UUID | None = None
    candidates: tuple[uuid.UUID, ...] = field(default_factory=tuple)


def _uuid(value: object) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


USABLE_ALIAS_SQL = """
    a.review_state = 'approved'
    AND (a.match_basis IN ('ccn', 'npi')
         OR (a.reviewed_by IS NOT NULL AND a.reviewed_at IS NOT NULL))
"""


def resolve_facility_by_name(conn: Connection, raw_name: str, state_code: str) -> FacilityMatch:
    """Exact lookup of the normalized name among usable aliases in one state."""
    rows = conn.execute(
        text(
            f"""
            SELECT DISTINCT a.facility_id
            FROM ref.facility_alias a
            JOIN ref.facility f ON f.id = a.facility_id
            WHERE a.alias_normalized = :key AND f.state_code = :st AND {USABLE_ALIAS_SQL}
            ORDER BY a.facility_id
            """  # noqa: S608 - fixed SQL fragment, values are bound
        ),
        {"key": normalize_name(raw_name), "st": state_code},
    ).all()
    ids = tuple(_uuid(r[0]) for r in rows)
    if not ids:
        return FacilityMatch(FacilityMatchStatus.UNMATCHED)
    if len(ids) > 1:
        return FacilityMatch(FacilityMatchStatus.AMBIGUOUS, candidates=ids)
    return FacilityMatch(FacilityMatchStatus.MATCHED, facility_id=ids[0], candidates=ids)


def resolve_facility_by_ccn(conn: Connection, ccn: str) -> uuid.UUID | None:
    value = conn.execute(
        text("SELECT id FROM ref.facility WHERE ccn = :c"), {"c": ccn.strip().upper()}
    ).scalar_one_or_none()
    return None if value is None else _uuid(value)


def add_alias(
    conn: Connection,
    facility_id: uuid.UUID,
    alias: str,
    *,
    alias_type: str,
    source: str,
    match_basis: str,
    reviewed_by: str | None = None,
) -> None:
    """Record a name for a facility.

    Identifier-linked aliases (match_basis 'ccn'/'npi') are usable at once.
    A 'manual' alias is usable only with a named reviewer; without one it is
    stored as proposed and ignored by resolve_facility_by_name.
    """
    if match_basis not in ("ccn", "npi", "manual"):
        raise ValueError(f"unknown match basis {match_basis!r}")
    approved = match_basis in ("ccn", "npi") or reviewed_by is not None
    conn.execute(
        text(
            """
            INSERT INTO ref.facility_alias
                (facility_id, alias, alias_normalized, alias_type, source, match_basis,
                 review_state, reviewed_by, reviewed_at)
            VALUES (:f, :a, :k, :t, :s, :b, CAST(:rs AS ref.review_state), :rb,
                    CASE WHEN CAST(:rb AS text) IS NULL THEN NULL ELSE now() END)
            ON CONFLICT (facility_id, alias) DO NOTHING
            """
        ),
        {
            "f": facility_id,
            "a": alias.strip(),
            "k": normalize_name(alias),
            "t": alias_type,
            "s": source,
            "b": match_basis,
            "rs": "approved" if approved else "proposed",
            "rb": reviewed_by,
        },
    )


def approved_campus_parent(conn: Connection, facility_id: uuid.UUID) -> uuid.UUID | None:
    value = conn.execute(
        text(
            """
            SELECT parent_facility_id FROM ref.facility_relationship
            WHERE child_facility_id = :f AND relationship_type = 'campus_of'
              AND review_state = 'approved'
            """
        ),
        {"f": facility_id},
    ).scalar_one_or_none()
    return None if value is None else _uuid(value)
