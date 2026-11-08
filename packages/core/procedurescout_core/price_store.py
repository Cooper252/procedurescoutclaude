"""Read published prices from the Parquet files (D-033).

The caller passes facilities and one code; every value is checked before any
file is opened (CLAUDE.md rule 12), only the *current published* files of
those facilities are read (from price.published_file, the view the API role
can see), and amounts come back as Decimal exactly as stored.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Connection, text

from .enums import CodeSystem
from .object_store import ObjectStore

MAX_FACILITIES = 200
MAX_ROWS = 5000
_CODE = re.compile(r"^[A-Za-z0-9.\-]{1,20}$")


class PriceQueryError(ValueError):
    """A filter failed validation; no price file was read."""


@dataclass(frozen=True, slots=True)
class PublishedPrice:
    facility_id: str
    price_source: str
    code_system: str
    code: str
    description_raw: str | None
    setting: str | None
    price_type: str
    payer_name_raw: str | None
    plan_name_raw: str | None
    amount: Decimal | None
    percentage: Decimal | None
    algorithm: str | None
    methodology: str | None
    dataset_version_id: str


def find_prices(
    conn: Connection,
    store: ObjectStore,
    facility_ids: Sequence[uuid.UUID | str],
    code_system: str,
    code: str,
    limit: int = MAX_ROWS,
) -> list[PublishedPrice]:
    import duckdb

    if not facility_ids:
        raise PriceQueryError("at least one facility is required")
    if len(facility_ids) > MAX_FACILITIES:
        raise PriceQueryError(f"at most {MAX_FACILITIES} facilities per search")
    try:
        ids = sorted({str(uuid.UUID(str(f))) for f in facility_ids})
        system = CodeSystem(code_system)
    except ValueError as exc:
        raise PriceQueryError(str(exc)) from exc
    if not _CODE.match(code):
        raise PriceQueryError(f"not a code: {code!r}")
    if not 1 <= limit <= MAX_ROWS:
        raise PriceQueryError(f"limit must be between 1 and {MAX_ROWS}")
    keys = [
        str(k)
        for k in conn.execute(
            text(
                "SELECT object_key FROM price.published_file "
                "WHERE facility_id = ANY(CAST(:ids AS uuid[])) ORDER BY object_key"
            ),
            {"ids": ids},
        ).scalars()
    ]
    if not keys:
        return []
    paths = [store.local_path(k) for k in keys]
    with duckdb.connect() as duck:
        rows = duck.execute(
            """
            SELECT facility_id, price_source, code_system, code, description_raw, setting,
                   price_type, payer_name_raw, plan_name_raw, amount, percentage, algorithm,
                   methodology, dataset_version_id
            FROM read_parquet(?)
            WHERE code_system = ? AND code = ?
            ORDER BY facility_id, price_type, payer_name_raw, plan_name_raw
            LIMIT ?
            """,
            [paths, system.value, code, limit],
        ).fetchall()
    return [
        PublishedPrice(
            facility_id=r[0],
            price_source=r[1],
            code_system=r[2],
            code=r[3],
            description_raw=r[4],
            setting=r[5],
            price_type=r[6],
            payer_name_raw=r[7],
            plan_name_raw=r[8],
            amount=None if r[9] is None else Decimal(str(r[9])),
            percentage=None if r[10] is None else Decimal(str(r[10])),
            algorithm=r[11],
            methodology=r[12],
            dataset_version_id=r[13],
        )
        for r in rows
    ]


def facility_payer_plans(
    conn: Connection, store: ObjectStore, facility_id: uuid.UUID | str
) -> list[tuple[str, str]]:
    """Payer and plan names exactly as this facility publishes them (for the
    insurance picker and to validate a choice before pricing)."""
    import duckdb

    fid = str(uuid.UUID(str(facility_id)))
    keys = [
        str(k)
        for k in conn.execute(
            text(
                "SELECT object_key FROM price.published_file WHERE facility_id = CAST(:f AS uuid)"
            ),
            {"f": fid},
        ).scalars()
    ]
    if not keys:
        return []
    with duckdb.connect() as duck:
        rows = duck.execute(
            "SELECT DISTINCT payer_name_raw, plan_name_raw FROM read_parquet(?) "
            "WHERE payer_name_raw IS NOT NULL AND plan_name_raw IS NOT NULL ORDER BY 1, 2",
            [[store.local_path(k) for k in keys]],
        ).fetchall()
    return [(str(r[0]), str(r[1])) for r in rows]
