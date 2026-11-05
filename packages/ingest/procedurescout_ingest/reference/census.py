"""U.S. Census lookups and the Census Geocoder.

Local tables (no third-party geocoding at search time):
- 2020 ZCTA-to-county relationship file (tab20_zcta520_county20_natl.txt):
  county names and FIPS codes, and each ZCTA's primary county (largest land
  overlap; ties go to the lower FIPS code).
- National ZCTA Gazetteer file (e.g. 2026_Gaz_zcta_national.txt): an internal
  point (INTPTLAT/INTPTLONG) and land area per ZCTA.

A ZCTA approximates a USPS ZIP code; PO-box-only ZIPs have no ZCTA.

Geocoder: the Census batch "geographies" endpoint (up to 10,000 addresses per
request). Input CSV columns: id, street, city, state, ZIP. Output rows have no
header: id, input address, match status (Match / No_Match / Tie), match type
(Exact / Non_Exact), matched address, "lon,lat", TIGER line id, side, state
FIPS, county FIPS, tract, block. Non-matches carry only the first 3 columns.
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

import httpx
from sqlalchemy import Connection, text

from .common import STATE_FIPS, LoadStats, SourceError, read_delimited

GEOCODER_BATCH_URL = "https://geocoding.geo.census.gov/geocoder/geographies/addressbatch"
GEOCODER_BENCHMARK = "Public_AR_Current"
GEOCODER_VINTAGE = "Current_Current"
GEOCODER_MAX_BATCH = 10_000
GEOCODER_SINGLE_URL = "https://geocoding.geo.census.gov/geocoder/geographies/address"

REL_COLUMNS = (
    "geoid_zcta5_20",
    "geoid_county_20",
    "namelsad_county_20",
    "arealand_part",
)
GAZ_COLUMNS = ("geoid", "aland", "intptlat", "intptlong")
_FIVE_DIGITS = re.compile(r"^[0-9]{5}$")
# The 2026 Gazetteer writes signed coordinates ("+144.751149", "-115.1").
_COORD = re.compile(r"^[+-]?[0-9]{1,3}\.[0-9]+$")


@dataclass(frozen=True, slots=True)
class County:
    fips: str
    state_code: str
    name: str


@dataclass(frozen=True, slots=True)
class ZctaPrimary:
    county_fips: str
    crosses_counties: bool


def parse_relationship(text_: str) -> tuple[dict[str, County], dict[str, ZctaPrimary]]:
    rows = read_delimited(text_)
    if not rows or any(c not in rows[0] for c in REL_COLUMNS):
        found = sorted(rows[0]) if rows else []
        raise SourceError(
            f"ZCTA-county relationship file lacks columns {REL_COLUMNS}; found {found[:20]}"
        )
    counties: dict[str, County] = {}
    parts: dict[str, list[tuple[int, str]]] = {}
    for r in rows:
        cfips = r["geoid_county_20"]
        if not _FIVE_DIGITS.match(cfips):
            continue
        state = STATE_FIPS.get(cfips[:2])
        if state is None:
            continue
        counties.setdefault(cfips, County(cfips, state, r["namelsad_county_20"]))
        zcta = r["geoid_zcta5_20"]
        if _FIVE_DIGITS.match(zcta):
            parts.setdefault(zcta, []).append((int(r["arealand_part"] or 0), cfips))
    primary: dict[str, ZctaPrimary] = {}
    for zcta, plist in parts.items():
        best = sorted(plist, key=lambda p: (-p[0], p[1]))[0]
        primary[zcta] = ZctaPrimary(best[1], len({c for _, c in plist}) > 1)
    return counties, primary


def _coord(raw: str, lo: int, hi: int) -> Decimal:
    if not _COORD.match(raw):
        raise SourceError(f"bad coordinate {raw!r}")
    value = Decimal(raw)
    if not Decimal(lo) <= value <= Decimal(hi):
        raise SourceError(f"coordinate out of range {raw!r}")
    return value


@dataclass(frozen=True, slots=True)
class GazetteerRow:
    lat: Decimal
    lon: Decimal
    aland_m2: int


def parse_gazetteer(text_: str) -> dict[str, GazetteerRow]:
    # Delimiter is detected from the header (tab in older Gazetteer years; the
    # 2026 file was not tab-delimited when first loaded on 2026-11-05).
    rows = read_delimited(text_)
    if not rows or any(c not in rows[0] for c in GAZ_COLUMNS):
        found = sorted(rows[0]) if rows else []
        raise SourceError(f"ZCTA Gazetteer file lacks columns {GAZ_COLUMNS}; found {found[:20]}")
    out: dict[str, GazetteerRow] = {}
    for r in rows:
        if not _FIVE_DIGITS.match(r["geoid"]):
            continue
        out[r["geoid"]] = GazetteerRow(
            lat=_coord(r["intptlat"], -90, 90),
            lon=_coord(r["intptlong"], -180, 180),
            aland_m2=int(r["aland"]),
        )
    return out


def load_census_lookups(
    conn: Connection,
    relationship_text: str,
    gazetteer_text: str,
    state_code: str,
    gazetteer_year: int,
    source_label: str,
) -> LoadStats:
    """Upsert ref.county and ref.zcta for one state."""
    counties, primary = parse_relationship(relationship_text)
    gaz = parse_gazetteer(gazetteer_text)
    stats = LoadStats()
    state_counties = [c for c in counties.values() if c.state_code == state_code]
    if not state_counties:
        raise SourceError(f"no counties for {state_code} in the relationship file")
    for c in state_counties:
        conn.execute(
            text(
                """
                INSERT INTO ref.county (county_fips, state_code, name, source)
                VALUES (:f, :s, :n, :src)
                ON CONFLICT (county_fips) DO UPDATE
                SET name = EXCLUDED.name, state_code = EXCLUDED.state_code,
                    source = EXCLUDED.source
                """
            ),
            {"f": c.fips, "s": c.state_code, "n": c.name, "src": source_label},
        )
    stats.summary["counties"] = len(state_counties)
    state_fips = {c.fips for c in state_counties}
    for zcta, prim in sorted(primary.items()):
        if prim.county_fips not in state_fips:
            continue
        stats.rows_in += 1
        g = gaz.get(zcta)
        if g is None:
            stats.reject(f"zcta:{zcta}", "not_in_gazetteer", f"ZCTA {zcta} has no Gazetteer row")
            continue
        conn.execute(
            text(
                """
                INSERT INTO ref.zcta (zcta5, state_code, county_fips, crosses_counties, aland_m2,
                                      geom, gazetteer_year, source)
                VALUES (:z, :s, :c, :x, :a,
                        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :y, :src)
                ON CONFLICT (zcta5) DO UPDATE SET
                    state_code = EXCLUDED.state_code, county_fips = EXCLUDED.county_fips,
                    crosses_counties = EXCLUDED.crosses_counties, aland_m2 = EXCLUDED.aland_m2,
                    geom = EXCLUDED.geom, gazetteer_year = EXCLUDED.gazetteer_year,
                    source = EXCLUDED.source
                """
            ),
            {
                "z": zcta,
                "s": state_code,
                "c": prim.county_fips,
                "x": prim.crosses_counties,
                "a": g.aland_m2,
                "lon": g.lon,
                "lat": g.lat,
                "y": gazetteer_year,
                "src": source_label,
            },
        )
        stats.rows_loaded += 1
    return stats


# --------------------------------------------------------------- geocoder
@dataclass(frozen=True, slots=True)
class AddressRow:
    id: str
    street: str
    city: str
    state: str
    zip5: str


@dataclass(frozen=True, slots=True)
class GeocodeResult:
    status: str  # "match", "no_match", "tie"
    exact: bool = False
    matched_address: str | None = None
    lon: Decimal | None = None
    lat: Decimal | None = None
    state_fips: str | None = None
    county_fips3: str | None = None
    method: str = "batch"  # "batch" or "single" (one-address endpoint)


def build_batch_csv(rows: Iterable[AddressRow]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for r in rows:
        writer.writerow([r.id, r.street, r.city, r.state, r.zip5])
    return buf.getvalue().encode()


def parse_batch_response(text_: str) -> dict[str, GeocodeResult]:
    out: dict[str, GeocodeResult] = {}
    for cells in csv.reader(io.StringIO(text_)):
        if not cells or not cells[0].strip():
            continue
        if len(cells) < 3:
            raise SourceError(f"unexpected geocoder row {cells!r}")
        rid, status = cells[0].strip(), cells[2].strip().lower()
        if status == "match":
            if len(cells) < 10:
                raise SourceError(f"geocoder match row too short: {cells!r}")
            lon_s, _, lat_s = cells[5].partition(",")
            out[rid] = GeocodeResult(
                status="match",
                exact=cells[3].strip().lower() == "exact",
                matched_address=cells[4].strip() or None,
                lon=_coord(lon_s.strip(), -180, 180),
                lat=_coord(lat_s.strip(), -90, 90),
                state_fips=cells[8].strip() or None,
                county_fips3=cells[9].strip() or None,
            )
        elif status in ("no_match", "tie"):
            out[rid] = GeocodeResult(status=status)
        else:
            raise SourceError(f"unknown geocoder status {cells[2]!r}")
    return out


RETRY_WAIT_SECONDS = (10, 30, 60)


def _post_with_retry(client: httpx.Client, chunk: list[AddressRow]) -> str:
    """POST one batch; retry server errors (5xx) and network errors a few times,
    since the Census geocoder is occasionally unavailable (HTTP 502 seen 2026-11-05)."""
    last = "no attempt"
    for wait in (*RETRY_WAIT_SECONDS, None):
        try:
            resp = client.post(
                GEOCODER_BATCH_URL,
                data={"benchmark": GEOCODER_BENCHMARK, "vintage": GEOCODER_VINTAGE},
                files={"addressFile": ("addresses.csv", build_batch_csv(chunk), "text/csv")},
                timeout=httpx.Timeout(600),
            )
        except httpx.TransportError as exc:
            last = f"{type(exc).__name__}: {exc}"
        else:
            if resp.status_code == 200:
                return resp.text
            last = f"HTTP {resp.status_code}"
            if resp.status_code < 500:
                break
        if wait is not None:
            time.sleep(wait)
    raise SourceError(f"Census geocoder failed: {last}")


def parse_single_response(body: str) -> GeocodeResult:
    """One-address JSON response: result.addressMatches[] with coordinates
    {x: lon, y: lat}, matchedAddress, geographies.Counties[].STATE/COUNTY.
    Numbers are read as Decimal, never float. Several matches = a tie."""
    data = json.loads(body, parse_float=Decimal)
    matches = data.get("result", {}).get("addressMatches") or []
    if not matches:
        return GeocodeResult(status="no_match", method="single")
    if len(matches) > 1:
        return GeocodeResult(status="tie", method="single")
    m = matches[0]
    coords = m.get("coordinates") or {}
    counties = (m.get("geographies") or {}).get("Counties") or []
    county = counties[0] if len(counties) == 1 else {}
    return GeocodeResult(
        status="match",
        exact=False,  # the one-address endpoint does not report Exact/Non_Exact
        matched_address=m.get("matchedAddress"),
        lon=_coord(str(coords.get("x", "")), -180, 180),
        lat=_coord(str(coords.get("y", "")), -90, 90),
        state_fips=county.get("STATE"),
        county_fips3=county.get("COUNTY"),
        method="single",
    )


MAX_CONSECUTIVE_SINGLE_FAILURES = 5


def census_single_geocode(client: httpx.Client, rows: list[AddressRow]) -> dict[str, GeocodeResult]:
    """Geocode one address per request. Used when the batch endpoint fails.
    A failed request leaves that address without a result; several failures in
    a row mean the service is down and raise SourceError."""
    results: dict[str, GeocodeResult] = {}
    consecutive = 0
    last = ""
    for r in rows:
        try:
            resp = client.get(
                GEOCODER_SINGLE_URL,
                params={
                    "street": r.street,
                    "city": r.city,
                    "state": r.state,
                    "zip": r.zip5,
                    "benchmark": GEOCODER_BENCHMARK,
                    "vintage": GEOCODER_VINTAGE,
                    "format": "json",
                },
                timeout=httpx.Timeout(60),
            )
            if resp.status_code != 200:
                raise SourceError(f"HTTP {resp.status_code}")
            results[r.id] = parse_single_response(resp.text)
            consecutive = 0
        except (SourceError, httpx.TransportError, ValueError) as exc:
            consecutive += 1
            last = f"{type(exc).__name__}: {exc}"
            if consecutive >= MAX_CONSECUTIVE_SINGLE_FAILURES:
                raise SourceError(f"Census one-address geocoder failed: {last}") from exc
    return results


def census_geocode(client: httpx.Client, rows: list[AddressRow]) -> dict[str, GeocodeResult]:
    """Batch endpoint first; if it keeps failing, one address at a time."""
    try:
        return census_batch_geocode(client, rows)
    except SourceError:
        return census_single_geocode(client, rows)


def census_batch_geocode(client: httpx.Client, rows: list[AddressRow]) -> dict[str, GeocodeResult]:
    """Geocode addresses with the Census batch geographies endpoint."""
    results: dict[str, GeocodeResult] = {}
    for start in range(0, len(rows), GEOCODER_MAX_BATCH):
        chunk = rows[start : start + GEOCODER_MAX_BATCH]
        results.update(parse_batch_response(_post_with_retry(client, chunk)))
    return results
