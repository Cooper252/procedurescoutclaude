"""Keep every code a price item was published with.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-07

A CMS charge item can carry several codes (for example CPT 70450, revenue
code 0350 and the hospital's own CDM number). Each price row is stored once,
under the item's primary code (the most specific billing code, see
price_parser.CODE_PRIORITY); price.price.other_codes keeps the rest exactly as
published, as "TYPE:code" strings, so nothing is lost and rows are not
multiplied.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


VIEW = """
    CREATE VIEW price.published_price AS
    SELECT p.*, dv.published_at
    FROM price.price p
    JOIN src.dataset_version dv ON dv.id = p.dataset_version_id
    WHERE dv.status = 'published'"""


def _recreate_view() -> None:
    # published_price is SELECT p.*: it must be recreated to see a new column,
    # and the API role's grant must be given again.
    op.execute("DROP VIEW price.published_price")
    op.execute(VIEW)
    api_role = os.environ.get("PS_API_ROLE", "ps_api")
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", api_role):
        raise ValueError(f"PS_API_ROLE is not a plain role name: {api_role!r}")
    op.execute(f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{api_role}') THEN
            EXECUTE 'GRANT SELECT ON price.published_price TO {api_role}';
        END IF;
    END $$""")


def upgrade() -> None:
    op.execute("ALTER TABLE price.price ADD COLUMN other_codes text[] NOT NULL DEFAULT '{}'")
    op.execute(
        "ALTER TABLE fixture.synthetic_price ADD COLUMN other_codes text[] NOT NULL DEFAULT '{}'"
    )
    _recreate_view()


def downgrade() -> None:
    op.execute("DROP VIEW price.published_price")
    op.execute("ALTER TABLE fixture.synthetic_price DROP COLUMN other_codes")
    op.execute("ALTER TABLE price.price DROP COLUMN other_codes")
    op.execute(VIEW)
    api_role = os.environ.get("PS_API_ROLE", "ps_api")
    if re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", api_role):
        op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{api_role}') THEN
                EXECUTE 'GRANT SELECT ON price.published_price TO {api_role}';
            END IF;
        END $$""")
