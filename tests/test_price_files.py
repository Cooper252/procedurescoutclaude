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


def test_downloader_retries_a_dropped_connection(tmp_path: Path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("Connection reset by peer", request=request)
        return httpx.Response(200, content=b"synthetic")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        waits: list[int] = []
        d = http_downloader(client, sleep=waits.append)("https://h.example/x.csv", tmp_path / "x")
    assert (d.error, d.nbytes, calls["n"], waits) == (None, 9, 2, [15])


def _home_dir(tmp_path: Path) -> Path:
    import json

    home = tmp_path / "prices-home"
    home.mkdir()
    (home / "price-1.bin").write_bytes(TALL.read_bytes())
    records = [
        {
            "url": f"{SITE}/mrf/shared.json",
            "file": "price-1.bin",
            "http_status": 200,
            "final_url": f"{SITE}/mrf/shared.json",
            "error": None,
        },
        {
            "url": "https://h.example/blocked.csv",
            "file": None,
            "http_status": 403,
            "error": "Forbidden",
        },
        {
            "url": "https://h.example/escape.csv",
            "file": "../outside.bin",
            "http_status": 200,
            "error": None,
        },
    ]
    # PowerShell writes UTF-8 with a byte-order mark
    (home / "prices.json").write_text(json.dumps(records), encoding="utf-8-sig")
    return home


def test_load_home_price_files(tmp_path: Path) -> None:
    import hashlib

    from procedurescout_ingest.price_files import load_home_price_files

    home = load_home_price_files(_home_dir(tmp_path))
    ok = home[f"{SITE}/mrf/shared.json"]
    assert ok.fetched_via == "home_runner" and ok.error is None
    assert ok.sha256 == hashlib.sha256(TALL.read_bytes()).hexdigest()
    assert home["https://h.example/blocked.csv"].error == "Forbidden"
    assert home["https://h.example/escape.csv"].error is not None  # stays inside the folder
    assert load_home_price_files(tmp_path / "missing") == {}


def test_home_fallback_only_when_github_fails(tmp_path: Path) -> None:
    from procedurescout_ingest.price_files import load_home_price_files, with_home_fallback

    home = load_home_price_files(_home_dir(tmp_path))

    def github(url: str, dest: Path) -> Download:
        if url.endswith("good.csv"):
            return Download(url, dest, "0" * 64, 1, 200, url)
        return Download(url, http_status=403, error="HTTP error")

    dl = with_home_fallback(github, home)
    assert dl("https://h.example/good.csv", tmp_path / "g").fetched_via == "github"
    used = dl(f"{SITE}/mrf/shared.json", tmp_path / "s")
    assert (used.fetched_via, used.error) == ("home_runner", None)
    both = dl("https://h.example/blocked.csv", tmp_path / "b")
    assert both.error == "HTTP error; from Cooper's computer: Forbidden (status 403)"
    assert dl("https://h.example/nowhere.csv", tmp_path / "n").error == "HTTP error"


def test_check_records_home_download_and_deletes_it(conn: Connection, tmp_path: Path) -> None:
    from procedurescout_ingest.price_files import load_home_price_files, with_home_fallback

    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    approved = load_co_listed(
        conn,
        "location_name,parent_ccn,note,reviewed_by,reviewed_at\n"
        "Synthetic Valley North Campus,SYN503,listed in its file,tester,2026-11-06\n",
        LoadStats(),
    )
    discover(conn, "NV", fake_fetcher, co_listed=approved)
    home_dir = _home_dir(tmp_path)

    def github(url: str, dest: Path) -> Download:
        return Download(url, http_status=403, error="HTTP error")

    dl = with_home_fallback(github, load_home_price_files(home_dir))
    stats = check_price_files(conn, "NV", dl, tmp_path / "work", today=date(2026, 11, 7))
    via = conn.execute(
        text(
            "SELECT t.fetched_via FROM src.transparency_file t "
            "JOIN src.transparency_source s ON s.id = t.source_id WHERE s.url = :u"
        ),
        {"u": f"{SITE}/mrf/shared.json"},
    ).scalar()
    assert via == "home_runner"
    assert not (home_dir / "price-1.bin").exists()
    assert stats.summary["download_failed"] == 1  # valley.json: GitHub refused, not at home
    assert any("downloaded on Cooper's computer" in r.message for r in stats.rejects)


def test_load_stages_prices_and_publishes_nothing(conn: Connection, tmp_path: Path) -> None:
    import hashlib

    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    approved = load_co_listed(
        conn,
        "location_name,parent_ccn,note,reviewed_by,reviewed_at\n"
        "Synthetic Valley North Campus,SYN503,listed in its file,tester,2026-11-06\n",
        LoadStats(),
    )
    discover(conn, "NV", fake_fetcher, co_listed=approved)
    broken = JSON_FILE.read_bytes()[:-200]  # valid header, cut off inside the items
    files = {f"{SITE}/mrf/valley.json": JSON_FILE.read_bytes(), f"{SITE}/mrf/shared.json": broken}

    def downloader(url: str, dest: Path) -> Download:
        dest.write_bytes(files[url])
        data = files[url]
        return Download(url, dest, hashlib.sha256(data).hexdigest(), len(data), 200, url)

    stats = check_price_files(
        conn, "NV", downloader, tmp_path / "w", today=date(2026, 11, 7), load=True, min_free_bytes=0
    )
    assert stats.summary["files_loaded"] == 1 and stats.summary["load_failed"] == 1
    assert stats.summary["price_rows_loaded"] == 6
    assert stats.summary["price_total_bytes"] > 0
    rows = conn.execute(
        text(
            """
            SELECT f.ccn, count(*), min(dv.status::text), min(r.state::text)
            FROM price.price p
            JOIN ref.facility f ON f.id = p.facility_id
            JOIN src.dataset_version dv ON dv.id = p.dataset_version_id
            JOIN src.import_run r ON r.id = dv.import_run_id
            WHERE f.ccn LIKE 'SYN%' GROUP BY f.ccn
            """
        )
    ).all()
    # the broken file's partial rows were rolled back; the good file waits for review
    assert [tuple(r) for r in rows] == [("SYN501", 6, "staged", "quality_review")]
    published = conn.execute(
        text(
            "SELECT count(*) FROM price.published_price p JOIN ref.facility f "
            "ON f.id = p.facility_id WHERE f.ccn LIKE 'SYN%'"
        )
    ).scalar()
    assert published == 0
    load = conn.execute(
        text(
            "SELECT t.read_summary->'load'->>'rows_loaded' FROM src.transparency_file t "
            "JOIN src.transparency_source s ON s.id = t.source_id WHERE s.url = :u"
        ),
        {"u": f"{SITE}/mrf/valley.json"},
    ).scalar()
    assert load == "6"


def test_load_skipped_when_disk_is_low(conn: Connection, tmp_path: Path) -> None:
    import hashlib

    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    discover(conn, "NV", fake_fetcher)

    def downloader(url: str, dest: Path) -> Download:
        data = JSON_FILE.read_bytes()
        dest.write_bytes(data)
        return Download(url, dest, hashlib.sha256(data).hexdigest(), len(data), 200, url)

    stats = check_price_files(
        conn, "NV", downloader, tmp_path / "w", load=True, min_free_bytes=10**18
    )
    assert stats.summary["load_skipped_low_disk"] >= 1
    assert "files_loaded" not in stats.summary


def test_file_limit_and_time_stop(conn: Connection, tmp_path: Path) -> None:
    """The all-states test run reads a few files per state (max_files); a long
    state run stops cleanly before its time limit (stop_at) so saved work stays."""
    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    approved = load_co_listed(
        conn,
        "location_name,parent_ccn,note,reviewed_by,reviewed_at\n"
        "Synthetic Valley North Campus,SYN503,listed in its file,tester,2026-11-06\n",
        LoadStats(),
    )
    discover(conn, "NV", fake_fetcher, co_listed=approved)
    files = {f"{SITE}/mrf/valley.json": JSON_FILE, f"{SITE}/mrf/shared.json": TALL}
    calls: list[str] = []

    def downloader(url: str, dest: Path) -> Download:
        import hashlib

        calls.append(url)
        dest.write_bytes(files[url].read_bytes())
        data = dest.read_bytes()
        return Download(url, dest, hashlib.sha256(data).hexdigest(), len(data), 200, url)

    one = check_price_files(
        conn, "NV", downloader, tmp_path / "w1", today=date(2026, 11, 6), max_files=1
    )
    assert len(calls) == 1
    assert one.summary["stopped_early"] == "file limit 1 reached"
    calls.clear()
    none = check_price_files(
        conn, "NV", downloader, tmp_path / "w2", today=date(2026, 11, 6), stop_at_ns=0
    )
    assert calls == []
    assert none.summary["stopped_early"].startswith("time limit reached")
