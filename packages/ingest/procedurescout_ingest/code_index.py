"""Index of every billing code in published hospital prices (D-045).

For each code: the description hospitals most often publish for it, how many
places and prices use it. Codes not yet in ref.code are added by number only
(version 'published', no descriptor), so a search by that code is validated
against a lookup table like every other filter (rule 12). CPT descriptor text
is never stored in ref.code (rule 11); the hospitals' own wording lives in
ref.code_index and is shown labeled as theirs.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from sqlalchemy import Connection, text

from .reference.common import LoadStats

_FILE_ROWS = text(
    "SELECT code_system::text, code, top_description, prices "
    "FROM price.file_code_summary WHERE dataset_version_id = CAST(:d AS uuid)"
)
# a published file without a summary (published before summaries existed)
_FILE_ROWS_OLD = text(
    """
    SELECT code_system::text, code,
           mode() WITHIN GROUP (ORDER BY left(btrim(description_raw), 300))
               FILTER (WHERE description_raw IS NOT NULL AND btrim(description_raw) <> ''),
           count(*)
    FROM price.published_price WHERE dataset_version_id = CAST(:d AS uuid)
    GROUP BY code_system, code
    """
)


def _file_rows(conn: Connection, dataset_id: str) -> list[tuple[str, str, str | None, int]]:
    rows = (
        conn.execute(_FILE_ROWS, {"d": dataset_id}).all()
        or conn.execute(_FILE_ROWS_OLD, {"d": dataset_id}).all()
    )
    return [(str(r[0]), str(r[1]), None if r[2] is None else str(r[2]), int(r[3])) for r in rows]


def _apply(conn: Connection, rows: list[tuple[str, str, str | None, int]], sign: int) -> None:
    """Add (sign 1) or take away (sign -1) one file's codes in the running totals."""
    for start in range(0, len(rows), 5000):
        chunk = rows[start : start + 5000]
        params = {
            "s": [r[0] for r in chunk],
            "c": [r[1] for r in chunk],
            "d": [r[2] for r in chunk],
            "p": [r[3] for r in chunk],
        }
        if sign > 0:
            conn.execute(
                text(
                    """
                    INSERT INTO ref.code_index_next AS n
                        (system, code, hospital_description, top_prices, facilities, prices)
                    SELECT CAST(s AS ref.code_system), c, d,
                           CASE WHEN d IS NULL THEN 0 ELSE p END, 1, p
                    FROM unnest(CAST(:s AS text[]), CAST(:c AS text[]), CAST(:d AS text[]),
                                CAST(:p AS bigint[])) AS x(s, c, d, p)
                    ON CONFLICT (system, code) DO UPDATE SET
                        facilities = n.facilities + 1,
                        prices = n.prices + EXCLUDED.prices,
                        hospital_description = CASE
                            WHEN EXCLUDED.hospital_description IS NOT NULL
                             AND (n.hospital_description IS NULL
                                  OR EXCLUDED.top_prices > n.top_prices)
                            THEN EXCLUDED.hospital_description ELSE n.hospital_description END,
                        top_prices = CASE
                            WHEN EXCLUDED.hospital_description IS NOT NULL
                             AND (n.hospital_description IS NULL
                                  OR EXCLUDED.top_prices > n.top_prices)
                            THEN EXCLUDED.top_prices ELSE n.top_prices END
                    """
                ),
                params,
            )
        else:
            conn.execute(
                text(
                    """
                    UPDATE ref.code_index_next n SET facilities = n.facilities - 1,
                           prices = n.prices - x.p
                    FROM unnest(CAST(:s AS text[]), CAST(:c AS text[]), CAST(:d AS text[]),
                                CAST(:p AS bigint[])) AS x(s, c, d, p)
                    WHERE n.system = CAST(x.s AS ref.code_system) AND n.code = x.c
                    """
                ),
                params,
            )
    if sign < 0:
        conn.execute(text("DELETE FROM ref.code_index_next WHERE facilities <= 0 OR prices <= 0"))


def rebuild_code_index(
    conn: Connection,
    *,
    seconds: int | None = None,
    commit: Callable[[], None] | None = None,
) -> LoadStats:
    """Keep the code index current file by file (2026-11-23). The single query
    over every summary filled the live database's disk; reading them all as a
    stream ran past the step's 20 minutes. Each run takes away files retired
    since the last run, adds newly published ones (oldest first, for at most
    `seconds`), and copies the totals to ref.code_index once every published
    file is counted. A place has one published file at a time, so each file is
    one place for its codes. The wording shown is the one used by the file that
    published the most prices for the code (hospitals' own wording, labeled)."""
    stats = LoadStats()
    started = time.monotonic()
    retired = [
        str(r[0])
        for r in conn.execute(
            text(
                "SELECT c.dataset_version_id FROM ref.code_index_counted c "
                "LEFT JOIN src.dataset_version dv ON dv.id = c.dataset_version_id "
                "WHERE dv.status IS DISTINCT FROM 'published'"
            )
        ).all()
    ]
    for d in retired:
        rows = _file_rows(conn, d)
        if not rows:
            # its summary is gone, so it can't be taken away: count everything again
            conn.execute(text("DELETE FROM ref.code_index_next"))
            conn.execute(text("DELETE FROM ref.code_index_counted"))
            stats.count("restarted_count")
            break
        _apply(conn, rows, -1)
        conn.execute(
            text("DELETE FROM ref.code_index_counted WHERE dataset_version_id = CAST(:d AS uuid)"),
            {"d": d},
        )
        stats.count("files_taken_away")
    if commit is not None:
        commit()
    waiting = [
        str(r[0])
        for r in conn.execute(
            text(
                "SELECT dv.id FROM src.dataset_version dv WHERE dv.status = 'published' "
                "AND NOT EXISTS (SELECT 1 FROM ref.code_index_counted c "
                "WHERE c.dataset_version_id = dv.id) ORDER BY dv.published_at NULLS FIRST, dv.id"
            )
        ).all()
    ]
    added = 0
    for d in waiting:
        if seconds is not None and time.monotonic() - started > seconds:
            break
        _apply(conn, _file_rows(conn, d), 1)
        conn.execute(
            text(
                "INSERT INTO ref.code_index_counted (dataset_version_id) VALUES (CAST(:d AS uuid))"
            ),
            {"d": d},
        )
        added += 1
        if commit is not None and added % 20 == 0:
            commit()
    stats.summary["files_added"] = added
    stats.summary["files_still_to_count"] = len(waiting) - added
    if added == len(waiting):
        # every published file is counted: the totals become the index
        conn.execute(text("DELETE FROM ref.code_index"))
        result = conn.execute(
            text(
                "INSERT INTO ref.code_index (system, code, hospital_description, facilities, "
                "prices) SELECT system, code, hospital_description, facilities, prices "
                "FROM ref.code_index_next WHERE facilities > 0 AND prices > 0"
            )
        )
        stats.rows_loaded = result.rowcount or 0
        stats.summary["index_updated"] = True
    else:
        stats.rows_loaded = conn.execute(text("SELECT count(*) FROM ref.code_index")).scalar_one()
        stats.summary["index_updated"] = False
    stats.rows_in = stats.rows_loaded
    new_codes = conn.execute(
        text(
            """
            INSERT INTO ref.code (system, code, version)
            SELECT i.system, i.code, 'published' FROM ref.code_index i
            WHERE NOT EXISTS (
                SELECT 1 FROM ref.code c WHERE c.system = i.system AND c.code = i.code
            )
            ON CONFLICT DO NOTHING
            """
        )
    )
    stats.summary["codes_added_to_lookup"] = new_codes.rowcount or 0
    stats.summary["payer_spellings"] = rebuild_payer_index(conn)
    return stats


def rebuild_payer_index(conn: Connection) -> int:
    """Every insurer spelling in published prices, most common written form."""
    from procedurescout_core.matching import normalize_name

    rows = conn.execute(
        text(
            """
            SELECT payer_name_raw, count(DISTINCT facility_id), sum(n) FROM (
                SELECT s.payer_name_raw, s.facility_id, s.prices AS n
                FROM price.file_payer_summary s
                JOIN src.dataset_version dv ON dv.id = s.dataset_version_id
                WHERE dv.status = 'published'
                UNION ALL
                SELECT payer_name_raw, facility_id, 1 FROM price.published_price pp
                WHERE payer_name_raw IS NOT NULL AND btrim(payer_name_raw) <> ''
                  AND NOT EXISTS (SELECT 1 FROM price.file_payer_summary s
                                  WHERE s.dataset_version_id = pp.dataset_version_id)
            ) x
            GROUP BY payer_name_raw
            """
        )
    ).all()
    # same name in other letter case or punctuation: add up, keep the commonest form
    merged: dict[str, tuple[str, int, int, int]] = {}
    for raw, facilities, prices in rows:
        key = normalize_name(str(raw))
        f, p = int(facilities), int(prices)
        if key not in merged:
            merged[key] = (str(raw), f, p, p)
        else:
            text_, f0, total, best = merged[key]
            if p > best:
                text_, best = str(raw), p
            merged[key] = (text_, max(f0, f), total + p, best)
    conn.execute(text("DELETE FROM ref.payer_index"))
    # one statement per 5,000 spellings, not one per spelling (2026-11-23: about
    # 100,000 single inserts to the hosted database ran past the step's 20 minutes)
    items = list(merged.items())
    for start in range(0, len(items), 5000):
        chunk = items[start : start + 5000]
        conn.execute(
            text(
                "INSERT INTO ref.payer_index (raw_normalized, raw_text, facilities, prices) "
                "SELECT * FROM unnest(CAST(:k AS text[]), CAST(:r AS text[]), "
                "CAST(:f AS bigint[]), CAST(:p AS bigint[]))"
            ),
            {
                "k": [k for k, _ in chunk],
                "r": [v[0] for _, v in chunk],
                "f": [v[1] for _, v in chunk],
                "p": [v[2] for _, v in chunk],
            },
        )
    return len(merged)
