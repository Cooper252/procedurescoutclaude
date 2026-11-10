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
    stats = LoadStats()
    conn.execute(text("DELETE FROM ref.code_index"))
    result = conn.execute(
        text(
            """
            INSERT INTO ref.code_index (system, code, hospital_description, facilities, prices)
            WITH per_file AS (
                -- published datasets: from their kept summaries (rows may be removed, D-054)
                SELECT s.code_system, s.code, s.top_description, s.facility_id, s.prices
                FROM price.file_code_summary s
                JOIN src.dataset_version dv ON dv.id = s.dataset_version_id
                WHERE dv.status = 'published'
                UNION ALL
                -- published datasets without a summary (older): from their rows
                SELECT code_system, code,
                       mode() WITHIN GROUP (ORDER BY left(btrim(description_raw), 300))
                           FILTER (WHERE description_raw IS NOT NULL
                                   AND btrim(description_raw) <> ''),
                       facility_id, count(*)
                FROM price.published_price pp
                WHERE NOT EXISTS (SELECT 1 FROM price.file_code_summary s
                                  WHERE s.dataset_version_id = pp.dataset_version_id)
                GROUP BY code_system, code, facility_id
            ),
            described AS (
                SELECT code_system, code, top_description, sum(prices) AS n,
                       row_number() OVER (PARTITION BY code_system, code
                                          ORDER BY sum(prices) DESC, top_description) AS rank
                FROM per_file WHERE top_description IS NOT NULL
                GROUP BY code_system, code, top_description
            )
            SELECT f.code_system, f.code, d.top_description,
                   count(DISTINCT f.facility_id), sum(f.prices)
            FROM per_file f
            LEFT JOIN described d ON d.code_system = f.code_system AND d.code = f.code
                                 AND d.rank = 1
            GROUP BY f.code_system, f.code, d.top_description
            """
        )
    )
    stats.rows_loaded = result.rowcount or 0
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
    for key, (raw, facilities, prices, _) in merged.items():
        conn.execute(
            text(
                "INSERT INTO ref.payer_index (raw_normalized, raw_text, facilities, prices) "
                "VALUES (:k, :r, :f, :p)"
            ),
            {"k": key, "r": raw, "f": facilities, "p": prices},
        )
    return len(merged)
