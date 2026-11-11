"""Price-list templates: services a practice priced that aren't on our list yet.

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-11

Cooper (2026-11-11): practices fill a downloadable price list made for their
kind of care and upload it; every line is checked against our services. A line
we don't have yet is kept here, under the practice's own wording, until staff
add the service to the list (then the practice's price can go live) or decline
it. Nothing here is shown on the site.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _role(env: str, default: str) -> str:
    role = os.environ.get(env, default)
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", role):
        raise ValueError(f"{env} is not a plain role name: {role!r}")
    return role


def upgrade() -> None:
    op.execute("""
    CREATE TABLE prov.service_suggestion (
        id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        facility_id   uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        submitted_by  uuid REFERENCES prov.account(id) ON DELETE SET NULL,
        name          text NOT NULL CHECK (length(btrim(name)) BETWEEN 3 AND 200),
        code_system   text CHECK (code_system IS NULL OR code_system ~ '^[A-Z-]{2,10}$'),
        code          text CHECK (code IS NULL OR code ~ '^[0-9A-Za-z.-]{1,12}$'),
        unit_note     text CHECK (unit_note IS NULL OR length(unit_note) <= 60),
        price         numeric NOT NULL CHECK (price > 0),
        status        text NOT NULL DEFAULT 'proposed'
                      CHECK (status IN ('proposed', 'added', 'declined')),
        review_note   text,
        created_at    timestamptz NOT NULL DEFAULT now(),
        reviewed_at   timestamptz
    )""")
    op.execute(
        "CREATE INDEX service_suggestion_open ON prov.service_suggestion (status, created_at)"
    )
    portal_role = _role("PS_PORTAL_ROLE", "ps_portal")
    op.execute(f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{portal_role}') THEN
            EXECUTE 'GRANT SELECT, INSERT ON prov.service_suggestion TO {portal_role}';
            EXECUTE 'GRANT SELECT ON ref.procedure_provider_type, ref.procedure_code,
                     ref.provider_type TO {portal_role}';
        END IF;
    END $$""")


def downgrade() -> None:
    op.execute("DROP TABLE prov.service_suggestion")
