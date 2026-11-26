"""Price files downloaded on Cooper's computer for hospitals that refuse
GitHub's computers (Cooper approved, 2026-11-26)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sqlalchemy import Connection, text

from procedurescout_core.object_store import LocalStore, home_key
from procedurescout_ingest.home_downloads import (
    looks_blocked,
    run_home_downloads,
    with_home_copies,
)
from procedurescout_ingest.price_files import Download, check_price_files
from tests.test_discovery import SITE
from tests.test_price_files import _copying, _two_hospitals

URL = f"{SITE}/mrf/valley.json"


def _only(files: dict[str, Path], calls: list[str]):  # type: ignore[no-untyped-def]
    """This test's files; other links (left by other tests) aren't reachable."""
    copy = _copying(files, calls)

    def download(url: str, dest: Path) -> Download:
        if url not in files:
            return Download(url, http_status=404, error="HTTP error")
        return copy(url, dest)

    return download


def refused(url: str, dest: Path) -> Download:
    return Download(url, http_status=403, error="HTTP error")


def test_what_counts_as_refused_to_github() -> None:
    assert looks_blocked(Download("u", http_status=403, error="HTTP error"))
    assert looks_blocked(Download("u", error="ConnectError: [Errno 104] Connection reset by peer"))
    assert not looks_blocked(Download("u", http_status=404, error="HTTP error"))  # broken link
    assert not looks_blocked(Download("u", http_status=200))


def test_refused_links_are_downloaded_at_home_and_used_by_the_load(
    conn: Connection, tmp_path: Path
) -> None:
    files = _two_hospitals(conn)
    store = LocalStore(tmp_path / "store")
    # 1. the load's own download is refused: the link is marked
    first = check_price_files(conn, "NV", refused, tmp_path / "w1", today=date(2026, 11, 6))
    assert first.summary["download_failed"] >= 1
    marked = conn.execute(
        text("SELECT count(*) FROM src.transparency_source WHERE blocked_at IS NOT NULL")
    ).scalar_one()
    assert marked >= 1
    # 2. Cooper's computer downloads it into the bucket and keeps nothing itself
    calls: list[str] = []
    work = tmp_path / "home"
    home = run_home_downloads(
        conn, store, work, _only(files, calls), free_bytes=lambda _p: 100 * 10**9
    )
    assert home.summary["downloaded"] >= 1
    assert list(work.iterdir()) == []  # deleted from the computer
    note = json.loads(store.get_home_text(home_key(URL, "json")) or "{}")
    assert note["url"] == URL and note["bytes"] > 0
    # a fresh copy isn't downloaded again
    again = run_home_downloads(
        conn, store, work, _only(files, []), free_bytes=lambda _p: 100 * 10**9
    )
    assert again.summary["fresh_copy_kept"] >= 1
    # 3. the load's own download is refused again: the home copy is used, labeled
    got = with_home_copies(refused, store)(URL, tmp_path / "f.bin")
    assert got.error is None and got.fetched_via == "home_runner"
    assert got.nbytes == note["bytes"] and got.sha256 == note["sha256"]


def test_no_download_without_room_on_the_computer(conn: Connection, tmp_path: Path) -> None:
    """Cooper: 'Need to make sure my computer has the storage space.'"""
    files = _two_hospitals(conn)
    check_price_files(conn, "NV", refused, tmp_path / "w1", today=date(2026, 11, 6))
    calls: list[str] = []
    stats = run_home_downloads(
        conn,
        LocalStore(tmp_path / "s"),
        tmp_path / "home",
        _only(files, calls),
        free_bytes=lambda _p: 5 * 10**9,  # under the 10 GB always left free
    )
    assert calls == [] and stats.summary["skipped_not_enough_space"] >= 1
