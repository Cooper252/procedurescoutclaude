"""How many runs in a row a price file has been cut off (2026-11-25).

A file cut off at the time limit is no longer skipped (Cooper: "I want every
hospital price listed"): the next run starts with it, so it has the whole run.
Only a file cut off again even when started first is moved to the end, where it
can't stop the rest of its state, and reported as needing a download from
Cooper's computer.

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE src.transparency_source ADD COLUMN slow_tries smallint NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE src.transparency_source DROP COLUMN slow_tries")
