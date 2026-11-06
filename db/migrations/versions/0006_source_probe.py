"""Record a size/date check of each price file before anything is downloaded.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-06

src.source_probe: one row per check of a src.transparency_source URL. The check
asks the server for the file's headers only (HEAD, or a GET that is closed
before the body is read) and records the published size, type and
last-modified date exactly as the server reports them. Nothing is downloaded.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE src.source_probe (
        id              bigserial PRIMARY KEY,
        source_id       uuid NOT NULL REFERENCES src.transparency_source(id) ON DELETE CASCADE,
        probed_at       timestamptz NOT NULL DEFAULT now(),
        method          text NOT NULL CHECK (method IN ('HEAD', 'GET-headers')),
        http_status     smallint,
        final_url       text,
        content_length  bigint CHECK (content_length >= 0),
        content_type    text,
        last_modified   text,
        error           text,
        fetched_via     text NOT NULL DEFAULT 'github'
            CHECK (fetched_via IN ('github', 'home_runner'))
    )""")
    op.execute("CREATE INDEX source_probe_source_idx ON src.source_probe (source_id, probed_at)")


def downgrade() -> None:
    op.execute("DROP TABLE src.source_probe")
