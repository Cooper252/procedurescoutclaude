"""Price files downloaded on Cooper's computer (Cooper approved, 2026-11-26).

About 40 hospitals refuse GitHub's computers (HTTP 403, or the connection is
cut) but answer a person's computer. A scheduled job on Cooper's computer (a
GitHub self-hosted runner, `.github/workflows/home-downloads.yml`) downloads
those files one at a time, puts each in the bucket next to a note about it
(`home-downloads/<hash of the link>.bin` and `.json`), and deletes it from the
computer. When the load's own download of that link fails again, it uses the
copy from the bucket, labeled as downloaded on Cooper's computer.

The computer's disk is checked before every file: a file is skipped unless at
least 10 GB would still be free afterwards (Cooper: "Need to make sure my
computer has the storage space").
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, text

from procedurescout_core.object_store import ObjectStore, home_key

from .price_files import Download, Downloader
from .reference.common import LoadStats

BLOCKED_DAYS = 60  # links refused within this many days are downloaded at home
FRESH_DAYS = 25  # a home copy younger than this isn't downloaded again
USE_DAYS = 35  # the load uses a home copy at most this old
MIN_FREE_BYTES = 10 * 10**9  # always left free on Cooper's computer

_BLOCKED_WORDS = ("reset", "ssl", "certificate", "connecterror", "remoteprotocolerror", "timeout")


def looks_blocked(d: Download) -> bool:
    """GitHub's download refused or cut off by the hospital's server (not a
    missing file: 404 stays a broken link)."""
    if d.http_status in (401, 403, 406, 429, 451):
        return True
    if d.http_status is None and d.error:
        low = d.error.lower()
        return any(w in low for w in _BLOCKED_WORDS)
    return False


def mark_blocked(conn: Connection, source_id: str) -> None:
    conn.execute(
        text("UPDATE src.transparency_source SET blocked_at = now() WHERE id = CAST(:s AS uuid)"),
        {"s": source_id},
    )


def _note(store: ObjectStore, url: str) -> dict[str, Any] | None:
    raw = store.get_home_text(home_key(url, "json"))
    if raw is None:
        return None
    note = json.loads(raw)
    return note if isinstance(note, dict) and note.get("url") == url else None


def _age(note: dict[str, Any], now: datetime) -> timedelta:
    return now - datetime.fromisoformat(str(note["fetched_at"]))


def with_home_copies(primary: Downloader, store: ObjectStore) -> Downloader:
    """GitHub first; if that fails and Cooper's computer downloaded the same link
    recently, that copy (checked against its note) is used and labeled."""

    def download(url: str, dest: Path) -> Download:
        result = primary(url, dest)
        if result.error is None:
            return result
        note = _note(store, url)
        if note is None or _age(note, datetime.now(UTC)) > timedelta(days=USE_DAYS):
            return result
        if not store.get_home_file(home_key(url, "bin"), dest):
            return result
        digest = hashlib.sha256()
        n = 0
        with dest.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
                n += len(chunk)
        if digest.hexdigest() != note.get("sha256") or n != note.get("bytes"):
            dest.unlink(missing_ok=True)
            return Download(
                url, error=f"{result.error}; the copy from Cooper's computer is damaged"
            )
        return Download(
            url,
            path=dest,
            sha256=note["sha256"],
            nbytes=n,
            http_status=int(note.get("http_status") or 200),
            final_url=note.get("final_url"),
            fetched_via="home_runner",
        )

    return download


def mark_from_recent_reports(conn: Connection) -> int:
    """Links the last runs' reports show as refused to GitHub (403 and similar,
    or the connection cut), in every state, so Cooper's computer doesn't wait
    for each state's next run to find them (2026-11-26)."""
    result = conn.execute(
        text(
            r"""
            UPDATE src.transparency_source s SET blocked_at = now()
            FROM (
                SELECT DISTINCT split_part(r.message, ' | ', 2) AS url
                FROM src.reference_reject r
                JOIN src.reference_load l ON l.id = r.load_id
                WHERE l.dataset = 'price_file_check' AND r.rule = 'download_failed'
                  AND l.started_at > now() - make_interval(days => :d)
                  AND (r.message ~ '\(status (401|403|406|429|451)\)$'
                       OR (r.message ~ '\(status None\)$' AND r.message ~*
                           '(reset|ssl|certificate|connecterror|remoteprotocolerror|timeout)'))
            ) x
            WHERE s.url = x.url AND s.blocked_at IS NULL
            """
        ),
        {"d": BLOCKED_DAYS},
    )
    return int(result.rowcount or 0)


def wanted(conn: Connection) -> list[tuple[str, str, str, int | None]]:
    """Links refused to GitHub lately: (url, hospital, state, reported size)."""
    rows = conn.execute(
        text(
            """
            SELECT s.url, f.name, f.state_code, p.content_length
            FROM src.transparency_source s
            JOIN ref.facility f ON f.id = s.facility_id
            LEFT JOIN LATERAL (
                SELECT content_length FROM src.source_probe
                WHERE source_id = s.id ORDER BY probed_at DESC, id DESC LIMIT 1
            ) p ON true
            WHERE s.active AND s.blocked_at > now() - make_interval(days => :d)
            ORDER BY p.content_length NULLS LAST, s.url
            """
        ),
        {"d": BLOCKED_DAYS},
    ).all()
    return [(str(r[0]), str(r[1]), str(r[2]), None if r[3] is None else int(r[3])) for r in rows]


def run_home_downloads(
    conn: Connection,
    store: ObjectStore,
    workdir: Path,
    downloader: Downloader,
    *,
    seconds: int | None = None,
    free_bytes: Callable[[Path], int] = lambda p: shutil.disk_usage(p).free,
) -> LoadStats:
    stats = LoadStats()
    started = time.monotonic()
    workdir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    stats.summary["marked_from_reports"] = mark_from_recent_reports(conn)
    for url, name, state, size in wanted(conn):
        stats.rows_in += 1
        if seconds is not None and time.monotonic() - started > seconds:
            stats.summary["stopped_early"] = "time limit reached; the next run continues"
            break
        note = _note(store, url)
        if note is not None and _age(note, now) < timedelta(days=FRESH_DAYS):
            stats.count("fresh_copy_kept")
            continue
        free = free_bytes(workdir)
        if free - (size or 0) < MIN_FREE_BYTES:
            stats.count("skipped_not_enough_space")
            stats.reject(
                f"{state} {name}",
                "not_enough_space",
                f"{url} | needs {(size or 0) // 10**6} MB; {free // 10**6} MB free on this "
                f"computer (keeping {MIN_FREE_BYTES // 10**9} GB free)",
            )
            continue
        dest = workdir / f"home-{hashlib.sha256(url.encode()).hexdigest()[:16]}.bin"
        try:
            d = downloader(url, dest)
            if d.error is not None or d.path is None or d.sha256 is None:
                stats.count("download_failed")
                stats.reject(
                    f"{state} {name}", "download_failed", f"{url} | {d.error} ({d.http_status})"
                )
                continue
            store.put_home_file(d.path, home_key(url, "bin"))
            store.put_home_text(
                home_key(url, "json"),
                json.dumps(
                    {
                        "url": url,
                        "fetched_at": datetime.now(UTC).isoformat(),
                        "bytes": d.nbytes,
                        "sha256": d.sha256,
                        "http_status": d.http_status,
                        "final_url": d.final_url,
                        "hospital": name,
                        "state": state,
                    }
                ),
            )
            stats.count("downloaded")
            stats.rows_loaded += 1
        finally:
            dest.unlink(missing_ok=True)  # never kept on the computer
    return stats
