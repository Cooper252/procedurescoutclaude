"""Facility campus/licence relationships.

Relationships are never inferred from names or addresses. They are either
- loaded from a reviewed CSV (data/reference/facility_relationships_reviewed.csv)
  in which every row names a reviewer, a review date and the evidence; or
- proposed by code (e.g. when a price file lists several locations) and left
  as 'proposed' until a person approves them.
"""

from __future__ import annotations

import re
import uuid
from datetime import date

from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from procedurescout_core.facility_repo import resolve_facility_by_ccn

from .common import LoadStats, read_delimited, require_columns

RELATIONSHIP_TYPES = ("campus_of", "same_license", "merged_into")
REVIEWED_COLUMNS = (
    "parent_ccn",
    "child_ccn",
    "relationship_type",
    "evidence",
    "reviewed_by",
    "reviewed_at",
)
SOURCE = "manual_relationships"


def propose_relationship(
    conn: Connection,
    parent_id: uuid.UUID,
    child_id: uuid.UUID,
    relationship_type: str,
    source: str,
    evidence: str,
) -> None:
    if relationship_type not in RELATIONSHIP_TYPES:
        raise ValueError(f"unknown relationship type {relationship_type!r}")
    conn.execute(
        text(
            """
            INSERT INTO ref.facility_relationship
                (parent_facility_id, child_facility_id, relationship_type, source, evidence)
            VALUES (:p, :c, :t, :s, :e)
            ON CONFLICT DO NOTHING
            """
        ),
        {"p": parent_id, "c": child_id, "t": relationship_type, "s": source, "e": evidence},
    )


def load_reviewed_relationships(conn: Connection, csv_text: str) -> LoadStats:
    stats = LoadStats()
    rows = read_delimited(csv_text, ",")
    if not rows:
        return stats
    require_columns(rows, REVIEWED_COLUMNS, "reviewed relationships CSV")
    for i, row in enumerate(rows, start=2):
        stats.rows_in += 1
        ref = f"line:{i}"
        rtype = row["relationship_type"]
        if rtype not in RELATIONSHIP_TYPES:
            stats.reject(ref, "relationship_type", f"unknown type {rtype!r}")
            continue
        if not row["evidence"] or not row["reviewed_by"]:
            stats.reject(ref, "unreviewed", "evidence and reviewed_by are required")
            continue
        try:
            reviewed_at = date.fromisoformat(row["reviewed_at"])
        except ValueError:
            stats.reject(ref, "reviewed_at", f"reviewed_at {row['reviewed_at']!r} is not a date")
            continue
        ids = []
        for col in ("parent_ccn", "child_ccn"):
            ccn = row[col].strip().upper()
            fid = (
                resolve_facility_by_ccn(conn, ccn) if re.fullmatch(r"[0-9A-Z]{6,10}", ccn) else None
            )
            if fid is None:
                stats.reject(ref, "facility_not_found", f"{col} {ccn!r} is not in ref.facility")
                break
            ids.append(fid)
        if len(ids) != 2:
            continue
        if ids[0] == ids[1]:
            stats.reject(ref, "self_relationship", "parent and child are the same facility")
            continue
        savepoint = conn.begin_nested()
        try:
            conn.execute(
                text(
                    """
                INSERT INTO ref.facility_relationship
                    (parent_facility_id, child_facility_id, relationship_type, source, evidence,
                     review_state, reviewed_by, reviewed_at)
                VALUES (:p, :c, :t, :s, :e, 'approved', :rb, CAST(:ra AS timestamptz))
                ON CONFLICT (parent_facility_id, child_facility_id, relationship_type)
                DO UPDATE SET review_state = 'approved', evidence = EXCLUDED.evidence,
                    reviewed_by = EXCLUDED.reviewed_by, reviewed_at = EXCLUDED.reviewed_at
                """
                ),
                {
                    "p": ids[0],
                    "c": ids[1],
                    "t": rtype,
                    "s": SOURCE,
                    "e": row["evidence"],
                    "rb": row["reviewed_by"],
                    "ra": reviewed_at,
                },
            )
        except (IntegrityError, DBAPIError) as exc:
            savepoint.rollback()
            stats.reject(ref, "refused_by_database", str(exc.orig).splitlines()[0])
            continue
        savepoint.commit()
        stats.rows_loaded += 1
    return stats
