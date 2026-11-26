"""Every billing code in published prices is searchable (D-045); provider
prices by code, sessions and packages."""

import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError

from procedurescout_core.object_store import LocalStore
from procedurescout_core.search import search, suggest
from procedurescout_ingest import publish
from procedurescout_ingest.code_index import rebuild_code_index
from procedurescout_ingest.discovery import discover
from procedurescout_ingest.reference.websites import load_websites
from tests.test_discovery import fake_fetcher, setup_hospitals, websites_csv
from tests.test_publish import stage, syn501
from tests.test_search_and_review import place


@pytest.fixture()
def published(conn: Connection, tmp_path: Path) -> LocalStore:
    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    place(conn, "SYN501", "36.17", "-115.14")
    discover(conn, "NV", fake_fetcher)
    stage(conn, tmp_path)
    store = LocalStore(tmp_path / "store")
    publish.approve(conn, uuid.UUID(syn501(conn)[0].dataset_version_id), "Tester", store)
    return store


def test_codes_in_published_prices_become_searchable(
    conn: Connection, published: LocalStore
) -> None:
    stats = rebuild_code_index(conn)
    assert stats.rows_loaded >= 2
    row = conn.execute(
        text(
            "SELECT facilities, prices FROM ref.code_index WHERE system = 'CPT' AND code = '99999'"
        )
    ).one()
    assert row[0] == 1 and row[1] >= 1
    by_number = suggest(conn, "99999")
    assert [(s.kind, s.code_system, s.code) for s in by_number] == [("code", "CPT", "99999")]
    result = search(
        conn,
        published,
        latitude=Decimal("36.17"),
        longitude=Decimal("-115.14"),
        radius_miles=Decimal(25),
        code_system="CPT",
        code="99999",
    )
    assert result.facilities[0].status == "prices"
    descriptor = conn.execute(
        text("SELECT descriptor FROM ref.code WHERE system = 'CPT' AND code = '99999'")
    ).scalar()
    assert descriptor is None  # hospital wording stays in code_index, labeled (rule 11)


def test_provider_prices_by_code_sessions_and_packages(conn: Connection) -> None:
    setup_hospitals(conn)
    conn.execute(
        text("INSERT INTO ref.code (system, code, version) VALUES ('CDT', 'D1110', '2026')")
    )
    fid = conn.execute(text("SELECT id FROM ref.facility WHERE ccn = 'SYN501'")).scalar()
    ins = (
        "INSERT INTO prov.listing_price (facility_id, code_system, code, quantity, regular_price) "
        "VALUES (:f, CAST(:s AS ref.code_system), :c, :q, :p)"
    )
    conn.execute(text(ins), {"f": fid, "s": "CDT", "c": "D1110", "q": 1, "p": 120})
    conn.execute(text(ins), {"f": fid, "s": "CDT", "c": "D1110", "q": 2, "p": 220})  # 2 visits
    sp = conn.begin_nested()
    with pytest.raises(DBAPIError):
        conn.execute(text(ins), {"f": fid, "s": "CDT", "c": "D9999X", "q": 1, "p": 10})
    sp.rollback()
    pkg = conn.execute(
        text(
            "INSERT INTO prov.package (facility_id, name, price) "
            "VALUES (:f, 'Cleaning plus whitening', 299) RETURNING id"
        ),
        {"f": fid},
    ).scalar()
    conn.execute(
        text(
            "INSERT INTO prov.package_item (package_id, code_system, code) "
            "VALUES (:p, 'CDT', 'D1110')"
        ),
        {"p": pkg},
    )
    sp = conn.begin_nested()
    with pytest.raises(DBAPIError):  # a piece must be a standard service or an official code
        conn.execute(
            text(
                "INSERT INTO prov.package_item (package_id, code_system, code) "
                "VALUES (:p, 'CDT', 'NOPE1')"
            ),
            {"p": pkg},
        )
    sp.rollback()


def test_any_published_insurer_name_can_be_searched_as_written(
    conn: Connection, published: LocalStore
) -> None:
    from procedurescout_core.search import SearchError, payer_suggestions

    rebuild_code_index(conn)
    assert payer_suggestions(conn, "payer two") == [("Synthetic Payer Two", 1)]
    kw = {
        "latitude": Decimal("36.17"),
        "longitude": Decimal("-115.14"),
        "radius_miles": Decimal(25),
        "service_slug": None,
        "code_system": "CPT",
        "code": "99999",
        "mode": "plan",
    }
    res = search(conn, published, payer_raw="SYNTHETIC PAYER ONE", **kw)  # type: ignore[arg-type]
    negotiated = [p for p in res.facilities[0].prices if p.price_type == "negotiated"]
    assert {p.payer_name_raw for p in negotiated} == {"Synthetic Payer One"}  # exactly as written
    with pytest.raises(SearchError):
        search(conn, published, payer_raw="Some Unknown Insurer", **kw)  # type: ignore[arg-type]


def test_the_code_index_counts_files_over_several_runs(
    conn: Connection, published: LocalStore
) -> None:
    """2026-11-23: the whole rebuild ran past the step's 20 minutes on the live
    database. A run with no time left counts nothing and leaves the index as it
    was; the next run catches up and only then replaces the index."""
    first = rebuild_code_index(conn, seconds=0)
    assert first.summary["files_added"] == 0 and first.summary["index_updated"] is False
    assert first.summary["files_still_to_count"] >= 1
    later = rebuild_code_index(conn)
    assert later.summary["files_still_to_count"] == 0 and later.summary["index_updated"] is True
    row = conn.execute(
        text("SELECT facilities FROM ref.code_index WHERE system = 'CPT' AND code = '99999'")
    ).one()
    assert row[0] == 1
    again = rebuild_code_index(conn)  # nothing new: same totals, nothing counted twice
    assert again.summary["files_added"] == 0
    assert (
        conn.execute(
            text("SELECT facilities FROM ref.code_index WHERE system = 'CPT' AND code = '99999'")
        ).scalar_one()
        == 1
    )


def test_cleanup_removes_replaced_files_bookkeeping_only_when_safe(
    conn: Connection, published: LocalStore
) -> None:
    """Cooper approved the cleanup (2026-11-26): summaries of replaced files go,
    but only once the code index has taken them out of its totals; current
    files' summaries stay."""
    from procedurescout_ingest.cleanup import clean_up

    rebuild_code_index(conn)
    dv = conn.execute(
        text("SELECT id FROM src.dataset_version WHERE status = 'published' LIMIT 1")
    ).scalar_one()

    def summaries() -> int:
        return int(
            conn.execute(
                text("SELECT count(*) FROM price.file_code_summary WHERE dataset_version_id = :d"),
                {"d": dv},
            ).scalar_one()
        )

    before = summaries()
    assert before > 0
    assert clean_up(conn)["summaries_of_replaced_files"] == 0  # still published
    conn.execute(
        text("UPDATE src.dataset_version SET status = 'retired', retired_at = now() WHERE id = :d"),
        {"d": dv},
    )
    clean_up(conn)
    assert summaries() == before  # still in the code index's totals: kept
    rebuild_code_index(conn)  # takes it out of the totals
    result = clean_up(conn)
    assert summaries() == 0 and result["summaries_of_replaced_files"] >= before
    assert result["finished"] is True and result["largest_tables_mb"]
