"""Phase 1: CMS hospital and ASC loads into ref.facility (synthetic rows only)."""

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from procedurescout_ingest.reference.cms_pdc import read_csv_rows
from procedurescout_ingest.reference.facilities import (
    REQUIRED_HOSPITAL_COLUMNS,
    load_ascs,
    load_hospitals,
)

FIXTURES = Path(__file__).parent / "fixtures" / "reference"
AS_OF = date(2026, 7, 22)


def hospital(**kw: str) -> dict[str, str]:
    row = {
        "facility_id": "SYN101",
        "facility_name": "SYNTHETIC TEST HOSPITAL",
        "address": "1 TEST WAY",
        "citytown": "LAS VEGAS",
        "state": "NV",
        "zip_code": "89990",
        "countyparish": "CLARK",
        "telephone_number": "(000) 555-0199",
        "hospital_type": "Acute Care Hospitals",
        "hospital_ownership": "Proprietary",
        "emergency_services": "Yes",
        "hospital_overall_rating": "4",
    }
    row.update(kw)
    return row


def asc(**kw: str) -> dict[str, str]:
    row = {
        "facility_id": "99C9999001",
        "facility_name": "SYNTHETIC SURGERY CENTER",
        "npi": "9999999991",
        "citytown": "LAS VEGAS",
        "state": "NV",
        "zip_code": "89990",
        "year": "2024",
    }
    row.update(kw)
    return row


def facility(conn: Connection, ccn: str) -> dict[str, object]:
    row = conn.execute(text("SELECT * FROM ref.facility WHERE ccn = :c"), {"c": ccn}).mappings()
    return dict(row.one())


def test_csv_titles_normalize_to_api_keys() -> None:
    rows = read_csv_rows(
        (FIXTURES / "synthetic_hospital_general_information.csv").read_bytes(), "NV"
    )
    assert len(rows) == 2  # the CA row is filtered out
    assert set(REQUIRED_HOSPITAL_COLUMNS) <= set(rows[0])


def test_csv_rows_load(conn: Connection) -> None:
    rows = read_csv_rows(
        (FIXTURES / "synthetic_hospital_general_information.csv").read_bytes(), "NV"
    )
    stats = load_hospitals(conn, rows, "NV", AS_OF)
    assert stats.rows_loaded == 2 and stats.rows_rejected == 0
    cah = facility(conn, "SYN002")
    assert cah["facility_type"] == "critical_access_hospital"
    assert cah["zip5"] == "89991"  # ZIP+4 reduced to five digits
    assert cah["cms_overall_rating"] is None  # "Not Available" is NULL, never 0
    assert cah["er_services"] is False


def test_hospital_fields_and_rating_date(conn: Connection) -> None:
    stats = load_hospitals(conn, [hospital()], "NV", AS_OF)
    assert (stats.rows_loaded, stats.summary["inserted"]) == (1, 1)
    f = facility(conn, "SYN101")
    assert f["facility_type"] == "acute_care_hospital"
    assert f["cms_facility_type_raw"] == "Acute Care Hospitals"
    assert (f["cms_overall_rating"], f["cms_rating_as_of"]) == (4, AS_OF)
    assert f["county_name"] == "CLARK" and f["source_dataset"] == "cms_pdc:xubh-q36u"
    alias = conn.execute(
        text("SELECT alias_type, match_basis, review_state::text FROM ref.facility_alias")
    ).one()
    assert tuple(alias) == ("cms_name", "ccn", "approved")


def test_rating_without_date_is_dropped(conn: Connection) -> None:
    stats = load_hospitals(conn, [hospital()], "NV", None)
    assert facility(conn, "SYN101")["cms_overall_rating"] is None
    assert any(r.rule == "rating_undated" for r in stats.rejects)


@pytest.mark.parametrize(
    ("override", "rule"),
    [
        ({"hospital_type": "Long-term Acute Care"}, "unknown_hospital_type"),
        ({"facility_id": "29001"}, "ccn_format"),
        ({"state": "CA"}, "state_mismatch"),
        ({"facility_name": " "}, "name_missing"),
    ],
)
def test_bad_rows_rejected_not_guessed(
    conn: Connection, override: dict[str, str], rule: str
) -> None:
    stats = load_hospitals(conn, [hospital(**override)], "NV", AS_OF)
    assert stats.rows_loaded == 0
    assert [r.rule for r in stats.rejects] == [rule]


def test_duplicate_ccn_keeps_first(conn: Connection) -> None:
    stats = load_hospitals(conn, [hospital(), hospital(facility_name="OTHER NAME")], "NV", AS_OF)
    assert stats.rows_loaded == 1
    assert facility(conn, "SYN101")["name"] == "SYNTHETIC TEST HOSPITAL"


def test_reload_is_idempotent_and_address_change_clears_geocode(conn: Connection) -> None:
    load_hospitals(conn, [hospital()], "NV", AS_OF)
    conn.execute(
        text(
            "UPDATE ref.facility SET geom = ST_SetSRID(ST_MakePoint(-115, 36), 4326)::geography, "
            "geocode_source = 'test', geocode_precision = 'address' WHERE ccn = 'SYN101'"
        )
    )
    again = load_hospitals(conn, [hospital()], "NV", AS_OF)
    assert again.summary == {"updated": 1, "type:acute_care_hospital": 1}
    assert facility(conn, "SYN101")["geom"] is not None
    load_hospitals(conn, [hospital(address="2 MOVED AVE")], "NV", AS_OF)
    moved = facility(conn, "SYN101")
    assert moved["geom"] is None and moved["geocode_precision"] is None
    count = conn.execute(text("SELECT count(*) FROM ref.facility WHERE ccn='SYN101'")).scalar()
    assert count == 1


def test_asc_ten_character_ccn_and_npi(conn: Connection) -> None:
    stats = load_ascs(conn, [asc()], "NV", date(2025, 12, 16))
    assert stats.rows_loaded == 1
    f = facility(conn, "99C9999001")
    assert f["facility_type"] == "ambulatory_surgery_center"
    assert f["address_line1"] is None  # CMS ASC file has no street address
    npi = conn.execute(text("SELECT npi FROM ref.facility_npi")).scalar_one()
    assert npi == "9999999991"


def test_asc_rejects_hospital_style_ccn(conn: Connection) -> None:
    stats = load_ascs(conn, [asc(facility_id="SYN101")], "NV", None)
    assert [r.rule for r in stats.rejects] == ["ccn_format"]


def test_asc_npi_conflict_not_moved(conn: Connection) -> None:
    load_ascs(conn, [asc()], "NV", None)
    stats = load_ascs(conn, [asc(facility_id="99C9999002", facility_name="OTHER")], "NV", None)
    assert any(r.rule == "npi_conflict" for r in stats.rejects)
    owner = conn.execute(
        text("SELECT f.ccn FROM ref.facility_npi n JOIN ref.facility f ON f.id = n.facility_id")
    ).scalar_one()
    assert owner == "99C9999001"


def test_asc_reload_keeps_nppes_address_unless_zip_changes(conn: Connection) -> None:
    load_ascs(conn, [asc()], "NV", None)
    conn.execute(
        text("UPDATE ref.facility SET address_line1 = '5 NPPES ST' WHERE ccn='99C9999001'")
    )
    load_ascs(conn, [asc()], "NV", None)
    assert facility(conn, "99C9999001")["address_line1"] == "5 NPPES ST"
    load_ascs(conn, [asc(zip_code="89991")], "NV", None)
    assert facility(conn, "99C9999001")["address_line1"] is None


def test_database_refuses_malformed_ccn(conn: Connection) -> None:
    with pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO ref.facility (ccn, name, facility_type, state_code) "
                "VALUES ('29C12', 'X', 'other', 'NV')"
            )
        )


def test_geom_requires_precision(conn: Connection) -> None:
    with pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO ref.facility (name, facility_type, state_code, geom, geocode_source) "
                "VALUES ('X', 'other', 'NV', "
                "ST_SetSRID(ST_MakePoint(-115, 36), 4326)::geography, 'test')"
            )
        )
