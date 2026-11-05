"""Database access for payer resolution. Read-only resolution plus
recording of unseen raw names as *unmapped*; never creates a mapping."""

from __future__ import annotations

import uuid

from sqlalchemy import Connection, text

from .matching import normalize_name


def resolve_payer(conn: Connection, raw_name: str) -> uuid.UUID | None:
    """Return the canonical payer id for a raw name, or None if not approved.

    Only an approved alias whose normalized text matches exactly counts.
    """
    row = conn.execute(
        text(
            """
            SELECT payer_id FROM ref.payer_alias
            WHERE raw_normalized = :key
              AND review_state = 'approved'
              AND match_type <> 'unmapped'
            """
        ),
        {"key": normalize_name(raw_name)},
    ).first()
    if row is None or row[0] is None:
        return None
    value = row[0]
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def record_raw_payer(conn: Connection, raw_name: str) -> None:
    """Remember a raw payer name for the review queue, unmapped.

    Existing rows (mapped or not) are left untouched.
    """
    conn.execute(
        text(
            """
            INSERT INTO ref.payer_alias (raw_text, raw_normalized, match_type, review_state)
            VALUES (:raw, :key, 'unmapped', 'proposed')
            ON CONFLICT (raw_normalized) DO NOTHING
            """
        ),
        {"raw": raw_name, "key": normalize_name(raw_name)},
    )
