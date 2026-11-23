"""Index of every billing code in published hospital prices (D-045).

For each code: the description hospitals most often publish for it, how many
places and prices use it. Codes not yet in ref.code are added by number only
(version 'published', no descriptor), so a search by that code is validated
against a lookup table like every other filter (rule 12). CPT descriptor text
is never stored in ref.code (rule 11); the hospitals' own wording lives in
ref.code_index and is shown labeled as theirs.
"""

from __future__ import annotations

from sqlalchemy import Connection, text

from .reference.common import LoadStats


def rebuild_code_index(conn: Connection) -> LoadStats:
    """(2026-11-23) The per-file summaries are read as one stream and added up
    here, not sorted by the database: with every state loaded the old single
    query sorted tens of millions of summary rows on the hosted database's disk,
    filled it ("could not write to file pg_wal/...: No space left on device"),
    and the database restarted, taking the site down every time a state
    finished. A facility has one published dataset at a time (publishing
    retires the previous one), so its rows add one place per code."""
    stats = LoadStats()
    places: dict[tuple[str, str], int] = {}
    prices: dict[tuple[str, str], int] = {}
    wording: dict[tuple[str, str], dict[str, int]] = {}

    def add(system: str, code: str, desc: str | None, n: int) -> None:
        key = (system, code)
        places[key] = places.get(key, 0) + 1
        prices[key] = prices.get(key, 0) + n
        if desc is not None:
            d = wording.setdefault(key, {})
            d[desc] = d.get(desc, 0) + n

    raw = conn.connection.driver_connection
    assert raw is not None
    with (
        raw.cursor() as cur,
        cur.copy(
            """
        COPY (
            SELECT s.code_system::text, s.code, s.top_description, s.prices
            FROM price.file_code_summary s
            JOIN src.dataset_version dv ON dv.id = s.dataset_version_id
            WHERE dv.status = 'published'
        ) TO STDOUT
        """
        ) as cp,
    ):
        for system, code, desc, n in cp.rows():
            add(str(system), str(code), None if desc is None else str(desc), int(str(n)))
    # published datasets without a summary (older): from their rows (few or none)
    for system, code, desc, n in conn.execute(
        text(
            """
            SELECT code_system::text, code,
                   mode() WITHIN GROUP (ORDER BY left(btrim(description_raw), 300))
                       FILTER (WHERE description_raw IS NOT NULL
                               AND btrim(description_raw) <> ''),
                   count(*)
            FROM price.published_price pp
            WHERE NOT EXISTS (SELECT 1 FROM price.file_code_summary s
                              WHERE s.dataset_version_id = pp.dataset_version_id)
            GROUP BY code_system, code, facility_id
            """
        )
    ).all():
        add(str(system), str(code), None if desc is None else str(desc), int(n))
    conn.execute(text("DELETE FROM ref.code_index"))
    with (
        raw.cursor() as cur,
        cur.copy(
            "COPY ref.code_index (system, code, hospital_description, facilities, prices) "
            "FROM STDIN"
        ) as cp,
    ):
        for key, n_places in places.items():
            descs = wording.get(key)
            # the wording with the most prices; ties: the alphabetically first
            top = min(descs.items(), key=lambda kv: (-kv[1], kv[0]))[0] if descs else None
            cp.write_row((key[0], key[1], top, n_places, prices[key]))
    stats.rows_loaded = len(places)
    stats.rows_in = stats.rows_loaded
    added = conn.execute(
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
    stats.summary["codes_added_to_lookup"] = added.rowcount or 0
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
