"""Assign county FIPS and coordinates to facilities.

Order of preference, recorded in geocode_precision / geocode_source:
1. 'address': a Census Geocoder match whose state and county agree with the
   facility's published state and county. Ties are never used.
2. 'zcta_centroid': the Census internal point of the facility's ZIP (ZCTA).
3. Nothing: geom stays NULL, so search must say the location is unknown.

County FIPS comes from the published county name when it matches exactly one
ref.county row in the state; otherwise from a validated address match.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from sqlalchemy import Connection, text

from procedurescout_core.enums import Severity

from .census import GEOCODER_BENCHMARK, GEOCODER_VINTAGE, AddressRow, GeocodeResult
from .common import USPS_TO_FIPS, LoadStats

Geocoder = Callable[[list[AddressRow]], dict[str, GeocodeResult]]

_COUNTY_SUFFIX = re.compile(r"\s+(county|parish|borough|census area|municipality)$")


def _county_key(name: str) -> str:
    key = " ".join(name.casefold().replace(".", "").split())
    return _COUNTY_SUFFIX.sub("", key)


def _counties_by_name(conn: Connection, state_code: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for fips, name in conn.execute(
        text("SELECT county_fips, name FROM ref.county WHERE state_code = :s"), {"s": state_code}
    ):
        out.setdefault(_county_key(name), []).append(fips)
    return out


def geocode_facilities(
    conn: Connection, state_code: str, geocoder: Geocoder | None, zcta_label: str = "census_zcta"
) -> LoadStats:
    stats = LoadStats()
    by_name = _counties_by_name(conn, state_code)
    if not by_name:
        stats.reject(
            "state",
            "no_counties",
            f"ref.county is empty for {state_code}; load Census lookups first",
        )
        return stats
    state_fips = USPS_TO_FIPS[state_code]

    # County FIPS from the published county name (exact, unambiguous only).
    facilities = conn.execute(
        text(
            "SELECT id, ccn, county_name FROM ref.facility "
            "WHERE state_code = :s AND county_fips IS NULL AND county_name IS NOT NULL"
        ),
        {"s": state_code},
    ).all()
    for fid, ccn, county_name in facilities:
        fips = by_name.get(_county_key(county_name), [])
        if len(fips) == 1:
            conn.execute(
                text("UPDATE ref.facility SET county_fips = :c WHERE id = :f"),
                {"c": fips[0], "f": fid},
            )
            stats.count("county_from_name")
        else:
            stats.reject(
                f"ccn:{ccn}",
                "county_name_unmatched",
                f"county {county_name!r} not found in {state_code}",
                Severity.WARNING,
            )

    pending = conn.execute(
        text(
            "SELECT id, ccn, address_line1, city, zip5, county_fips FROM ref.facility "
            "WHERE state_code = :s AND geom IS NULL ORDER BY ccn"
        ),
        {"s": state_code},
    ).all()
    stats.rows_in = len(pending)

    results: dict[str, GeocodeResult] = {}
    addressable = [
        AddressRow(str(r[0]), r[2], r[3] or "", state_code, r[4] or "") for r in pending if r[2]
    ]
    if geocoder is not None and addressable:
        results = geocoder(addressable)
        stats.summary["sent_to_geocoder"] = len(addressable)

    source = f"census_geocoder:{GEOCODER_BENCHMARK}/{GEOCODER_VINTAGE}"
    for fid, ccn, address, _city, zip5, county_fips in pending:
        ref = f"ccn:{ccn}"
        res = results.get(str(fid))
        if res is not None and res.status == "match":
            got_county = f"{res.state_fips}{res.county_fips3}"
            if res.state_fips != state_fips:
                stats.reject(
                    ref,
                    "geocode_wrong_state",
                    f"matched state FIPS {res.state_fips}",
                    Severity.WARNING,
                )
            elif county_fips is not None and got_county != county_fips:
                stats.reject(
                    ref,
                    "geocode_wrong_county",
                    f"matched county {got_county}, published county is {county_fips}",
                    Severity.WARNING,
                )
            else:
                conn.execute(
                    text(
                        """
                        UPDATE ref.facility SET
                            geom = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                            geocode_source = :src, geocode_precision = 'address',
                            geocoded_at = now(), county_fips = COALESCE(county_fips, :c)
                        WHERE id = :f
                        """
                    ),
                    {
                        "lon": res.lon,
                        "lat": res.lat,
                        "src": f"{source}:{'exact' if res.exact else 'non_exact'}",
                        "c": got_county,
                        "f": fid,
                    },
                )
                stats.rows_loaded += 1
                stats.count("address")
                continue
        elif res is not None:
            stats.reject(
                ref, f"geocode_{res.status}", f"Census geocoder: {res.status}", Severity.INFO
            )
        elif address and geocoder is not None:
            stats.reject(
                ref, "geocode_missing_result", "no row returned for this address", Severity.WARNING
            )

        updated = conn.execute(
            text(
                """
                UPDATE ref.facility f SET
                    geom = z.geom, geocode_source = :src || ':' || z.gazetteer_year,
                    geocode_precision = 'zcta_centroid', geocoded_at = now()
                FROM ref.zcta z
                WHERE f.id = :f AND z.zcta5 = f.zip5
                """
            ),
            {"f": fid, "src": zcta_label},
        ).rowcount
        if updated:
            stats.rows_loaded += 1
            stats.count("zcta_centroid")
        else:
            stats.reject(ref, "no_location", f"no address match and ZIP {zip5!r} is not a ZCTA")
    return stats
