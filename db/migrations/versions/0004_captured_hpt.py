"""Phase 2, step 1b: captured cms-hpt.txt copies and reviewed manual price-file links.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-05

Some hospital sites refuse automated requests from cloud servers (HTTP 403)
but serve the same public cms-hpt.txt to a normal browser. A copy captured in
a browser, approved by a person, is used only when the live fetch fails, and
is labeled as such:

- src.hpt_txt_fetch.content_source: 'live' or 'captured'; captured rows keep
  the capture date and who approved the copy.
- src.transparency_source.review_note: why a manually entered source exists.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE src.hpt_txt_fetch
        ADD COLUMN content_source  text NOT NULL DEFAULT 'live'
            CHECK (content_source IN ('live', 'captured')),
        ADD COLUMN captured_at     date,
        ADD COLUMN captured_from   text,
        ADD COLUMN copy_reviewed_by text,
        ADD CONSTRAINT hpt_txt_fetch_captured_provenance CHECK (
            content_source = 'live'
            OR (captured_at IS NOT NULL AND captured_from IS NOT NULL
                AND copy_reviewed_by IS NOT NULL)
        )
    """)
    op.execute("""
    ALTER TABLE src.transparency_source
        ADD COLUMN review_note text,
        ADD CONSTRAINT transparency_source_manual_noted
            CHECK (discovery_method <> 'manual' OR review_note IS NOT NULL)
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE src.transparency_source
        DROP CONSTRAINT transparency_source_manual_noted,
        DROP COLUMN review_note""")
    op.execute("""
    ALTER TABLE src.hpt_txt_fetch
        DROP CONSTRAINT hpt_txt_fetch_captured_provenance,
        DROP COLUMN copy_reviewed_by, DROP COLUMN captured_from,
        DROP COLUMN captured_at, DROP COLUMN content_source""")
