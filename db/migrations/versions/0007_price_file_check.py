"""Reviewed co-listed locations; price files read and checked without keeping them.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-06

1. src.hpt_txt_entry.match_status gains 'co_listed': a location that a person
   approved as listed inside one hospital's own price file (for example the
   hospital's freestanding ERs). co_listed_with names that hospital. Such an
   entry no longer stops the file from being assigned to the hospital, and the
   location itself is not treated as a facility of ours.
2. src.transparency_file can describe a file that was downloaded, checked and
   then deleted: object_store_key becomes optional (NULL = not kept), and the
   check results are stored beside it (header exactly as published, counts).
3. Adds the 'price_file_check' reference-load dataset.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATASETS_0003 = [
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
]
DATASETS_0007 = [*DATASETS_0003, "price_file_check"]


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
    ALTER TABLE src.hpt_txt_entry
        DROP CONSTRAINT hpt_txt_entry_match_status_check,
        ADD COLUMN co_listed_with uuid REFERENCES ref.facility(id) ON DELETE SET NULL,
        ADD CONSTRAINT hpt_txt_entry_match_status_check CHECK (
            match_status IN ('matched', 'unmatched', 'ambiguous', 'invalid', 'co_listed')),
        ADD CONSTRAINT hpt_txt_entry_co_listed_check CHECK (
            (match_status = 'co_listed') = (co_listed_with IS NOT NULL))
    """)

    op.execute("""
    ALTER TABLE src.transparency_file
        ALTER COLUMN object_store_key DROP NOT NULL,
        ADD COLUMN final_url         text,
        ADD COLUMN content_type      text,
        ADD COLUMN server_last_modified text,
        ADD COLUMN last_updated_raw  text,
        ADD COLUMN header            jsonb,
        ADD COLUMN read_summary      jsonb,
        ADD COLUMN read_error        text
    """)
    _dataset_check(DATASETS_0007)


def downgrade() -> None:
    _dataset_check(DATASETS_0003)
    op.execute("DELETE FROM src.transparency_file WHERE object_store_key IS NULL")
    op.execute("""
    ALTER TABLE src.transparency_file
        ALTER COLUMN object_store_key SET NOT NULL,
        DROP COLUMN final_url,
        DROP COLUMN content_type,
        DROP COLUMN server_last_modified,
        DROP COLUMN last_updated_raw,
        DROP COLUMN header,
        DROP COLUMN read_summary,
        DROP COLUMN read_error
    """)
    op.execute("DELETE FROM src.hpt_txt_entry WHERE match_status = 'co_listed'")
    op.execute("""
    ALTER TABLE src.hpt_txt_entry
        DROP CONSTRAINT hpt_txt_entry_co_listed_check,
        DROP CONSTRAINT hpt_txt_entry_match_status_check,
        DROP COLUMN co_listed_with,
        ADD CONSTRAINT hpt_txt_entry_match_status_check CHECK (
            match_status IN ('matched', 'unmatched', 'ambiguous', 'invalid'))
    """)
