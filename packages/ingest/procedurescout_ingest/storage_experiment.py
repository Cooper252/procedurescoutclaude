"""Measure cheaper ways to store prices at national scale (NAT-02, D-031).

Runs after a price load in the throwaway workflow database and reports, for
the same prices:

A. the current layout: one PostgreSQL row per amount (sizes measured);
B. a normalized PostgreSQL layout (one row per charge item holding the
   description, codes, setting; one small row per amount pointing at it; one
   row per distinct payer/plan) - *estimated* from exact counts of distinct
   items and payer/plan pairs and measured average column sizes on a sample;
C. compressed Parquet files, one per facility, sorted by code - *measured*:
   written with DuckDB from the loaded rows, total size, and the time to find
   one common code across all facilities, next to the same lookup in
   PostgreSQL.

Nothing here changes the stored prices; the Parquet files are written to a
temporary folder and deleted with it.

SQL text in this module is built only from the fixed column lists above,
facility ids read back from the database and checked as UUIDs, and paths of
our own temporary folder; no outside input reaches it (hence the S608 notes).
"""

from __future__ import annotations

import gzip
import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, text

PARQUET_COLUMNS = (
    ("facility_id", "VARCHAR"),
    ("code_system", "VARCHAR"),
    ("code", "VARCHAR"),
    ("other_codes", "VARCHAR"),
    ("description_raw", "VARCHAR"),
    ("setting", "VARCHAR"),
    ("billing_class", "VARCHAR"),
    ("modifiers", "VARCHAR"),
    ("drug_unit", "DECIMAL(38,15)"),
    ("drug_unit_type", "VARCHAR"),
    ("price_type", "VARCHAR"),
    ("payer_name_raw", "VARCHAR"),
    ("plan_name_raw", "VARCHAR"),
    ("amount", "DECIMAL(38,15)"),
    ("percentage", "DECIMAL(38,15)"),
    ("algorithm", "VARCHAR"),
    ("methodology", "VARCHAR"),
    ("allowed_count_raw", "VARCHAR"),
    ("additional_notes_raw", "VARCHAR"),
    ("quality_flags", "VARCHAR"),
    ("raw_row_ref", "VARCHAR"),
)
ITEM_COLUMNS = (
    "facility_id",
    "code_system",
    "code",
    "other_codes",
    "description_raw",
    "setting",
    "billing_class",
    "modifiers",
    "drug_unit",
    "drug_unit_type",
)
VALUE_COLUMNS = (
    "price_type",
    "amount",
    "percentage",
    "algorithm",
    "methodology",
    "allowed_count_raw",
    "additional_notes_raw",
    "quality_flags",
    "raw_row_ref",
)


def _scalar(conn: Connection, sql: str, **params: Any) -> Any:
    return conn.execute(text(sql), params).scalar()


def current_layout(conn: Connection) -> dict[str, Any]:
    return {
        "rows": int(_scalar(conn, "SELECT count(*) FROM price.price_nv")),
        "table_bytes": int(_scalar(conn, "SELECT pg_relation_size('price.price_nv')")),
        "total_bytes_with_indexes": int(
            _scalar(conn, "SELECT pg_total_relation_size('price.price_nv')")
        ),
    }


def normalized_estimate(conn: Connection, rows: int) -> dict[str, Any]:
    """Exact distinct counts; average column sizes from a ~1% sample."""
    item_key = "md5(ROW(" + ", ".join(ITEM_COLUMNS) + ")::text)"
    items = int(_scalar(conn, f"SELECT count(DISTINCT {item_key}) FROM price.price_nv"))
    pairs = int(
        _scalar(
            conn,
            "SELECT count(*) FROM (SELECT DISTINCT payer_name_raw, plan_name_raw "
            "FROM price.price_nv WHERE payer_name_raw IS NOT NULL) d",
        )
    )
    sizes = conn.execute(
        text(
            "SELECT "
            + ", ".join(
                f"avg(coalesce(pg_column_size({c}), 0))"
                for c in ITEM_COLUMNS + VALUE_COLUMNS + ("payer_name_raw", "plan_name_raw")
            )
            + " FROM price.price_nv TABLESAMPLE SYSTEM (1)"
        )
    ).one()
    # average sizes in bytes (Decimal from PostgreSQL; not money)
    avg: dict[str, Decimal] = {
        c: Decimal(v or 0)
        for c, v in zip(
            ITEM_COLUMNS + VALUE_COLUMNS + ("payer_name", "plan_name"), sizes, strict=True
        )
    }
    row_overhead = 24 + 4  # tuple header + line pointer
    item_bytes = row_overhead + 8 + sum(avg[c] for c in ITEM_COLUMNS)
    value_bytes = row_overhead + 8 + 4 + sum(avg[c] for c in VALUE_COLUMNS)
    value_no_ref = value_bytes - avg["raw_row_ref"]
    current_row = row_overhead + sum(avg.values(), Decimal(0)) + 16 + 16 + 2  # ids, state
    return {
        "distinct_items": items,
        "distinct_payer_plan_pairs": pairs,
        "avg_column_bytes_sample": {k: str(round(v, 1)) for k, v in avg.items()},
        "estimated_current_row_bytes": round(current_row),
        "estimated_item_table_bytes": round(items * item_bytes),
        "estimated_value_table_bytes": round(rows * value_bytes),
        "estimated_value_table_bytes_without_row_ref": round(rows * value_no_ref),
        "note": "estimate from exact counts and sampled column sizes; indexes not included",
    }


def _common_code(conn: Connection) -> tuple[str, str] | None:
    """A CPT/HCPCS code listed by the most facilities (a 1% sample first; the
    whole table when the sample is empty, as in small test databases)."""
    for sample in ("TABLESAMPLE SYSTEM (1)", ""):
        row = conn.execute(
            text(
                f"""
                SELECT code_system::text, code FROM price.price_nv {sample}
                WHERE code_system IN ('CPT', 'HCPCS')
                GROUP BY 1, 2 ORDER BY count(DISTINCT facility_id) DESC, count(*) DESC LIMIT 1
                """
            )
        ).first()
        if row:
            return (str(row[0]), str(row[1]))
    return None


def parquet_layout(conn: Connection, workdir: Path) -> dict[str, Any]:
    import duckdb

    workdir.mkdir(parents=True, exist_ok=True)
    facilities = [
        str(f)
        for f in conn.execute(
            text("SELECT DISTINCT facility_id FROM price.price_nv ORDER BY 1")
        ).scalars()
    ]
    select_cols = ", ".join(
        f"{c}::text"
        if c
        in ("code_system", "setting", "billing_class", "price_type", "methodology", "facility_id")
        else c
        for c, _ in PARQUET_COLUMNS
    )
    types = "{" + ", ".join(f"'{c}': '{t}'" for c, t in PARQUET_COLUMNS) + "}"
    dbapi = conn.connection.driver_connection
    assert dbapi is not None
    duck = duckdb.connect()
    total = 0
    started = time.monotonic()
    for fid in facilities:
        uuid.UUID(fid)  # only ids read back from the database, checked
        csv_path = workdir / f"{fid}.csv.gz"  # compressed: big facilities make GB of CSV
        out = workdir / f"{fid}.parquet"
        with dbapi.cursor() as cur, gzip.open(csv_path, "wb", compresslevel=1) as fh:
            sql = (
                f"COPY (SELECT {select_cols} FROM price.price_nv "
                f"WHERE facility_id = '{fid}') TO STDOUT (FORMAT csv)"
            )
            with cur.copy(sql) as copy:
                for chunk in copy:
                    fh.write(bytes(chunk))
        duck.execute(
            f"COPY (SELECT * FROM read_csv('{csv_path}', header=false, columns={types}, "
            f"quote='\"', escape='\"') ORDER BY code_system, code) "
            f"TO '{out}' (FORMAT parquet, COMPRESSION zstd)"
        )
        csv_path.unlink()
        total += out.stat().st_size
    write_seconds = round(time.monotonic() - started)
    result: dict[str, Any] = {
        "files": len(facilities),
        "total_bytes": total,
        "write_seconds": write_seconds,
    }
    # exactness check: every amount survived the round trip unchanged
    pattern = f"{workdir}/*.parquet"
    pq_row = duck.execute(
        "SELECT count(*), sum(amount), sum(percentage) FROM read_parquet(?)", [pattern]
    ).fetchone()
    pg_row = conn.execute(
        text("SELECT count(*), sum(amount), sum(percentage) FROM price.price_nv")
    ).one()

    def same(a: object, b: object) -> bool:
        if a is None or b is None:
            return a is b
        return Decimal(str(a)) == Decimal(str(b))

    result["round_trip_exact"] = bool(
        pq_row is not None
        and int(pq_row[0]) == int(pg_row[0])
        and same(pq_row[1], pg_row[1])
        and same(pq_row[2], pg_row[2])
    )
    code = _common_code(conn)
    if code:
        system, value = code
        t0 = time.monotonic()
        found = duck.execute(
            "SELECT count(*), count(DISTINCT facility_id) FROM read_parquet(?) "
            "WHERE code_system = ? AND code = ?",
            [pattern, system, value],
        ).fetchone()
        parquet_ms = round((time.monotonic() - t0) * 1000)
        t1 = time.monotonic()
        pg = conn.execute(
            text(
                "SELECT count(*), count(DISTINCT facility_id) FROM price.price_nv "
                "WHERE code_system = CAST(:s AS ref.code_system) AND code = :c"
            ),
            {"s": system, "c": value},
        ).one()
        pg_ms = round((time.monotonic() - t1) * 1000)
        result["lookup"] = {
            "code": f"{system} {value}",
            "parquet_rows_found": int(found[0]) if found else 0,
            "parquet_facilities": int(found[1]) if found else 0,
            "parquet_ms": parquet_ms,
            "postgres_rows_found": int(pg[0]),
            "postgres_facilities": int(pg[1]),
            "postgres_ms": pg_ms,
        }
    duck.close()
    return result


def run(conn: Connection, workdir: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"current": current_layout(conn)}
    if out["current"]["rows"] == 0:
        return out
    out["normalized_estimate"] = normalized_estimate(conn, out["current"]["rows"])
    out["parquet"] = parquet_layout(conn, workdir)
    return out
