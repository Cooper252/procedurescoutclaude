"""Price files too slow to finish in a run wait two weeks (2026-11-25).

Indiana passes 2-4 each spent the whole run on Community Hospital East's file
(its server sends it very slowly) until the time limit cut it off, and the chain
kept running Indiana again. A file cut off at the time limit, or whose download
ran past an hour, is now skipped (and reported) until slow_until.

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE src.transparency_source ADD COLUMN slow_until timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE src.transparency_source DROP COLUMN slow_until")
