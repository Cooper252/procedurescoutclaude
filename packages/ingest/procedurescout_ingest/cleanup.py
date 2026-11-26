"""Housekeeping on the live database (Cooper approved, 2026-11-26).

The live database grew about 0.1 GB with every state run and reached 16.4 of
its 20 GB. Most of the growth is bookkeeping, not prices:
- the per-file summaries (codes, insurer names) of price files that were
  replaced by a newer file (status 'retired'); the site never reads them, and
  the code index has already taken them out of its totals;
- the notes on refused rows ("rejects") from runs more than 14 days old.

Published prices (the Parquet files the site reads), current summaries and the
record of every file are never touched. Each run deletes for at most a few
minutes, in small batches, so the hosted database is never asked for much at
once; the freed space is reused by later runs (autovacuum).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import Connection, text

REJECT_DAYS = 14
BATCH_FILES = 100
BATCH_REJECTS = 50_000


def table_sizes(conn: Connection, top: int = 8) -> list[tuple[str, int]]:
    rows = conn.execute(
        text(
            """
            SELECT n.nspname || '.' || c.relname, pg_total_relation_size(c.oid)
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r', 'p') AND n.nspname IN ('ref', 'src', 'price', 'prov')
            ORDER BY 2 DESC LIMIT :n
            """
        ),
        {"n": top},
    ).all()
    return [(str(r[0]), int(r[1])) for r in rows]


def clean_up(
    conn: Connection, *, seconds: int | None = None, commit: Callable[[], None] | None = None
) -> dict[str, Any]:
    started = time.monotonic()

    def time_up() -> bool:
        return seconds is not None and time.monotonic() - started > seconds

    out: dict[str, Any] = {"summaries_of_replaced_files": 0, "old_rejects": 0}
    while not time_up():
        ids = [
            str(r[0])
            for r in conn.execute(
                text(
                    """
                    SELECT dv.id FROM src.dataset_version dv
                    WHERE dv.status = 'retired'
                      AND NOT EXISTS (SELECT 1 FROM ref.code_index_counted c
                                      WHERE c.dataset_version_id = dv.id)
                      AND (EXISTS (SELECT 1 FROM price.file_code_summary s
                                   WHERE s.dataset_version_id = dv.id)
                           OR EXISTS (SELECT 1 FROM price.file_payer_summary s
                                      WHERE s.dataset_version_id = dv.id))
                    LIMIT :n
                    """
                ),
                {"n": BATCH_FILES},
            ).all()
        ]
        if not ids:
            break
        for sql in (
            "DELETE FROM price.file_code_summary "
            "WHERE dataset_version_id = ANY(CAST(:ids AS uuid[]))",
            "DELETE FROM price.file_payer_summary "
            "WHERE dataset_version_id = ANY(CAST(:ids AS uuid[]))",
        ):
            result = conn.execute(text(sql), {"ids": ids})
            out["summaries_of_replaced_files"] += int(result.rowcount or 0)
        if commit is not None:
            commit()
    while not time_up():
        result = conn.execute(
            text(
                """
                DELETE FROM src.reference_reject WHERE id IN (
                    SELECT r.id FROM src.reference_reject r
                    JOIN src.reference_load l ON l.id = r.load_id
                    WHERE l.started_at < now() - make_interval(days => :d)
                    LIMIT :n)
                """
            ),
            {"d": REJECT_DAYS, "n": BATCH_REJECTS},
        )
        n = int(result.rowcount or 0)
        out["old_rejects"] += n
        if commit is not None:
            commit()
        if n < BATCH_REJECTS:
            break
    out["finished"] = not time_up()
    out["largest_tables_mb"] = {name: size // 10**6 for name, size in table_sizes(conn)}
    return out
