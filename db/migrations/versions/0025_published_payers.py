"""Insurer names per place, from published files only (Cooper, 2026-11-12).

Typing "Blue Cross" listed about 15 insurers from every state. The insurance
picker now lists only insurers with prices near the person, so the website
needs to know which insurer spellings each place published. This view shows
only rows of files that are currently published (never staged or rejected
files), and only names, not prices.

Also: a bundle may list the same code twice for different parts of the bill
(the scan's facility part and the radiologist's reading both use CPT 70551),
so a bundle's pieces are unique by code *and* role.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-12
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    CREATE VIEW price.published_payer AS
    SELECT DISTINCT s.facility_id, s.payer_name_raw, s.plan_name_raw
    FROM price.file_payer_summary s
    JOIN src.published_file pf
      ON pf.dataset_version_id = s.dataset_version_id AND pf.retired_at IS NULL
    UNION
    -- files published before per-file summaries existed (as in code_index.py)
    SELECT DISTINCT pp.facility_id, pp.payer_name_raw, coalesce(pp.plan_name_raw, '')
    FROM price.published_price pp
    WHERE pp.payer_name_raw IS NOT NULL AND btrim(pp.payer_name_raw) <> ''
      AND NOT EXISTS (SELECT 1 FROM price.file_payer_summary s
                      WHERE s.dataset_version_id = pp.dataset_version_id)""")
    op.execute(
        "CREATE INDEX IF NOT EXISTS file_payer_summary_facility "
        "ON price.file_payer_summary (facility_id)"
    )
    op.execute(
        "ALTER TABLE ref.bundle_component "
        "DROP CONSTRAINT bundle_component_bundle_id_code_system_code_key, "
        "ADD CONSTRAINT bundle_component_bundle_id_code_system_code_role_key "
        "UNIQUE (bundle_id, code_system, code, role)"
    )
    api_role = os.environ.get("PS_API_ROLE", "ps_api")
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", api_role):
        raise ValueError(f"PS_API_ROLE is not a plain role name: {api_role!r}")
    op.execute(f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{api_role}') THEN
            EXECUTE 'GRANT SELECT ON price.published_payer TO {api_role}';
        END IF;
    END $$""")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE ref.bundle_component "
        "DROP CONSTRAINT IF EXISTS bundle_component_bundle_id_code_system_code_role_key, "
        "DROP CONSTRAINT IF EXISTS bundle_component_bundle_id_code_system_code_key, "
        "ADD CONSTRAINT bundle_component_bundle_id_code_system_code_key "
        "UNIQUE (bundle_id, code_system, code)"
    )
    op.execute("DROP VIEW price.published_payer")
    op.execute("DROP INDEX IF EXISTS price.file_payer_summary_facility")
