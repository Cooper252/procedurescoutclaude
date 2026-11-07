"""Record which network downloaded a price file.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-07

A few hospital servers refuse GitHub's servers (run #10: Boulder City and
Desert Parkway answered 403). Their price files can be downloaded live on
Cooper's computer during the same run (scripts/fetch_prices_home.ps1).
src.transparency_file.fetched_via says which: 'github' or 'home_runner'.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE src.transparency_file
        ADD COLUMN fetched_via text NOT NULL DEFAULT 'github'
            CHECK (fetched_via IN ('github', 'home_runner'))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE src.transparency_file DROP COLUMN fetched_via")
