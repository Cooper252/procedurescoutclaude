"""Record which network fetched a cms-hpt.txt.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-06

Some hospital sites refuse GitHub's servers. The manual workflow can also
fetch every approved site live from Cooper's own computer (a GitHub
self-hosted runner) during the same run. Those fetches are just as live; this
column records the network so the two are never confused:
'github' (GitHub-hosted runner) or 'home_runner' (Cooper's computer).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE src.hpt_txt_fetch
        ADD COLUMN fetched_via text NOT NULL DEFAULT 'github'
            CHECK (fetched_via IN ('github', 'home_runner'))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE src.hpt_txt_fetch DROP COLUMN fetched_via")
