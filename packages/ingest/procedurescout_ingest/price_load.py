"""Phase 2, step 2b: load one price file's prices as a *staged* dataset.

Each load creates an import run (moved through the enforced state machine up
to `quality_review`) and a staged dataset version for the facility, then
bulk-copies the parsed prices into price.price. Nothing is published here:
staged prices are invisible to the API (price.published_price shows only
published datasets) until a person approves the quality review.

Rejected rows are counted by rule; the first few of each rule are kept as
examples (a large file can reject thousands of rows for the same reason).
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Connection, text

from procedurescout_core.enums import ImportState

from .base import ParsedPrice, RejectedRow
from .price_parser import MAX_EXAMPLES, PARSER_VERSION

STATES_TO_LOADING = (
    ImportState.QUEUED,
    ImportState.DOWNLOADING,
    ImportState.DOWNLOADED,
    ImportState.VALIDATING,
    ImportState.PARSING,
    ImportState.NORMALIZING,
    ImportState.LOADING,
)

COLUMNS = (
    "state_code",
    "dataset_version_id",
    "facility_id",
    "raw_row_ref",
    "code_system",
    "code",
    "modifiers",
    "setting",
    "billing_class",
    "description_raw",
    "drug_unit",
    "drug_unit_type",
    "payer_name_raw",
    "plan_name_raw",
    "price_type",
    "amount",
    "percentage",
    "algorithm",
    "methodology",
    "allowed_count_raw",
    "additional_notes_raw",
    "quality_flags",
    "other_codes",
)
COPY_TYPES = (
    "text",
    "uuid",
    "uuid",
    "text",
    "text",
    "text",
    "text[]",
    "text",
    "text",
    "text",
    "numeric",
    "text",
    "text",
    "text",
    "text",
    "numeric",
    "numeric",
    "text",
    "text",
    "text",
    "text",
    "text[]",
    "text[]",
)


@dataclass(slots=True)
class LoadResult:
    import_run_id: uuid.UUID
    dataset_version_id: uuid.UUID
    rows_loaded: int = 0
    rows_rejected: int = 0
    by_type: Counter[str] = field(default_factory=Counter)
    rejects_by_rule: Counter[str] = field(default_factory=Counter)
    examples: list[RejectedRow] = field(default_factory=list)
    flags: Counter[str] = field(default_factory=Counter)
    payers: set[str] = field(default_factory=set)

    def summary(self) -> dict[str, Any]:
        return {
            "import_run_id": str(self.import_run_id),
            "dataset_version_id": str(self.dataset_version_id),
            "rows_loaded": self.rows_loaded,
            "rows_rejected": self.rows_rejected,
            "by_price_type": dict(self.by_type),
            "rejects_by_rule": dict(self.rejects_by_rule),
            "quality_flags": dict(self.flags),
            "payer_plan_names": len(self.payers),
        }


def _start_run(conn: Connection, file_id: str, facility_id: str) -> tuple[uuid.UUID, uuid.UUID]:
    run_id = conn.execute(
        text(
            "INSERT INTO src.import_run (file_id, parser_version, started_at) "
            "VALUES (:f, :v, now()) RETURNING id"
        ),
        {"f": file_id, "v": PARSER_VERSION},
    ).scalar_one()
    for state in STATES_TO_LOADING:
        _move(conn, run_id, state)
    dv_id = conn.execute(
        text(
            "INSERT INTO src.dataset_version (facility_id, import_run_id) "
            "VALUES (:f, :r) RETURNING id"
        ),
        {"f": facility_id, "r": run_id},
    ).scalar_one()
    return uuid.UUID(str(run_id)), uuid.UUID(str(dv_id))


def _move(conn: Connection, run_id: object, state: ImportState) -> None:
    conn.execute(
        text("UPDATE src.import_run SET state = CAST(:s AS src.import_state) WHERE id = :r"),
        {"s": state.value, "r": run_id},
    )


def load_prices(
    conn: Connection,
    *,
    file_id: str,
    facility_id: str,
    state_code: str,
    records: Iterable[ParsedPrice | RejectedRow],
    rows_conn: Connection | None = None,
) -> LoadResult:
    """Copy parsed prices into price.price under a new staged dataset version.

    `rows_conn` (the live national load, D-059) puts the price rows in a
    throwaway database on the loading computer instead; the import run and
    dataset version are still recorded in `conn`."""
    run_id, dv_id = _start_run(conn, file_id, facility_id)
    result = LoadResult(run_id, dv_id)
    facility_uuid = uuid.UUID(str(facility_id))
    dbapi = (rows_conn or conn).connection.driver_connection
    assert dbapi is not None
    with dbapi.cursor() as cur:
        with cur.copy(f"COPY price.price ({', '.join(COLUMNS)}) FROM STDIN") as copy:
            copy.set_types(COPY_TYPES)
            for rec in records:
                if isinstance(rec, RejectedRow):
                    result.rows_rejected += 1
                    result.rejects_by_rule[rec.rule] += 1
                    if result.rejects_by_rule[rec.rule] <= MAX_EXAMPLES:
                        result.examples.append(rec)
                    continue
                copy.write_row(
                    (
                        state_code,
                        dv_id,
                        facility_uuid,
                        rec.raw_row_ref,
                        rec.code_system.value,
                        rec.code,
                        list(rec.modifiers),
                        rec.setting.value if rec.setting else None,
                        rec.billing_class.value if rec.billing_class else None,
                        rec.description_raw,
                        rec.drug_unit,
                        rec.drug_unit_type,
                        rec.payer_name_raw,
                        rec.plan_name_raw,
                        rec.price_type.value,
                        rec.amount,
                        rec.percentage,
                        rec.algorithm,
                        rec.methodology.value if rec.methodology else None,
                        rec.allowed_count_raw,
                        rec.additional_notes_raw,
                        list(rec.quality_flags),
                        list(rec.other_codes),
                    )
                )
                result.rows_loaded += 1
                result.by_type[rec.price_type.value] += 1
                for flag in rec.quality_flags:
                    result.flags[flag] += 1
                if rec.payer_name_raw is not None and len(result.payers) < 5000:
                    result.payers.add(f"{rec.payer_name_raw} | {rec.plan_name_raw}")
    conn.execute(
        text(
            """
            UPDATE src.import_run SET rows_in = :i, rows_out = :o, rows_rejected = :r,
                finished_at = now()
            WHERE id = :id
            """
        ),
        {
            "i": result.rows_loaded + result.rows_rejected,
            "o": result.rows_loaded,
            "r": result.rows_rejected,
            "id": run_id,
        },
    )
    # Waits here for a person: nothing is published automatically.
    _move(conn, run_id, ImportState.QUALITY_REVIEW)
    return result
