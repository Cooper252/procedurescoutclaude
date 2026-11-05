"""CMS Provider Data Catalog (data.cms.gov/provider-data) access.

Datasets (identifiers confirmed 2026-11-04 via the PDC metastore):
- xubh-q36u  Hospital General Information  (modified 2026-07-22)
- 4jcv-atw7  Ambulatory Surgical Center Quality Measures - Facility (modified 2025-12-16)

Rows come either from the datastore query API, filtered by state and paged,
or from a downloaded CSV. Both are reduced to dicts keyed by the PDC machine
names (normalize_header makes CSV titles match the API keys).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from .common import SourceError, decode_text, normalize_header, read_delimited

PDC_BASE = "https://data.cms.gov/provider-data/api/1"
HOSPITAL_GENERAL_INFORMATION = "xubh-q36u"
ASC_FACILITY = "4jcv-atw7"
PAGE_SIZE = 500


@dataclass(frozen=True, slots=True)
class PdcRows:
    rows: list[dict[str, str]]
    source_url: str
    modified: date | None
    sha256: str  # of the canonical JSON of the rows received
    nbytes: int


def _str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def dataset_modified(client: httpx.Client, dataset_id: str) -> date | None:
    resp = client.get(f"{PDC_BASE}/metastore/schemas/dataset/items/{dataset_id}")
    if resp.status_code != 200:
        raise SourceError(f"PDC metastore for {dataset_id} returned HTTP {resp.status_code}")
    modified = resp.json().get("modified")
    return date.fromisoformat(modified[:10]) if isinstance(modified, str) else None


def fetch_state_rows(client: httpx.Client, dataset_id: str, state_code: str) -> PdcRows:
    """All rows of a PDC dataset for one state, via the datastore query API.

    Fails if the number of rows received differs from the count the API reports.
    """
    url = f"{PDC_BASE}/datastore/query/{dataset_id}/0"
    rows: list[dict[str, str]] = []
    expected: int | None = None
    offset = 0
    while True:
        params: dict[str, str | int] = {
            "conditions[0][property]": "state",
            "conditions[0][value]": state_code,
            "conditions[0][operator]": "=",
            "limit": PAGE_SIZE,
            "offset": offset,
            "count": "true",
            "results": "true",
            "schema": "false",
        }
        resp = client.get(url, params=params)
        if resp.status_code != 200:
            raise SourceError(f"PDC query {dataset_id} returned HTTP {resp.status_code}")
        body = resp.json()
        if expected is None:
            expected = int(body["count"])
        page = body.get("results") or []
        rows.extend({normalize_header(k): _str(v) for k, v in r.items()} for r in page)
        offset += len(page)
        if not page or offset >= expected:
            break
    if len(rows) != expected:
        raise SourceError(f"PDC {dataset_id}: received {len(rows)} rows, API reported {expected}")
    canonical = json.dumps(rows, sort_keys=True).encode()
    return PdcRows(
        rows=rows,
        source_url=f"{url}?state={state_code}",
        modified=dataset_modified(client, dataset_id),
        sha256=hashlib.sha256(canonical).hexdigest(),
        nbytes=len(canonical),
    )


def read_csv_rows(data: bytes, state_code: str) -> list[dict[str, str]]:
    """Rows of a downloaded PDC CSV for one state."""
    rows = read_delimited(decode_text(data), ",")
    if rows and "state" not in rows[0]:
        raise SourceError("CSV has no State column; not a Provider Data Catalog file?")
    return [r for r in rows if r.get("state", "").upper() == state_code]
