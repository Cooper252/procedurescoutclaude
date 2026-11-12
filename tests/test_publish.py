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


def stage(
    conn: Connection, tmp_path: Path, content: bytes | None = None, skip_unchanged: bool = False
) -> None:
    data = content or JSON_FILE.read_bytes()

    def downloader(url: str, dest: Path) -> Download:
        dest.write_bytes(data)
        return Download(url, dest, hashlib.sha256(data).hexdigest(), len(data), 200, url)

    check_price_files(
        conn,
        "NV",
        downloader,
        tmp_path / "w",
        today=date(2026, 11, 8),
        load=True,
        min_free_bytes=0,
        skip_unchanged=skip_unchanged,
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


def test_refresh_skips_a_file_with_the_same_content(
    conn: Connection, staged: publish.Pending, tmp_path: Path
) -> None:
    """National refreshes (D-048): once a facility's prices are published, the
    same file again is not loaded again."""
    store = LocalStore(tmp_path / "store")
    publish.approve(conn, uuid.UUID(staged.dataset_version_id), "Synthetic Reviewer", store)
    before = conn.execute(text("SELECT count(*) FROM src.dataset_version")).scalar_one()
    stage(conn, tmp_path, skip_unchanged=True)
    after = conn.execute(text("SELECT count(*) FROM src.dataset_version")).scalar_one()
    assert after == before
    stage(conn, tmp_path, skip_unchanged=False)  # forced: loaded again
    assert conn.execute(text("SELECT count(*) FROM src.dataset_version")).scalar_one() > before


def test_after_publishing_staged_rows_go_but_index_and_search_remain(
    conn: Connection, staged: publish.Pending, tmp_path: Path
) -> None:
    """National storage (D-054): the Parquet file is what the site reads; staged
    rows are removed after publishing, summaries keep the indexes complete."""
    from procedurescout_ingest.code_index import rebuild_code_index

    store = LocalStore(tmp_path / "store")
    dv = uuid.UUID(staged.dataset_version_id)
    publish.approve(conn, dv, "Synthetic Reviewer", store)
    rebuild_code_index(conn)
    before_codes = conn.execute(
        text("SELECT system::text, code, facilities, prices FROM ref.code_index ORDER BY 1, 2")
    ).all()
    before_payers = conn.execute(
        text("SELECT raw_text, prices FROM ref.payer_index ORDER BY 1")
    ).all()
    removed = publish.prune_published(conn)
    assert removed == 6
    assert (
        conn.execute(
            text("SELECT count(*) FROM price.price WHERE dataset_version_id = :d"), {"d": dv}
        ).scalar_one()
        == 0
    )
    rebuild_code_index(conn)
    after_codes = conn.execute(
        text("SELECT system::text, code, facilities, prices FROM ref.code_index ORDER BY 1, 2")
    ).all()
    assert after_codes == before_codes and len(after_codes) > 0
    assert (
        conn.execute(text("SELECT raw_text, prices FROM ref.payer_index ORDER BY 1")).all()
        == before_payers
    )
    fid = conn.execute(text("SELECT id FROM ref.facility WHERE ccn = 'SYN501'")).scalar_one()
    code = conn.execute(text("SELECT code FROM ref.code_index LIMIT 1")).scalar_one()
    system = conn.execute(text("SELECT system::text FROM ref.code_index LIMIT 1")).scalar_one()
    assert find_prices(conn, store, [fid], system, code)  # the published file still answers


def test_first_files_publish_automatically_only_when_allowed(
    conn: Connection, staged: publish.Pending, tmp_path: Path
) -> None:
    store = LocalStore(tmp_path / "store")
    dv = uuid.UUID(staged.dataset_version_id)
    ok, reasons = publish.auto_check(conn, dv)
    assert not ok and "first file" in reasons[0]
    ok, reasons = publish.auto_check(conn, dv, allow_first=True)
    assert ok, reasons
    decisions = publish.auto_publish_pending(
        conn, store, allow_first=True, facility_id=staged.facility_id
    )
    assert [d.published for d in decisions] == [True]


def test_publish_as_you_go_hook_runs_after_each_file(conn: Connection, tmp_path: Path) -> None:
    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    discover(conn, "NV", fake_fetcher)
    data = JSON_FILE.read_bytes()
    store = LocalStore(tmp_path / "store")
    seen: list[str] = []

    def downloader(url: str, dest: Path) -> Download:
        dest.write_bytes(data)
        return Download(url, dest, hashlib.sha256(data).hexdigest(), len(data), 200, url)

    def after(c: Connection, facility_id: str) -> None:
        seen.append(facility_id)
        publish.auto_publish_pending(c, store, True, facility_id)
        publish.prune_published(c, facility_id)

    check_price_files(
        conn,
        "NV",
        downloader,
        tmp_path / "w",
        today=date(2026, 11, 8),
        load=True,
        min_free_bytes=0,
        after_load=after,
    )
    assert seen
    published = conn.execute(
        text("SELECT count(*) FROM src.dataset_version WHERE status = 'published'")
    ).scalar_one()
    staged_rows = conn.execute(
        text(
            "SELECT count(*) FROM price.price p JOIN src.dataset_version dv "
            "ON dv.id = p.dataset_version_id WHERE dv.status = 'published'"
        )
    ).scalar_one()
    assert published >= 1 and staged_rows == 0


def test_a_big_hospital_cannot_crowd_others_out_of_a_search(tmp_path: Path) -> None:
    """All-states test (2026-11-10): the row cap applied to the whole search, so
    a hospital with thousands of insurer rates for a code hid the next hospital's
    prices. The cap is now per facility, and searches ask only for the types they show."""
    import duckdb

    store = LocalStore(tmp_path / "store")
    big, small = "00000000-0000-0000-0000-00000000000a", "00000000-0000-0000-0000-00000000000b"
    for fid, n in ((big, 50), (small, 0)):
        path = store.local_path(f"published/NV/{fid}/{fid}.parquet")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        duckdb.sql(
            f"""
            COPY (
              SELECT '{fid}' AS facility_id, 'hospital_file' AS price_source, 'CPT' AS code_system,
                     '99999' AS code, NULL::VARCHAR AS description_raw, 'outpatient' AS setting,
                     t.price_type, t.payer AS payer_name_raw, NULL::VARCHAR AS plan_name_raw,
                     CAST(t.amount AS DECIMAL(18,4)) AS amount, NULL::DECIMAL(18,4) AS percentage,
                     NULL::VARCHAR AS algorithm, NULL::VARCHAR AS methodology,
                     NULL::VARCHAR AS dataset_version_id, '' AS quality_flags
              FROM (
                SELECT 'negotiated' AS price_type, 'Payer ' || i AS payer, 100 + i AS amount
                FROM range({n}) r(i)
                UNION ALL SELECT 'gross', NULL, 500 UNION ALL SELECT 'discounted_cash', NULL, 300
              ) t
            ) TO '{path}' (FORMAT parquet)
            """
        )

    class Keys:
        def execute(self, *_: object, **__: object) -> "Keys":
            return self

        def scalars(self) -> list[str]:
            return [f"published/NV/{big}/{big}.parquet", f"published/NV/{small}/{small}.parquet"]

    rows = find_prices(Keys(), store, [big, small], "CPT", "99999", limit=10)  # type: ignore[arg-type]
    by = {f: [p.price_type for p in rows if p.facility_id == f] for f in (big, small)}
    assert len(by[big]) == 10 and sorted(by[small]) == ["discounted_cash", "gross"]
    shown = find_prices(
        Keys(),  # type: ignore[arg-type]
        store,
        [big, small],
        "CPT",
        "99999",
        price_types=["discounted_cash", "gross"],
    )
    assert sorted(p.price_type for p in shown) == ["discounted_cash"] * 2 + ["gross"] * 2
    with pytest.raises(PriceQueryError, match="price type"):
        find_prices(Keys(), store, [big], "CPT", "99999", price_types=["DROP TABLE"])  # type: ignore[arg-type]


def test_rows_kept_elsewhere_publish_or_are_set_aside(
    conn: Connection, staged: publish.Pending, tmp_path: Path
) -> None:
    """D-059 (first live load): price rows staged in a work database on the loading
    computer. Here the same connection plays both parts, which exercises the
    two-place path: summaries counted where the rows are, rows removed after
    the decision, and a file that fails the checks is set aside, not left waiting."""
    store = LocalStore(tmp_path / "store")
    dv = uuid.UUID(staged.dataset_version_id)
    held = publish.auto_publish_pending(conn, store, False, staged.facility_id, rows=conn)
    assert [d.published for d in held] == [False]  # a first file needs allow_first
    status = conn.execute(
        text("SELECT status::text, reviewed_by FROM src.dataset_version WHERE id = :d"), {"d": dv}
    ).one()
    assert tuple(status) == ("retired", publish.AUTO_REVIEWER)
    assert publish.pending_reviews(conn) == []
    left = conn.execute(
        text("SELECT count(*) FROM price.price WHERE dataset_version_id = :d"), {"d": dv}
    ).scalar_one()
    assert left == 0


def test_rows_kept_elsewhere_publish_with_summaries(conn: Connection, tmp_path: Path) -> None:
    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    discover(conn, "NV", fake_fetcher)
    stage(conn, tmp_path)
    p = syn501(conn)[0]
    store = LocalStore(tmp_path / "store")
    done = publish.auto_publish_pending(conn, store, True, p.facility_id, rows=conn)
    assert [d.published for d in done] == [True]
    dv = uuid.UUID(p.dataset_version_id)
    codes = conn.execute(
        text("SELECT count(*) FROM price.file_code_summary WHERE dataset_version_id = :d"),
        {"d": dv},
    ).scalar_one()
    left = conn.execute(
        text("SELECT count(*) FROM price.price WHERE dataset_version_id = :d"), {"d": dv}
    ).scalar_one()
    assert codes > 0 and left == 0
    fid = uuid.UUID(p.facility_id)
    assert find_prices(conn, store, [fid], "CPT", "99999")


def test_places_with_prices_are_not_pushed_out_by_nearer_offices(
    conn: Connection, staged: publish.Pending, tmp_path: Path
) -> None:
    """First live load: the 50 nearest places were all unpriced offices, so the
    hospitals with prices never showed. Places that can answer now come first."""
    from procedurescout_core.search import search
    from procedurescout_ingest.code_index import rebuild_code_index

    store = LocalStore(tmp_path / "store")
    publish.approve(conn, uuid.UUID(staged.dataset_version_id), "Synthetic Reviewer", store)
    rebuild_code_index(conn)
    conn.execute(
        text(
            "UPDATE ref.facility SET geom = ST_SetSRID(ST_MakePoint(:x, 36.10), 4326)::geography, "
            "geocode_source = 'census_geocoder', geocode_precision = 'address' "
            "WHERE ccn = :c"
        ),
        [{"x": -115.10, "c": "SYN501"}, {"x": -115.0001, "c": "SYN503"}],
    )
    r = search(
        conn,
        store,
        latitude=Decimal("36.10"),
        longitude=Decimal("-115.00"),
        radius_miles=Decimal(25),
        code_system="CPT",
        code="99999",
        max_facilities=1,
        mode="list",
    )
    assert [f.facility_id for f in r.facilities] == [staged.facility_id]
    assert r.facilities[0].headline is not None
