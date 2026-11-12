"""Phase 2 step 1: approved websites, cms-hpt.txt parsing, discovery."""

import csv
import re
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from procedurescout_ingest.discovery import HptFetch, discover, http_fetcher, parse_hpt_txt
from procedurescout_ingest.reference.facilities import load_hospitals
from procedurescout_ingest.reference.websites import (
    STATUSES,
    WEBSITE_COLUMNS,
    load_reviewed_aliases,
    load_websites,
)

ROOT = Path(__file__).resolve().parent.parent
HPT = (ROOT / "tests" / "fixtures" / "discovery" / "synthetic_cms-hpt.txt").read_text()
HEADER = ",".join(WEBSITE_COLUMNS) + "\n"
SITE = "https://synthetic-health.example"


def test_parse_blocks_and_problems() -> None:
    entries = parse_hpt_txt("﻿" + HPT)
    names = [e.get("location-name") for e in entries]
    assert names == [
        "Synthetic Valley Medical Center",
        "Synthetic Valley North Campus",
        "Synthetic Desert Hospital",  # no blank line before it; keys in other case
        "Synthetic Clinic Nobody Knows",
        "Synthetic Broken Block",
    ]
    assert entries[0].problems == ()
    assert entries[0].get("mrf-url") == "https://synthetic-health.example/mrf/valley.json"
    assert entries[2].get("source-page-url") == "https://synthetic-health.example/pricing"
    assert set(entries[4].problems) == {
        "missing source-page-url",
        "missing contact-name",
        "missing contact-email",
        "mrf-url is not a URL",
    }


def test_parse_reports_unrecognized_lines() -> None:
    entries = parse_hpt_txt("location-name: X\nsomething odd\nmrf-url: https://x.example/a\n")
    assert any(p.startswith("unrecognized line") for p in entries[0].problems)


def transport(routes: dict[str, httpx.Response]) -> httpx.MockTransport:
    return httpx.MockTransport(lambda r: routes.get(str(r.url), httpx.Response(404)))


def test_http_fetcher_cases() -> None:
    routes = {
        "https://a.example/cms-hpt.txt": httpx.Response(
            200, text=HPT, headers={"content-type": "text/plain"}
        ),
        "https://b.example/cms-hpt.txt": httpx.Response(
            200, text="<!DOCTYPE html><p>Home</p>", headers={"content-type": "text/html"}
        ),
        "https://c.example/cms-hpt.txt": httpx.Response(
            301, headers={"location": "https://c.example/files/cms-hpt.txt"}
        ),
        "https://c.example/files/cms-hpt.txt": httpx.Response(200, text=HPT),
        "https://e.example/cms-hpt.txt": httpx.Response(200, content=b"x" * (1024 * 1024 + 1)),
    }
    with httpx.Client(transport=transport(routes), follow_redirects=True) as client:
        fetch = http_fetcher(client)
        ok = fetch("https://a.example")
        assert ok.error is None and ok.data is not None
        assert fetch("https://b.example").error == "returned a web page, not a text file"
        redirected = fetch("https://c.example")
        assert redirected.error is None
        assert redirected.final_url == "https://c.example/files/cms-hpt.txt"
        missing = fetch("https://d.example")
        assert (missing.http_status, missing.error) == (404, "HTTP error")
        assert fetch("https://e.example").error == "larger than 1 MB"


def hospital(ccn: str, name: str) -> dict[str, str]:
    return {
        "facility_id": ccn,
        "facility_name": name,
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


def setup_hospitals(conn: Connection) -> None:
    load_hospitals(
        conn,
        [
            hospital("SYN501", "SYNTHETIC VALLEY MEDICAL CENTER"),
            hospital("SYN502", "SYNTHETIC VALLEY NORTH"),  # name differs from the txt
            hospital("SYN503", "SYNTHETIC DESERT HOSPITAL"),
            hospital("SYN504", "SYNTHETIC OTHER SITE HOSPITAL"),
            hospital("SYN505", "SYNTHETIC FEDERAL HOSPITAL"),
        ],
        "NV",
        None,
    )


def websites_csv(reviewed: bool = True) -> str:
    rb, ra = ("tester", "2026-11-05") if reviewed else ("", "")
    rows = [
        ["SYN501", "x", SITE, "website", f"{SITE}/pricing", "", "proposed:test", rb, ra],
        ["SYN502", "x", SITE + "/", "website", "", "", "proposed:test", rb, ra],
        ["SYN503", "x", SITE, "website", "", "", "proposed:test", rb, ra],
        ["SYN504", "x", "https://down.example", "website", "", "", "proposed:test", rb, ra],
        ["SYN505", "x", "", "federal_exempt", "", "VA hospital", "proposed:test", rb, ra],
        ["SYN999", "x", SITE, "website", "", "", "proposed:test", rb, ra],
        ["SYN501", "x", "http://insecure.example/path", "website", "", "", "p", rb, ra],
    ]
    lines = [HEADER] + [",".join(r) + "\n" for r in rows]
    return "".join(lines)


def test_only_reviewed_websites_are_used(conn: Connection) -> None:
    setup_hospitals(conn)
    stats = load_websites(conn, websites_csv(reviewed=False))
    assert stats.rows_loaded == 0
    assert stats.summary == {"unreviewed_website": 5, "unreviewed_federal_exempt": 1}
    n = conn.execute(text("SELECT count(*) FROM ref.facility WHERE website IS NOT NULL"))
    assert n.scalar() == 0


def test_reviewed_websites_load(conn: Connection) -> None:
    setup_hospitals(conn)
    stats = load_websites(conn, websites_csv())
    assert sorted(r.rule for r in stats.rejects) == ["facility_not_found", "website_format"]
    got = dict(conn.execute(text("SELECT ccn, website FROM ref.facility")).all())
    assert got["SYN502"] == SITE  # trailing slash removed
    assert got["SYN505"] is None
    reason = conn.execute(
        text("SELECT hpt_exempt_reason FROM ref.facility WHERE ccn = 'SYN505'")
    ).scalar()
    assert reason == "VA hospital"


def test_database_refuses_unreviewed_website(conn: Connection) -> None:
    setup_hospitals(conn)
    with pytest.raises(IntegrityError):
        conn.execute(
            text("UPDATE ref.facility SET website = 'https://x.example' WHERE ccn = 'SYN501'")
        )


def fake_fetcher(site: str) -> HptFetch:
    if site == SITE:
        return HptFetch(site, f"{site}/cms-hpt.txt", 200, f"{site}/cms-hpt.txt", HPT.encode())
    return HptFetch(site, f"{site}/cms-hpt.txt", 503, error="HTTP error")


def test_discover(conn: Connection) -> None:
    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    stats = discover(conn, "NV", fake_fetcher)
    assert stats.summary["sites"] == 2
    assert stats.summary["sites_ok"] == 1 and stats.summary["sites_failed"] == 1
    assert stats.summary["entries_matched"] == 2  # Valley Medical Center, Desert Hospital
    assert stats.summary["entries_unmatched"] == 2  # North Campus (name differs), unknown clinic
    assert stats.summary["entries_invalid"] == 1
    entries = conn.execute(
        text(
            "SELECT e.location_name, e.match_status, f.ccn FROM src.hpt_txt_entry e "
            "LEFT JOIN ref.facility f ON f.id = e.facility_id ORDER BY e.block_index"
        )
    ).all()
    assert [tuple(e) for e in entries] == [
        ("Synthetic Valley Medical Center", "matched", "SYN501"),
        ("Synthetic Valley North Campus", "unmatched", None),
        ("Synthetic Desert Hospital", "matched", "SYN503"),
        ("Synthetic Clinic Nobody Knows", "unmatched", None),
        ("Synthetic Broken Block", "invalid", None),
    ]
    sources = dict(
        conn.execute(
            text(
                "SELECT s.url, f.ccn FROM src.transparency_source s "
                "LEFT JOIN ref.facility f ON f.id = s.facility_id WHERE s.url LIKE :site"
            ),
            {"site": f"{SITE}/%"},
        ).all()
    )
    assert sources == {
        f"{SITE}/mrf/valley.json": "SYN501",
        f"{SITE}/mrf/shared.json": None,  # one file, two locations: mapped later per file
        f"{SITE}/mrf/unknown.json": None,
    }
    not_named = sorted(r.row_ref for r in stats.rejects if r.rule == "facility_not_named")
    assert not_named == ["ccn:SYN502", "ccn:SYN504"]
    failed = conn.execute(text("SELECT error FROM src.hpt_txt_fetch WHERE http_status = 503"))
    assert failed.scalar() == "HTTP error"


def test_reviewed_alias_lets_discovery_match(conn: Connection) -> None:
    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    aliases = (
        "ccn,alias,evidence,reviewed_by,reviewed_at\n"
        "SYN502,Synthetic Valley North Campus,name used in its cms-hpt.txt,tester,2026-11-05\n"
        "SYN501,Unreviewed Name,some evidence,,\n"
    )
    stats = load_reviewed_aliases(conn, aliases)
    assert stats.rows_loaded == 1 and [r.rule for r in stats.rejects] == ["unreviewed"]
    result = discover(conn, "NV", fake_fetcher)
    assert result.summary["entries_matched"] == 3


def test_committed_websites_file_is_well_formed() -> None:
    path = ROOT / "data" / "reference" / "facility_websites.csv"
    rows = list(csv.DictReader(path.open()))
    assert rows and list(rows[0]) == list(WEBSITE_COLUMNS)
    assert len({r["ccn"] for r in rows}) == len(rows)
    for r in rows:
        assert re.fullmatch(r"[0-9A-Z]{6}", r["ccn"]), r
        assert r["status"] in STATUSES, r
        assert r["proposed_by"], r
        if r["status"] == "website":
            assert re.fullmatch(r"https://[^/?#\s]+", r["website"]), r
        else:
            assert r["website"] == "", r
        if r["reviewed_by"]:
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["reviewed_at"]), r


def test_rate_limited_site_is_retried_after_waiting() -> None:
    answers = [
        httpx.Response(429, headers={"retry-after": "7"}),
        httpx.Response(200, text=HPT, headers={"content-type": "text/plain"}),
    ]
    waits: list[int] = []
    with httpx.Client(transport=httpx.MockTransport(lambda r: answers.pop(0))) as client:
        result = http_fetcher(client, sleep=waits.append)("https://slow.example")
    assert result.error is None and waits == [7]


def test_forbidden_site_is_not_retried() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(403)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = http_fetcher(client, sleep=lambda _s: None)("https://blocked.example")
    assert (result.http_status, len(calls)) == (403, 1)


def test_captured_copy_used_only_when_live_fetch_fails(conn: Connection, tmp_path: Path) -> None:
    from procedurescout_ingest.discovery import load_captured_copies
    from procedurescout_ingest.reference.common import LoadStats

    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    (tmp_path / "synthetic_down.txt").write_text(
        "location-name: SYNTHETIC OTHER SITE HOSPITAL\n"
        "source-page-url: https://down.example/pricing\n"
        "mrf-url: https://down.example/mrf/other.csv\n"
        "contact-name: Synthetic\ncontact-email: x@down.example\n"
    )
    manifest = (
        "site,file,captured_from,captured_at,captured_by,reviewed_by,reviewed_at\n"
        "https://down.example,synthetic_down.txt,https://down.example/cms-hpt.txt,2026-11-05,"
        "test,tester,2026-11-05\n"
        f"{SITE},synthetic_down.txt,{SITE}/cms-hpt.txt,2026-11-05,test,,\n"
    )
    mstats = LoadStats()
    copies = load_captured_copies(tmp_path, manifest, mstats)
    assert set(copies) == {"https://down.example"}  # the unreviewed row is ignored
    assert mstats.summary == {"captured_copies_unreviewed": 1}
    stats = discover(conn, "NV", fake_fetcher, copies)
    assert stats.summary["sites_from_captured_copy"] == 1
    assert "sites_failed" not in stats.summary
    rows = conn.execute(
        text(
            "SELECT content_source, http_status, copy_reviewed_by FROM src.hpt_txt_fetch "
            "WHERE site = 'https://down.example' ORDER BY content_source DESC"
        )
    ).all()
    assert [tuple(r) for r in rows] == [("live", 503, None), ("captured", None, "tester")]
    owner = conn.execute(
        text(
            "SELECT f.ccn FROM src.transparency_source s JOIN ref.facility f "
            "ON f.id = s.facility_id WHERE s.url = 'https://down.example/mrf/other.csv'"
        )
    ).scalar()
    assert owner == "SYN504"


def test_captured_copy_requires_provenance(conn: Connection) -> None:
    with pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO src.hpt_txt_fetch (site, url, content_source) "
                "VALUES ('https://x.example', 'https://x.example/cms-hpt.txt', 'captured')"
            )
        )


def test_manual_sources(conn: Connection) -> None:
    from procedurescout_ingest.discovery import load_manual_sources

    setup_hospitals(conn)
    csv_text = (
        "ccn,mrf_url,source_page_url,note,evidence,reviewed_by,reviewed_at\n"
        "SYN501,https://synthetic.example/a.xlsx,https://synthetic.example/,xlsx not CMS format,"
        "homepage link,tester,2026-11-05\n"
        "SYN502,https://synthetic.example/b.csv,,,,,\n"
        "SYN503,not-a-url,,,evidence,tester,2026-11-05\n"
    )
    stats = load_manual_sources(conn, csv_text)
    assert stats.rows_loaded == 1
    assert stats.summary == {"unreviewed": 1}
    assert [r.rule for r in stats.rejects] == ["incomplete"]
    row = conn.execute(
        text(
            "SELECT discovery_method::text, review_note FROM src.transparency_source "
            "WHERE url = 'https://synthetic.example/a.xlsx'"
        )
    ).one()
    assert row[0] == "manual" and "reviewed by tester" in row[1]


def test_committed_captured_manifest_matches_files() -> None:
    base = ROOT / "data" / "reference" / "hpt_captured"
    rows = list(csv.DictReader((base / "manifest.csv").open()))
    assert rows
    for r in rows:
        assert (base / r["file"]).is_file(), r
        assert r["site"].startswith("https://"), r
        assert parse_hpt_txt((base / r["file"]).read_text())[0].get("mrf-url"), r


def test_temporary_server_error_is_retried() -> None:
    answers = [httpx.Response(502), httpx.Response(200, text=HPT)]
    waits: list[int] = []
    with httpx.Client(transport=httpx.MockTransport(lambda r: answers.pop(0))) as client:
        result = http_fetcher(client, sleep=waits.append)("https://flaky.example")
    assert result.error is None and waits == [15]


def write_home(tmp_path: Path, records: object) -> None:
    import json

    (tmp_path / "fetches.json").write_text(
        "﻿" + json.dumps(records), encoding="utf-8"
    )  # PowerShell 5.1 writes UTF-8 with a BOM


def test_home_runner_fetch_used_when_github_is_refused(conn: Connection, tmp_path: Path) -> None:
    from procedurescout_ingest.discovery import load_home_fetches
    from procedurescout_ingest.reference.common import LoadStats

    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    (tmp_path / "down.example.txt").write_text(
        "location-name: SYNTHETIC OTHER SITE HOSPITAL\n"
        "source-page-url: https://down.example/pricing\n"
        "mrf-url: https://down.example/mrf/other.csv\n"
        "contact-name: Synthetic\ncontact-email: x@down.example\n"
    )
    write_home(
        tmp_path,
        [
            {
                "site": "https://down.example",
                "url": "https://down.example/cms-hpt.txt",
                "file": "down.example.txt",
                "http_status": 200,
                "final_url": "https://down.example/cms-hpt.txt",
                "error": None,
            },
            {
                "site": SITE,
                "url": f"{SITE}/cms-hpt.txt",
                "file": None,
                "http_status": 404,
                "final_url": None,
                "error": "Not Found",
            },
        ],
    )
    hstats = LoadStats()
    home = load_home_fetches(tmp_path, hstats)
    assert hstats.summary == {"home_fetches_ok": 1, "home_fetches_failed": 1}
    stats = discover(conn, "NV", fake_fetcher, None, home)
    assert stats.summary["sites_from_home_runner"] == 1
    rows = conn.execute(
        text(
            "SELECT fetched_via, http_status, error IS NULL, entries FROM src.hpt_txt_fetch "
            "WHERE site = 'https://down.example' ORDER BY fetched_via"
        )
    ).all()
    assert [tuple(r) for r in rows] == [("github", 503, False, None), ("home_runner", 200, True, 1)]
    owner = conn.execute(
        text(
            "SELECT f.ccn FROM src.transparency_source s JOIN ref.facility f "
            "ON f.id = s.facility_id WHERE s.url = 'https://down.example/mrf/other.csv'"
        )
    ).scalar()
    assert owner == "SYN504"


def test_home_runner_failure_is_reported(conn: Connection, tmp_path: Path) -> None:
    from procedurescout_ingest.discovery import load_home_fetches
    from procedurescout_ingest.reference.common import LoadStats

    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    (tmp_path / "down.example.txt").write_text("<!DOCTYPE html><p>blocked</p>")
    write_home(
        tmp_path,
        {
            "site": "https://down.example",
            "url": "https://down.example/cms-hpt.txt",
            "file": "down.example.txt",
            "http_status": 200,
            "final_url": None,
            "error": None,
        },
    )
    home = load_home_fetches(tmp_path, LoadStats())
    stats = discover(conn, "NV", fake_fetcher, None, home)
    failed = [r.message for r in stats.rejects if r.rule == "hpt_fetch_failed"]
    assert any("from Cooper's computer: returned a web page" in m for m in failed)


def test_no_home_directory_means_no_home_fetches(tmp_path: Path) -> None:
    from procedurescout_ingest.discovery import load_home_fetches
    from procedurescout_ingest.reference.common import LoadStats

    assert load_home_fetches(tmp_path / "missing", LoadStats()) == {}


def test_prober_reads_headers_without_downloading() -> None:
    from procedurescout_ingest.discovery import http_prober

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        if request.url.path == "/head-ok.json":
            return httpx.Response(
                200,
                headers={
                    "content-length": "123456789",
                    "content-type": "application/json",
                    "last-modified": "Tue, 01 Sep 2026 00:00:00 GMT",
                },
            )
        if request.url.path == "/no-head.csv":
            if request.method == "HEAD":
                return httpx.Response(405)
            return httpx.Response(200, headers={"content-length": "2048"}, content=b"x" * 2048)
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        probe = http_prober(client, sleep=lambda _s: None)
        a = probe("https://files.example/head-ok.json")
        b = probe("https://files.example/no-head.csv")
        c = probe("https://files.example/missing.csv")
    assert (a.method, a.content_length, a.last_modified) == (
        "HEAD",
        123456789,
        "Tue, 01 Sep 2026 00:00:00 GMT",
    )
    assert (b.method, b.content_length) == ("GET-headers", 2048)
    assert (c.http_status, c.error, c.content_length) == (404, "HTTP error", None)
    assert seen == [
        "HEAD /head-ok.json",
        "HEAD /no-head.csv",
        "GET /no-head.csv",
        "HEAD /missing.csv",
        "GET /missing.csv",
    ]


def test_probe_sources_records_sizes(conn: Connection) -> None:
    from procedurescout_ingest.discovery import ProbeResult, probe_sources

    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    discover(conn, "NV", fake_fetcher)
    sizes = {f"{SITE}/mrf/valley.json": 3 * 1024 * 1024, f"{SITE}/mrf/shared.json": None}

    probed: list[str] = []

    def prober(url: str) -> ProbeResult:
        probed.append(url)
        if url.endswith("shared.json"):
            return ProbeResult("HEAD", 404, url, error="HTTP error")
        return ProbeResult("HEAD", 200, url, sizes.get(url), "application/json", None)

    stats = probe_sources(conn, prober)
    # valley.json is assigned; shared.json is held back but lists a facility of
    # ours; unknown.json lists nobody we know and is skipped.
    assert sorted(probed) == [f"{SITE}/mrf/shared.json", f"{SITE}/mrf/valley.json"]
    assert stats.summary["probe_skipped_out_of_area"] >= 1  # other suites may add sources
    assert stats.summary["probe_sized"] == 1 and stats.summary["probe_failed"] == 1
    failed = [r for r in stats.rejects if r.rule == "probe_failed"]
    assert failed[0].row_ref.startswith("held back (matched ccn ")
    row = conn.execute(
        text(
            "SELECT p.content_length FROM src.source_probe p JOIN src.transparency_source s "
            "ON s.id = p.source_id WHERE s.url = :u"
        ),
        {"u": f"{SITE}/mrf/valley.json"},
    ).scalar()
    assert row == 3 * 1024 * 1024
    assert any("3.0 MB" in r.message for r in stats.rejects if r.rule == "probe_ok")


CO_HEADER = "location_name,parent_ccn,note,reviewed_by,reviewed_at\n"


def _source_owner(conn: Connection, url: str) -> str | None:
    return conn.execute(
        text(
            "SELECT f.ccn FROM src.transparency_source s "
            "LEFT JOIN ref.facility f ON f.id = s.facility_id WHERE s.url = :u"
        ),
        {"u": url},
    ).scalar()


def test_co_listed_location_lets_file_be_assigned(conn: Connection) -> None:
    from procedurescout_ingest.discovery import load_co_listed
    from procedurescout_ingest.reference.common import LoadStats

    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    stats0 = LoadStats()
    approved = load_co_listed(
        conn,
        CO_HEADER
        # spacing and letter case aside, the published name must match exactly
        + "synthetic valley  north campus,SYN503,listed in its file,tester,2026-11-06\n"
        + "Synthetic Clinic Nobody Knows,SYN501,unreviewed row,,\n",
        stats0,
    )
    assert len(approved) == 1 and stats0.summary["co_listed_unreviewed"] == 1
    stats = discover(conn, "NV", fake_fetcher, co_listed=approved)
    assert _source_owner(conn, f"{SITE}/mrf/shared.json") == "SYN503"
    assert _source_owner(conn, f"{SITE}/mrf/unknown.json") is None  # nobody matched there
    row = conn.execute(
        text(
            "SELECT e.match_status, e.facility_id, f.ccn FROM src.hpt_txt_entry e "
            "JOIN ref.facility f ON f.id = e.co_listed_with "
            "WHERE e.location_name = 'Synthetic Valley North Campus'"
        )
    ).one()
    assert tuple(row) == ("co_listed", None, "SYN503")  # not made into a facility of ours
    assert stats.summary["entries_co_listed"] == 1
    assert stats.summary["entries_unmatched"] == 1  # the unknown clinic


def test_co_listed_approval_for_another_hospital_does_not_assign(conn: Connection) -> None:
    from procedurescout_ingest.discovery import load_co_listed
    from procedurescout_ingest.reference.common import LoadStats

    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    approved = load_co_listed(
        conn,
        CO_HEADER + "Synthetic Valley North Campus,SYN501,wrong hospital,tester,2026-11-06\n",
        LoadStats(),
    )
    discover(conn, "NV", fake_fetcher, co_listed=approved)
    assert _source_owner(conn, f"{SITE}/mrf/shared.json") is None
    status = conn.execute(
        text(
            "SELECT match_status FROM src.hpt_txt_entry "
            "WHERE location_name = 'Synthetic Valley North Campus'"
        )
    ).scalar()
    assert status == "unmatched"


def test_co_listed_requires_parent(conn: Connection) -> None:
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(
                text(
                    "INSERT INTO src.hpt_txt_fetch (id, site, url) VALUES "
                    "('00000000-0000-0000-0000-000000000077', 'https://x.example', 'u')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO src.hpt_txt_entry (fetch_id, block_index, match_status) VALUES "
                    "('00000000-0000-0000-0000-000000000077', 0, 'co_listed')"
                )
            )


def test_campus_child_listed_with_parent_gives_file_to_parent(conn: Connection) -> None:
    from procedurescout_ingest.reference.relationships import load_reviewed_relationships

    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    load_reviewed_aliases(
        conn,
        "ccn,alias,evidence,reviewed_by,reviewed_at\n"
        "SYN502,Synthetic Valley North Campus,name used in its cms-hpt.txt,tester,2026-11-07\n",
    )
    # without a relationship: the file names two of our facilities, so nobody gets it
    discover(conn, "NV", fake_fetcher)
    assert _source_owner(conn, f"{SITE}/mrf/shared.json") is None
    rel = load_reviewed_relationships(
        conn,
        "parent_ccn,child_ccn,relationship_type,evidence,reviewed_by,reviewed_at\n"
        "SYN503,SYN502,campus_of,listed as an extension in the parent's file,tester,2026-11-07\n",
    )
    assert rel.rows_loaded == 1
    conn.execute(text("DELETE FROM src.transparency_source WHERE url LIKE :u"), {"u": f"{SITE}/%"})
    stats = discover(conn, "NV", fake_fetcher)
    assert _source_owner(conn, f"{SITE}/mrf/shared.json") == "SYN503"
    child = [r for r in stats.rejects if r.rule == "listed_in_parent_file"]
    assert [r.row_ref for r in child] == ["ccn:SYN502"]


def test_a_listed_location_is_matched_by_its_price_file_address(conn: Connection) -> None:
    """Vermont run (2026-11-12): only 3 of 17 hospitals were found. A health
    system's file lists its sister hospitals under other names; the price
    file's header address (street number + ZIP) names the hospital."""
    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    conn.execute(
        text(
            "UPDATE ref.facility SET address_line1 = '77 PORTER DR', zip5 = '89991', "
            "website = NULL WHERE ccn = 'SYN505'"
        )
    )
    header = (
        b'{"hospital_name": "Synthetic Clinic Nobody Knows", '
        b'"hospital_address": ["77 Porter Drive, Testville, NV 89991"], '
        b'"standard_charge_information": ['
    )

    def head(url: str) -> bytes:
        return header if url.endswith("/mrf/unknown.json") else b""

    stats = discover(conn, "NV", fake_fetcher, head=head)
    assert stats.summary["entries_matched_by_price_file_address"] == 1
    row = conn.execute(
        text(
            "SELECT e.match_status, f.ccn, f.website, f.website_reviewed_by "
            "FROM src.hpt_txt_entry e "
            "JOIN ref.facility f ON f.id = e.facility_id "
            "WHERE e.location_name = 'Synthetic Clinic Nobody Knows'"
        )
    ).first()
    assert row is not None and (row[0], row[1], row[2]) == ("matched", "SYN505", SITE)
    assert "price file's header" in row[3]
    # the name now resolves on later runs, as an approved alias with its evidence
    from procedurescout_core.facility_repo import resolve_facility_by_name

    assert resolve_facility_by_name(conn, "Synthetic Clinic Nobody Knows", "NV").facility_id
