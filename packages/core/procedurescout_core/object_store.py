"""Where published Parquet files live (D-033).

Only a local-folder store exists so far: it is what tests and the throwaway
workflow use. An S3-compatible store (e.g. Cloudflare R2) will implement the
same three methods once hosting is chosen and approved; nothing paid is set up
here.

Keys look like `published/NV/<facility_id>/<dataset_version_id>.parquet`.
"""

from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path
from typing import Protocol

_KEY = re.compile(r"^published/[A-Z]{2}/[0-9a-f-]{36}/[0-9a-f-]{36}\.parquet$")


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
