"""Procedure bundles and financial assistance (D-036, D-037).

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-08

Bundles
- ref.procedure.kind: 'service' or 'bundle'. A bundle (e.g. "Upper endoscopy,
  everything included") is a catalog entry made of components.
- ref.bundle_component: one row per piece (the procedure, the doctor, the
  anesthesia, pathology...), each either required or optional, included by
  default or not, with the code it is billed under. Reviewed like everything
  else; only approved components are used.

Financial assistance
- ref.poverty_guideline: HHS poverty guidelines by year and region
  (48 states + DC, Alaska, Hawaii) and household size, exactly as published.
- ref.assistance_policy / ref.assistance_tier: each hospital's financial
  assistance policy (links, and income limits as a percent of the guideline
  for free or discounted care), reviewed by a person with evidence.
The API role can read all of these.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REVIEW = """
        review_state  ref.review_state NOT NULL DEFAULT 'proposed',
        reviewed_by   text,
        reviewed_at   timestamptz,
        CHECK (review_state <> 'approved' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
"""


def upgrade() -> None:
    op.execute("""
    ALTER TABLE ref.procedure
        ADD COLUMN kind text NOT NULL DEFAULT 'service' CHECK (kind IN ('service', 'bundle'))
    """)
    op.execute(f"""
    CREATE TABLE ref.bundle_component (
        id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        bundle_id           uuid NOT NULL REFERENCES ref.procedure(id) ON DELETE CASCADE,
        position            smallint NOT NULL CHECK (position >= 0),
        label               text NOT NULL,
        role                text NOT NULL CHECK (role IN ('procedure', 'facility', 'physician',
                                'anesthesia', 'pathology', 'imaging', 'lab', 'newborn',
                                'supplies', 'other')),
        requirement         text NOT NULL CHECK (requirement IN ('required', 'optional')),
        included_by_default boolean NOT NULL,
        code_system         ref.code_system NOT NULL,
        code                text NOT NULL,
        code_version        text NOT NULL,
        notes               text,
        source              ref.suggestion_source NOT NULL DEFAULT 'human',
        {REVIEW},
        UNIQUE (bundle_id, position),
        UNIQUE (bundle_id, code_system, code),
        CHECK (requirement = 'optional' OR included_by_default),
        FOREIGN KEY (code_system, code, code_version)
            REFERENCES ref.code(system, code, version) ON DELETE RESTRICT
    )""")
    op.execute("""
    CREATE TABLE ref.poverty_guideline (
        year            smallint NOT NULL CHECK (year BETWEEN 2000 AND 2100),
        region          text NOT NULL CHECK (region IN ('contiguous', 'alaska', 'hawaii')),
        household_size  smallint NOT NULL CHECK (household_size BETWEEN 1 AND 8),
        amount          numeric NOT NULL CHECK (amount > 0),
        per_additional  numeric NOT NULL CHECK (per_additional > 0),
        source_url      text NOT NULL,
        PRIMARY KEY (year, region, household_size)
    )""")
    op.execute(f"""
    CREATE TABLE ref.assistance_policy (
        id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        facility_id           uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        policy_url            text NOT NULL CHECK (policy_url ~ '^https://'),
        application_url       text CHECK (application_url ~ '^https://'),
        summary_url           text CHECK (summary_url ~ '^https://'),
        phone                 text,
        guideline_year        smallint,
        effective_date        date,
        checked_at            date NOT NULL,
        evidence              text NOT NULL,
        notes                 text,
        source                ref.suggestion_source NOT NULL DEFAULT 'human',
        {REVIEW}
    )""")
    op.execute("""
    CREATE UNIQUE INDEX assistance_policy_one_approved
    ON ref.assistance_policy (facility_id) WHERE review_state = 'approved'""")
    op.execute("""
    CREATE TABLE ref.assistance_tier (
        policy_id         uuid NOT NULL REFERENCES ref.assistance_policy(id) ON DELETE CASCADE,
        max_percent_fpg   numeric NOT NULL CHECK (max_percent_fpg > 0 AND max_percent_fpg <= 1000),
        benefit           text NOT NULL CHECK (benefit IN ('free', 'discount')),
        discount_percent  numeric CHECK (discount_percent > 0 AND discount_percent < 100),
        description       text,
        PRIMARY KEY (policy_id, max_percent_fpg, benefit),
        CHECK (benefit = 'discount' OR discount_percent IS NULL),
        CHECK (benefit = 'free' OR discount_percent IS NOT NULL OR description IS NOT NULL)
    )""")
    api_role = os.environ.get("PS_API_ROLE", "ps_api")
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", api_role):
        raise ValueError(f"PS_API_ROLE is not a plain role name: {api_role!r}")
    op.execute(f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{api_role}') THEN
            EXECUTE 'GRANT SELECT ON ref.bundle_component, ref.poverty_guideline,
                     ref.assistance_policy, ref.assistance_tier TO {api_role}';
        END IF;
    END $$""")


def downgrade() -> None:
    op.execute("DROP TABLE ref.assistance_tier")
    op.execute("DROP TABLE ref.assistance_policy")
    op.execute("DROP TABLE ref.poverty_guideline")
    op.execute("DROP TABLE ref.bundle_component")
    op.execute("ALTER TABLE ref.procedure DROP COLUMN kind")
