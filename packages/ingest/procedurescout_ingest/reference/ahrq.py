"""Health-system links from the AHRQ Compendium of U.S. Health Systems,
hospital linkage file (one row per CCN; variables per the AHRQ technical
documentation: ccn, hospital_name, hospital_state, health_sys_id,
health_sys_name, health_sys_city, health_sys_state, ...).

- Joined to facilities by CCN only. Rows whose CCN we do not have are
  reported, not created: CMS is the facility master list.
- Systems are keyed by AHRQ health_sys_id, never by name.
- A link entered by a person (health_system_source not from AHRQ) is never
  overwritten; a disagreement is reported for review.
- CCNs that lost leading zeros (5 digits) are refused, not padded.
"""

from __future__ import annotations

import re

from sqlalchemy import Connection, text

from procedurescout_core.enums import Severity
from procedurescout_core.facility_repo import add_alias, resolve_facility_by_ccn

from .common import LoadStats, read_delimited, require_columns

AHRQ_SOURCE = "ahrq_compendium"
REQUIRED = ("ccn", "hospital_name", "hospital_state", "health_sys_id", "health_sys_name")
_CCN = re.compile(r"^[0-9A-Z]{6}$")


def parse_linkage(text_: str) -> list[dict[str, str]]:
    rows = read_delimited(text_, ",")
    require_columns(rows, REQUIRED, "AHRQ hospital linkage file")
    return rows


def load_linkage(
    conn: Connection, rows: list[dict[str, str]], state_code: str, source_year: int
) -> LoadStats:
    link_source = f"{AHRQ_SOURCE}:{source_year}"
    stats = LoadStats()
    for i, row in enumerate(rows, start=2):
        if row.get("hospital_state", "").upper() != state_code:
            continue
        stats.rows_in += 1
        ref = f"line:{i}"
        ccn = row["ccn"].strip().upper()
        if not ccn:
            stats.reject(ref, "ccn_missing", f"{row['hospital_name']!r} has no CCN", Severity.INFO)
            continue
        if not _CCN.match(ccn):
            stats.reject(ref, "ccn_format", f"CCN {ccn!r} is not 6 characters; not padded")
            continue
        fid = resolve_facility_by_ccn(conn, ccn)
        if fid is None:
            stats.reject(
                ref, "facility_not_found", f"CCN {ccn} is not in ref.facility", Severity.WARNING
            )
            continue
        if row.get("hospital_name"):
            add_alias(
                conn,
                fid,
                row["hospital_name"],
                alias_type="ahrq_name",
                source=link_source,
                match_basis="ccn",
            )
        current = conn.execute(
            text(
                "SELECT f.health_system_source, h.source, h.source_system_id "
                "FROM ref.facility f LEFT JOIN ref.health_system h ON h.id = f.health_system_id "
                "WHERE f.id = :f"
            ),
            {"f": fid},
        ).one()
        manual_link = current[0] is not None and not str(current[0]).startswith(AHRQ_SOURCE)
        sys_id = row["health_sys_id"].strip()
        if not sys_id:
            if manual_link:
                stats.reject(
                    ref,
                    "manual_link_conflict",
                    f"{ccn}: AHRQ lists no system; manual link kept",
                    Severity.WARNING,
                )
            elif current[0] is not None:
                conn.execute(
                    text(
                        "UPDATE ref.facility SET health_system_id = NULL, "
                        "health_system_source = NULL WHERE id = :f"
                    ),
                    {"f": fid},
                )
            stats.count("no_system")
            stats.rows_loaded += 1
            continue
        hs_state = row.get("health_sys_state", "").strip().upper() or None
        system_id = conn.execute(
            text(
                """
                INSERT INTO ref.health_system
                    (name, source, source_system_id, source_year, hq_city, hq_state)
                VALUES (:n, :src, :sid, :y, :c, :st)
                ON CONFLICT (source, source_system_id) DO UPDATE SET
                    name = EXCLUDED.name, source_year = EXCLUDED.source_year,
                    hq_city = EXCLUDED.hq_city, hq_state = EXCLUDED.hq_state, updated_at = now()
                RETURNING id
                """
            ),
            {
                "n": row["health_sys_name"].strip(),
                "src": AHRQ_SOURCE,
                "sid": sys_id,
                "y": source_year,
                "c": row.get("health_sys_city", "").strip() or None,
                "st": hs_state if hs_state and re.fullmatch(r"[A-Z]{2}", hs_state) else None,
            },
        ).scalar_one()
        if manual_link:
            if (current[1], current[2]) != (AHRQ_SOURCE, sys_id):
                stats.reject(
                    ref,
                    "manual_link_conflict",
                    f"{ccn}: AHRQ system {sys_id} differs from manual link; kept manual",
                    Severity.WARNING,
                )
        else:
            conn.execute(
                text(
                    "UPDATE ref.facility SET health_system_id = :h, health_system_source = :s, "
                    "updated_at = now() WHERE id = :f"
                ),
                {"h": system_id, "s": link_source, "f": fid},
            )
        stats.count("linked")
        stats.rows_loaded += 1
    return stats
