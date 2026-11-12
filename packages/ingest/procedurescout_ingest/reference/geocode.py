"""Assign county FIPS and coordinates to facilities.

Order of preference, recorded in geocode_precision / geocode_source:
1. 'address': a Census Geocoder match (batch endpoint, or the one-address
   endpoint when the batch endpoint fails) whose state and county agree with the
   facility's published state and county. Ties are never used.
2. 'zcta_centroid': the Census internal point of the facility's ZIP (ZCTA).
3. Nothing: geom stays NULL, so search must say the location is unknown.

County FIPS comes from the published county name when it matches exactly one
ref.county row in the state; otherwise from a validated address match.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Any

import httpx
from sqlalchemy import Connection, text

from procedurescout_core.enums import Severity

from .census import GEOCODER_BENCHMARK, GEOCODER_VINTAGE, AddressRow, GeocodeResult
from .common import USPS_TO_FIPS, LoadStats, SourceError

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


DEFERRED = "census_zcta_deferred"  # ZIP location for now; the exact address is tried next run
CHUNK = 2_000


def geocode_facilities(
    conn: Connection,
    state_code: str,
    geocoder: Geocoder | None,
    zcta_label: str = "census_zcta",
    *,
    chunk_size: int = CHUNK,
    stop_at_ns: int | None = None,
    commit: Callable[[], None] | None = None,
    parallel: int = 1,
) -> LoadStats:
    """Addresses go to the geocoder in chunks, each saved as it finishes
    (`commit`), so a long state (about 100,000 offices in California) never
    loses finished work. When the geocoder is down, or the time limit
    (`stop_at_ns`, a time.monotonic_ns() value) is reached, the rest get their
    ZIP location now, marked so the next run tries the exact address again
    (2026-11-12). `parallel` chunks are sent to the geocoder at once (the
    database writes stay one at a time)."""
    import time
    from concurrent.futures import ThreadPoolExecutor

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
    if commit is not None:
        commit()

    pending = conn.execute(
        text(
            "SELECT id, ccn, address_line1, city, zip5, county_fips FROM ref.facility "
            "WHERE state_code = :s AND (geom IS NULL OR geocode_source LIKE :d) "
            "ORDER BY ccn NULLS LAST, id"
        ),
        {"s": state_code, "d": DEFERRED + "%"},
    ).all()
    stats.rows_in = len(pending)
    source = f"census_geocoder:{GEOCODER_BENCHMARK}/{GEOCODER_VINTAGE}"
    failures_in_a_row = 0
    sent = 0
    chunks = [pending[i : i + chunk_size] for i in range(0, len(pending), chunk_size)]

    def addresses(chunk: Sequence[Any]) -> list[AddressRow]:
        return [
            AddressRow(str(r[0]), r[2], r[3] or "", state_code, r[4] or "") for r in chunk if r[2]
        ]

    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        for g in range(0, len(chunks), max(1, parallel)):
            group = chunks[g : g + max(1, parallel)]
            out_of_time = stop_at_ns is not None and time.monotonic_ns() >= stop_at_ns
            use_geocoder = geocoder is not None and failures_in_a_row < 2 and not out_of_time
            if out_of_time and "stopped_for_time" not in stats.summary:
                stats.summary["stopped_for_time"] = (
                    "time limit reached; the rest are tried next run"
                )
            asks = [addresses(c) for c in group]
            futures = [
                pool.submit(geocoder, a) if use_geocoder and a and geocoder is not None else None
                for a in asks
            ]
            for chunk, ask, fut in zip(group, asks, futures, strict=True):
                results: dict[str, GeocodeResult] = {}
                label = zcta_label
                if fut is not None:
                    sent += len(ask)
                    try:
                        results = fut.result()
                        failures_in_a_row = 0
                    except (SourceError, httpx.HTTPError) as exc:
                        # The geocoder being down must not block ZIP-level locations.
                        failures_in_a_row += 1
                        label = DEFERRED
                        stats.reject(
                            "geocoder",
                            "geocoder_unavailable",
                            f"{exc}; using ZIP centroids for now",
                            Severity.WARNING,
                        )
                elif geocoder is not None and ask:
                    label = DEFERRED  # geocoder down or out of time: exact address next run
                for row in chunk:
                    _place(
                        conn,
                        row,
                        results.get(str(row[0])),
                        state_fips,
                        source,
                        label,
                        stats,
                        expect_result=fut is not None and label != DEFERRED,
                    )
                if commit is not None:
                    commit()
    stats.summary["sent_to_geocoder"] = sent
    return stats


def _place(
    conn: Connection,
    row: tuple,  # type: ignore[type-arg]
    res: GeocodeResult | None,
    state_fips: str,
    source: str,
    zcta_label: str,
    stats: LoadStats,
    expect_result: bool,
) -> None:
    fid, ccn, address, _city, zip5, county_fips = row
    ref = f"ccn:{ccn}"
    if res is not None and res.status == "match":
        got_county = f"{res.state_fips}{res.county_fips3}"
        if res.state_fips != state_fips:
            stats.reject(
                ref, "geocode_wrong_state", f"matched state FIPS {res.state_fips}", Severity.WARNING
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
                    "src": f"{source}:{res.method}:{'exact' if res.exact else 'non_exact'}",
                    "c": got_county,
                    "f": fid,
                },
            )
            stats.rows_loaded += 1
            stats.count("address")
            return
    elif res is not None:
        stats.reject(ref, f"geocode_{res.status}", f"Census geocoder: {res.status}", Severity.INFO)
    elif address and expect_result:
        stats.reject(
            ref, "geocode_missing_result", "no row returned for this address", Severity.WARNING
        )

    updated = conn.execute(
        text(
            """
            UPDATE ref.facility f SET
                geom = z.geom, geocode_source = :src || ':' || z.gazetteer_year,
                geocode_precision = 'zcta_centroid', geocoded_at = now(),
                -- A ZCTA lying wholly in one county gives that county; one that
                -- crosses county lines gives none.
                county_fips = COALESCE(
                    f.county_fips, CASE WHEN NOT z.crosses_counties THEN z.county_fips END)
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
