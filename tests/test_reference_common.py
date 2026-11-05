"""Source acquisition, PDC paging, and load lineage."""

import io
import json
import zipfile
from datetime import date
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Engine, text

from procedurescout_ingest.reference import cli
from procedurescout_ingest.reference.cms_pdc import fetch_state_rows
from procedurescout_ingest.reference.common import (
    LoadStats,
    SourceBlob,
    SourceError,
    acquire,
    maybe_unzip,
    normalize_header,
    parse_zip5,
)


@pytest.mark.parametrize(
    ("raw", "key"),
    [
        ("City/Town", "citytown"),
        ("County/Parish", "countyparish"),
        ("ZIP Code", "zip_code"),
        ("Hospital overall rating", "hospital_overall_rating"),
        ("﻿Facility ID", "facility_id"),
        ("zip_code", "zip_code"),
        ("INTPTLONG      ", "intptlong"),
    ],
)
def test_normalize_header(raw: str, key: str) -> None:
    assert normalize_header(raw) == key


@pytest.mark.parametrize(
    ("raw", "zip5"),
    [
        ("89502", "89502"),
        ("89502-1234", "89502"),
        ("895021234", "89502"),
        ("8950", None),
        ("", None),
        ("ABCDE", None),
    ],
)
def test_parse_zip5(raw: str, zip5: str | None) -> None:
    assert parse_zip5(raw) == zip5


def test_download_size_cap() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 2048))
    with httpx.Client(transport=transport) as client:
        assert len(acquire("https://example.test/a", client, max_bytes=4096).data) == 2048
        with pytest.raises(SourceError, match="larger"):
            acquire("https://example.test/a", client, max_bytes=1024)


def test_http_error_is_an_error() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(404))
    with httpx.Client(transport=transport) as client, pytest.raises(SourceError, match="404"):
        acquire("https://example.test/missing", client)


def test_unzip_picks_exactly_one_member() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.pdf", b"%PDF")
        zf.writestr("data.txt", b"GEOID\n")
    blob = SourceBlob(buf.getvalue(), "0" * 64)
    assert maybe_unzip(blob, lambda n, _d: n.endswith(".txt")) == ("data.txt", b"GEOID\n")
    with pytest.raises(SourceError):
        maybe_unzip(blob, lambda n, _d: True)


def pdc_transport(total: int, pages: list[list[dict[str, str]]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/metastore/" in request.url.path:
            return httpx.Response(200, json={"modified": "2026-07-22"})
        assert request.url.params["conditions[0][value]"] == "NV"
        page = pages.pop(0) if pages else []
        return httpx.Response(200, json={"count": total, "results": page})

    return httpx.MockTransport(handler)


def test_pdc_pages_until_count() -> None:
    pages = [[{"facility_id": "SYN001", "State": "NV"}], [{"facility_id": "SYN002", "State": "NV"}]]
    with httpx.Client(transport=pdc_transport(2, pages)) as client:
        got = fetch_state_rows(client, "xubh-q36u", "NV")
    assert [r["facility_id"] for r in got.rows] == ["SYN001", "SYN002"]
    assert got.rows[0]["state"] == "NV"
    assert got.modified == date(2026, 7, 22) and len(got.sha256) == 64


def test_pdc_short_read_fails() -> None:
    with (
        httpx.Client(transport=pdc_transport(3, [[{"facility_id": "SYN001"}]])) as client,
        pytest.raises(SourceError, match="received 1 rows"),
    ):
        fetch_state_rows(client, "xubh-q36u", "NV")


def test_load_lineage_success_and_failure(engine: Engine) -> None:
    ok = LoadStats(rows_in=2, rows_loaded=1)
    ok.reject("line:3", "synthetic_rule", "synthetic reject")

    def boom(_c: object) -> LoadStats:
        raise SourceError("synthetic failure")

    try:
        cli._run(
            engine,
            "manual_relationships",
            lambda c: ok,
            source_file="synthetic_test.csv",
            parameters={"test": "synthetic"},
        )
        with pytest.raises(SourceError):
            cli._run(
                engine,
                "manual_relationships",
                boom,
                source_file="synthetic_test.csv",
                parameters={"test": "synthetic"},
            )
        with engine.connect() as c:
            rows = c.execute(
                text(
                    "SELECT status, rows_in, rows_loaded, rows_rejected, error, "
                    "(SELECT count(*) FROM src.reference_reject r WHERE r.load_id = l.id) "
                    "FROM src.reference_load l WHERE parameters->>'test' = 'synthetic' "
                    "ORDER BY started_at"
                )
            ).all()
        assert [tuple(r) for r in rows] == [
            ("succeeded", 2, 1, 1, None, 1),
            ("failed", None, None, None, "SourceError: synthetic failure", 0),
        ]
    finally:
        with engine.begin() as c:
            c.execute(
                text("DELETE FROM src.reference_load WHERE parameters->>'test' = 'synthetic'")
            )


def test_reviewed_relationships_file_is_header_only() -> None:
    path = Path(__file__).resolve().parent.parent / cli.RELATIONSHIPS_CSV
    lines = path.read_text().splitlines()
    assert lines == ["parent_ccn,child_ccn,relationship_type,evidence,reviewed_by,reviewed_at"]


def test_cli_parser_defaults() -> None:
    args = cli.build_parser().parse_args(["msdrg"])
    assert (args.fiscal_year, args.grouper_version, args.min_rows) == (2027, 44, 700)
    assert json.dumps(vars(cli.build_parser().parse_args(["hospitals", "--state", "nv"])))
