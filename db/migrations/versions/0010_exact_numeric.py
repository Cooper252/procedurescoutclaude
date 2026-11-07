"""Store every published amount exactly: unconstrained NUMERIC.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-07

Run #12 (real Nevada files) refused about 120,000 prices because they had
more than 4 decimal places: sub-cent negotiated rates (2669.73225, 1.53765 in
the UHS files) and spreadsheet artifacts (460.370000000001, 19.380000000000003).
Rounding them is not allowed (CLAUDE.md rule 4), so the columns become
unconstrained NUMERIC and the values are kept exactly as published (D-029,
supersedes the 4-place limit of D-008). Display rounding happens only in the
presentation layer. Range checks stay.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIEW = """
    CREATE VIEW price.published_price AS
    SELECT p.*, dv.published_at
    FROM price.price p
    JOIN src.dataset_version dv ON dv.id = p.dataset_version_id
    WHERE dv.status = 'published'"""


def _grant() -> None:
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


def _alter(numeric_type: str, percent_type: str) -> None:
    op.execute("DROP VIEW price.published_price")
    for table in ("price.price", "fixture.synthetic_price"):
        op.execute(f"""
        ALTER TABLE {table}
            ALTER COLUMN amount TYPE {numeric_type},
            ALTER COLUMN percentage TYPE {percent_type},
            ALTER COLUMN drug_unit TYPE {numeric_type}
        """)
    op.execute(VIEW)
    _grant()


def upgrade() -> None:
    _alter("numeric", "numeric")


def downgrade() -> None:
    # Casting to numeric(16,4) would round silently: refuse instead.
    for table in ("price.price", "fixture.synthetic_price"):
        op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM {table} WHERE scale(amount) > 4
                       OR scale(percentage) > 4 OR scale(drug_unit) > 4) THEN
                RAISE EXCEPTION 'values with more than 4 decimal places in {table}; '
                    'downgrade would round them';
            END IF;
        END $$""")
    _alter("numeric(16,4)", "numeric(9,4)")
