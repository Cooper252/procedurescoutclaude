"""Street addresses for ambulatory surgical centers from the NPPES NPI Registry.

The CMS ASC file has city and ZIP but no street address. For each ASC with an
NPI from that file, the NPI Registry API (version 2.1) is asked for the
record. The LOCATION address is used only if the record is an active
organization (NPI-2) in the same state and the same 5-digit ZIP as CMS lists.
Anything else is reported and the facility keeps its ZIP-level location.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
from sqlalchemy import Connection, text

from procedurescout_core.enums import Severity
from procedurescout_core.facility_repo import add_alias

from .common import LoadStats, SourceError

NPPES_API = "https://npiregistry.cms.hhs.gov/api/"
NPPES_SOURCE = "nppes_npi_registry"

NpiLookup = Callable[[str], dict[str, Any] | None]


def npi_lookup(client: httpx.Client) -> NpiLookup:
    def _lookup(npi: str) -> dict[str, Any] | None:
        resp = client.get(NPPES_API, params={"version": "2.1", "number": npi})
        if resp.status_code != 200:
            raise SourceError(f"NPI Registry returned HTTP {resp.status_code} for {npi}")
        body = resp.json()
        results = body.get("results") or []
        if body.get("result_count") != 1 or len(results) != 1:
            return None
        result = results[0]
        return result if isinstance(result, dict) else None

    return _lookup


def _location(record: dict[str, Any]) -> dict[str, Any] | None:
    for addr in record.get("addresses") or []:
        if isinstance(addr, dict) and addr.get("address_purpose") == "LOCATION":
            return addr
    return None


def enrich_asc_addresses(conn: Connection, state_code: str, lookup: NpiLookup) -> LoadStats:
    stats = LoadStats()
    rows = conn.execute(
        text(
            """
            SELECT f.id, f.ccn, f.zip5, n.npi
            FROM ref.facility f JOIN ref.facility_npi n ON n.facility_id = f.id
            WHERE f.state_code = :s AND f.facility_type = 'ambulatory_surgery_center'
              AND f.address_line1 IS NULL
            ORDER BY f.ccn
            """
        ),
        {"s": state_code},
    ).all()
    stats.rows_in = len(rows)
    for fid, ccn, zip5, npi in rows:
        ref = f"ccn:{ccn}"
        record = lookup(npi)
        if record is None:
            stats.reject(
                ref, "npi_not_found", f"NPI {npi}: no single registry record", Severity.WARNING
            )
            continue
        basic = record.get("basic") or {}
        if record.get("enumeration_type") != "NPI-2" or basic.get("status") != "A":
            stats.reject(
                ref,
                "npi_not_active_org",
                f"NPI {npi}: not an active organization",
                Severity.WARNING,
            )
            continue
        loc = _location(record)
        if loc is None or not loc.get("address_1"):
            stats.reject(
                ref, "npi_no_location", f"NPI {npi}: no location address", Severity.WARNING
            )
            continue
        loc_zip = str(loc.get("postal_code", ""))[:5]
        if loc.get("state") != state_code or loc_zip != zip5:
            stats.reject(
                ref,
                "npi_address_mismatch",
                f"NPI {npi}: location {loc.get('state')} {loc_zip} vs CMS {state_code} {zip5}",
                Severity.WARNING,
            )
            continue
        street = " ".join(str(p).strip() for p in (loc.get("address_1"), loc.get("address_2")) if p)
        conn.execute(
            text(
                """
                UPDATE ref.facility SET address_line1 = :a, updated_at = now(),
                    geom = NULL, geocode_source = NULL, geocode_precision = NULL,
                    geocoded_at = NULL
                WHERE id = :f
                """
            ),
            {"a": street, "f": fid},
        )
        taxonomies = [t for t in record.get("taxonomies") or [] if isinstance(t, dict)]
        primary = next((t for t in taxonomies if t.get("primary")), None)
        if primary and primary.get("code"):
            conn.execute(
                text("UPDATE ref.facility_npi SET taxonomy_code = :t WHERE npi = :n"),
                {"t": primary["code"], "n": npi},
            )
        org = basic.get("organization_name")
        if org:
            add_alias(
                conn, fid, str(org), alias_type="nppes_name", source=NPPES_SOURCE, match_basis="npi"
            )
        stats.rows_loaded += 1
    return stats
