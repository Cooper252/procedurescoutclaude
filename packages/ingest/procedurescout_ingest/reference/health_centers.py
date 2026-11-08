"""HRSA health center sites (community health centers with sliding fees).

Source: data.hrsa.gov "Health Center Service Delivery and Look-Alike Sites"
(CSV, refreshed daily). Columns are found by name from a short list of known
spellings; if a required one is missing the load stops and reports the
headers it saw, so nothing is guessed.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal, InvalidOperation

from sqlalchemy import Connection, text

from .common import LoadStats, read_delimited

HRSA_SITES_URL = "https://data.hrsa.gov/DataDownload/DD_Files/Health_Center_Service_Delivery_and_LookAlike_Sites.csv"

COLUMNS: dict[str, tuple[str, ...]] = {
    "name": ("site name",),
    "organization": ("health center name", "grantee organization name", "organization name"),
    "address": ("site address", "site street address"),
    "city": ("site city",),
    "state": ("site state abbreviation", "site state"),
    "zip": ("site postal code", "site zip code"),
    "phone": ("site telephone number", "site phone number"),
    "website": ("site web address", "site url"),
    "lng": ("geocoding artifact address primary x coordinate", "longitude", "x coordinate"),
    "lat": ("geocoding artifact address primary y coordinate", "latitude", "y coordinate"),
    "status": ("site status description", "site status"),
    "site_type": (
        "health center service delivery site location setting description",
        "health center location type description",
        "site type description",
    ),
    "center_type": ("health center type", "health center type description"),
    "key": ("bphc assigned number", "site number", "health center service delivery site id"),
}
REQUIRED = ("name", "address", "city", "state")


class HealthCenterError(ValueError):
    pass


def _norm(h: str) -> str:
    return " ".join(h.lower().replace("_", " ").split())


def find_columns(headers: list[str]) -> dict[str, str]:
    by_norm = {_norm(h): h for h in headers}
    found = {}
    for field, names in COLUMNS.items():
        for n in names:
            if n in by_norm:
                found[field] = by_norm[n]
                break
    missing = [f for f in REQUIRED if f not in found]
    if missing:
        raise HealthCenterError(
            f"HRSA file is missing {missing}; headers seen: {sorted(headers)[:60]}"
        )
    return found


def load_health_centers(conn: Connection, csv_text: str, state_code: str) -> LoadStats:
    stats = LoadStats()
    rows = read_delimited(csv_text, ",")
    if not rows:
        raise HealthCenterError("HRSA file is empty")
    col = find_columns(list(rows[0].keys()))
    st = state_code.upper()
    conn.execute(text("DELETE FROM ref.health_center WHERE state_code = :s"), {"s": st})
    for row in rows:
        if row[col["state"]].strip().upper() != st:
            continue
        stats.rows_in += 1
        if "status" in col and row[col["status"]].strip().lower() not in ("active", ""):
            stats.count("not_active")
            continue

        def g(field: str, row: dict[str, str] = row) -> str | None:
            if field not in col:
                return None
            return (row.get(col[field]) or "").strip() or None

        lat, lng = g("lat"), g("lng")
        try:
            ok = (
                lat is not None
                and lng is not None
                and Decimal(-90) <= Decimal(lat) <= Decimal(90)
                and Decimal(-180) <= Decimal(lng) <= Decimal(180)
            )
        except InvalidOperation:
            ok = False
        key = (
            g("key")
            or hashlib.sha256(f"{g('name')}|{g('address')}|{g('city')}".encode()).hexdigest()[:24]
        )
        conn.execute(
            text(
                """
                INSERT INTO ref.health_center (source_key, name, organization, address_line1,
                    city, state_code, zip5, phone, website, site_type, center_type, geom, source)
                VALUES (:k, :n, :o, :a, :c, :s, :z, :p, :w, :st, :ct,
                    CASE WHEN :ok THEN CAST(ST_SetSRID(ST_MakePoint(CAST(:lng AS numeric),
                        CAST(:lat AS numeric)), 4326) AS geography) END,
                    'HRSA health center sites')
                ON CONFLICT (source_key) DO NOTHING
                """
            ),
            {
                "k": key,
                "n": g("name"),
                "o": g("organization"),
                "a": g("address"),
                "c": g("city"),
                "s": st,
                "z": (g("zip") or "")[:5] or None,
                "p": g("phone"),
                "w": g("website"),
                "st": g("site_type"),
                "ct": g("center_type"),
                "ok": ok,
                "lat": lat if ok else None,
                "lng": lng if ok else None,
            },
        )
        stats.rows_loaded += 1
        stats.count("with_location" if ok else "without_location")
    return stats
