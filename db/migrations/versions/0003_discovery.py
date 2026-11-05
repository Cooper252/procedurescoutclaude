"""Phase 2, step 1: hospital websites and cms-hpt.txt discovery.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-05

- ref.facility: website provenance (a website is used only after a named
  person approved it) and a reason when a facility is exempt from publishing
  price files (e.g. federally owned hospitals).
- src.hpt_txt_fetch: each attempt to read https://<site>/cms-hpt.txt.
- src.hpt_txt_entry: one row per location block in a cms-hpt.txt, exactly as
  published, with the facility it was matched to (exact name match only) or
  why it was not matched.
- Adds 'facility_websites' and 'cms_hpt_txt_discovery' to the reference-load
  datasets.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATASETS_0002 = [
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
DATASETS_0003 = [*DATASETS_0002, "facility_websites", "cms_hpt_txt_discovery"]


def _q(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _dataset_check(datasets: list[str]) -> None:
    op.execute("ALTER TABLE src.reference_load DROP CONSTRAINT reference_load_dataset_check")
    op.execute(
        "ALTER TABLE src.reference_load ADD CONSTRAINT reference_load_dataset_check "
        f"CHECK (dataset IN ({', '.join(_q(d) for d in datasets)}))"
    )


def upgrade() -> None:
    op.execute("""
    ALTER TABLE ref.facility
        ADD COLUMN website_evidence_url  text,
        ADD COLUMN website_reviewed_by   text,
        ADD COLUMN website_reviewed_at   timestamptz,
        ADD COLUMN hpt_exempt_reason     text,
        ADD CONSTRAINT facility_website_reviewed CHECK (
            website IS NULL
            OR (website ~ '^https://[^/?#]+$'
                AND website_reviewed_by IS NOT NULL AND website_reviewed_at IS NOT NULL)
        )
    """)
    _dataset_check(DATASETS_0003)

    op.execute("""
    CREATE TABLE src.hpt_txt_fetch (
        id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        site         text NOT NULL CHECK (site ~ '^https://[^/?#]+$'),
        url          text NOT NULL,
        fetched_at   timestamptz NOT NULL DEFAULT now(),
        http_status  smallint,
        final_url    text,
        sha256       char(64) CHECK (sha256 ~ '^[0-9a-f]{64}$'),
        bytes        bigint CHECK (bytes >= 0),
        error        text,
        entries      integer CHECK (entries >= 0),
        CHECK ((sha256 IS NULL) = (bytes IS NULL))
    )""")
    op.execute("CREATE INDEX hpt_txt_fetch_site_idx ON src.hpt_txt_fetch (site, fetched_at)")

    op.execute("""
    CREATE TABLE src.hpt_txt_entry (
        id                 bigserial PRIMARY KEY,
        fetch_id           uuid NOT NULL REFERENCES src.hpt_txt_fetch(id) ON DELETE CASCADE,
        block_index        integer NOT NULL CHECK (block_index >= 0),
        location_name      text,
        source_page_url    text,
        mrf_url            text,
        contact_name       text,
        contact_email      text,
        facility_id        uuid REFERENCES ref.facility(id) ON DELETE SET NULL,
        match_status       text NOT NULL
            CHECK (match_status IN ('matched', 'unmatched', 'ambiguous', 'invalid')),
        problems           text[] NOT NULL DEFAULT '{}',
        UNIQUE (fetch_id, block_index),
        CHECK ((match_status = 'matched') = (facility_id IS NOT NULL))
    )""")
    op.execute("CREATE INDEX hpt_txt_entry_facility_idx ON src.hpt_txt_entry (facility_id)")
    op.execute("CREATE INDEX hpt_txt_entry_mrf_idx ON src.hpt_txt_entry (mrf_url)")

    # Discovery tables are internal: the API role is granted nothing here.


def downgrade() -> None:
    op.execute("DROP TABLE src.hpt_txt_entry")
    op.execute("DROP TABLE src.hpt_txt_fetch")
    op.execute(
        "DELETE FROM src.reference_load WHERE dataset IN "
        "('facility_websites', 'cms_hpt_txt_discovery')"
    )
    _dataset_check(DATASETS_0002)
    op.execute("""
    ALTER TABLE ref.facility
        DROP CONSTRAINT facility_website_reviewed,
        DROP COLUMN hpt_exempt_reason, DROP COLUMN website_reviewed_at,
        DROP COLUMN website_reviewed_by, DROP COLUMN website_evidence_url""")
