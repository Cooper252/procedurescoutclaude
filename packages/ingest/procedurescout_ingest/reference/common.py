"""Shared pieces for reference-data loaders: source acquisition with a size
cap and a checksum, header normalization, rejects, and load lineage rows in
src.reference_load / src.reference_reject."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import Connection, text

from procedurescout_core.enums import Severity

# CLAUDE.md: ask before any download over 50 MB.
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
USER_AGENT = "ProcedureScout-reference-loader/0.1"


class SourceError(RuntimeError):
    """A source could not be read, or does not look like what we expected."""


@dataclass(frozen=True, slots=True)
class SourceBlob:
    data: bytes
    sha256: str
    url: str | None = None
    path: str | None = None


def is_url(location: str) -> bool:
    return location.startswith(("https://", "http://"))


def new_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(120),
        follow_redirects=True,
    )


def acquire(
    location: str, client: httpx.Client | None = None, max_bytes: int = MAX_DOWNLOAD_BYTES
) -> SourceBlob:
    """Read a local file or download a URL, refusing anything over max_bytes."""
    if is_url(location):
        if client is None:
            raise SourceError(f"a URL was given but no HTTP client: {location}")
        buf = bytearray()
        with client.stream("GET", location) as resp:
            if resp.status_code != 200:
                raise SourceError(f"GET {location} returned HTTP {resp.status_code}")
            for chunk in resp.iter_bytes():
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    raise SourceError(
                        f"{location} is larger than {max_bytes} bytes; ask before downloading"
                    )
        data = bytes(buf)
        return SourceBlob(data, hashlib.sha256(data).hexdigest(), url=location)
    path = Path(location)
    if path.stat().st_size > max_bytes:
        raise SourceError(f"{location} is larger than {max_bytes} bytes")
    data = path.read_bytes()
    return SourceBlob(data, hashlib.sha256(data).hexdigest(), path=str(path))


def zip_members(data: bytes) -> dict[str, bytes]:
    """All regular members of a zip archive (nested folders flattened by name)."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            out: dict[str, bytes] = {}
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if info.file_size > MAX_DOWNLOAD_BYTES * 4:
                    raise SourceError(f"zip member {info.filename} is implausibly large")
                out[info.filename] = zf.read(info)
            return out
    except zipfile.BadZipFile as exc:
        raise SourceError("not a zip archive") from exc


def maybe_unzip(blob: SourceBlob, pick: Callable[[str, bytes], bool]) -> tuple[str, bytes]:
    """Return (member name, bytes) for the one member `pick` accepts, or the
    blob itself when it is not a zip."""
    if not blob.data.startswith(b"PK\x03\x04"):
        return (blob.path or blob.url or "input", blob.data)
    chosen = [(n, d) for n, d in zip_members(blob.data).items() if pick(n, d)]
    if len(chosen) != 1:
        names = [n for n, _ in chosen]
        raise SourceError(f"expected exactly one matching zip member, found {names}")
    return chosen[0]


def decode_text(data: bytes) -> str:
    """UTF-8 (with or without BOM), else Windows-1252, which CMS text files use."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")


_NON_ALNUM_SPACE = re.compile(r"[^a-z0-9 _]")
_SPACES = re.compile(r"[ _]+")


def normalize_header(name: str) -> str:
    """CMS Provider Data Catalog machine-name style: 'City/Town' -> 'citytown',
    'ZIP Code' -> 'zip_code'. Idempotent, so API keys pass through unchanged."""
    text_ = _NON_ALNUM_SPACE.sub("", name.strip().lstrip("﻿").lower())
    return _SPACES.sub("_", text_).strip("_")


def read_delimited(text_: str, delimiter: str | None = None) -> list[dict[str, str]]:
    """Read a delimited file with a header row; keys normalized, values stripped."""
    lines = text_.splitlines()
    if not lines:
        return []
    if delimiter is None:
        header = lines[0]
        delimiter = max(("|", "\t", ","), key=header.count)
    reader = csv.reader(io.StringIO(text_), delimiter=delimiter)
    rows = list(reader)
    keys = [normalize_header(h) for h in rows[0]]
    out: list[dict[str, str]] = []
    for raw in rows[1:]:
        if not any(cell.strip() for cell in raw):
            continue
        out.append({k: (raw[i].strip() if i < len(raw) else "") for i, k in enumerate(keys)})
    return out


def require_columns(rows: list[dict[str, str]], needed: Iterable[str], what: str) -> None:
    if not rows:
        raise SourceError(f"{what}: no data rows")
    missing = sorted(set(needed) - set(rows[0]))
    if missing:
        raise SourceError(f"{what}: missing expected columns {missing}; layout may have changed")


@dataclass(frozen=True, slots=True)
class Reject:
    row_ref: str
    rule: str
    message: str
    severity: Severity = Severity.ERROR


@dataclass
class LoadStats:
    rows_in: int = 0
    rows_loaded: int = 0
    rejects: list[Reject] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def reject(
        self, row_ref: str, rule: str, message: str, severity: Severity = Severity.ERROR
    ) -> None:
        self.rejects.append(Reject(row_ref, rule, message, severity))

    def count(self, key: str, by: int = 1) -> None:
        self.summary[key] = int(self.summary.get(key, 0)) + by

    @property
    def rows_rejected(self) -> int:
        return sum(1 for r in self.rejects if r.severity is Severity.ERROR)


def begin_load(
    conn: Connection,
    dataset: str,
    *,
    source_url: str | None = None,
    source_file: str | None = None,
    source_modified: date | None = None,
    sha256: str | None = None,
    nbytes: int | None = None,
    parameters: dict[str, Any] | None = None,
) -> uuid.UUID:
    value = conn.execute(
        text(
            """
            INSERT INTO src.reference_load
                (dataset, source_url, source_file, source_modified, sha256, bytes, parameters)
            VALUES (:d, :u, :f, :m, :h, :b, CAST(:p AS jsonb))
            RETURNING id
            """
        ),
        {
            "d": dataset,
            "u": source_url,
            "f": source_file,
            "m": source_modified,
            "h": sha256,
            "b": nbytes,
            "p": json.dumps(parameters or {}, sort_keys=True),
        },
    ).scalar_one()
    return uuid.UUID(str(value))


def finish_load(conn: Connection, load_id: uuid.UUID, stats: LoadStats) -> None:
    if stats.rejects:
        conn.execute(
            text(
                "INSERT INTO src.reference_reject (load_id, row_ref, severity, rule, message) "
                "VALUES (:l, :r, CAST(:s AS src.severity), :rule, :m)"
            ),
            [
                {
                    "l": load_id,
                    "r": r.row_ref,
                    "s": r.severity.value,
                    "rule": r.rule,
                    "m": r.message,
                }
                for r in stats.rejects
            ],
        )
    conn.execute(
        text(
            """
            UPDATE src.reference_load
            SET status = 'succeeded', finished_at = now(), rows_in = :i, rows_loaded = :o,
                rows_rejected = :r, summary = CAST(:s AS jsonb)
            WHERE id = :id
            """
        ),
        {
            "id": load_id,
            "i": stats.rows_in,
            "o": stats.rows_loaded,
            "r": stats.rows_rejected,
            "s": json.dumps(stats.summary, sort_keys=True, default=str),
        },
    )


def fail_load(conn: Connection, load_id: uuid.UUID, error: str) -> None:
    conn.execute(
        text(
            "UPDATE src.reference_load SET status = 'failed', finished_at = now(), error = :e "
            "WHERE id = :id"
        ),
        {"id": load_id, "e": error[:4000]},
    )


# Census state FIPS -> USPS code (50 states, DC, Puerto Rico and island areas).
STATE_FIPS: dict[str, str] = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT",
    "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL",
    "18": "IN", "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME", "24": "MD",
    "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT", "31": "NE",
    "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV",
    "55": "WI", "56": "WY", "60": "AS", "66": "GU", "69": "MP", "72": "PR", "78": "VI",
}  # fmt: skip
USPS_TO_FIPS: dict[str, str] = {v: k for k, v in STATE_FIPS.items()}

_ZIP_RE = re.compile(r"^(\d{5})(?:-?\d{4})?$")


def parse_zip5(raw: str) -> str | None:
    """'89502', '89502-1234' or '895021234' -> '89502'. Anything else -> None.
    Short numeric ZIPs (leading zeros lost in a spreadsheet) are refused, not padded."""
    m = _ZIP_RE.match(raw.strip())
    return m.group(1) if m else None
