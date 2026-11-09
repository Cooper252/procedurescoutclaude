"""Offices from the national provider list and practices asking to be added
(D-052). Synthetic rows only, rolled back after each test."""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import Connection, text

from procedurescout_core import listing_requests as lr
from procedurescout_ingest.reference import nppes_offices as no
from procedurescout_ingest.reference.common import LoadStats
from tests.test_catalog_offers import load_all

NUCC = (
    "Code,Grouping,Classification,Specialization,Definition\n"
    "SYN0000001X,Dental Providers,Dentist,,\n"
    "SYN0000002X,Dental Providers,Dentist,General Practice,\n"
    "SYN0000003X,Ambulatory Health Care Facilities,Clinic/Center,Radiology,\n"
    'SYN0000004X,Ambulatory Health Care Facilities,Clinic/Center,"Radiology, Mammography",\n'
    "SYN0000005X,Chiropractic Providers,Chiropractor,,\n"
    "SYN0000009X,Other,Unrelated Thing,,\n"
)
MAP = (
    "classification,specialization,provider_type,reviewed_by,reviewed_at,notes\n"
    "Dentist,*,dental_office,Cooper,2026-11-09,\n"
    "Clinic/Center,Radiology,imaging_center,Cooper,2026-11-09,\n"
    "Chiropractor,*,chiropractic_office,,,not reviewed yet\n"
    "Massage Therapistt,*,massage_therapy,Cooper,2026-11-09,misspelled on purpose\n"
)
HEAD = [
    "NPI",
    "Entity Type Code",
    "Provider Organization Name (Legal Business Name)",
    "Provider Other Organization Name",
    "Provider Other Organization Name Type Code",
    "Provider First Line Business Practice Location Address",
    "Provider Second Line Business Practice Location Address",
    "Provider Business Practice Location Address City Name",
    "Provider Business Practice Location Address State Name",
    "Provider Business Practice Location Address Postal Code",
    "Provider Business Practice Location Address Telephone Number",
    "NPI Deactivation Date",
    "NPI Reactivation Date",
    *[f"Healthcare Provider Taxonomy Code_{i}" for i in range(1, 16)],
]


def _row(npi: str, entity: str, name: str, state: str, tax: list[str], **kw: str) -> list[str]:
    r = dict.fromkeys(HEAD, "")
    r.update(
        {
            "NPI": npi,
            "Entity Type Code": entity,
            "Provider Organization Name (Legal Business Name)": name,
            "Provider First Line Business Practice Location Address": "100 SYNTHETIC WAY",
            "Provider Business Practice Location Address City Name": "LAS VEGAS",
            "Provider Business Practice Location Address State Name": state,
            "Provider Business Practice Location Address Postal Code": "891011234",
            "Provider Business Practice Location Address Telephone Number": "7025550100",
        }
    )
    for i, t in enumerate(tax, start=1):
        r[f"Healthcare Provider Taxonomy Code_{i}"] = t
    r.update(kw)
    return [r[h] for h in HEAD]


def _zip(tmp: Path, rows: list[list[str]]) -> Path:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(HEAD)
    w.writerows(rows)
    p = tmp / "synthetic_nppes.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("npidata_pfile_20260101-20261101.csv", buf.getvalue())
        z.writestr("npidata_pfile_20260101-20261101_fileheader.csv", ",".join(HEAD))
    return p


def _run(conn: Connection, path: Path) -> LoadStats:
    stats = LoadStats()
    mapping = no.read_map(MAP, stats)
    codes = no.codes_for(NUCC, mapping, stats)
    return no.load(conn, no.offices(no.open_npi_csv(path), {"NV"}, codes, stats), stats)


def test_taxonomy_map_uses_reviewed_rows_and_reports_unknown_names() -> None:
    stats = LoadStats()
    mapping = no.read_map(MAP, stats)
    assert stats.summary["taxonomy_rows_waiting_for_review"] == 1  # chiropractor row
    codes = no.codes_for(NUCC, mapping, stats)
    assert codes == {
        "SYN0000001X": {"dental_office"},
        "SYN0000002X": {"dental_office"},
        "SYN0000003X": {"imaging_center"},
        "SYN0000004X": {"imaging_center"},  # "Radiology, Mammography" counts as Radiology
    }
    assert [r.rule for r in stats.rejects] == ["taxonomy_not_in_nucc"]  # the misspelling


def test_loads_offices_skips_people_other_states_and_unmapped(
    conn: Connection, tmp_path: Path
) -> None:
    load_all(conn)
    path = _zip(
        tmp_path,
        [
            _row(
                "1000000001",
                "2",
                "SYNTHETIC SMILES DENTAL PLLC",
                "NV",
                ["SYN0000002X"],
                **{
                    "Provider Other Organization Name": "SYNTHETIC SMILES",
                    "Provider Other Organization Name Type Code": "3",
                },
            ),
            _row("1000000002", "1", "", "NV", ["SYN0000001X"]),  # a person, not an office
            _row("1000000003", "2", "SYNTHETIC IMAGING LLC", "CA", ["SYN0000003X"]),  # other state
            _row("1000000004", "2", "SYNTHETIC CHIRO INC", "NV", ["SYN0000005X"]),  # not reviewed
            _row(
                "1000000005",
                "2",
                "SYNTHETIC CLOSED DENTAL",
                "NV",
                ["SYN0000001X"],
                **{"NPI Deactivation Date": "01/05/2025"},
            ),
        ],
    )
    stats = _run(conn, path)
    assert stats.rows_loaded == 1
    row = conn.execute(
        text(
            "SELECT f.name, f.address_line1, f.city, f.zip5, f.phone, f.facility_type::text, "
            "f.source_dataset, n.npi FROM ref.facility f JOIN ref.facility_npi n "
            "ON n.facility_id = f.id WHERE n.npi = '1000000001'"
        )
    ).one()
    assert row == (
        "Synthetic Smiles",
        "100 Synthetic Way",
        "Las Vegas",
        "89101",
        "(702) 555-0100",
        "other",
        "nppes_offices",
        "1000000001",
    )
    types = conn.execute(
        text(
            "SELECT t.provider_type, t.source FROM ref.facility_provider_type t "
            "JOIN ref.facility_npi n "
            "ON n.facility_id = t.facility_id WHERE n.npi = '1000000001'"
        )
    ).all()
    assert types == [("dental_office", "nppes_taxonomy")]
    # a later file: renamed and then deactivated
    _run(
        conn, _zip(tmp_path, [_row("1000000001", "2", "SYNTHETIC SMILES 2", "NV", ["SYN0000001X"])])
    )
    assert (
        conn.execute(
            text(
                "SELECT name FROM ref.facility f JOIN ref.facility_npi n ON n.facility_id = f.id "
                "WHERE n.npi = '1000000001'"
            )
        ).scalar_one()
        == "Synthetic Smiles 2"
    )
    _run(
        conn,
        _zip(
            tmp_path,
            [
                _row(
                    "1000000001",
                    "2",
                    "X",
                    "NV",
                    ["SYN0000001X"],
                    **{"NPI Deactivation Date": "02/01/2026"},
                )
            ],
        ),
    )
    assert (
        conn.execute(
            text(
                "SELECT status::text FROM ref.facility f "
                "JOIN ref.facility_npi n ON n.facility_id = f.id "
                "WHERE n.npi = '1000000001'"
            )
        ).scalar_one()
        == "inactive"
    )


def test_missing_columns_stop_the_load(tmp_path: Path) -> None:
    p = tmp_path / "synthetic_bad.csv"
    p.write_text("NPI,Something\n1000000001,x\n")
    with pytest.raises(no.NppesError):
        list(no.offices(no.open_npi_csv(p), {"NV"}, {}, LoadStats()))


def test_practice_asks_to_be_added_and_becomes_owner(conn: Connection) -> None:
    load_all(conn)
    aid = str(
        conn.execute(
            text("INSERT INTO prov.account (email) VALUES ('spa@synthetic.test') RETURNING id")
        ).scalar_one()
    )
    form = {
        "name": "Synthetic Glow Med Spa",
        "address_line1": "1 Synthetic Ave",
        "city": "Henderson",
        "state_code": "nv",
        "zip5": "89002",
        "provider_type": "medical_spa",
        "website": "synthetic-glow.test",
    }
    with pytest.raises(lr.ListingError):
        lr.request(conn, aid, {**form, "provider_type": "not_a_type"})
    rid = lr.request(conn, aid, form)
    with pytest.raises(lr.ListingError):  # rejecting needs a reason
        lr.decide(conn, rid, "Synthetic Reviewer", False, "")
    fid = lr.decide(conn, rid, "Synthetic Reviewer", True, "checked website and phone")
    owner = conn.execute(
        text("SELECT role, status FROM prov.membership WHERE account_id = :a AND facility_id = :f"),
        {"a": aid, "f": fid},
    ).one()
    assert owner == ("owner", "active")
    assert lr.mine(conn, aid)[0]["status"] == "approved"
    ptype = conn.execute(
        text("SELECT provider_type FROM ref.facility_provider_type WHERE facility_id = :f"),
        {"f": fid},
    ).scalar_one()
    assert ptype == "medical_spa"
