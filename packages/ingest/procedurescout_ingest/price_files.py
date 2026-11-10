"""Phase 2, step 2a: download each price file of one state, check what is inside, delete it.

No prices are loaded yet. For every price file assigned to one of our
facilities this module:

1. picks one file per facility (when a facility has several links, the one
   whose server reports the newest Last-Modified date, decided by Cooper on
   2026-11-06; the others are reported, not read);
2. streams it to a temporary file while computing its SHA-256 (a size limit
   stops runaway downloads);
3. works out the format from the bytes (JSON, CMS CSV tall or wide, ZIP) and
   reads it once, in bounded memory, to record the header exactly as
   published (hospital name, last_updated_on, version, attestation) and
   counts (charge items, payer names, code types, settings);
4. stores the result in src.transparency_file (object_store_key NULL: the file
   is not kept) and deletes the temporary file.

Dates are taken as published; a last_updated_on older than a year is flagged
because CMS requires an annual update. Nothing is rounded or converted;
numbers are read as Decimal and only counted.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import time
import zipfile
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import IO, Any, cast

import httpx
import ijson  # type: ignore[import-untyped]
from sqlalchemy import Connection, text

from procedurescout_core.enums import FileFormat, Severity

from .discovery import RATE_LIMIT_WAITS, RETRY_STATUSES
from .reference.common import LoadStats

DEFAULT_MAX_BYTES = 4 * 1024 * 1024 * 1024  # 4 GiB; Cooper approved ~5 GB in total
CHUNK = 1024 * 1024
MAX_PAYER_NAMES = 2000
MAX_TEXT = 2000
STALE_DAYS = 365
csv.field_size_limit(16 * 1024 * 1024)


# ------------------------------------------------------------------ download
@dataclass(frozen=True, slots=True)
class Download:
    url: str
    path: Path | None = None
    sha256: str | None = None
    nbytes: int | None = None
    http_status: int | None = None
    final_url: str | None = None
    content_type: str | None = None
    last_modified: str | None = None
    error: str | None = None
    fetched_via: str = "github"  # or "home_runner": downloaded on Cooper's computer


Downloader = Callable[[str, Path], Download]


def http_downloader(
    client: httpx.Client,
    max_bytes: int = DEFAULT_MAX_BYTES,
    sleep: Callable[[int], None] = time.sleep,
) -> Downloader:
    """Plain GET, streamed to `dest`. One retry after a 429/502/503/504 or a
    dropped connection; any other refusal (403, 404, ...) is recorded as it is."""

    def once(url: str, dest: Path) -> Download:
        digest = hashlib.sha256()
        n = 0
        try:
            with client.stream("GET", url) as resp:
                base = {
                    "url": url,
                    "http_status": resp.status_code,
                    "final_url": str(resp.url),
                    "content_type": resp.headers.get("content-type"),
                    "last_modified": resp.headers.get("last-modified"),
                }
                if resp.status_code != 200:
                    return Download(**base, error="HTTP error")
                with dest.open("wb") as out:
                    for chunk in resp.iter_bytes(CHUNK):
                        n += len(chunk)
                        if n > max_bytes:
                            out.close()
                            dest.unlink(missing_ok=True)
                            return Download(
                                **base, error=f"larger than the {max_bytes} byte limit; stopped"
                            )
                        digest.update(chunk)
                        out.write(chunk)
        except httpx.HTTPError as exc:
            dest.unlink(missing_ok=True)
            return Download(url, error=f"{type(exc).__name__}: {exc}")
        return Download(**base, path=dest, sha256=digest.hexdigest(), nbytes=n)

    def download(url: str, dest: Path) -> Download:
        result = once(url, dest)
        dropped = result.http_status is None and result.error is not None
        if result.http_status in RETRY_STATUSES or dropped:
            sleep(RATE_LIMIT_WAITS[0])
            result = once(url, dest)
        return result

    return download


def load_home_price_files(base_dir: Path) -> dict[str, Download]:
    """Price files downloaded live on Cooper's computer earlier in the same run
    (scripts/fetch_prices_home.ps1), keyed by URL. Used only when GitHub's own
    download of that URL fails."""
    index = base_dir / "prices.json"
    if not index.is_file():
        return {}
    records = json.loads(index.read_text(encoding="utf-8-sig"))
    if isinstance(records, dict):  # PowerShell writes one object for one record
        records = [records]
    out: dict[str, Download] = {}
    for rec in records:
        url = str(rec.get("url") or "")
        if not url.startswith(("https://", "http://")):
            continue
        status = rec.get("http_status")
        http_status = int(status) if isinstance(status, int) else None
        final_url = str(rec["final_url"]) if rec.get("final_url") else None
        name = rec.get("file")
        path = base_dir / str(name) if name else None
        if rec.get("error") or path is None or path.parent != base_dir or not path.is_file():
            out[url] = Download(
                url,
                http_status=http_status,
                final_url=final_url,
                error=str(rec.get("error") or "file missing"),
                fetched_via="home_runner",
            )
            continue
        digest = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(CHUNK), b""):
                digest.update(chunk)
        out[url] = Download(
            url,
            path=path,
            sha256=digest.hexdigest(),
            nbytes=path.stat().st_size,
            http_status=http_status,
            final_url=final_url,
            fetched_via="home_runner",
        )
    return out


def with_home_fallback(primary: Downloader, home: dict[str, Download]) -> Downloader:
    """Try GitHub first; if that fails and Cooper's computer has the same URL,
    use that live download instead and say so in the error-free result."""

    def download(url: str, dest: Path) -> Download:
        result = primary(url, dest)
        if result.error is None:
            return result
        alt = home.get(url)
        if alt is None:
            return result
        if alt.error is not None:
            return Download(
                url,
                http_status=result.http_status,
                error=f"{result.error}; from Cooper's computer: {alt.error} "
                f"(status {alt.http_status})",
            )
        return alt

    return download


# ------------------------------------------------------------------ reading
@dataclass(slots=True)
class FileCheck:
    format: FileFormat = FileFormat.UNKNOWN
    header: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    inner_name: str | None = None

    def get(self, *names: str) -> str | None:
        """First header value whose key matches one of `names` (case and
        surrounding spaces ignored)."""
        wanted = {n.casefold() for n in names}
        for key, value in self.header.items():
            if key.strip().casefold() in wanted and value not in (None, ""):
                return str(value)
        return None

    @property
    def version(self) -> str | None:
        return self.get("version")

    @property
    def last_updated_raw(self) -> str | None:
        return self.get("last_updated_on")

    @property
    def attester_name(self) -> str | None:
        return self.get("attester_name", "attestation.attester_name")

    @property
    def attestation_text(self) -> str | None:
        found = self.get("attestation.attestation", "affirmation.affirmation")
        if found:
            return found
        for key in self.header:
            if key.strip().casefold().startswith("to the best of its knowledge"):
                return key.strip()
        return None


def _clip(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_TEXT:
        return value[:MAX_TEXT] + "…"
    return value


def sniff(path: Path) -> str:
    """'json', 'zip', 'xlsx' or 'text', from the first bytes."""
    with path.open("rb") as f:
        head = f.read(4096)
    if head.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
        except zipfile.BadZipFile:
            return "text"
        return "xlsx" if any(n.startswith("xl/") for n in names) else "zip"
    stripped = head.lstrip(b"\xef\xbb\xbf \t\r\n")
    if stripped[:1] in (b"{", b"["):
        return "json"
    return "text"


class _Payers:
    def __init__(self) -> None:
        self.names: set[str] = set()
        self.capped = False

    def add(self, name: object) -> None:
        if not isinstance(name, str) or not name.strip():
            return
        if len(self.names) < MAX_PAYER_NAMES:
            self.names.add(name.strip())
        elif name.strip() not in self.names:
            self.capped = True

    def summary(self) -> dict[str, Any]:
        return {
            "payer_names_distinct": len(self.names),
            "payer_names_capped": self.capped,
            "payer_names": sorted(self.names)[:200],
        }


BIG_JSON_ARRAYS = frozenset({"standard_charge_information", "modifier_information"})
SCI = "standard_charge_information.item"
SC = SCI + ".standard_charges.item"
PI = SC + ".payers_information.item"


def read_json(stream: IO[bytes]) -> FileCheck:
    """CMS JSON (v2.x or v3.0), read as a stream of events."""
    check = FileCheck(format=FileFormat.JSON)
    items = charges = payer_rows = modifiers = gross = cash = 0
    code_types: Counter[str] = Counter()
    settings: Counter[str] = Counter()
    methodologies: Counter[str] = Counter()
    payers = _Payers()
    header = check.header
    try:
        for prefix, event, value in ijson.parse(stream, use_float=False):
            if event == "start_map":
                if prefix == SCI:
                    items += 1
                elif prefix == SC:
                    charges += 1
                elif prefix == PI:
                    payer_rows += 1
                elif prefix == "modifier_information.item":
                    modifiers += 1
                continue
            if event in ("start_array", "end_array", "end_map", "map_key"):
                continue
            # scalar events
            if prefix == SCI + ".code_information.item.type":
                code_types[str(value)] += 1
            elif prefix == PI + ".payer_name":
                payers.add(value)
            elif prefix == PI + ".methodology":
                methodologies[str(value)] += 1
            elif prefix == SC + ".setting":
                settings[str(value)] += 1
            elif prefix == SC + ".gross_charge":
                gross += 1
            elif prefix == SC + ".discounted_cash":
                cash += 1
            else:
                top = prefix.split(".", 1)[0]
                if top in BIG_JSON_ARRAYS or prefix.count(".") > 2:
                    continue
                key = prefix.replace(".item", "")
                val = _clip(str(value) if value is not None else None)
                if prefix.endswith(".item"):
                    existing = header.setdefault(key, [])
                    if isinstance(existing, list) and len(existing) < 50:
                        existing.append(val)
                else:
                    header[key] = val
    except ijson.JSONError as exc:
        check.problems.append(f"not valid JSON: {exc}")
    check.summary.update(
        {
            "charge_items": items,
            "standard_charges": charges,
            "payer_rows": payer_rows,
            "modifier_items": modifiers,
            "gross_charges": gross,
            "discounted_cash": cash,
            "code_types": dict(code_types.most_common(30)),
            "settings": dict(settings),
            "methodologies": dict(methodologies),
            **payers.summary(),
        }
    )
    return check


def _text_lines(stream: IO[bytes]) -> Iterator[str]:
    wrapper = io.TextIOWrapper(
        cast(io.BufferedReader, stream), encoding="utf-8-sig", errors="replace", newline=""
    )
    yield from wrapper


def read_csv(stream: IO[bytes]) -> FileCheck:
    """CMS CSV template: row 1 header labels, row 2 their values, row 3 the
    column names, then one row per charge. Tall = one row per payer/plan
    (payer_name column); wide = payer and plan inside column names
    (standard_charge|payer|plan|...)."""
    check = FileCheck()
    reader = csv.reader(_text_lines(stream))
    try:
        labels = next(reader)
        values = next(reader)
        columns = next(reader)
    except StopIteration:
        check.problems.append("fewer than three rows: not the CMS CSV template")
        return check
    except csv.Error as exc:
        check.problems.append(f"not readable as CSV: {exc}")
        return check
    for i, label in enumerate(labels):
        if label.strip():
            check.header[label.strip()] = _clip(values[i].strip() if i < len(values) else None)
    cols = [re.sub(r"\s*\|\s*", "|", c.strip()).casefold() for c in columns]
    payers = _Payers()
    wide_payer_cols = [
        c
        for c in columns
        if c.count("|") >= 3 and c.strip().casefold().startswith("standard_charge")
    ]
    if "payer_name" in cols:
        check.format = FileFormat.CSV_TALL
    elif wide_payer_cols:
        check.format = FileFormat.CSV_WIDE
        first_seen: dict[str, str] = {}
        for c in wide_payer_cols:
            label = c.split("|")[1].strip()
            first_seen.setdefault(" ".join(label.split()).casefold(), label)
        for label in first_seen.values():
            payers.add(label)
    else:
        check.problems.append(
            "column row has neither payer_name nor standard_charge|payer|... columns"
        )
    idx = {c: i for i, c in enumerate(cols)}
    payer_i = idx.get("payer_name")
    setting_i = idx.get("setting")
    gross_i = idx.get("standard_charge|gross")
    cash_i = idx.get("standard_charge|discounted_cash")
    type_is = [i for c, i in idx.items() if c.startswith("code|") and c.endswith("|type")]
    rows = ragged = replaced = gross = cash = 0
    code_types: Counter[str] = Counter()
    settings: Counter[str] = Counter()
    width = len(columns)
    try:
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            rows += 1
            if len(row) != width:
                ragged += 1
            if any("�" in cell for cell in row):
                replaced += 1
            if payer_i is not None and payer_i < len(row):
                payers.add(row[payer_i])
            if setting_i is not None and setting_i < len(row) and row[setting_i]:
                settings[row[setting_i]] += 1
            if gross_i is not None and gross_i < len(row) and row[gross_i].strip():
                gross += 1
            if cash_i is not None and cash_i < len(row) and row[cash_i].strip():
                cash += 1
            for ti in type_is:
                if ti < len(row) and row[ti].strip():
                    code_types[row[ti].strip()] += 1
    except csv.Error as exc:
        check.problems.append(f"CSV error after {rows} rows: {exc}")
    if ragged:
        check.problems.append(f"{ragged} rows have a different number of columns than the header")
    if replaced:
        check.problems.append(f"{replaced} rows contain bytes that are not valid UTF-8")
    check.summary.update(
        {
            "rows": rows,
            "columns": width,
            "gross_charges": gross,
            "discounted_cash": cash,
            "code_types": dict(code_types.most_common(30)),
            "settings": dict(settings),
            **payers.summary(),
        }
    )
    return check


def read_file(path: Path) -> FileCheck:
    kind = sniff(path)
    if kind == "json":
        with path.open("rb") as f:
            return read_json(f)
    if kind == "text":
        with path.open("rb") as f:
            return read_csv(f)
    if kind == "xlsx":
        return FileCheck(problems=["Excel workbook: not a CMS machine-readable format"])
    with zipfile.ZipFile(path) as z:
        members = [
            m
            for m in z.infolist()
            if not m.is_dir() and m.filename.lower().endswith((".json", ".csv"))
        ]
        if not members:
            names = ", ".join(z.namelist()[:10])
            return FileCheck(format=FileFormat.ZIP, problems=[f"ZIP has no JSON/CSV: {names}"])
        member = max(members, key=lambda m: m.file_size)
        with z.open(member) as inner:
            check = (
                read_json(inner) if member.filename.lower().endswith(".json") else read_csv(inner)
            )
        check.inner_name = member.filename
        if len(members) > 1:
            check.problems.append(
                f"ZIP has {len(members)} JSON/CSV files; read the largest ({member.filename})"
            )
        check.summary["zip_member"] = member.filename
        return check


@contextmanager
def open_payload(path: Path, check: FileCheck) -> Iterator[IO[bytes]]:
    """The bytes the check read: the file itself, or the ZIP member it chose."""
    if check.inner_name is None:
        with path.open("rb") as f:
            yield f
        return
    with zipfile.ZipFile(path) as z, z.open(check.inner_name) as inner:
        yield inner


LOADABLE = frozenset({FileFormat.JSON, FileFormat.CSV_TALL, FileFormat.CSV_WIDE})
DEFAULT_MIN_FREE_BYTES = 4 * 1024 * 1024 * 1024


def parse_published_date(raw: str | None) -> date | None:
    if not raw:
        return None
    value = raw.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(value, fmt).date()  # noqa: DTZ007 (a calendar date)
        except ValueError:
            continue
    return None


def _server_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ the run
@dataclass(frozen=True, slots=True)
class Candidate:
    source_id: str
    url: str
    facility_id: str
    ccn: str | None  # providers outside the CMS lists may have none
    name: str
    reported_bytes: int | None
    last_modified: str | None


def candidates(conn: Connection, state_code: str) -> list[Candidate]:
    rows = conn.execute(
        text(
            """
            SELECT s.id, s.url, f.id, f.ccn, f.name, p.content_length, p.last_modified
            FROM src.transparency_source s
            JOIN ref.facility f ON f.id = s.facility_id
            LEFT JOIN LATERAL (
                SELECT content_length, last_modified FROM src.source_probe
                WHERE source_id = s.id ORDER BY probed_at DESC, id DESC LIMIT 1
            ) p ON true
            WHERE s.active AND f.state_code = :s
            ORDER BY f.ccn, s.url
            """
        ),
        {"s": state_code},
    ).all()
    return [Candidate(str(r[0]), r[1], str(r[2]), r[3], r[4], r[5], r[6]) for r in rows]


def choose_per_facility(
    cands: list[Candidate],
) -> tuple[list[Candidate], list[tuple[Candidate, Candidate]]]:
    """One file per facility: the newest server Last-Modified wins. If any of a
    facility's links has no usable date, all its links are kept (no guessing).
    Returns (chosen, [(skipped, winner)])."""
    by_fac: dict[str, list[Candidate]] = {}
    for c in cands:
        by_fac.setdefault(c.facility_id, []).append(c)
    chosen: list[Candidate] = []
    skipped: list[tuple[Candidate, Candidate]] = []
    for group in by_fac.values():
        dated: list[tuple[datetime, Candidate]] = []
        for c in group:
            when = _server_date(c.last_modified)
            if when is not None:
                dated.append((when, c))
        if len(group) == 1 or len(dated) < len(group):
            chosen.extend(group)
            continue
        winner = max(dated, key=lambda dc: dc[0])[1]
        chosen.append(winner)
        skipped.extend((c, winner) for c in group if c is not winner)
    # small files first, unknown sizes last, so one slow giant cannot starve the rest
    chosen.sort(key=lambda c: (c.reported_bytes is None, c.reported_bytes or 0, c.ccn or ""))
    return chosen, skipped


def check_price_files(
    conn: Connection,
    state_code: str,
    downloader: Downloader,
    workdir: Path,
    today: date | None = None,
    load: bool = False,
    min_free_bytes: int = DEFAULT_MIN_FREE_BYTES,
    skip_unchanged: bool = True,
    after_load: Callable[[Connection, str], None] | None = None,
    max_files: int | None = None,
    stop_at_ns: int | None = None,
) -> LoadStats:
    """Download, check and delete each file; with `load`, also read its prices
    into a staged dataset (price_load) before deleting it.

    National refreshes (D-048): a file whose server date and size match the
    last file we read from that link, for a facility whose prices are already
    published, is not downloaded again; a downloaded file whose SHA-256 equals
    the last one read is not loaded again.

    `after_load(conn, facility_id)` runs after each file's prices are staged:
    the production run publishes and removes the staged rows right away, so
    the database never holds a whole state's prices at once (D-054).

    `max_files` stops after that many downloads (the all-states test run);
    `stop_at_ns` (a time.monotonic_ns() value) stops cleanly before a time limit such
    as GitHub's 6 hours, so finished files stay saved and the next run carries
    on from there (published, unchanged files are skipped)."""
    stats = LoadStats()
    today = today or datetime.now().astimezone().date()
    chosen, skipped = choose_per_facility(candidates(conn, state_code))
    for old, winner in skipped:
        stats.count("older_duplicate_skipped")
        stats.reject(
            f"ccn:{old.ccn}",
            "older_link_skipped",
            f"{old.url} (server date {old.last_modified}) skipped; using {winner.url} "
            f"(server date {winner.last_modified})",
            Severity.INFO,
        )
    workdir.mkdir(parents=True, exist_ok=True)
    total = 0
    downloads = 0
    for c in chosen:
        if stop_at_ns is not None and time.monotonic_ns() >= stop_at_ns:
            stats.count("stopped_for_time")
            stats.summary["stopped_early"] = "time limit reached; run again to continue"
            break
        if max_files is not None and downloads >= max_files:
            stats.summary["stopped_early"] = f"file limit {max_files} reached"
            break
        stats.rows_in += 1
        who = f"ccn:{c.ccn}"
        last = (
            conn.execute(
                text(
                    """
                    SELECT t.server_last_modified, t.bytes, t.sha256,
                           EXISTS (SELECT 1 FROM price.published_file p
                                   WHERE p.facility_id = CAST(:f AS uuid))
                    FROM src.transparency_file t WHERE t.source_id = CAST(:s AS uuid)
                    ORDER BY t.downloaded_at DESC LIMIT 1
                    """
                ),
                {"s": c.source_id, "f": c.facility_id},
            ).first()
            if skip_unchanged
            else None
        )
        if (
            last is not None
            and last[3]
            and c.last_modified
            and c.reported_bytes is not None
            and last[0] == c.last_modified
            and last[1] == c.reported_bytes
        ):
            stats.count("unchanged_skipped")
            continue
        dest = workdir / f"price-file-{c.ccn}-{c.source_id[:8]}"
        downloads += 1
        started = time.monotonic()
        d = downloader(c.url, dest)
        try:
            if d.error is not None or d.path is None or d.sha256 is None or d.nbytes is None:
                stats.count("download_failed")
                stats.reject(
                    who,
                    "download_failed",
                    f"{c.name} | {c.url} | {d.error} (status {d.http_status})",
                    Severity.WARNING,
                )
                continue
            try:
                check = read_file(d.path)
            except (OSError, zipfile.BadZipFile, UnicodeError, ValueError) as exc:
                check = FileCheck(problems=[f"could not read: {type(exc).__name__}: {exc}"])
            seconds = round(time.monotonic() - started)
            total += d.nbytes
            file_id = _record(conn, c, d, check, today, stats, seconds)
            if load and last is not None and last[3] and last[2] == d.sha256:
                stats.count("same_content_not_reloaded")
                continue
            if load:
                _load(conn, c, d.path, check, file_id, state_code, stats, min_free_bytes, workdir)
                if after_load is not None:
                    after_load(conn, c.facility_id)
        finally:
            dest.unlink(missing_ok=True)
            if d.path is not None:
                d.path.unlink(missing_ok=True)
    stats.summary["bytes_downloaded"] = total
    stats.summary["files_chosen"] = len(chosen)
    if load:
        # every state's partition (Nevada has its own; other states use the default)
        sizes = conn.execute(
            text(
                "SELECT coalesce(sum(pg_total_relation_size(relid)), 0), "
                "coalesce(sum(pg_relation_size(relid)), 0), pg_database_size(current_database()) "
                "FROM pg_partition_tree('price.price') WHERE isleaf"
            )
        ).one()
        stats.summary["price_total_bytes"] = int(sizes[0])
        stats.summary["price_table_bytes"] = int(sizes[1])
        stats.summary["database_bytes"] = int(sizes[2])
    return stats


def _load(
    conn: Connection,
    c: Candidate,
    path: Path,
    check: FileCheck,
    file_id: str,
    state_code: str,
    stats: LoadStats,
    min_free_bytes: int,
    workdir: Path,
) -> None:
    from . import price_load, price_parser

    who = f"ccn:{c.ccn}"
    if check.format not in LOADABLE:
        stats.count("load_skipped_format")
        return
    free = shutil.disk_usage(workdir).free
    if free < min_free_bytes:
        stats.count("load_skipped_low_disk")
        stats.reject(
            who,
            "load_skipped_low_disk",
            f"{c.name} | only {free} bytes free; prices not loaded",
            Severity.WARNING,
        )
        return
    started = time.monotonic()
    savepoint = conn.begin_nested()
    try:
        with open_payload(path, check) as payload:
            result = price_load.load_prices(
                conn,
                file_id=file_id,
                facility_id=c.facility_id,
                state_code=state_code,
                records=price_parser.parse(payload, check.format),
            )
    except Exception as exc:  # one bad file must not stop the others
        savepoint.rollback()
        stats.count("load_failed")
        stats.reject(
            who, "load_failed", f"{c.name} | {type(exc).__name__}: {exc}"[:2000], Severity.WARNING
        )
        return
    savepoint.commit()
    summary = result.summary()
    summary["seconds"] = round(time.monotonic() - started)
    conn.execute(
        text(
            "UPDATE src.transparency_file SET read_summary = read_summary || "
            "jsonb_build_object('load', CAST(:s AS jsonb)) WHERE id = :f"
        ),
        {"s": json.dumps(summary), "f": file_id},
    )
    stats.count("files_loaded")
    stats.count("price_rows_loaded", result.rows_loaded)
    stats.count("price_rows_rejected", result.rows_rejected)
    stats.reject(
        who,
        "prices_loaded",
        f"{c.name} | {result.rows_loaded} prices staged | {result.rows_rejected} refused "
        f"{dict(result.rejects_by_rule)} | {summary['seconds']}s",
        Severity.INFO,
    )
    for ex in result.examples:
        stats.reject(
            who, f"price_{ex.rule}", f"{ex.raw_row_ref}: {ex.message}"[:500], Severity.INFO
        )


def _record(
    conn: Connection,
    c: Candidate,
    d: Download,
    check: FileCheck,
    today: date,
    stats: LoadStats,
    seconds: int,
) -> str:
    who = f"ccn:{c.ccn}"
    problems = list(check.problems)
    version = check.version
    if version is None:
        problems.append("no version in the header")
    elif not version.strip().startswith(("2.", "3.")):
        problems.append(f"version {version!r} is not a CMS 2.x/3.x template")
    raw_date = check.last_updated_raw
    published = parse_published_date(raw_date)
    if raw_date is None:
        problems.append("no last_updated_on in the header")
    elif published is None:
        problems.append(f"last_updated_on {raw_date!r} is not a date")
    elif (today - published).days > STALE_DAYS:
        problems.append(f"last_updated_on {published} is more than a year old")
    summary = dict(check.summary)
    summary["seconds"] = seconds
    summary["problems"] = problems
    file_id = conn.execute(
        text(
            """
            INSERT INTO src.transparency_file
                (source_id, sha256, bytes, http_status, reported_last_updated, schema_version,
                 format, object_store_key, attester_name, attestation_text, final_url,
                 content_type, server_last_modified, last_updated_raw, header, read_summary,
                 read_error, fetched_via)
            VALUES (:s, :sha, :b, :st, :rlu, :v, CAST(:fmt AS src.file_format), NULL, :an,
                    :at, :fu, :ct, :lm, :lur, CAST(:h AS jsonb), CAST(:rs AS jsonb), :err, :via)
            ON CONFLICT (source_id, sha256) DO UPDATE SET downloaded_at = now(),
                read_summary = EXCLUDED.read_summary, read_error = EXCLUDED.read_error
            RETURNING id
            """
        ),
        {
            "s": c.source_id,
            "sha": d.sha256,
            "b": d.nbytes,
            "st": d.http_status,
            "rlu": published,
            "v": version,
            "fmt": check.format.value,
            "an": check.attester_name,
            "at": check.attestation_text,
            "fu": d.final_url,
            "ct": d.content_type,
            "lm": d.last_modified,
            "lur": raw_date,
            "h": json.dumps(check.header, default=str),
            "rs": json.dumps(summary, default=str),
            "err": "; ".join(problems) or None,
            "via": d.fetched_via,
        },
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO src.file_facility (file_id, facility_id) VALUES (:f, :fac) "
            "ON CONFLICT DO NOTHING"
        ),
        {"f": file_id, "fac": c.facility_id},
    )
    stats.rows_loaded += 1
    stats.count(f"format_{check.format.value}")
    size = summary.get("rows", summary.get("charge_items"))
    line = (
        f"{c.name} | {check.format.value} | version {version} | last_updated_on {raw_date} | "
        f"{d.nbytes} bytes | {size} rows/items | "
        f"{summary.get('payer_names_distinct')} payer names | {seconds}s"
    )
    if d.fetched_via == "home_runner":
        line += " | downloaded on Cooper's computer"
    stats.reject(who, "file_read", line, Severity.INFO)
    if problems:
        stats.count("files_with_problems")
    for p in problems:
        stats.reject(who, "file_problem", f"{c.name} | {p}", Severity.WARNING)
    return str(file_id)
