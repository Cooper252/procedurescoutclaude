"""The bucket store (Cloudflare R2, D-048), tested against a local S3 emulator (moto).

Reading through DuckDB needs its httpfs extension, which is downloaded from
extensions.duckdb.org; that test is skipped where the download is blocked and
runs in GitHub Actions.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest

from procedurescout_core.object_store import LocalStore, S3Store, open_store, published_key

moto_server = pytest.importorskip("moto.server")
boto3 = pytest.importorskip("boto3")

BUCKET = "procedurescout-test"
KEY = published_key("NV", uuid.uuid4(), uuid.uuid4())


@pytest.fixture(scope="module")
def endpoint() -> Iterator[str]:
    server = moto_server.ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
    server.start()
    host, port = server.get_host_and_port()
    url = f"http://{host}:{port}"
    boto3.client(
        "s3",
        endpoint_url=url,
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
    ).create_bucket(Bucket=BUCKET)
    yield url
    server.stop()


@pytest.fixture
def store(endpoint: str) -> S3Store:
    return S3Store(BUCKET, endpoint, "test", "test-secret", region="us-east-1")


@pytest.fixture
def parquet(tmp_path: Path) -> Path:
    import duckdb

    out = tmp_path / "prices.parquet"
    with duckdb.connect() as duck:
        duck.execute(
            "COPY (SELECT '0270'::VARCHAR AS code, 1234.567890123456789::DECIMAL(38,15) AS amount) "
            f"TO '{out}' (FORMAT parquet)"
        )
    return out


def test_put_exists_and_never_overwrites(store: S3Store, parquet: Path) -> None:
    key = published_key("NV", uuid.uuid4(), uuid.uuid4())
    assert not store.exists(key)
    store.put(parquet, key)
    assert store.exists(key)
    with pytest.raises(FileExistsError):
        store.put(parquet, key)
    body = (
        boto3.client(
            "s3",
            endpoint_url=store.endpoint,
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name="us-east-1",
        )
        .get_object(Bucket=BUCKET, Key=key)["Body"]
        .read()
    )
    assert body == parquet.read_bytes()  # uploaded byte for byte


def test_keys_are_validated(store: S3Store, parquet: Path) -> None:
    for bad in ("../secret", "published/NV/x/y.parquet", "fixture/NV/a/b.parquet"):
        with pytest.raises(ValueError):
            store.put(parquet, bad)
        with pytest.raises(ValueError):
            store.local_path(bad)
    assert store.local_path(KEY) == f"s3://{BUCKET}/{KEY}"


def test_secret_is_never_shown(store: S3Store) -> None:
    assert "test-secret" not in repr(store)


def test_settings_validation() -> None:
    with pytest.raises(ValueError):
        S3Store("Bad_Bucket", "https://x.r2.cloudflarestorage.com", "k", "s")
    with pytest.raises(ValueError):
        S3Store("ok-bucket", "x.r2.cloudflarestorage.com", "k", "s")  # no https://
    with pytest.raises(ValueError):
        S3Store("ok-bucket", "https://x.r2.cloudflarestorage.com", "", "")
    assert isinstance(open_store("price-store"), LocalStore)
    s3 = open_store("s3://ok-bucket", "https://acct.r2.cloudflarestorage.com", "k", "s")
    assert isinstance(s3, S3Store) and s3.bucket == "ok-bucket"
    # Cloudflare's page shows the address with the bucket on the end (first live load)
    shown = S3Store("ok-bucket", "https://acct.r2.cloudflarestorage.com/ok-bucket/", "k", "s")
    assert shown.endpoint == "https://acct.r2.cloudflarestorage.com"
    with pytest.raises(ValueError):
        S3Store("ok-bucket", "https://acct.r2.cloudflarestorage.com/other-bucket", "k", "s")


def _httpfs_available() -> bool:
    import duckdb

    try:
        with duckdb.connect() as duck:
            duck.execute("INSTALL httpfs")
            duck.execute("LOAD httpfs")
    except duckdb.Error:
        return False
    return True


def test_duckdb_reads_exact_amounts_from_the_bucket(store: S3Store, parquet: Path) -> None:
    if not _httpfs_available():
        pytest.skip("DuckDB httpfs extension cannot be downloaded here")
    key = published_key("NV", uuid.uuid4(), uuid.uuid4())
    store.put(parquet, key)
    with store.duckdb() as duck:
        row = duck.execute(
            "SELECT code, amount FROM read_parquet(?)", [[store.local_path(key)]]
        ).fetchone()
    assert row is not None
    assert row[0] == "0270"
    assert Decimal(str(row[1])) == Decimal("1234.567890123456789")
