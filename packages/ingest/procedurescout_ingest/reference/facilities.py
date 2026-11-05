"""Load hospitals (CMS Hospital General Information) and ambulatory surgical
centers (CMS ASC Quality Measures - Facility) into ref.facility.

Identity is the CMS Certification Number (CCN). Rows are upserted by CCN; a
name never decides identity. Facility names from CMS become identifier-linked
aliases. Unknown hospital types are rejected, not guessed. When an address
changes, the old geocode is cleared so it is redone.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, replace
from datetime import date

from sqlalchemy import Connection, text

from procedurescout_core.enums import FacilityType, Severity
from procedurescout_core.facility_repo import add_alias

from .common import LoadStats, parse_zip5

HOSPITAL_SOURCE = "cms_pdc:xubh-q36u"
ASC_SOURCE = "cms_pdc:4jcv-atw7"

# CMS "Hospital Type" values -> our facility type. The raw value is always kept.
HOSPITAL_TYPE_MAP: dict[str, FacilityType] = {
    "acute care hospitals": FacilityType.ACUTE_CARE_HOSPITAL,
    "acute care - veterans administration": FacilityType.ACUTE_CARE_HOSPITAL,
    "acute care - department of defense": FacilityType.ACUTE_CARE_HOSPITAL,
    "critical access hospitals": FacilityType.CRITICAL_ACCESS_HOSPITAL,
    "childrens": FacilityType.CHILDRENS_HOSPITAL,
    "psychiatric": FacilityType.PSYCHIATRIC_HOSPITAL,
    "rural emergency hospital": FacilityType.OTHER,
}

HOSPITAL_CCN_RE = re.compile(r"^[0-9A-Z]{6}$")
ASC_CCN_RE = re.compile(r"^[0-9]{2}C[0-9]{7}$")
NPI_RE = re.compile(r"^[0-9]{10}$")
REQUIRED_HOSPITAL_COLUMNS = (
    "facility_id",
    "facility_name",
    "address",
    "citytown",
    "state",
    "zip_code",
    "countyparish",
    "telephone_number",
    "hospital_type",
    "hospital_ownership",
    "emergency_services",
    "hospital_overall_rating",
)
REQUIRED_ASC_COLUMNS = ("facility_id", "facility_name", "npi", "citytown", "state", "zip_code")


@dataclass(frozen=True, slots=True)
class FacilityRecord:
    ccn: str
    name: str
    facility_type: FacilityType
    cms_type_raw: str
    state_code: str
    city: str | None
    zip5: str | None
    address_line1: str | None = None
    county_name: str | None = None
    phone: str | None = None
    ownership: str | None = None
    er_services: bool | None = None
    rating: int | None = None
    npi: str | None = None


def _blank(value: str) -> str | None:
    value = value.strip()
    return value or None


def parse_hospital(
    row: dict[str, str], row_ref: str, state_code: str, stats: LoadStats
) -> FacilityRecord | None:
    ccn = row.get("facility_id", "").strip().upper()
    if not HOSPITAL_CCN_RE.match(ccn):
        stats.reject(row_ref, "ccn_format", f"facility_id {ccn!r} is not a 6-character CCN")
        return None
    name = row.get("facility_name", "").strip()
    if not name:
        stats.reject(row_ref, "name_missing", f"{ccn}: no facility name")
        return None
    if row.get("state", "").strip().upper() != state_code:
        stats.reject(row_ref, "state_mismatch", f"{ccn}: state {row.get('state')!r}")
        return None
    raw_type = row.get("hospital_type", "").strip()
    ftype = HOSPITAL_TYPE_MAP.get(raw_type.lower())
    if ftype is None:
        stats.reject(row_ref, "unknown_hospital_type", f"{ccn}: hospital type {raw_type!r}")
        return None
    zip_raw = row.get("zip_code", "")
    zip5 = parse_zip5(zip_raw)
    if zip5 is None:
        stats.reject(
            row_ref,
            "zip_format",
            f"{ccn}: ZIP {zip_raw!r} unreadable; stored without ZIP",
            Severity.WARNING,
        )
    er_raw = row.get("emergency_services", "").strip().lower()
    er = {"yes": True, "no": False}.get(er_raw)
    if er is None and er_raw:
        stats.reject(row_ref, "er_value", f"{ccn}: emergency_services {er_raw!r}", Severity.WARNING)
    rating_raw = row.get("hospital_overall_rating", "").strip()
    rating: int | None = None
    if rating_raw in {"1", "2", "3", "4", "5"}:
        rating = int(rating_raw)
    elif rating_raw and rating_raw.lower() != "not available":
        stats.reject(row_ref, "rating_value", f"{ccn}: rating {rating_raw!r}", Severity.WARNING)
    return FacilityRecord(
        ccn=ccn,
        name=name,
        facility_type=ftype,
        cms_type_raw=raw_type,
        state_code=state_code,
        city=_blank(row.get("citytown", "")),
        zip5=zip5,
        address_line1=_blank(row.get("address", "")),
        county_name=_blank(row.get("countyparish", "")),
        phone=_blank(row.get("telephone_number", "")),
        ownership=_blank(row.get("hospital_ownership", "")),
        er_services=er,
        rating=rating,
    )


def parse_asc(
    row: dict[str, str], row_ref: str, state_code: str, stats: LoadStats
) -> FacilityRecord | None:
    ccn = row.get("facility_id", "").strip().upper()
    if not ASC_CCN_RE.match(ccn):
        stats.reject(row_ref, "ccn_format", f"facility_id {ccn!r} is not a 10-character ASC CCN")
        return None
    name = row.get("facility_name", "").strip()
    if not name:
        stats.reject(row_ref, "name_missing", f"{ccn}: no facility name")
        return None
    if row.get("state", "").strip().upper() != state_code:
        stats.reject(row_ref, "state_mismatch", f"{ccn}: state {row.get('state')!r}")
        return None
    npi = row.get("npi", "").strip()
    if npi and not NPI_RE.match(npi):
        stats.reject(row_ref, "npi_format", f"{ccn}: NPI {npi!r} ignored", Severity.WARNING)
        npi = ""
    zip_raw = row.get("zip_code", "")
    zip5 = parse_zip5(zip_raw)
    if zip5 is None:
        stats.reject(row_ref, "zip_format", f"{ccn}: ZIP {zip_raw!r} unreadable", Severity.WARNING)
    return FacilityRecord(
        ccn=ccn,
        name=name,
        facility_type=FacilityType.AMBULATORY_SURGERY_CENTER,
        cms_type_raw="Ambulatory Surgical Center (ASCQR program)",
        state_code=state_code,
        city=_blank(row.get("citytown", "")),
        zip5=zip5,
        npi=npi or None,
    )


# On conflict, an address/ZIP change invalidates the stored geocode.
_UPSERT = """
INSERT INTO ref.facility AS f
    (ccn, name, facility_type, cms_facility_type_raw, ownership, address_line1, city,
     state_code, zip5, county_name, phone, er_services, cms_overall_rating, cms_rating_as_of,
     source_dataset, source_updated_at, source_last_seen_at)
VALUES
    (:ccn, :name, CAST(:ftype AS ref.facility_type), :raw_type, :ownership, :address, :city,
     :state, :zip5, :county, :phone, :er, :rating, :rating_as_of,
     :source, CAST(:as_of AS timestamptz), now())
ON CONFLICT (ccn) DO UPDATE SET
    name = EXCLUDED.name,
    facility_type = EXCLUDED.facility_type,
    cms_facility_type_raw = EXCLUDED.cms_facility_type_raw,
    ownership = COALESCE(EXCLUDED.ownership, f.ownership),
    address_line1 = {address_update},
    city = EXCLUDED.city,
    zip5 = EXCLUDED.zip5,
    county_name = COALESCE(EXCLUDED.county_name, f.county_name),
    phone = COALESCE(EXCLUDED.phone, f.phone),
    er_services = {er_update},
    cms_overall_rating = {rating_update},
    cms_rating_as_of = {rating_as_of_update},
    source_dataset = EXCLUDED.source_dataset,
    source_updated_at = EXCLUDED.source_updated_at,
    source_last_seen_at = now(),
    updated_at = now(),
    geom = CASE WHEN {moved} THEN NULL ELSE f.geom END,
    geocode_source = CASE WHEN {moved} THEN NULL ELSE f.geocode_source END,
    geocode_precision = CASE WHEN {moved} THEN NULL ELSE f.geocode_precision END,
    geocoded_at = CASE WHEN {moved} THEN NULL ELSE f.geocoded_at END
RETURNING id, (xmax = 0) AS inserted
"""

# Hospitals: CMS address, ER flag and rating are authoritative and replace old values.
_HOSPITAL_UPSERT = _UPSERT.format(
    address_update="EXCLUDED.address_line1",
    er_update="EXCLUDED.er_services",
    rating_update="EXCLUDED.cms_overall_rating",
    rating_as_of_update="EXCLUDED.cms_rating_as_of",
    moved="(f.address_line1, f.city, f.zip5) IS DISTINCT FROM "
    "(EXCLUDED.address_line1, EXCLUDED.city, EXCLUDED.zip5)",
)
# ASCs: the CMS ASC file has no street address or rating; keep what NPPES supplied
# unless the city or ZIP changed, in which case the old street address is dropped too.
_ASC_UPSERT = _UPSERT.format(
    address_update="CASE WHEN (f.city, f.zip5) IS DISTINCT FROM (EXCLUDED.city, EXCLUDED.zip5) "
    "THEN NULL ELSE f.address_line1 END",
    er_update="f.er_services",
    rating_update="f.cms_overall_rating",
    rating_as_of_update="f.cms_rating_as_of",
    moved="(f.city, f.zip5) IS DISTINCT FROM (EXCLUDED.city, EXCLUDED.zip5)",
)


def _upsert(
    conn: Connection, rec: FacilityRecord, sql: str, source: str, as_of: date | None
) -> tuple[uuid.UUID, bool]:
    row = conn.execute(
        text(sql),
        {
            "ccn": rec.ccn,
            "name": rec.name,
            "ftype": rec.facility_type.value,
            "raw_type": rec.cms_type_raw,
            "ownership": rec.ownership,
            "address": rec.address_line1,
            "city": rec.city,
            "state": rec.state_code,
            "zip5": rec.zip5,
            "county": rec.county_name,
            "phone": rec.phone,
            "er": rec.er_services,
            "rating": rec.rating,
            "rating_as_of": as_of if rec.rating is not None else None,
            "source": source,
            "as_of": as_of,
        },
    ).one()
    return uuid.UUID(str(row[0])), bool(row[1])


def _check_existing_state(
    conn: Connection, rec: FacilityRecord, row_ref: str, stats: LoadStats
) -> bool:
    existing = conn.execute(
        text("SELECT state_code FROM ref.facility WHERE ccn = :c"), {"c": rec.ccn}
    ).scalar_one_or_none()
    if existing is not None and existing != rec.state_code:
        stats.reject(row_ref, "ccn_state_changed", f"{rec.ccn}: stored state {existing}")
        return False
    return True


def load_hospitals(
    conn: Connection, rows: list[dict[str, str]], state_code: str, as_of: date | None
) -> LoadStats:
    """Upsert hospitals for one state. `as_of` is the dataset's modified date; it
    dates the star rating (the database refuses a rating without a date)."""
    stats = LoadStats(rows_in=len(rows))
    seen: set[str] = set()
    for i, row in enumerate(rows, start=1):
        ref = f"row:{i}"
        rec = parse_hospital(row, ref, state_code, stats)
        if rec is None:
            continue
        if rec.ccn in seen:
            stats.reject(ref, "duplicate_ccn", f"{rec.ccn} appears twice; first row kept")
            continue
        seen.add(rec.ccn)
        if rec.rating is not None and as_of is None:
            stats.reject(
                ref,
                "rating_undated",
                f"{rec.ccn}: rating dropped (no as-of date)",
                Severity.WARNING,
            )
            rec = replace(rec, rating=None)
        if not _check_existing_state(conn, rec, ref, stats):
            continue
        fid, inserted = _upsert(conn, rec, _HOSPITAL_UPSERT, HOSPITAL_SOURCE, as_of)
        add_alias(
            conn, fid, rec.name, alias_type="cms_name", source=HOSPITAL_SOURCE, match_basis="ccn"
        )
        stats.rows_loaded += 1
        stats.count("inserted" if inserted else "updated")
        stats.count(f"type:{rec.facility_type.value}")
    return stats


def load_ascs(
    conn: Connection, rows: list[dict[str, str]], state_code: str, as_of: date | None
) -> LoadStats:
    stats = LoadStats(rows_in=len(rows))
    seen: set[str] = set()
    for i, row in enumerate(rows, start=1):
        ref = f"row:{i}"
        rec = parse_asc(row, ref, state_code, stats)
        if rec is None:
            continue
        if rec.ccn in seen:
            stats.reject(ref, "duplicate_ccn", f"{rec.ccn} appears twice; first row kept")
            continue
        seen.add(rec.ccn)
        if not _check_existing_state(conn, rec, ref, stats):
            continue
        fid, inserted = _upsert(conn, rec, _ASC_UPSERT, ASC_SOURCE, as_of)
        add_alias(conn, fid, rec.name, alias_type="cms_name", source=ASC_SOURCE, match_basis="ccn")
        if rec.npi:
            owner = conn.execute(
                text("SELECT facility_id FROM ref.facility_npi WHERE npi = :n"), {"n": rec.npi}
            ).scalar_one_or_none()
            if owner is None:
                conn.execute(
                    text(
                        "INSERT INTO ref.facility_npi (facility_id, npi, source) "
                        "VALUES (:f, :n, :s)"
                    ),
                    {"f": fid, "n": rec.npi, "s": ASC_SOURCE},
                )
            elif uuid.UUID(str(owner)) != fid:
                stats.reject(
                    ref,
                    "npi_conflict",
                    f"{rec.ccn}: NPI {rec.npi} already belongs to another facility",
                    Severity.WARNING,
                )
        stats.rows_loaded += 1
        stats.count("inserted" if inserted else "updated")
    return stats
