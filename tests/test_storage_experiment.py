"""NAT-02 storage experiment on synthetic prices."""

import hashlib
from datetime import date
from pathlib import Path

from sqlalchemy import Connection

from procedurescout_ingest import storage_experiment
from procedurescout_ingest.discovery import discover
from procedurescout_ingest.price_files import Download, check_price_files
from procedurescout_ingest.reference.websites import load_websites
from tests.test_discovery import SITE, fake_fetcher, setup_hospitals, websites_csv

JSON_FILE = (
    Path(__file__).resolve().parent / "fixtures" / "price_files" / "synthetic_standardcharges.json"
)


def test_storage_experiment_measures_layouts(conn: Connection, tmp_path: Path) -> None:
    setup_hospitals(conn)
    load_websites(conn, websites_csv())
    discover(conn, "NV", fake_fetcher)

    def downloader(url: str, dest: Path) -> Download:
        data = JSON_FILE.read_bytes()
        dest.write_bytes(data)
        return Download(url, dest, hashlib.sha256(data).hexdigest(), len(data), 200, url)

    check_price_files(
        conn, "NV", downloader, tmp_path / "w", today=date(2026, 11, 7), load=True, min_free_bytes=0
    )
    out = storage_experiment.run(conn, tmp_path / "parquet")
    assert out["current"]["rows"] >= 6
    est = out["normalized_estimate"]
    assert est["distinct_items"] >= 2 and est["distinct_payer_plan_pairs"] >= 2
    pq = out["parquet"]
    assert pq["files"] >= 1 and pq["total_bytes"] > 0
    # the same code is found in both stores
    lookup = pq["lookup"]
    assert lookup["code"] == "CPT 99999"
    assert lookup["parquet_rows_found"] == lookup["postgres_rows_found"] > 0
    assert pq["round_trip_exact"] is True
    assert not list((tmp_path / "parquet").glob("*.csv.gz"))  # intermediate files removed
    assert SITE
