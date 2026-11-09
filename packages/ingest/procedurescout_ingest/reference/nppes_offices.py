"""Offices from the national provider list (NPPES), so dentists, chiropractors,
eye doctors, therapists, urgent care and more can be found and claim a page
(D-052).

Sources:
- the NPPES Data Dissemination file (monthly full file, about 1.1 GB zipped,
  or the weekly update file in the same format), download.cms.gov/nppes;
- the NUCC taxonomy code list (nucc.org), which names each taxonomy code;
- data/reference/nppes_taxonomy_map.csv, which says which taxonomy
  classifications become which of our provider types. Only reviewed rows are
  used (rule 10); a row that matches no NUCC code is reported, never guessed.

Only organizations (entity type 2) with an active NPI and a practice location
in the chosen state are loaded. An NPI already linked to a hospital or surgery
center is attached to that facility instead of creating a second one. Columns
are found by name; if a required one is missing the load stops and lists what
it saw.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from sqlalchemy import Connection, text

from .common import LoadStats

NPPES_FILES_PAGE = "https://download.cms.gov/nppes/NPI_Files.html"
NUCC_CSV_PAGE = "https://www.nucc.org/index.php/code-sets-mainmenu-41/provider-taxonomy-mainmenu-40/csv-mainmenu-57"
DATASET = "nppes_offices"
MAX_TAXONOMIES = 15

COL = {
    "npi": "NPI",
    "entity": "Entity Type Code",
    "legal_name": "Provider Organization Name (Legal Business Name)",
    "other_name": "Provider Other Organization Name",
    "other_name_type": "Provider Other Organization Name Type Code",
    "addr1": "Provider First Line Business Practice Location Address",
    "addr2": "Provider Second Line Business Practice Location Address",
    "city": "Provider Business Practice Location Address City Name",
    "state": "Provider Business Practice Location Address State Name",
    "zip": "Provider Business Practice Location Address Postal Code",
    "phone": "Provider Business Practice Location Address Telephone Number",
    "deactivated": "NPI Deactivation Date",
    "reactivated": "NPI Reactivation Date",
}
REQUIRED = ("npi", "entity", "legal_name", "addr1", "city", "state", "zip")


class NppesError(ValueError):
    pass


# ---------------------------------------------------------------- taxonomy
@dataclass(frozen=True, slots=True)
class MapRow:
    classification: str
    specialization: str  # "*" = any
    provider_type: str


def read_map(csv_text: str, stats: LoadStats | None = None) -> list[MapRow]:
    rows = []
    for i, r in enumerate(csv.DictReader(io.StringIO(csv_text)), start=2):
        if not (r.get("reviewed_by") or "").strip():
            if stats is not None:
                stats.count("taxonomy_rows_waiting_for_review")
            continue
        rows.append(
            MapRow(
                r["classification"].strip(),
                (r.get("specialization") or "*").strip() or "*",
                r["provider_type"].strip(),
            )
        )
        if not rows[-1].classification or not rows[-1].provider_type:
            raise NppesError(f"taxonomy map line {i} is incomplete")
    return rows


def _n(s: str) -> str:
    return " ".join(s.lower().split())


def codes_for(nucc_csv: str, mapping: list[MapRow], stats: LoadStats) -> dict[str, set[str]]:
    """taxonomy code -> our provider types, from the NUCC list."""
    reader = csv.DictReader(io.StringIO(nucc_csv.lstrip("﻿")))
    headers = {_n(h): h for h in (reader.fieldnames or [])}
    for need in ("code", "classification", "specialization"):
        if need not in headers:
            raise NppesError(f"NUCC file is missing '{need}'; saw {sorted(headers)}")
    out: dict[str, set[str]] = {}
    used: set[MapRow] = set()
    for r in reader:
        code = (r[headers["code"]] or "").strip()
        cls = _n(r[headers["classification"]] or "")
        spec = _n(r[headers["specialization"]] or "")
        for m in mapping:
            if _n(m.classification) != cls:
                continue
            want = _n(m.specialization)
            if want != "*" and not (spec == want or spec.startswith(want + ",")):
                continue
            out.setdefault(code, set()).add(m.provider_type)
            used.add(m)
    for m in mapping:
        if m not in used:
            stats.reject(
                f"map:{m.classification}/{m.specialization}",
                "taxonomy_not_in_nucc",
                "this classification/specialization matched no NUCC code; check the spelling",
            )
    stats.summary["taxonomy_codes_mapped"] = len(out)
    return out


# ------------------------------------------------------------------- NPPES
def open_npi_csv(path: Path) -> Iterator[dict[str, str]]:
    """Rows of the main NPI file inside the NPPES zip (or a plain CSV)."""
    if path.suffix.lower() == ".zip":
        zf = zipfile.ZipFile(path)
        names = [
            n
            for n in zf.namelist()
            if re.search(r"npidata_pfile_.*\.csv$", n, re.I) and "fileheader" not in n.lower()
        ]
        if not names:
            raise NppesError(f"no npidata_pfile CSV in {path.name}; saw {zf.namelist()[:10]}")
        raw: IO[bytes] = zf.open(names[0])
        handle: IO[str] = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
    else:
        handle = path.open(encoding="utf-8", errors="replace", newline="")
    with handle:
        yield from csv.DictReader(handle)


def _zip5(z: str) -> str | None:
    d = re.sub(r"\D", "", z or "")
    return d[:5] if len(d) >= 5 else None


def _phone(p: str) -> str | None:
    d = re.sub(r"\D", "", p or "")
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if len(d) == 10 else None


def _date_key(s: str) -> str:
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", (s or "").strip())
    return f"{m.group(3)}{m.group(1)}{m.group(2)}" if m else (s or "").strip()


def _active(r: dict[str, str]) -> bool:
    off = (r.get(COL["deactivated"]) or "").strip()
    on = (r.get(COL["reactivated"]) or "").strip()
    return not off or (bool(on) and _date_key(on) >= _date_key(off))


def _title(name: str) -> str:
    """NPPES names are often ALL CAPS; make them readable without guessing."""
    if name != name.upper():
        return name.strip()
    keep = {
        "LLC",
        "PLLC",
        "PC",
        "PA",
        "DDS",
        "DMD",
        "MD",
        "DO",
        "OD",
        "PT",
        "LLP",
        "INC",
        "USA",
        "II",
        "III",
        "IV",
        "MRI",
        "CT",
        "ENT",
    }
    words = []
    for w in name.strip().split():
        core = re.sub(r"[^A-Z]", "", w)
        words.append(w if core in keep else w.capitalize())
    return " ".join(words)


@dataclass(frozen=True, slots=True)
class Office:
    npi: str
    name: str
    address: str
    city: str
    state: str
    zip5: str
    phone: str | None
    taxonomies: tuple[str, ...]
    types: tuple[str, ...]
    active: bool


def offices(
    rows: Iterable[dict[str, str]],
    states: set[str],
    code_types: dict[str, set[str]],
    stats: LoadStats,
) -> Iterator[Office]:
    checked = False
    for r in rows:
        if not checked:
            missing = [k for k in REQUIRED if COL[k] not in r]
            if missing:
                raise NppesError(
                    f"NPPES file is missing {[COL[k] for k in missing]}; saw {list(r)[:20]}"
                )
            checked = True
        stats.rows_in += 1
        if (r.get(COL["entity"]) or "").strip() != "2":
            continue
        state = (r.get(COL["state"]) or "").strip().upper()
        if state not in states:
            continue
        taxes = tuple(
            t
            for t in (
                (r.get(f"Healthcare Provider Taxonomy Code_{i}") or "").strip()
                for i in range(1, MAX_TAXONOMIES + 1)
            )
            if t
        )
        types = sorted({pt for t in taxes for pt in code_types.get(t, ())})
        if not types:
            continue
        npi = (r.get(COL["npi"]) or "").strip()
        zip5 = _zip5(r.get(COL["zip"]) or "")
        if not re.fullmatch(r"\d{10}", npi) or zip5 is None:
            stats.reject(npi or "?", "bad_npi_or_zip", "NPI or ZIP is not valid")
            continue
        other = (r.get(COL["other_name"]) or "").strip()
        use_other = other and (r.get(COL["other_name_type"]) or "").strip() == "3"  # d/b/a
        name = _title(other if use_other else (r.get(COL["legal_name"]) or "").strip())
        addr = " ".join(
            x
            for x in ((r.get(COL["addr1"]) or "").strip(), (r.get(COL["addr2"]) or "").strip())
            if x
        )
        if not name or not addr:
            stats.reject(npi, "missing_name_or_address", "no name or practice address")
            continue
        yield Office(
            npi=npi,
            name=name,
            address=_title(addr),
            city=_title((r.get(COL["city"]) or "").strip()),
            state=state,
            zip5=zip5,
            phone=_phone(r.get(COL["phone"]) or ""),
            taxonomies=taxes,
            types=tuple(types),
            active=_active(r),
        )


# -------------------------------------------------------------------- load
def load(conn: Connection, items: Iterable[Office], stats: LoadStats) -> LoadStats:
    for o in items:
        existing = conn.execute(
            text(
                "SELECT n.facility_id, f.source_dataset FROM ref.facility_npi n "
                "JOIN ref.facility f ON f.id = n.facility_id WHERE n.npi = :n"
            ),
            {"n": o.npi},
        ).first()
        if existing is not None and existing[1] != DATASET:
            stats.count("already_listed_hospital_or_surgery_center")
            continue
        if not o.active:
            if existing is not None:
                conn.execute(
                    text(
                        "UPDATE ref.facility SET status = 'inactive', updated_at = now() "
                        "WHERE id = :f"
                    ),
                    {"f": existing[0]},
                )
                stats.count("deactivated")
            continue
        params = {
            "name": o.name,
            "a": o.address,
            "c": o.city,
            "s": o.state,
            "z": o.zip5,
            "p": o.phone,
            "t": list(o.taxonomies),
            "ds": DATASET,
        }
        if existing is None:
            fid = conn.execute(
                text(
                    """
                    INSERT INTO ref.facility (name, facility_type, address_line1, city,
                        state_code, zip5, phone, taxonomy_codes, source_dataset, status,
                        source_updated_at)
                    VALUES (:name, 'other', :a, :c, :s, :z, :p, :t, :ds, 'active', now())
                    RETURNING id
                    """
                ),
                params,
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO ref.facility_npi (facility_id, npi, taxonomy_code, source) "
                    "VALUES (:f, :n, :tc, :ds)"
                ),
                {
                    "f": fid,
                    "n": o.npi,
                    "tc": o.taxonomies[0] if o.taxonomies else None,
                    "ds": DATASET,
                },
            )
            stats.count("inserted")
        else:
            fid = existing[0]
            moved = conn.execute(
                text("SELECT address_line1 IS DISTINCT FROM :a FROM ref.facility WHERE id = :f"),
                {"a": o.address, "f": fid},
            ).scalar()
            conn.execute(
                text(
                    """
                    UPDATE ref.facility SET name = :name, address_line1 = :a, city = :c,
                        state_code = :s, zip5 = :z, phone = :p, taxonomy_codes = :t,
                        status = 'active', source_updated_at = now(), updated_at = now()
                    WHERE id = :f
                    """
                ),
                {**params, "f": fid},
            )
            if moved:  # a new address needs a new map location
                conn.execute(
                    text(
                        "UPDATE ref.facility SET geom = NULL, geocode_source = NULL, "
                        "geocode_precision = NULL WHERE id = :f"
                    ),
                    {"f": fid},
                )
            stats.count("updated")
        conn.execute(
            text(
                "DELETE FROM ref.facility_provider_type WHERE facility_id = :f "
                "AND source = 'nppes_taxonomy' AND provider_type <> ALL(:t)"
            ),
            {"f": fid, "t": list(o.types)},
        )
        for t in o.types:
            conn.execute(
                text(
                    "INSERT INTO ref.facility_provider_type (facility_id, provider_type, source) "
                    "VALUES (:f, :t, 'nppes_taxonomy') ON CONFLICT DO NOTHING"
                ),
                {"f": fid, "t": t},
            )
            stats.count(f"type:{t}")
        stats.rows_loaded += 1
    return stats
