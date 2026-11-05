"""Phase 1: facility and reference data.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04

- ref.facility: accepts 10-character ASC CCNs (e.g. 29C0001035) as well as
  6-character hospital CCNs; keeps the CMS facility type and county exactly as
  published; records geocode precision; records where a health-system link
  came from.
- ref.health_system: keyed by (source, source_system_id). The UNIQUE(name)
  constraint is dropped on purpose: two different systems can share a name,
  and a name match must never merge them (DECISIONS D-013).
- ref.facility_alias: normalized lookup key, the basis of the link (an
  identifier such as CCN/NPI, or a person) and a review state. Only
  identifier-based or reviewer-approved aliases are used.
- ref.facility_relationship: review state; only approved rows count; a child
  has at most one approved campus parent; reversed pairs are refused.
- ref.county, ref.zcta: local Census lookup tables (no third-party geocoding
  at search time).
- ref.code.descriptor_short: HCPCS short descriptor (same CPT licence rule).
- src.reference_load (+ rejects): lineage for every reference-data load.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REFERENCE_DATASETS = [
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
]


def _q(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def upgrade() -> None:
    # ----------------------------------------------------------- facility
    op.execute("ALTER TABLE ref.facility DROP CONSTRAINT facility_ccn_check")
    op.execute("""
    ALTER TABLE ref.facility ADD CONSTRAINT facility_ccn_format CHECK (
        ccn ~ '^[0-9A-Z]{6}$'            -- hospitals (e.g. 290001)
        OR ccn ~ '^[0-9]{2}C[0-9]{7}$'   -- ambulatory surgical centers (e.g. 29C0001035)
    )""")
    op.execute("""
    ALTER TABLE ref.facility
        ADD COLUMN cms_facility_type_raw   text,
        ADD COLUMN county_name             text,
        ADD COLUMN geocode_precision       text
            CHECK (geocode_precision IN ('address', 'zcta_centroid')),
        ADD COLUMN geocoded_at             timestamptz,
        ADD COLUMN health_system_source    text,
        ADD COLUMN source_last_seen_at     timestamptz,
        ADD CONSTRAINT facility_geocode_precision_pairs
            CHECK ((geom IS NULL) = (geocode_precision IS NULL)),
        ADD CONSTRAINT facility_health_system_sourced
            CHECK (health_system_id IS NULL OR health_system_source IS NOT NULL)
    """)

    # ------------------------------------------------------ health system
    op.execute("ALTER TABLE ref.health_system DROP CONSTRAINT health_system_name_key")
    op.execute("""
    ALTER TABLE ref.health_system
        ADD COLUMN source            text NOT NULL DEFAULT 'manual',
        ADD COLUMN source_system_id  text,
        ADD COLUMN source_year       smallint,
        ADD COLUMN hq_city           text,
        ADD COLUMN hq_state          char(2) CHECK (hq_state ~ '^[A-Z]{2}$'),
        ADD COLUMN updated_at        timestamptz NOT NULL DEFAULT now(),
        ADD CONSTRAINT health_system_source_id_unique UNIQUE (source, source_system_id),
        ADD CONSTRAINT health_system_external_needs_id
            CHECK (source = 'manual' OR source_system_id IS NOT NULL)
    """)

    # ----------------------------------------------------- facility alias
    op.execute("""
    ALTER TABLE ref.facility_alias
        ADD COLUMN alias_normalized text,
        ADD COLUMN alias_type       text NOT NULL DEFAULT 'other'
            CHECK (alias_type IN ('cms_name', 'ahrq_name', 'nppes_name', 'dba',
                                  'former_name', 'mrf_name', 'other')),
        ADD COLUMN match_basis      text NOT NULL DEFAULT 'manual'
            CHECK (match_basis IN ('ccn', 'npi', 'manual')),
        ADD COLUMN review_state     ref.review_state NOT NULL DEFAULT 'proposed',
        ADD COLUMN reviewed_by      text,
        ADD COLUMN reviewed_at      timestamptz,
        ADD COLUMN created_at       timestamptz NOT NULL DEFAULT now()
    """)
    op.execute("UPDATE ref.facility_alias SET alias_normalized = lower(alias)")
    op.execute("ALTER TABLE ref.facility_alias ALTER COLUMN alias_normalized SET NOT NULL")
    # An alias linked through a shared identifier (CCN, NPI) is evidence by itself;
    # any other approved alias needs a named reviewer.
    op.execute("""
    ALTER TABLE ref.facility_alias ADD CONSTRAINT facility_alias_approval_evidence CHECK (
        review_state <> 'approved'
        OR match_basis IN ('ccn', 'npi')
        OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)
    )""")
    # Not unique: two different facilities can legitimately share a name.
    op.execute(
        "CREATE INDEX facility_alias_normalized_idx ON ref.facility_alias (alias_normalized)"
    )

    # ---------------------------------------------- facility relationship
    op.execute("""
    ALTER TABLE ref.facility_relationship
        ADD COLUMN review_state ref.review_state NOT NULL DEFAULT 'proposed',
        ADD COLUMN reviewed_by  text,
        ADD COLUMN reviewed_at  timestamptz,
        ADD COLUMN evidence     text,
        ADD COLUMN created_at   timestamptz NOT NULL DEFAULT now(),
        ADD CONSTRAINT facility_relationship_approval_evidence CHECK (
            review_state <> 'approved'
            OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL AND evidence IS NOT NULL)
        )
    """)
    op.execute("""
    CREATE UNIQUE INDEX facility_relationship_one_campus_parent
    ON ref.facility_relationship (child_facility_id)
    WHERE relationship_type = 'campus_of' AND review_state = 'approved'""")
    op.execute("""
    CREATE FUNCTION ref.refuse_reversed_relationship() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM ref.facility_relationship
            WHERE parent_facility_id = NEW.child_facility_id
              AND child_facility_id = NEW.parent_facility_id
              AND relationship_type = NEW.relationship_type
              AND review_state <> 'rejected'
        ) THEN
            RAISE EXCEPTION 'reversed % relationship already exists', NEW.relationship_type
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END $$""")
    op.execute("""
    CREATE TRIGGER facility_relationship_no_reverse
    BEFORE INSERT OR UPDATE ON ref.facility_relationship
    FOR EACH ROW EXECUTE FUNCTION ref.refuse_reversed_relationship()""")

    # ------------------------------------------------- census lookups
    op.execute("""
    CREATE TABLE ref.county (
        county_fips   char(5) PRIMARY KEY CHECK (county_fips ~ '^[0-9]{5}$'),
        state_code    char(2) NOT NULL CHECK (state_code ~ '^[A-Z]{2}$'),
        name          text NOT NULL,
        source        text NOT NULL
    )""")
    op.execute("CREATE INDEX county_state_idx ON ref.county (state_code)")

    op.execute("""
    CREATE TABLE ref.zcta (
        zcta5            char(5) PRIMARY KEY CHECK (zcta5 ~ '^[0-9]{5}$'),
        state_code       char(2) NOT NULL CHECK (state_code ~ '^[A-Z]{2}$'),
        county_fips      char(5) NOT NULL REFERENCES ref.county(county_fips) ON DELETE RESTRICT,
        crosses_counties boolean NOT NULL,
        aland_m2         bigint NOT NULL CHECK (aland_m2 >= 0),
        geom             geography(Point, 4326) NOT NULL,
        gazetteer_year   smallint NOT NULL,
        source           text NOT NULL
    )""")
    op.execute("CREATE INDEX zcta_geom_gix ON ref.zcta USING gist (geom)")
    op.execute("CREATE INDEX zcta_state_idx ON ref.zcta (state_code)")

    # -------------------------------------------------------------- codes
    op.execute("""
    ALTER TABLE ref.code
        ADD COLUMN descriptor_short text,
        ADD CONSTRAINT code_short_descriptor_licence
            CHECK (system <> 'CPT' OR descriptor_short IS NULL OR descriptor_licensed),
        ADD CONSTRAINT code_short_descriptor_sourced
            CHECK (descriptor_short IS NULL OR descriptor_source IS NOT NULL)
    """)

    # ------------------------------------------------- reference lineage
    datasets = ", ".join(_q(d) for d in REFERENCE_DATASETS)
    op.execute(f"""
    CREATE TABLE src.reference_load (
        id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        dataset         text NOT NULL CHECK (dataset IN ({datasets})),
        source_url      text,
        source_file     text,
        source_modified date,
        sha256          char(64) CHECK (sha256 ~ '^[0-9a-f]{{64}}$'),
        bytes           bigint CHECK (bytes >= 0),
        parameters      jsonb NOT NULL DEFAULT '{{}}',
        started_at      timestamptz NOT NULL DEFAULT now(),
        finished_at     timestamptz,
        status          text NOT NULL DEFAULT 'running'
            CHECK (status IN ('running', 'succeeded', 'failed')),
        rows_in         bigint CHECK (rows_in >= 0),
        rows_loaded     bigint CHECK (rows_loaded >= 0),
        rows_rejected   bigint CHECK (rows_rejected >= 0),
        summary         jsonb,
        error           text,
        CHECK (source_url IS NOT NULL OR source_file IS NOT NULL),
        CHECK (status = 'running' OR finished_at IS NOT NULL),
        CHECK (status <> 'failed' OR error IS NOT NULL)
    )""")
    op.execute("""
    CREATE TABLE src.reference_reject (
        id        bigserial PRIMARY KEY,
        load_id   uuid NOT NULL REFERENCES src.reference_load(id) ON DELETE CASCADE,
        row_ref   text NOT NULL,
        severity  src.severity NOT NULL,
        rule      text NOT NULL,
        message   text NOT NULL
    )""")
    op.execute("CREATE INDEX reference_reject_load_idx ON src.reference_reject (load_id)")

    # ------------------------------------------------------------- grants
    api_role = os.environ.get("PS_API_ROLE", "ps_api")
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", api_role):
        raise ValueError(f"PS_API_ROLE is not a plain role name: {api_role!r}")
    op.execute(f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {_q(api_role)}) THEN
            EXECUTE 'GRANT SELECT ON ref.county, ref.zcta TO {api_role}';
        ELSE
            RAISE NOTICE 'role % not found; API grants skipped', {_q(api_role)};
        END IF;
    END $$""")


def downgrade() -> None:
    op.execute("DROP TABLE src.reference_reject")
    op.execute("DROP TABLE src.reference_load")
    op.execute("""
    ALTER TABLE ref.code
        DROP CONSTRAINT code_short_descriptor_sourced,
        DROP CONSTRAINT code_short_descriptor_licence,
        DROP COLUMN descriptor_short""")
    op.execute("DROP TABLE ref.zcta")
    op.execute("DROP TABLE ref.county")

    op.execute("DROP TRIGGER facility_relationship_no_reverse ON ref.facility_relationship")
    op.execute("DROP FUNCTION ref.refuse_reversed_relationship()")
    op.execute("DROP INDEX ref.facility_relationship_one_campus_parent")
    op.execute("""
    ALTER TABLE ref.facility_relationship
        DROP CONSTRAINT facility_relationship_approval_evidence,
        DROP COLUMN created_at, DROP COLUMN evidence, DROP COLUMN reviewed_at,
        DROP COLUMN reviewed_by, DROP COLUMN review_state""")

    op.execute("DROP INDEX ref.facility_alias_normalized_idx")
    op.execute("""
    ALTER TABLE ref.facility_alias
        DROP CONSTRAINT facility_alias_approval_evidence,
        DROP COLUMN created_at, DROP COLUMN reviewed_at, DROP COLUMN reviewed_by,
        DROP COLUMN review_state, DROP COLUMN match_basis, DROP COLUMN alias_type,
        DROP COLUMN alias_normalized""")

    op.execute("""
    ALTER TABLE ref.health_system
        DROP CONSTRAINT health_system_external_needs_id,
        DROP CONSTRAINT health_system_source_id_unique,
        DROP COLUMN updated_at, DROP COLUMN hq_state, DROP COLUMN hq_city,
        DROP COLUMN source_year, DROP COLUMN source_system_id, DROP COLUMN source""")
    # Fails if two systems now share a name; resolve by hand before downgrading.
    op.execute("ALTER TABLE ref.health_system ADD CONSTRAINT health_system_name_key UNIQUE (name)")

    op.execute("""
    ALTER TABLE ref.facility
        DROP CONSTRAINT facility_health_system_sourced,
        DROP CONSTRAINT facility_geocode_precision_pairs,
        DROP COLUMN source_last_seen_at, DROP COLUMN health_system_source,
        DROP COLUMN geocoded_at, DROP COLUMN geocode_precision,
        DROP COLUMN county_name, DROP COLUMN cms_facility_type_raw""")
    op.execute("ALTER TABLE ref.facility DROP CONSTRAINT facility_ccn_format")
    # Fails if ASC rows (10-character CCNs) exist; delete them before downgrading.
    op.execute(
        "ALTER TABLE ref.facility ADD CONSTRAINT facility_ccn_check CHECK (ccn ~ '^[0-9A-Z]{6}$')"
    )
