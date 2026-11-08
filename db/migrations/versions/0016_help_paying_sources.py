"""Community health centers and public coverage income limits (HELP-01).

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-08

ref.health_center holds HRSA's public list of health center sites (federally
funded health centers and look-alikes charge on a sliding fee scale by income).
ref.coverage_limit holds reviewed income limits for Medicaid, CHIP (Nevada
Check Up) and marketplace savings as a percent of the poverty guideline, with
the official source; rows are proposed until a person approves them (rule 10).
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATASETS_0012 = [
    "cms_hospital_general_information",
    "cms_asc_facility",
    "census_zcta_gazetteer",
    "census_zcta_county_relationship",
    "census_geocoder",
    "nppes_npi_registry",
    "ahrq_compendium_hospital_linkage",
    "cms_hcpcs_level2",
    "cms_ms_drg_table5",
    "manual_relationships",
    "facility_websites",
    "cms_hpt_txt_discovery",
    "price_file_check",
    "service_catalog",
]
DATASETS_0016 = [*DATASETS_0012, "hrsa_health_center_sites"]


def _dataset_check(datasets: list[str]) -> None:
    quoted = ", ".join("'" + d + "'" for d in datasets)
    op.execute("ALTER TABLE src.reference_load DROP CONSTRAINT reference_load_dataset_check")
    op.execute(
        "ALTER TABLE src.reference_load ADD CONSTRAINT reference_load_dataset_check "
        f"CHECK (dataset IN ({quoted}))"
    )


def upgrade() -> None:
    _dataset_check(DATASETS_0016)
    op.execute("""
    CREATE TABLE ref.health_center (
        id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        source_key    text NOT NULL UNIQUE,
        name          text NOT NULL,
        organization  text,
        address_line1 text,
        city          text,
        state_code    character(2) NOT NULL,
        zip5          text,
        phone         text,
        website       text,
        site_type     text,
        center_type   text,
        geom          geography(Point, 4326),
        source        text NOT NULL,
        loaded_at     timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX health_center_geom_gix ON ref.health_center USING gist (geom)")
    op.execute("""
    CREATE TABLE ref.coverage_limit (
        id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        state_code      character(2) NOT NULL,
        program         text NOT NULL CHECK (program IN ('medicaid', 'chip', 'marketplace_savings')),
        group_code      text NOT NULL CHECK (group_code IN
                            ('adults', 'children', 'pregnant', 'everyone')),
        min_percent_fpg numeric NOT NULL DEFAULT 0 CHECK (min_percent_fpg >= 0),
        max_percent_fpg numeric NOT NULL CHECK (max_percent_fpg > min_percent_fpg),
        label           text NOT NULL,
        apply_url       text NOT NULL,
        source_url      text NOT NULL,
        effective_from  date NOT NULL,
        notes           text,
        review_state    ref.review_state NOT NULL DEFAULT 'proposed',
        reviewed_by     text,
        reviewed_at     timestamptz,
        UNIQUE (state_code, program, group_code),
        CHECK (review_state <> 'approved' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
    )""")
    api_role = os.environ.get("PS_API_ROLE", "ps_api")
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", api_role):
        raise ValueError(f"PS_API_ROLE is not a plain role name: {api_role!r}")
    op.execute(f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{api_role}') THEN
            EXECUTE 'GRANT SELECT ON ref.health_center, ref.coverage_limit TO {api_role}';
        END IF;
    END $$""")


def downgrade() -> None:
    op.execute("DROP TABLE ref.coverage_limit")
    op.execute("DROP TABLE ref.health_center")
    op.execute("DELETE FROM src.reference_load WHERE dataset = 'hrsa_health_center_sites'")
    _dataset_check(DATASETS_0012)
