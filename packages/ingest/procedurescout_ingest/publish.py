"""The review step: a person approves or rejects a staged dataset (D-028, D-033).

- `pending_reviews` lists datasets waiting in quality review with what the
  automatic checks found (rows, refusals, flags, file date, problems).
- `approve` needs a reviewer's name. It writes the dataset to one Parquet
  file, proves the copy is exact, stores it under a new key (never
  overwriting), retires the facility's previous published dataset and file,
  marks the new one published, and records an audit event, all in one
  database transaction.
- `reject` needs a reviewer and a reason; the dataset is retired unpublished.

- `auto_publish_pending` publishes a refresh of an already-approved facility
  without a person only when every automatic check passes (Cooper, Q19,
  D-035); everything else waits for a person.

Nothing is published any other way.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, text

from procedurescout_core.enums import ImportState
from procedurescout_core.object_store import ObjectStore, published_key

from . import parquet_io


class ReviewError(ValueError):
    """The dataset cannot be approved or rejected in its current state."""


@dataclass(frozen=True, slots=True)
class Pending:
    dataset_version_id: str
    facility_id: str
    ccn: str | None
    facility_name: str
    rows: int
    summary: dict[str, Any]
    file_problems: str | None
    last_updated_raw: str | None


def pending_reviews(conn: Connection) -> list[Pending]:
    rows = conn.execute(
        text(
            """
            SELECT dv.id, f.id, f.ccn, f.name, coalesce(r.rows_out, 0),
                   coalesce(t.read_summary->'load', '{}'::jsonb), t.read_error,
                   t.last_updated_raw
            FROM src.dataset_version dv
            JOIN src.import_run r ON r.id = dv.import_run_id
            JOIN src.transparency_file t ON t.id = r.file_id
            JOIN ref.facility f ON f.id = dv.facility_id
            WHERE dv.status = 'staged' AND r.state = 'quality_review'
            ORDER BY f.state_code, f.name
            """
        )
    ).all()
    return [
        Pending(str(r[0]), str(r[1]), r[2], r[3], int(r[4]), dict(r[5]), r[6], r[7]) for r in rows
    ]


def _require_reviewer(reviewer: str) -> str:
    name = reviewer.strip()
    if len(name) < 2:
        raise ReviewError("a reviewer's name is required")
    return name


def _load_staged(conn: Connection, dataset_version_id: uuid.UUID) -> tuple[Any, ...]:
    row = conn.execute(
        text(
            """
            SELECT dv.facility_id, f.state_code, dv.import_run_id, r.state::text, dv.status::text
            FROM src.dataset_version dv
            JOIN src.import_run r ON r.id = dv.import_run_id
            JOIN ref.facility f ON f.id = dv.facility_id
            WHERE dv.id = :d FOR UPDATE OF dv
            """
        ),
        {"d": dataset_version_id},
    ).first()
    if row is None:
        raise ReviewError(f"dataset {dataset_version_id} not found")
    if row[4] != "staged" or row[3] != ImportState.QUALITY_REVIEW.value:
        raise ReviewError(
            f"dataset {dataset_version_id} is {row[4]}/{row[3]}, not waiting for review"
        )
    return tuple(row)


def _audit(conn: Connection, actor: str, action: str, entity: str, after: dict[str, Any]) -> None:
    conn.execute(
        text(
            "INSERT INTO src.audit_event (actor, action, entity_type, entity_id, after) "
            "VALUES (:a, :ac, 'dataset_version', :e, CAST(:after AS jsonb))"
        ),
        {"a": actor, "ac": action, "e": entity, "after": json.dumps(after, default=str)},
    )


def _move(conn: Connection, run_id: object, state: ImportState) -> None:
    conn.execute(
        text("UPDATE src.import_run SET state = CAST(:s AS src.import_state) WHERE id = :r"),
        {"s": state.value, "r": run_id},
    )


def approve(
    conn: Connection,
    dataset_version_id: uuid.UUID,
    reviewer: str,
    store: ObjectStore,
    note: str | None = None,
) -> str:
    """Publish a reviewed dataset; returns the object key of its Parquet file."""
    who = _require_reviewer(reviewer)
    dv = uuid.UUID(str(dataset_version_id))
    facility_id, state_code, run_id, _, _ = _load_staged(conn, dv)
    totals = parquet_io.db_totals(conn, dv)
    if totals.rows == 0:
        raise ReviewError("dataset has no prices; nothing to publish")
    key = published_key(str(state_code), uuid.UUID(str(facility_id)), dv)
    with tempfile.TemporaryDirectory(prefix="publish-") as work:
        out = Path(work) / "dataset.parquet"
        parquet_io.write_dataset(conn, dv, out, Path(work))
        data_sha = hashlib.sha256(out.read_bytes()).hexdigest()
        size = out.stat().st_size
        store.put(out, key)

    previous = conn.execute(
        text(
            "SELECT id, import_run_id FROM src.dataset_version "
            "WHERE facility_id = :f AND status = 'published' FOR UPDATE"
        ),
        {"f": facility_id},
    ).all()
    for old_id, old_run in previous:
        conn.execute(
            text(
                "UPDATE src.dataset_version SET status = 'retired', retired_at = now() "
                "WHERE id = :d"
            ),
            {"d": old_id},
        )
        _move(conn, old_run, ImportState.RETIRED)
        conn.execute(
            text(
                "UPDATE src.published_file SET retired_at = now() "
                "WHERE dataset_version_id = :d AND retired_at IS NULL"
            ),
            {"d": old_id},
        )
    conn.execute(
        text(
            """
            UPDATE src.dataset_version SET status = 'published', published_at = now(),
                reviewed_by = :who, reviewed_at = now(), review_note = :note
            WHERE id = :d
            """
        ),
        {"who": who, "note": note, "d": dv},
    )
    _move(conn, run_id, ImportState.PUBLISHED)
    write_summaries(conn, dv, str(facility_id))
    conn.execute(
        text(
            """
            INSERT INTO src.published_file (dataset_version_id, facility_id, state_code,
                object_key, bytes, sha256, rows, amount_sum, percentage_sum)
            VALUES (:d, :f, :s, :k, :b, :h, :r, :a, :p)
            """
        ),
        {
            "d": dv,
            "f": facility_id,
            "s": state_code,
            "k": key,
            "b": size,
            "h": data_sha,
            "r": totals.rows,
            "a": totals.amount_sum,
            "p": totals.percentage_sum,
        },
    )
    _audit(
        conn,
        who,
        "approve_and_publish",
        str(dv),
        {
            "object_key": key,
            "rows": totals.rows,
            "sha256": data_sha,
            "note": note,
            "retired": [str(p[0]) for p in previous],
        },
    )
    return key


def reject(conn: Connection, dataset_version_id: uuid.UUID, reviewer: str, reason: str) -> None:
    who = _require_reviewer(reviewer)
    if len(reason.strip()) < 3:
        raise ReviewError("a reason is required to reject a dataset")
    dv = uuid.UUID(str(dataset_version_id))
    _, _, run_id, _, _ = _load_staged(conn, dv)
    conn.execute(
        text(
            """
            UPDATE src.dataset_version SET status = 'retired', retired_at = now(),
                reviewed_by = :who, reviewed_at = now(), review_note = :note
            WHERE id = :d
            """
        ),
        {"who": who, "note": reason.strip(), "d": dv},
    )
    conn.execute(
        text("UPDATE src.import_run SET error_summary = :e WHERE id = :r"),
        {"e": f"rejected by {who}: {reason.strip()}", "r": run_id},
    )
    _move(conn, run_id, ImportState.FAILED)
    _audit(conn, who, "reject", str(dv), {"reason": reason.strip()})


# ------------------------------------------------------------------ automatic refreshes
AUTO_REVIEWER = "automatic checks (D-035)"
MAX_COUNT_CHANGE = Decimal("0.30")


@dataclass(frozen=True, slots=True)
class AutoDecision:
    dataset_version_id: str
    facility_name: str
    published: bool
    reasons: tuple[str, ...]


FIRST_FILE_MAX_REFUSED = Decimal("0.01")


def auto_check(
    conn: Connection, dataset_version_id: uuid.UUID, allow_first: bool = False
) -> tuple[bool, list[str]]:
    """A staged refresh may publish without a person only when the facility
    already has an approved dataset and nothing got worse (Cooper, Q19):
    refused rows not more than last time, price count within 30%, no new
    file problems, and the file's own date not older.

    With allow_first (only if Cooper approves it for the national launch,
    Q35), a facility's first file may also publish automatically when it has
    prices, no file problems, and at most 1% of rows refused."""
    row = conn.execute(
        text(
            """
            SELECT dv.facility_id, r.rows_out, r.rows_rejected, t.read_error,
                   t.reported_last_updated
            FROM src.dataset_version dv
            JOIN src.import_run r ON r.id = dv.import_run_id
            JOIN src.transparency_file t ON t.id = r.file_id
            WHERE dv.id = :d AND dv.status = 'staged' AND r.state = 'quality_review'
            """
        ),
        {"d": dataset_version_id},
    ).first()
    if row is None:
        return False, ["not waiting for review"]
    prev = conn.execute(
        text(
            """
            SELECT r.rows_out, r.rows_rejected, t.read_error, t.reported_last_updated
            FROM src.dataset_version dv
            JOIN src.import_run r ON r.id = dv.import_run_id
            JOIN src.transparency_file t ON t.id = r.file_id
            WHERE dv.facility_id = :f AND dv.status = 'published'
            """
        ),
        {"f": row[0]},
    ).first()
    if prev is None:
        if not allow_first:
            return False, ["first file for this facility: a person reviews it"]
        rows_out, refused = int(row[1] or 0), int(row[2] or 0)
        first: list[str] = []
        if rows_out == 0:
            first.append("no prices")
        if row[3]:
            first.append(f"file problems: {row[3]}")
        if rows_out and Decimal(refused) > FIRST_FILE_MAX_REFUSED * (rows_out + refused):
            first.append(f"{refused} rows refused (more than 1%)")
        return not first, first
    reasons = []
    new_rows, new_rej = int(row[1] or 0), int(row[2] or 0)
    old_rows, old_rej = int(prev[0] or 0), int(prev[1] or 0)
    if new_rej > old_rej:
        reasons.append(f"refused rows rose from {old_rej} to {new_rej}")
    if old_rows == 0 or abs(Decimal(new_rows - old_rows)) > MAX_COUNT_CHANGE * old_rows:
        reasons.append(f"price count changed from {old_rows} to {new_rows} (more than 30%)")
    new_problems = {p for p in (row[3] or "").split("; ") if p}
    old_problems = {p for p in (prev[2] or "").split("; ") if p}
    if new_problems - old_problems:
        reasons.append("new file problems: " + "; ".join(sorted(new_problems - old_problems)))
    new_date, old_date = row[4], prev[3]
    if old_date is not None and (new_date is None or new_date < old_date):
        reasons.append(f"file date {new_date} is older than the approved file's {old_date}")
    return not reasons, reasons


def auto_publish_pending(
    conn: Connection,
    store: ObjectStore,
    allow_first: bool = False,
    facility_id: str | None = None,
) -> list[AutoDecision]:
    decisions = []
    for p in pending_reviews(conn):
        if facility_id is not None and p.facility_id != facility_id:
            continue
        dv = uuid.UUID(p.dataset_version_id)
        ok, reasons = auto_check(conn, dv, allow_first)
        if ok:
            approve(conn, dv, AUTO_REVIEWER, store, note="all automatic checks passed")
        decisions.append(AutoDecision(p.dataset_version_id, p.facility_name, ok, tuple(reasons)))
    return decisions


# --------------------------------------------------- national storage (D-054)
def write_summaries(conn: Connection, dataset_version_id: uuid.UUID, facility_id: str) -> None:
    """Keep the small per-file summaries the code index and insurance-name
    matching need, so the staged rows can be removed after publishing."""
    conn.execute(
        text(
            """
            INSERT INTO price.file_code_summary (dataset_version_id, facility_id, code_system,
                code, top_description, prices)
            SELECT :d, CAST(:f AS uuid), code_system, code,
                   mode() WITHIN GROUP (ORDER BY left(btrim(description_raw), 300))
                       FILTER (WHERE description_raw IS NOT NULL AND btrim(description_raw) <> ''),
                   count(*)
            FROM price.price WHERE dataset_version_id = :d
            GROUP BY code_system, code
            ON CONFLICT DO NOTHING
            """
        ),
        {"d": dataset_version_id, "f": facility_id},
    )
    conn.execute(
        text(
            """
            INSERT INTO price.file_payer_summary (dataset_version_id, facility_id,
                payer_name_raw, plan_name_raw, prices)
            SELECT :d, CAST(:f AS uuid), payer_name_raw, coalesce(plan_name_raw, ''), count(*)
            FROM price.price
            WHERE dataset_version_id = :d AND payer_name_raw IS NOT NULL
              AND btrim(payer_name_raw) <> ''
            GROUP BY payer_name_raw, coalesce(plan_name_raw, '')
            ON CONFLICT DO NOTHING
            """
        ),
        {"d": dataset_version_id, "f": facility_id},
    )


def prune_published(conn: Connection, facility_id: str | None = None) -> int:
    """Remove staged rows of datasets that are published (their Parquet file is
    the copy the site reads) or retired, once their summaries exist."""
    result = conn.execute(
        text(
            """
            DELETE FROM price.price p USING src.dataset_version dv
            WHERE dv.id = p.dataset_version_id AND dv.status IN ('published', 'retired')
              AND (CAST(:f AS uuid) IS NULL OR dv.facility_id = CAST(:f AS uuid))
              AND EXISTS (SELECT 1 FROM price.file_code_summary s
                          WHERE s.dataset_version_id = dv.id)
            """
        ),
        {"f": facility_id},
    )
    return int(result.rowcount or 0)
