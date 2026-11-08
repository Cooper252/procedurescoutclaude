"""Review step and published Parquet files (synthetic prices only)."""

import hashlib
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import ProgrammingError

from procedurescout_core.object_store import LocalStore, published_key
from procedurescout_core.price_store import PriceQueryError, find_prices
from procedurescout_ingest import publish
from procedurescout_ingest.discovery import discover
from procedurescout_ingest.price_files import Download, check_price_files
from procedurescout_ingest.reference.websites import load_websites
from tests.test_discovery import fake_fetcher, setup_hospitals, websites_csv

JSON_FILE = (
    Path(__file__).resolve().parent / "fixtures" / "price_files" / "synthetic_standardcharges.json"
)


def stage(conn: Connection, tmp_path: Path, content: bytes | None = None) -> None:
    data = content or JSON_FILE.read_bytes()

    def downloader(url: str, dest: Path) -> Download:
        dest.write_bytes(data)
        return Download(url, dest, hashlib.sha256(data).hexdigest(), len(data), 200, url)

    check_price_files(
        conn, "NV", downloader, tmp_path / "w", today=date(2026, 11, 8), load=True, min_free_bytes=0
    )


def syn501(conn: Connection) -> list[publish.Pending]:
    return [p for p in publish.pending_reviews(conn) if p.ccn == "SYN501"]


@pytest.fixture()
def staged(conn: Connection, tmp_path: Path) -> publish.Pending:
    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    discover(conn, "NV", fake_fetcher)
    stage(conn, tmp_path)
    pending = syn501(conn)
    assert len(pending) == 1 and pending[0].rows == 6
    return pending[0]


def test_approve_publishes_exact_parquet_and_search_reads_it(
    conn: Connection, tmp_path: Path, staged: publish.Pending
) -> None:
    store = LocalStore(tmp_path / "store")
    with pytest.raises(publish.ReviewError, match="reviewer"):
        publish.approve(conn, uuid.UUID(staged.dataset_version_id), " ", store)
    key = publish.approve(
        conn, uuid.UUID(staged.dataset_version_id), "Tester", store, "looks right"
    )
    assert store.exists(key) and key.startswith("published/NV/")
    row = conn.execute(
        text(
            "SELECT dv.status::text, dv.reviewed_by, r.state::text, pf.rows, pf.amount_sum "
            "FROM src.dataset_version dv JOIN src.import_run r ON r.id = dv.import_run_id "
            "JOIN src.published_file pf ON pf.dataset_version_id = dv.id WHERE dv.id = :d"
        ),
        {"d": staged.dataset_version_id},
    ).one()
    assert tuple(row[:4]) == ("published", "Tester", "published", 6)
    assert row[4] == Decimal("100.10") + Decimal("80.00") + Decimal("75.25") + Decimal(
        "25000"
    ) + Decimal("20000")
    prices = find_prices(conn, store, [staged.facility_id], "CPT", "99999")
    assert {(p.price_type, p.amount, p.percentage) for p in prices} == {
        ("gross", Decimal("100.10"), None),
        ("discounted_cash", Decimal("80.00"), None),
        ("negotiated", Decimal("75.25"), None),
        ("negotiated", None, Decimal("60")),
    }
    assert all(p.price_source == "hospital_file" for p in prices)
    audit = conn.execute(
        text("SELECT actor, action FROM src.audit_event WHERE entity_id = :d"),
        {"d": staged.dataset_version_id},
    ).one()
    assert tuple(audit) == ("Tester", "approve_and_publish")
    with pytest.raises(publish.ReviewError, match="not waiting for review"):
        publish.approve(conn, uuid.UUID(staged.dataset_version_id), "Tester", store)


def test_next_approval_retires_the_previous_file(
    conn: Connection, tmp_path: Path, staged: publish.Pending
) -> None:
    store = LocalStore(tmp_path / "store")
    first = publish.approve(conn, uuid.UUID(staged.dataset_version_id), "Tester", store)
    changed = JSON_FILE.read_bytes().replace(b'"gross_charge": 100.10', b'"gross_charge": 101.10')
    stage(conn, tmp_path, changed)
    second_pending = syn501(conn)
    assert len(second_pending) == 1
    second = publish.approve(conn, uuid.UUID(second_pending[0].dataset_version_id), "Tester", store)
    assert first != second and store.exists(first)  # old file kept, never overwritten
    current = (
        conn.execute(
            text("SELECT object_key FROM price.published_file WHERE facility_id = :f"),
            {"f": staged.facility_id},
        )
        .scalars()
        .all()
    )
    assert current == [second]
    gross = [
        p.amount
        for p in find_prices(conn, store, [staged.facility_id], "CPT", "99999")
        if p.price_type == "gross"
    ]
    assert gross == [Decimal("101.10")]
    old = conn.execute(
        text("SELECT status::text FROM src.dataset_version WHERE id = :d"),
        {"d": staged.dataset_version_id},
    ).scalar()
    assert old == "retired"


def test_reject_needs_a_reason_and_publishes_nothing(
    conn: Connection, tmp_path: Path, staged: publish.Pending
) -> None:
    dv = uuid.UUID(staged.dataset_version_id)
    with pytest.raises(publish.ReviewError, match="reason"):
        publish.reject(conn, dv, "Tester", "")
    publish.reject(conn, dv, "Tester", "payer names look wrong")
    row = conn.execute(
        text(
            "SELECT dv.status::text, r.state::text, r.error_summary FROM src.dataset_version dv "
            "JOIN src.import_run r ON r.id = dv.import_run_id WHERE dv.id = :d"
        ),
        {"d": dv},
    ).one()
    assert tuple(row) == ("retired", "failed", "rejected by Tester: payer names look wrong")
    store = LocalStore(tmp_path / "store")
    assert find_prices(conn, store, [staged.facility_id], "CPT", "99999") == []


def test_search_filters_are_validated_before_any_file_is_read(
    conn: Connection, tmp_path: Path
) -> None:
    store = LocalStore(tmp_path / "store")
    fid = uuid.uuid4()
    for bad in (
        lambda: find_prices(conn, store, [], "CPT", "99999"),
        lambda: find_prices(conn, store, ["not-a-uuid"], "CPT", "99999"),
        lambda: find_prices(conn, store, [fid], "CPT4", "99999"),
        lambda: find_prices(conn, store, [fid], "CPT", "99999; DROP"),
        lambda: find_prices(conn, store, [uuid.uuid4() for _ in range(201)], "CPT", "1"),
    ):
        with pytest.raises(PriceQueryError):
            bad()


def test_store_refuses_bad_keys_and_overwrites(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    with pytest.raises(ValueError):
        store.local_path("../../etc/passwd")
    key = published_key("NV", uuid.uuid4(), uuid.uuid4())
    src = tmp_path / "x.parquet"
    src.write_bytes(b"x")
    store.put(src, key)
    with pytest.raises(FileExistsError):
        store.put(src, key)


def test_api_role_sees_current_files_but_not_the_manifest_table(api_engine: Engine) -> None:
    with api_engine.connect() as c:
        c.execute(text("SELECT count(*) FROM price.published_file"))
    with api_engine.connect() as c, pytest.raises(ProgrammingError, match="permission denied"):
        c.execute(text("SELECT count(*) FROM src.published_file"))
