"""Where published Parquet files live (D-033).

Two stores share one interface:
- `LocalStore`: a folder (tests, the throwaway workflow, local development);
- `S3Store`: any S3-compatible bucket, chosen for Cloudflare R2 (D-048). The
  API reads Parquet straight from the bucket with DuckDB's httpfs extension,
  fetching only the parts a search needs; publishing uploads with boto3.

`open_store()` picks one from settings: a location starting with `s3://` is a
bucket, anything else is a folder. Published files are never overwritten.

Keys look like `published/NV/<facility_id>/<dataset_version_id>.parquet`.
"""

from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import urlparse

if TYPE_CHECKING:
    import duckdb

_KEY = re.compile(r"^published/[A-Z]{2}/[0-9a-f-]{36}/[0-9a-f-]{36}\.parquet$")
# Provider logos and photos (D-050): served only after review.
_MEDIA_KEY = re.compile(r"^media/[0-9a-f-]{36}/[0-9a-f-]{36}\.(png|jpg|webp)$")


def media_key(facility_id: uuid.UUID, media_id: uuid.UUID, ext: str) -> str:
    key = f"media/{facility_id}/{media_id}.{ext}"
    if not _MEDIA_KEY.match(key):
        raise ValueError(f"not a valid media key: {key!r}")
    return key


def published_key(state_code: str, facility_id: uuid.UUID, dataset_version_id: uuid.UUID) -> str:
    key = f"published/{state_code}/{facility_id}/{dataset_version_id}.parquet"
    if not _KEY.match(key):
        raise ValueError(f"not a valid published key: {key!r}")
    return key


class ObjectStore(Protocol):
    def put(self, local: Path, key: str) -> None: ...

    def local_path(self, key: str) -> str:
        """A path or URL DuckDB can read."""
        ...

    def exists(self, key: str) -> bool: ...

    def duckdb(self) -> duckdb.DuckDBPyConnection:
        """A DuckDB connection able to read this store's paths."""
        ...

    def put_media(self, key: str, data: bytes, content_type: str) -> None: ...

    def get_media(self, key: str) -> bytes | None: ...


class LocalStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        if not _KEY.match(key):
            raise ValueError(f"not a valid published key: {key!r}")
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError(f"key escapes the store: {key!r}")
        return path

    def put(self, local: Path, key: str) -> None:
        dest = self._path(key)
        if dest.exists():
            raise FileExistsError(f"refusing to overwrite published file {key}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".partial")
        shutil.copyfile(local, tmp)
        tmp.replace(dest)

    def local_path(self, key: str) -> str:
        return str(self._path(key))

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def duckdb(self) -> duckdb.DuckDBPyConnection:
        import duckdb

        return duckdb.connect()

    def _media_path(self, key: str) -> Path:
        if not _MEDIA_KEY.match(key):
            raise ValueError(f"not a valid media key: {key!r}")
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError(f"key escapes the store: {key!r}")
        return path

    def put_media(self, key: str, data: bytes, content_type: str) -> None:
        dest = self._media_path(key)
        if dest.exists():
            raise FileExistsError(f"refusing to overwrite {key}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".partial")
        tmp.write_bytes(data)
        tmp.replace(dest)

    def get_media(self, key: str) -> bytes | None:
        path = self._media_path(key)
        return path.read_bytes() if path.is_file() else None


def _q(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class S3Store:
    """An S3-compatible bucket (Cloudflare R2 in production, D-048).

    `endpoint` is the bucket service URL, e.g.
    https://<account>.r2.cloudflarestorage.com. The API is given a read-only
    key; only the publishing job holds a key that can write.
    """

    def __init__(
        self,
        bucket: str,
        endpoint: str,
        key_id: str,
        secret: str,
        region: str = "auto",
        extension_dir: str = "",
    ) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
            raise ValueError(f"not a bucket name: {bucket!r}")
        url = urlparse(endpoint)
        if url.scheme not in ("https", "http") or not url.netloc or url.path not in ("", "/"):
            raise ValueError(f"endpoint must look like https://host[:port], got {endpoint!r}")
        if not key_id or not secret:
            raise ValueError("an access key id and secret are required for a bucket")
        self.bucket = bucket
        self.endpoint = f"{url.scheme}://{url.netloc}"
        self._host = url.netloc
        self._ssl = url.scheme == "https"
        self._key_id = key_id
        self._secret = secret
        self._region = region
        self._client: Any = None
        # Where the DuckDB httpfs extension was installed at build time (hosts
        # such as Render keep only the project folder between build and run).
        self._extension_dir = extension_dir

    def __repr__(self) -> str:  # never show the secret
        return f"S3Store(bucket={self.bucket!r}, endpoint={self.endpoint!r})"

    @staticmethod
    def _check(key: str) -> str:
        if not _KEY.match(key):
            raise ValueError(f"not a valid published key: {key!r}")
        return key

    def _s3(self) -> Any:
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint,
                aws_access_key_id=self._key_id,
                aws_secret_access_key=self._secret,
                region_name=self._region,
                config=Config(retries={"max_attempts": 5, "mode": "standard"}),
            )
        return self._client

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._s3().head_object(Bucket=self.bucket, Key=self._check(key))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise
        return True

    def put(self, local: Path, key: str) -> None:
        if self.exists(key):
            raise FileExistsError(f"refusing to overwrite published file {key}")
        with open(local, "rb") as fh:
            self._s3().put_object(
                Bucket=self.bucket,
                Key=self._check(key),
                Body=fh,
                ContentType="application/vnd.apache.parquet",
            )

    def local_path(self, key: str) -> str:
        return f"s3://{self.bucket}/{self._check(key)}"

    def put_media(self, key: str, data: bytes, content_type: str) -> None:
        if not _MEDIA_KEY.match(key):
            raise ValueError(f"not a valid media key: {key!r}")
        self._s3().put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get_media(self, key: str) -> bytes | None:
        from botocore.exceptions import ClientError

        if not _MEDIA_KEY.match(key):
            raise ValueError(f"not a valid media key: {key!r}")
        try:
            obj = self._s3().get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise
        return bytes(obj["Body"].read())

    def duckdb(self) -> duckdb.DuckDBPyConnection:
        import duckdb

        duck = duckdb.connect()
        if self._extension_dir:
            duck.execute(f"SET extension_directory = {_q(self._extension_dir)}")
        try:
            duck.execute("LOAD httpfs")
        except duckdb.Error:
            # Production installs the extension at build time; this is a fallback.
            duck.execute("INSTALL httpfs")
            duck.execute("LOAD httpfs")
        # DuckDB does not take parameters in CREATE SECRET; values are quoted here.
        duck.execute(
            f"CREATE TEMPORARY SECRET store (TYPE s3, KEY_ID {_q(self._key_id)}, "
            f"SECRET {_q(self._secret)}, ENDPOINT {_q(self._host)}, REGION {_q(self._region)}, "
            f"URL_STYLE 'path', USE_SSL {'true' if self._ssl else 'false'})"
        )
        return duck


def open_store(
    location: str, endpoint: str = "", key_id: str = "", secret: str = ""
) -> LocalStore | S3Store:
    """`s3://bucket` means a bucket (endpoint and keys required); anything else is a folder."""
    if location.startswith("s3://"):
        import os

        bucket = location.removeprefix("s3://").strip("/")
        return S3Store(
            bucket,
            endpoint,
            key_id,
            secret,
            extension_dir=os.environ.get("DUCKDB_EXTENSION_DIRECTORY", ""),
        )
    return LocalStore(Path(location))
