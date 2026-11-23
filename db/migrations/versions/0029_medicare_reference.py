"""Medicare's physician payment amounts, as a labeled reference (D-071).

Hospital price files usually leave out the doctor's own bill (the radiologist's
reading, the surgeon, the pathologist), because a separate group bills it.
Where a doctor's piece isn't in the hospital's file, the whole-cost panel shows
what Medicare pays for it in that area, labeled as Medicare's amount and never
added to the hospital's prices or called this place's price.

- ref.medicare_locality_zip: ZIP code ranges to Medicare carrier and pricing
  locality (CMS ZIP Code to Carrier Locality File).
- ref.medicare_physician_fee: the CMS Physician Fee Schedule payment amount for
  a code and modifier in one locality (facility and non-facility amounts).

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-23
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE ref.medicare_locality_zip (
        zip_from  text NOT NULL CHECK (zip_from ~ '^[0-9]{5}$'),
        zip_to    text NOT NULL CHECK (zip_to ~ '^[0-9]{5}$'),
        carrier   text NOT NULL CHECK (carrier ~ '^[0-9]{5}$'),
        locality  text NOT NULL CHECK (locality ~ '^[0-9]{2}$'),
        PRIMARY KEY (zip_from),
        CHECK (zip_from <= zip_to)
    )""")
    op.execute("""
    CREATE TABLE ref.medicare_physician_fee (
        year                 integer NOT NULL,
        code_system          ref.code_system NOT NULL,
        code                 text NOT NULL,
        modifier             text NOT NULL DEFAULT '',
        carrier              text NOT NULL,
        locality             text NOT NULL,
        facility_amount      numeric NOT NULL CHECK (facility_amount > 0),
        non_facility_amount  numeric NOT NULL CHECK (non_facility_amount > 0),
        source               text NOT NULL,
        PRIMARY KEY (year, code_system, code, modifier, carrier, locality)
    )""")
    api_role = os.environ.get("PS_API_ROLE", "ps_api")
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", api_role):
        raise ValueError(f"PS_API_ROLE is not a plain role name: {api_role!r}")
    op.execute(f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{api_role}') THEN
            EXECUTE 'GRANT SELECT ON ref.medicare_locality_zip, ref.medicare_physician_fee
                     TO {api_role}';
        END IF;
    END $$""")


def downgrade() -> None:
    op.execute("DROP TABLE ref.medicare_physician_fee")
    op.execute("DROP TABLE ref.medicare_locality_zip")
