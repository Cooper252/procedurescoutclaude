"""Price history: the API may read retired published files (PRC-02).

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-08

A retired file was published once; reading it to say "price up 12% since
March" shows nothing that was never public. price.published_file_history
lists current and retired published files (no staged or rejected data).
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    CREATE VIEW price.published_file_history AS
    SELECT facility_id, state_code, price_source, object_key, rows, published_at, retired_at
    FROM src.published_file""")
    api_role = os.environ.get("PS_API_ROLE", "ps_api")
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", api_role):
        raise ValueError(f"PS_API_ROLE is not a plain role name: {api_role!r}")
    op.execute(f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{api_role}') THEN
            EXECUTE 'GRANT SELECT ON price.published_file_history TO {api_role}';
        END IF;
    END $$""")


def downgrade() -> None:
    op.execute("DROP VIEW price.published_file_history")
