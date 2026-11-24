"""The code index is kept up to date file by file (2026-11-23).

Rebuilding ref.code_index from every published file's summary at the end of
each state first filled the live database's disk (a single sorting query), then,
read as one stream, ran past the step's 20 minutes. Now each run adds the files
published since the last run and takes away the ones retired, into
ref.code_index_next, and copies it to ref.code_index once every published file
is counted.

- ref.code_index_next: the running totals (places, prices) per code, with the
  wording of the file that published the most prices for it (top_prices).
- ref.code_index_counted: which published files are in those totals.

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE ref.code_index_next (
        system               ref.code_system NOT NULL,
        code                 text NOT NULL,
        hospital_description text,
        top_prices           bigint NOT NULL DEFAULT 0,
        facilities           integer NOT NULL,
        prices               bigint NOT NULL,
        PRIMARY KEY (system, code)
    )""")
    op.execute("""
    CREATE TABLE ref.code_index_counted (
        dataset_version_id uuid PRIMARY KEY,
        counted_at         timestamptz NOT NULL DEFAULT now()
    )""")


def downgrade() -> None:
    op.execute("DROP TABLE ref.code_index_counted")
    op.execute("DROP TABLE ref.code_index_next")
