"""Write PostgreSQL price rows to a compressed Parquet file, exactly.

Rows are copied out with COPY (gzip-compressed CSV in a temporary file), read
by DuckDB with fixed column types (amounts DECIMAL(38,15), which holds every
value the money parser accepts) and written as zstd Parquet sorted by code.
`verify` re-reads the file and compares row count and exact sums against the
database, so a publish fails instead of storing a changed price.

The SQL here is built only from the fixed column list below and UUIDs checked
by the caller.
"""

from __future__ import annotations

import gzip
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Connection, text

# (column, DuckDB type, SQL expression in PostgreSQL)
COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("state_code", "VARCHAR", "state_code::text"),
    ("facility_id", "VARCHAR", "facility_id::text"),
    ("dataset_version_id", "VARCHAR", "dataset_version_id::text"),
    ("price_source", "VARCHAR", "'hospital_file'"),
    ("code_system", "VARCHAR", "code_system::text"),
    ("code", "VARCHAR", "code"),
    ("other_codes", "VARCHAR", "array_to_string(other_codes, '|')"),
    ("modifiers", "VARCHAR", "array_to_string(modifiers, '|')"),
    ("setting", "VARCHAR", "setting::text"),
    ("billing_class", "VARCHAR", "billing_class::text"),
    ("description_raw", "VARCHAR", "description_raw"),
    ("drug_unit", "DECIMAL(38,15)", "drug_unit"),
    ("drug_unit_type", "VARCHAR", "drug_unit_type"),
    ("payer_name_raw", "VARCHAR", "payer_name_raw"),
    ("plan_name_raw", "VARCHAR", "plan_name_raw"),
    ("payer_id", "VARCHAR", "payer_id::text"),
    ("plan_id", "VARCHAR", "plan_id::text"),
    ("match_type", "VARCHAR", "match_type::text"),
    ("price_type", "VARCHAR", "price_type::text"),
    ("amount", "DECIMAL(38,15)", "amount"),
    ("percentage", "DECIMAL(38,15)", "percentage"),
    ("algorithm", "VARCHAR", "algorithm"),
    ("methodology", "VARCHAR", "methodology::text"),
    ("allowed_count_raw", "VARCHAR", "allowed_count_raw"),
    ("additional_notes_raw", "VARCHAR", "additional_notes_raw"),
    ("quality_flags", "VARCHAR", "array_to_string(quality_flags, '|')"),
    ("raw_row_ref", "VARCHAR", "raw_row_ref"),
)


@dataclass(frozen=True, slots=True)
class Totals:
    rows: int
    amount_sum: Decimal | None
    percentage_sum: Decimal | None


def _dec(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def db_totals(conn: Connection, dataset_version_id: uuid.UUID) -> Totals:
    row = conn.execute(
        text(
            "SELECT count(*), sum(amount), sum(percentage) FROM price.price "
            "WHERE dataset_version_id = :d"
        ),
        {"d": dataset_version_id},
    ).one()
    return Totals(int(row[0]), _dec(row[1]), _dec(row[2]))


def file_totals(path: Path) -> Totals:
    import duckdb

    with duckdb.connect() as duck:
        row = duck.execute(
            "SELECT count(*), sum(amount), sum(percentage) FROM read_parquet(?)", [str(path)]
        ).fetchone()
    assert row is not None
    return Totals(int(row[0]), _dec(row[1]), _dec(row[2]))


def write_dataset(
    conn: Connection, dataset_version_id: uuid.UUID, out: Path, workdir: Path
) -> Totals:
    """Write one dataset version's rows to `out`; returns the file's totals
    after checking they equal the database's."""
    import duckdb

    dv = uuid.UUID(str(dataset_version_id))
    workdir.mkdir(parents=True, exist_ok=True)
    csv_path = workdir / f"{dv}.csv.gz"
    select = ", ".join(expr for _, _, expr in COLUMNS)
    dbapi = conn.connection.driver_connection
    assert dbapi is not None
    with dbapi.cursor() as cur, gzip.open(csv_path, "wb", compresslevel=1) as fh:
        sql = (
            f"COPY (SELECT {select} FROM price.price WHERE dataset_version_id = '{dv}') "
            "TO STDOUT (FORMAT csv)"
        )
        with cur.copy(sql) as copy:
            for chunk in copy:
                fh.write(bytes(chunk))
    types = "{" + ", ".join(f"'{c}': '{t}'" for c, t, _ in COLUMNS) + "}"
    try:
        with duckdb.connect() as duck:
            duck.execute(
                f"COPY (SELECT * FROM read_csv('{csv_path}', header=false, columns={types}, "
                "quote='\"', escape='\"') ORDER BY code_system, code) "
                f"TO '{out}' (FORMAT parquet, COMPRESSION zstd)"
            )
    finally:
        csv_path.unlink(missing_ok=True)
    expected = db_totals(conn, dv)
    got = file_totals(out)
    if got != expected:
        out.unlink(missing_ok=True)
        raise ValueError(f"Parquet copy differs from the database: {got} vs {expected}")
    return got
