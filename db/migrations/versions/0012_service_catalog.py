"""Service catalog and provider types (D-032).

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-08

- ref.procedure becomes the searchable service catalog: a URL-safe slug, the
  unit prices are quoted in (per service, per unit, per area, ...), and review
  state. Only approved services and approved code links are used by search;
  suggestions (including AI suggestions) stay 'proposed' (CLAUDE.md rule 10).
- ref.provider_type: reviewed list of provider kinds (hospital, surgery
  center, dental office, medical spa, ...).
- ref.facility_provider_type: which kinds each facility is, and where that
  came from (CMS facility type, the provider, or a reviewer).
- The API role can read the new reference tables.
- Adds the 'service_catalog' reference-load dataset.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATASETS_0007 = [
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
]
DATASETS_0012 = [*DATASETS_0007, "service_catalog"]


def _dataset_check(datasets: list[str]) -> None:
    quoted = ", ".join("'" + d + "'" for d in datasets)
    op.execute("ALTER TABLE src.reference_load DROP CONSTRAINT reference_load_dataset_check")
    op.execute(
        "ALTER TABLE src.reference_load ADD CONSTRAINT reference_load_dataset_check "
        f"CHECK (dataset IN ({quoted}))"
    )


UNITS = (
    "per_service",
    "per_unit",
    "per_area",
    "per_syringe",
    "per_session",
    "per_visit",
    "per_day",
    "per_month",
)


def upgrade() -> None:
    units = ", ".join(f"'{u}'" for u in UNITS)
    op.execute(f"""
    ALTER TABLE ref.procedure
        ADD COLUMN slug text UNIQUE CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
        ADD COLUMN unit text NOT NULL DEFAULT 'per_service' CHECK (unit IN ({units})),
        ADD COLUMN source ref.suggestion_source NOT NULL DEFAULT 'human',
        ADD COLUMN review_state ref.review_state NOT NULL DEFAULT 'proposed',
        ADD COLUMN reviewed_by text,
        ADD COLUMN reviewed_at timestamptz,
        ADD CONSTRAINT procedure_approval_reviewed CHECK (
            review_state <> 'approved' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)),
        ADD CONSTRAINT procedure_approved_has_slug CHECK (
            review_state <> 'approved' OR slug IS NOT NULL)
    """)
    op.execute("""
    CREATE TABLE ref.provider_type (
        code          text PRIMARY KEY CHECK (code ~ '^[a-z][a-z_]*$'),
        name          text NOT NULL UNIQUE,
        source        ref.suggestion_source NOT NULL DEFAULT 'human',
        review_state  ref.review_state NOT NULL DEFAULT 'proposed',
        reviewed_by   text,
        reviewed_at   timestamptz,
        CHECK (review_state <> 'approved' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
    )""")
    op.execute("""
    CREATE TABLE ref.facility_provider_type (
        facility_id    uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        provider_type  text NOT NULL REFERENCES ref.provider_type(code) ON DELETE RESTRICT,
        source         text NOT NULL CHECK (source IN ('cms_facility_type', 'provider', 'reviewer')),
        created_at     timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (facility_id, provider_type)
    )""")
    op.execute(
        "CREATE INDEX facility_provider_type_type_idx ON ref.facility_provider_type (provider_type)"
    )
    _dataset_check(DATASETS_0012)
    api_role = os.environ.get("PS_API_ROLE", "ps_api")
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", api_role):
        raise ValueError(f"PS_API_ROLE is not a plain role name: {api_role!r}")
    op.execute(f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{api_role}') THEN
            EXECUTE 'GRANT SELECT ON ref.provider_type, ref.facility_provider_type TO {api_role}';
        END IF;
    END $$""")


def downgrade() -> None:
    op.execute("DELETE FROM src.reference_load WHERE dataset = 'service_catalog'")
    _dataset_check(DATASETS_0007)
    op.execute("DROP TABLE ref.facility_provider_type")
    op.execute("DROP TABLE ref.provider_type")
    op.execute("""
    ALTER TABLE ref.procedure
        DROP CONSTRAINT procedure_approved_has_slug,
        DROP CONSTRAINT procedure_approval_reviewed,
        DROP COLUMN reviewed_at,
        DROP COLUMN reviewed_by,
        DROP COLUMN review_state,
        DROP COLUMN source,
        DROP COLUMN unit,
        DROP COLUMN slug
    """)
