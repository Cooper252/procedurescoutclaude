"""Reviewed facility websites and aliases.

data/reference/facility_websites.csv lists, per hospital, a proposed website
(or 'federal_exempt' / 'not_found'), the evidence, who proposed it and - once a
person has checked it - who approved it and when. Only approved rows change
the database (CLAUDE.md rule 10: proposals are never used until approved).

data/reference/facility_aliases_reviewed.csv adds names a person confirmed
belong to a facility (e.g. the name a hospital uses in its cms-hpt.txt).
"""

from __future__ import annotations

import re
from datetime import date

from sqlalchemy import Connection, text

from procedurescout_core.enums import Severity
from procedurescout_core.facility_repo import add_alias, resolve_facility_by_ccn

from .common import LoadStats, read_delimited, require_columns

WEBSITE_COLUMNS = (
    "ccn",
    "name",
    "website",
    "status",
    "evidence_url",
    "note",
    "proposed_by",
    "reviewed_by",
    "reviewed_at",
)
ALIAS_COLUMNS = ("ccn", "alias", "evidence", "reviewed_by", "reviewed_at")
STATUSES = ("website", "federal_exempt", "not_found")
_SITE = re.compile(r"^https://[^/?#\s]+$")


def _reviewed(row: dict[str, str], stats: LoadStats, ref: str) -> date | None:
    if not row.get("reviewed_by") or not row.get("reviewed_at"):
        return None
    try:
        return date.fromisoformat(row["reviewed_at"])
    except ValueError:
        stats.reject(ref, "reviewed_at", f"reviewed_at {row['reviewed_at']!r} is not a date")
        return None


def load_websites(conn: Connection, csv_text: str) -> LoadStats:
    stats = LoadStats()
    rows = read_delimited(csv_text, ",")
    require_columns(rows, WEBSITE_COLUMNS, "facility websites CSV")
    for i, row in enumerate(rows, start=2):
        stats.rows_in += 1
        ref = f"line:{i} ccn:{row['ccn']}"
        status = row["status"]
        if status not in STATUSES:
            stats.reject(ref, "status", f"unknown status {status!r}")
            continue
        fid = resolve_facility_by_ccn(conn, row["ccn"])
        if fid is None:
            stats.reject(ref, "facility_not_found", f"CCN {row['ccn']!r} is not loaded")
            continue
        reviewed_at = _reviewed(row, stats, ref)
        if reviewed_at is None:
            stats.count(f"unreviewed_{status}")
            continue
        if status == "website":
            site = row["website"].strip().rstrip("/").lower()
            if not _SITE.match(site):
                stats.reject(ref, "website_format", f"{row['website']!r} is not https://<host>")
                continue
            conn.execute(
                text(
                    """
                    UPDATE ref.facility SET website = :w, website_evidence_url = :e,
                        website_reviewed_by = :rb, website_reviewed_at = CAST(:ra AS timestamptz),
                        hpt_exempt_reason = NULL, updated_at = now()
                    WHERE id = :f
                    """
                ),
                {
                    "w": site,
                    "e": row["evidence_url"] or None,
                    "rb": row["reviewed_by"],
                    "ra": reviewed_at,
                    "f": fid,
                },
            )
        elif status == "federal_exempt":
            conn.execute(
                text(
                    "UPDATE ref.facility SET hpt_exempt_reason = :r, updated_at = now() "
                    "WHERE id = :f"
                ),
                {"r": row["note"] or "federally owned", "f": fid},
            )
        else:
            stats.reject(ref, "website_not_found", row["note"] or "no website", Severity.INFO)
        stats.rows_loaded += 1
        stats.count(f"approved_{status}")
    return stats


def load_reviewed_aliases(conn: Connection, csv_text: str) -> LoadStats:
    stats = LoadStats()
    rows = read_delimited(csv_text, ",")
    if not rows:
        return stats
    require_columns(rows, ALIAS_COLUMNS, "reviewed aliases CSV")
    for i, row in enumerate(rows, start=2):
        stats.rows_in += 1
        ref = f"line:{i}"
        if not row["alias"] or not row["evidence"]:
            stats.reject(ref, "incomplete", "alias and evidence are required")
            continue
        if _reviewed(row, stats, ref) is None:
            stats.reject(ref, "unreviewed", "reviewed_by and reviewed_at are required")
            continue
        fid = resolve_facility_by_ccn(conn, row["ccn"])
        if fid is None:
            stats.reject(ref, "facility_not_found", f"CCN {row['ccn']!r} is not loaded")
            continue
        add_alias(
            conn,
            fid,
            row["alias"],
            alias_type="mrf_name",
            source="reviewed_aliases",
            match_basis="manual",
            reviewed_by=row["reviewed_by"],
        )
        stats.rows_loaded += 1
    return stats
