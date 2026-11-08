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
            SELECT code_system, code,
                   mode() WITHIN GROUP (ORDER BY left(btrim(description_raw), 300))
                       FILTER (WHERE description_raw IS NOT NULL AND btrim(description_raw) <> ''),
                   count(DISTINCT facility_id), count(*)
            FROM price.published_price
            GROUP BY code_system, code
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
    return stats
