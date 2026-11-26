"""Price files whose hospital refuses GitHub's computers (2026-11-26).

When GitHub's download of a price file is refused (403 and similar) or cut off
by the hospital's server, the source is marked; Cooper's computer then downloads
those files (scripts' "home-downloads" job) into the bucket, and the load uses
that copy when GitHub's own download fails again.

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE src.transparency_source ADD COLUMN blocked_at timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE src.transparency_source DROP COLUMN blocked_at")
