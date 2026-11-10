"""Small per-file summaries so staged prices can be removed after publishing.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-10

National scale (D-048, D-054): the published Parquet file is the copy the
site reads, so a dataset's rows in price.price are no longer needed once it is
published. Before they are removed, two small summaries are kept per dataset:

- price.file_code_summary: each billing code, the description the file uses
  most, and how many prices — feeds ref.code_index;
- price.file_payer_summary: each insurer + plan spelling and how many prices —
  feeds ref.payer_index and the insurance-name matching.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE price.file_code_summary (
        dataset_version_id  uuid NOT NULL REFERENCES src.dataset_version(id) ON DELETE CASCADE,
        facility_id         uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        code_system         ref.code_system NOT NULL,
        code                text NOT NULL,
        top_description     text,
        prices              bigint NOT NULL CHECK (prices > 0),
        PRIMARY KEY (dataset_version_id, code_system, code)
    )""")
    op.execute("""
    CREATE TABLE price.file_payer_summary (
        dataset_version_id  uuid NOT NULL REFERENCES src.dataset_version(id) ON DELETE CASCADE,
        facility_id         uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        payer_name_raw      text NOT NULL,
        plan_name_raw       text NOT NULL DEFAULT '',
        prices              bigint NOT NULL CHECK (prices > 0),
        PRIMARY KEY (dataset_version_id, payer_name_raw, plan_name_raw)
    )""")
    op.execute(
        "CREATE INDEX file_payer_summary_names ON price.file_payer_summary "
        "(payer_name_raw, plan_name_raw)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE price.file_payer_summary")
    op.execute("DROP TABLE price.file_code_summary")
