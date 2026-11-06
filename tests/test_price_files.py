"""Phase 2 step 2a: download, check and delete price files (synthetic files only)."""

import io
import zipfile
from datetime import date
from pathlib import Path

import httpx
from sqlalchemy import Connection, text

from procedurescout_core.enums import FileFormat
from procedurescout_ingest.discovery import discover, load_co_listed
from procedurescout_ingest.price_files import (
    Candidate,
    Download,
    check_price_files,
    choose_per_facility,
    http_downloader,
    parse_published_date,
    read_csv,
    read_file,
    read_json,
    sniff,
)
from procedurescout_ingest.reference.common import LoadStats
from procedurescout_ingest.reference.websites import load_websites
from tests.test_discovery import SITE, fake_fetcher, setup_hospitals, websites_csv

FIX = Path(__file__).resolve().parent / "fixtures" / "price_files"
JSON_FILE = FIX / "synthetic_standardcharges.json"
TALL = FIX / "synthetic_standardcharges_tall.csv"
WIDE = FIX / "synthetic_standardcharges_wide.csv"


def test_read_json_header_and_counts() -> None:
    with JSON_FILE.open("rb") as f:
        check = read_json(f)
    assert check.format is FileFormat.JSON
    assert check.version == "3.0.0"
    assert check.last_updated_raw == "2026-09-01"
    assert check.attester_name == "Synthetic Attester"
    assert (check.attestation_text or "").startswith("To the best of its knowledge")
    assert check.header["location_name"] == ["Synthetic Valley Medical Center"]
    assert check.header["license_information.state"] == "NV"
    s = check.summary
    assert (s["charge_items"], s["standard_charges"], s["payer_rows"]) == (2, 2, 3)
    assert s["code_types"] == {"CPT": 1, "RC": 1, "MS-DRG": 1}
    assert s["settings"] == {"outpatient": 1, "inpatient": 1}
    assert s["payer_names"] == ["Synthetic Payer One", "Synthetic Payer Two"]
    assert (s["gross_charges"], s["discounted_cash"]) == (2, 1)
    assert check.problems == []


def test_read_json_reports_broken_file() -> None:
    check = read_json(io.BytesIO(b'{"hospital_name": "x", "standard_charge_information": [ {'))
    assert check.problems and check.problems[0].startswith("not valid JSON")


def test_read_csv_tall() -> None:
    with TALL.open("rb") as f:
        check = read_csv(f)
    assert check.format is FileFormat.CSV_TALL
    assert (check.version, check.last_updated_raw) == ("3.0.0", "2023-11-30")
    assert check.attester_name == "Synthetic Attester"
    assert (check.attestation_text or "").startswith("To the best of its knowledge")
    assert check.summary["rows"] == 3
    assert check.summary["payer_names"] == ["Synthetic Payer One", "Synthetic Payer Two"]
    assert check.summary["code_types"] == {"CPT": 2, "RC": 2, "MS-DRG": 1}
    assert check.problems == []


def test_read_csv_wide_and_ragged_row() -> None:
    with WIDE.open("rb") as f:
        check = read_csv(f)
    assert check.format is FileFormat.CSV_WIDE
    assert check.last_updated_raw == "09/01/2026"
    assert check.summary["payer_names"] == ["Synthetic Payer One", "Synthetic Payer Two"]
    assert check.summary["rows"] == 2
    assert check.problems == ["1 rows have a different number of columns than the header"]


def test_read_csv_flags_bad_bytes_and_non_template() -> None:
    data = TALL.read_bytes().replace(b"SYNTHETIC SERVICE B", b"SYNTHETIC \xff SERVICE B")
    check = read_csv(io.BytesIO(data))
    assert "1 rows contain bytes that are not valid UTF-8" in check.problems
    short = read_csv(io.BytesIO(b"a,b\n1,2\n"))
    assert short.problems == ["fewer than three rows: not the CMS CSV template"]


def test_sniff_and_zip(tmp_path: Path) -> None:
    assert sniff(JSON_FILE) == "json" and sniff(TALL) == "text"
    z = tmp_path / "synthetic_file.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("readme.txt", "x")
        zf.write(TALL, "inner/synthetic_standardcharges_tall.csv")
    assert sniff(z) == "zip"
    check = read_file(z)
    assert check.format is FileFormat.CSV_TALL
    assert check.inner_name == "inner/synthetic_standardcharges_tall.csv"
    x = tmp_path / "synthetic_book.xlsx"
    with zipfile.ZipFile(x, "w") as zf:
        zf.writestr("xl/workbook.xml", "<workbook/>")
    assert sniff(x) == "xlsx"
    assert read_file(x).problems == ["Excel workbook: not a CMS machine-readable format"]


def test_parse_published_date() -> None:
    assert parse_published_date("2026-09-01") == date(2026, 9, 1)
    assert parse_published_date("09/01/2026") == date(2026, 9, 1)
    assert parse_published_date("September 2026") is None
    assert parse_published_date(None) is None


def cand(ccn: str, url: str, lm: str | None, size: int | None = None, fac: str = "f1") -> Candidate:
    return Candidate("00000000-aaaa", url, fac, ccn, "n", size, lm)


def test_newest_link_wins_and_undated_keeps_all() -> None:
    old = cand("1", "https://a/old", "Fri, 03 Jan 2025 23:06:50 GMT")
    new = cand("1", "https://a/new", "Wed, 21 Oct 2026 20:50:34 GMT")
    chosen, skipped = choose_per_facility([old, new])
    assert chosen == [new] and skipped == [(old, new)]
    undated = cand("1", "https://a/undated", None)
    chosen, skipped = choose_per_facility([old, undated])
    assert {c.url for c in chosen} == {"https://a/old", "https://a/undated"} and skipped == []
    big = cand("2", "https://b/big", None, 900, fac="f2")
    small = cand("3", "https://c/small", None, 10, fac="f3")
    unknown = cand("4", "https://d/unknown", None, None, fac="f4")
    chosen, _ = choose_per_facility([unknown, big, small])
    assert [c.ccn for c in chosen] == ["3", "2", "4"]  # small first, unknown size last


def test_downloader_streams_hashes_and_limits(tmp_path: Path) -> None:
    body = JSON_FILE.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ok.json":
            return httpx.Response(200, content=body, headers={"last-modified": "x"})
        if request.url.path == "/blocked.csv":
            return httpx.Response(403)
        return httpx.Response(200, content=b"y" * 5000)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        dl = http_downloader(client, max_bytes=len(body), sleep=lambda _s: None)
        ok = dl("https://h.example/ok.json", tmp_path / "a")
        blocked = dl("https://h.example/blocked.csv", tmp_path / "b")
        big = dl("https://h.example/huge.csv", tmp_path / "c")
    import hashlib

    assert ok.sha256 == hashlib.sha256(body).hexdigest() and ok.nbytes == len(body)
    assert ok.path is not None and ok.path.read_bytes() == body
    assert (blocked.http_status, blocked.error, blocked.path) == (403, "HTTP error", None)
    assert big.error is not None and "limit" in big.error
    assert not (tmp_path / "b").exists() and not (tmp_path / "c").exists()


def test_check_price_files_records_and_deletes(conn: Connection, tmp_path: Path) -> None:
    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    approved = load_co_listed(
        conn,
        "location_name,parent_ccn,note,reviewed_by,reviewed_at\n"
        "Synthetic Valley North Campus,SYN503,listed in its file,tester,2026-11-06\n",
        LoadStats(),
    )
    discover(conn, "NV", fake_fetcher, co_listed=approved)
    files = {
        f"{SITE}/mrf/valley.json": JSON_FILE,  # SYN501
        f"{SITE}/mrf/shared.json": TALL,  # SYN503 (co-listed approved); dated 2023
    }
    seen: list[Path] = []

    def downloader(url: str, dest: Path) -> Download:
        if url not in files:
            return Download(url, http_status=403, error="HTTP error")
        dest.write_bytes(files[url].read_bytes())
        seen.append(dest)
        import hashlib

        data = dest.read_bytes()
        return Download(url, dest, hashlib.sha256(data).hexdigest(), len(data), 200, url)

    stats = check_price_files(conn, "NV", downloader, tmp_path / "work", today=date(2026, 11, 6))
    assert stats.summary["files_chosen"] == 2
    assert all(not p.exists() for p in seen)  # nothing kept
    rows = conn.execute(
        text(
            """
            SELECT f.ccn, t.format::text, t.schema_version, t.reported_last_updated,
                   t.object_store_key, t.read_error, (t.read_summary->>'payer_names_distinct')
            FROM src.transparency_file t
            JOIN src.file_facility ff ON ff.file_id = t.id
            JOIN ref.facility f ON f.id = ff.facility_id
            WHERE f.ccn LIKE 'SYN%' ORDER BY f.ccn
            """
        )
    ).all()
    assert [tuple(r) for r in rows] == [
        ("SYN501", "json", "3.0.0", date(2026, 9, 1), None, None, "2"),
        (
            "SYN503",
            "csv_tall",
            "3.0.0",
            date(2023, 11, 30),
            None,
            "last_updated_on 2023-11-30 is more than a year old",
            "2",
        ),
    ]
    assert stats.summary["files_with_problems"] == 1
    assert any(r.rule == "file_read" and "csv_tall" in r.message for r in stats.rejects)
