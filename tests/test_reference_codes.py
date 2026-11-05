"""HCPCS Level II and MS-DRG reference codes."""

import io
from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from procedurescout_core.enums import CodeSystem
from procedurescout_ingest.reference.codes import (
    CodeRow,
    join_segments,
    load_hcpcs,
    load_msdrg,
    looks_like_hcpcs_text,
    parse_hcpcs,
    parse_table5,
    upsert_codes,
)
from procedurescout_ingest.reference.common import LoadStats, SourceError

FIX = Path(__file__).parent / "fixtures" / "reference"
HCPCS = (FIX / "synthetic_hcpcs_anweb.txt").read_text()


def test_hcpcs_text_member_detection() -> None:
    assert looks_like_hcpcs_text("HCPC2026_OCT_ANWEB.txt", HCPCS.encode())
    assert not looks_like_hcpcs_text("record_layout.txt", b"HCPCS RECORD LAYOUT\nfield 1\n")
    assert not looks_like_hcpcs_text("HCPC2026.xlsx", HCPCS.encode())


def test_hcpcs_parse() -> None:
    stats = LoadStats()
    rows = {r.code: r for r in parse_hcpcs(HCPCS, stats)}
    assert sorted(rows) == ["A9901", "E9902", "J9903"]
    assert rows["A9901"].long == "Synthetic ambulance service, test only"
    assert rows["A9901"].short == "SYN AMB TEST"
    assert rows["A9901"].added == date(2020, 1, 1) and rows["A9901"].terminated is None
    # Word-boundary wrap gets a space; a break inside a word does not.
    assert rows["E9902"].long.endswith("long description that continues on a second record")
    assert rows["J9903"].long.endswith("filling all eightyyz tail")
    assert rows["J9903"].terminated == date(2025, 12, 31)
    assert stats.summary == {"numeric_codes_skipped": 1, "modifier_records_skipped": 2}
    assert stats.rejects == []


def test_join_segments() -> None:
    assert join_segments(["abc   ", "def"]) == "abc def"
    assert join_segments(["x" * 80, "yz"]) == "x" * 80 + "yz"
    assert join_segments(["x" * 80, " yz"]) == "x" * 80 + " yz"


def test_hcpcs_layout_change_refused() -> None:
    shifted = "\n".join(" " + line for line in HCPCS.splitlines())
    with pytest.raises(SourceError, match="layout"):
        parse_hcpcs(shifted, LoadStats())


def test_hcpcs_load_and_reload(conn: Connection) -> None:
    stats = load_hcpcs(conn, HCPCS, 2026, "synthetic HCPCS fixture")
    assert stats.rows_loaded == 3 and stats.summary["terminated"] == 1
    again = load_hcpcs(conn, HCPCS, 2026, "synthetic HCPCS fixture v2")
    assert again.rows_loaded == 3
    rows = conn.execute(
        text("SELECT code, descriptor_source FROM ref.code WHERE system = 'HCPCS' ORDER BY code")
    ).all()
    assert [tuple(r) for r in rows] == [
        ("A9901", "synthetic HCPCS fixture v2"),
        ("E9902", "synthetic HCPCS fixture v2"),
        ("J9903", "synthetic HCPCS fixture v2"),
    ]
    cpt = conn.execute(text("SELECT count(*) FROM ref.code WHERE code = '99999'")).scalar()
    assert cpt == 0


def test_cpt_text_never_upserted(conn: Connection) -> None:
    with pytest.raises(ValueError, match="AMA"):
        upsert_codes(conn, CodeSystem.CPT, "2026", [CodeRow("99999", "x", None, None, None)], "s")


def test_database_refuses_cpt_short_descriptor(conn: Connection) -> None:
    with pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO ref.code (system, code, version, descriptor_short, descriptor_source) "
                "VALUES ('CPT', '99999', '2026', 'short text', 'test')"
            )
        )


def test_table5_text() -> None:
    stats = LoadStats()
    data = (FIX / "synthetic_msdrg_table5.txt").read_bytes()
    rows = {r.code: r.long for r in parse_table5("synthetic_msdrg_table5.txt", data, stats)}
    assert rows == {
        "001": "SYNTHETIC TRANSPLANT WITH MCC",
        "002": "SYNTHETIC TRANSPLANT WITHOUT MCC",  # "2" restored to the 3-digit code
        "470": "SYNTHETIC JOINT REPLACEMENT",
    }
    assert sorted(r.rule for r in stats.rejects) == ["duplicate_code", "row_format"]


def synthetic_table5_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["Table 5 (synthetic)"])
    ws.append([])
    ws.append(["MS-DRG", "MDC", "TYPE", "MS-DRG Title", "Weights"])
    ws.append([1, "PRE", "SURG", "SYNTHETIC ONE", 1])
    ws.append([871, "18", "MED", "SYNTHETIC SEPSIS", 1])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_table5_xlsx_load(conn: Connection) -> None:
    stats = load_msdrg(conn, "synthetic.xlsx", synthetic_table5_xlsx(), 44, 2027, "synthetic")
    assert stats.rows_loaded == 2
    row = conn.execute(
        text(
            "SELECT descriptor, version, effective_from, effective_to FROM ref.code "
            "WHERE system = 'MS-DRG' AND code = '871'"
        )
    ).one()
    assert tuple(row) == ("SYNTHETIC SEPSIS", "v44", date(2026, 10, 1), date(2027, 9, 30))


def two_sheet_table5(mark_correction: bool) -> bytes:
    wb = Workbook()
    final = wb.active
    assert final is not None
    final.title = "FY 2027 Final Rule"
    final.append(["TABLE 5 (synthetic) -- Final Rule"])
    final.append(["MS-DRG", "MS-DRG Title"])
    final.append([1, "SYNTHETIC OLD TITLE"])
    final.append([2, "SYNTHETIC TWO"])
    cn = wb.create_sheet("FY 2027 CN" if mark_correction else "Sheet2")
    cn.append([f"TABLE 5 (synthetic){' -- Correction Notice' if mark_correction else ''}"])
    cn.append(["MS-DRG", "MS-DRG Title"])
    cn.append([1, "SYNTHETIC CORRECTED TITLE"])
    cn.append([2, "SYNTHETIC TWO"])
    cn.append([3, "SYNTHETIC THREE"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_table5_correction_notice_supersedes_final_rule() -> None:
    stats = LoadStats()
    rows = {r.code: r.long for r in parse_table5("t5.xlsx", two_sheet_table5(True), stats)}
    assert rows == {
        "001": "SYNTHETIC CORRECTED TITLE",
        "002": "SYNTHETIC TWO",
        "003": "SYNTHETIC THREE",
    }
    assert stats.rejects == []
    assert stats.summary == {
        "table": "FY 2027 CN",
        "superseded_table": "FY 2027 Final Rule",
        "titles_changed_vs_superseded": 1,
        "codes_added_vs_superseded": 1,
        "codes_removed_vs_superseded": 0,
    }


def test_table5_two_unmarked_tables_refused() -> None:
    with pytest.raises(SourceError, match="cannot tell which is current"):
        parse_table5("t5.xlsx", two_sheet_table5(False), LoadStats())


def test_table5_too_few_rows_refused(conn: Connection) -> None:
    with pytest.raises(SourceError, match="at least 700"):
        load_msdrg(conn, "synthetic.xlsx", synthetic_table5_xlsx(), 44, 2027, "s", min_rows=700)


def test_table5_without_header_refused() -> None:
    with pytest.raises(SourceError, match="header"):
        parse_table5("x.txt", b"DRG\tDescription\n001\tX\n", LoadStats())
