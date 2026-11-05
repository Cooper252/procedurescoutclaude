"""NPPES address enrichment for ASCs and AHRQ health-system links."""

from pathlib import Path
from typing import Any

from sqlalchemy import Connection, text

from procedurescout_ingest.reference.ahrq import load_linkage, parse_linkage
from procedurescout_ingest.reference.facilities import load_ascs, load_hospitals
from procedurescout_ingest.reference.nppes import enrich_asc_addresses

FIX = Path(__file__).parent / "fixtures" / "reference"


def nppes_record(**kw: Any) -> dict[str, Any]:
    loc = {
        "address_1": "1 SYNTHETIC DR",
        "address_2": "STE 100",
        "address_purpose": "LOCATION",
        "city": "LAS VEGAS",
        "state": "NV",
        "postal_code": "899901234",
    }
    loc.update(kw.pop("loc", {}))
    rec: dict[str, Any] = {
        "number": "9999999991",
        "enumeration_type": "NPI-2",
        "basic": {"organization_name": "SYNTHETIC SURGERY CENTER LLC", "status": "A"},
        "addresses": [{**loc, "address_purpose": "MAILING", "address_1": "PO BOX 1"}, loc],
        "taxonomies": [{"code": "261QA1903X", "primary": True}],
    }
    rec.update(kw)
    return rec


def asc_row(ccn: str, npi: str) -> dict[str, str]:
    return {
        "facility_id": ccn,
        "facility_name": f"SYNTHETIC ASC {ccn}",
        "npi": npi,
        "citytown": "LAS VEGAS",
        "state": "NV",
        "zip_code": "89990",
    }


def test_nppes_location_address_used_when_consistent(conn: Connection) -> None:
    load_ascs(conn, [asc_row("99C9999001", "9999999991")], "NV", None)
    stats = enrich_asc_addresses(conn, "NV", lambda npi: nppes_record())
    assert stats.rows_loaded == 1
    row = conn.execute(
        text(
            "SELECT f.address_line1, n.taxonomy_code FROM ref.facility f "
            "JOIN ref.facility_npi n ON n.facility_id = f.id"
        )
    ).one()
    assert tuple(row) == ("1 SYNTHETIC DR STE 100", "261QA1903X")
    alias = conn.execute(
        text("SELECT match_basis FROM ref.facility_alias WHERE alias_type = 'nppes_name'")
    ).scalar()
    assert alias == "npi"


def test_nppes_mismatches_are_reported_not_applied(conn: Connection) -> None:
    load_ascs(
        conn,
        [
            asc_row("99C9999001", "9999999991"),
            asc_row("99C9999002", "9999999992"),
            asc_row("99C9999003", "9999999993"),
            asc_row("99C9999004", "9999999994"),
        ],
        "NV",
        None,
    )
    answers = {
        "9999999991": nppes_record(loc={"postal_code": "891010000"}),  # different ZIP
        "9999999992": nppes_record(basic={"status": "D"}),  # deactivated
        "9999999993": nppes_record(enumeration_type="NPI-1"),  # an individual
        "9999999994": None,  # not found
    }
    stats = enrich_asc_addresses(conn, "NV", lambda npi: answers[npi])
    assert stats.rows_loaded == 0
    assert sorted(r.rule for r in stats.rejects) == [
        "npi_address_mismatch",
        "npi_not_active_org",
        "npi_not_active_org",
        "npi_not_found",
    ]
    n = conn.execute(text("SELECT count(*) FROM ref.facility WHERE address_line1 IS NOT NULL"))
    assert n.scalar() == 0


def hospital(ccn: str) -> dict[str, str]:
    return {
        "facility_id": ccn,
        "facility_name": f"SYNTHETIC {ccn}",
        "address": "1 TEST WAY",
        "citytown": "TESTVILLE",
        "state": "NV",
        "zip_code": "89990",
        "countyparish": "CLARK",
        "telephone_number": "",
        "hospital_type": "Acute Care Hospitals",
        "hospital_ownership": "",
        "emergency_services": "",
        "hospital_overall_rating": "",
    }


def linkage_rows() -> list[dict[str, str]]:
    return parse_linkage((FIX / "synthetic_ahrq_hospital_linkage.csv").read_text())


def test_ahrq_links_by_ccn_and_reports_the_rest(conn: Connection) -> None:
    load_hospitals(conn, [hospital("SYN001"), hospital("SYN002")], "NV", None)
    stats = load_linkage(conn, linkage_rows(), "NV", 2023)
    assert stats.rows_in == 5  # the CA row is skipped
    assert stats.summary == {"linked": 1, "no_system": 1}
    assert sorted(r.rule for r in stats.rejects) == [
        "ccn_format",
        "ccn_missing",
        "facility_not_found",
    ]
    row = conn.execute(
        text(
            "SELECT h.name, h.source_system_id, f.health_system_source FROM ref.facility f "
            "JOIN ref.health_system h ON h.id = f.health_system_id WHERE f.ccn = 'SYN001'"
        )
    ).one()
    assert tuple(row) == ("Synthetic Health", "HSI90000001", "ahrq_compendium:2023")
    # The unknown CCN did not create a facility.
    assert conn.execute(text("SELECT count(*) FROM ref.facility")).scalar() == 2


def test_ahrq_never_overwrites_manual_link(conn: Connection) -> None:
    load_hospitals(conn, [hospital("SYN001")], "NV", None)
    manual = conn.execute(
        text("INSERT INTO ref.health_system (name) VALUES ('Synthetic Manual System') RETURNING id")
    ).scalar()
    conn.execute(
        text(
            "UPDATE ref.facility SET health_system_id = :h, health_system_source = 'manual:tester' "
            "WHERE ccn = 'SYN001'"
        ),
        {"h": manual},
    )
    stats = load_linkage(conn, linkage_rows(), "NV", 2023)
    assert any(r.rule == "manual_link_conflict" for r in stats.rejects)
    kept = conn.execute(text("SELECT health_system_id FROM ref.facility WHERE ccn='SYN001'"))
    assert kept.scalar() == manual


def test_ahrq_reload_updates_by_system_id_not_name(conn: Connection) -> None:
    load_hospitals(conn, [hospital("SYN001")], "NV", None)
    rows = linkage_rows()
    load_linkage(conn, rows, "NV", 2023)
    rows[0]["health_sys_name"] = "Synthetic Health (renamed)"
    load_linkage(conn, rows, "NV", 2024)
    systems = conn.execute(text("SELECT name, source_year FROM ref.health_system")).all()
    assert [tuple(s) for s in systems] == [("Synthetic Health (renamed)", 2024)]
