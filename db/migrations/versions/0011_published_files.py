"""Published prices live in Parquet files; record who approved each dataset.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-08

D-033 (approved by Cooper 2026-11-08): a dataset version that a person
approves is written to one compressed Parquet file per facility in object
storage; PostgreSQL keeps the manifest.

- src.dataset_version: reviewed_by, reviewed_at, review_note (a review always
  names who and when; publish.approve refuses to publish without one).
- src.published_file: one row per published Parquet file (key, size,
  SHA-256, row count, sums used to prove the copy is exact), retired when the
  facility's next dataset is published.
- price.published_file: the current files only; the API role can read this
  view and nothing else about prices except price.published_price.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE src.dataset_version
        ADD COLUMN reviewed_by text,
        ADD COLUMN reviewed_at timestamptz,
        ADD COLUMN review_note text,
        ADD CONSTRAINT dataset_version_published_reviewed CHECK (
            (reviewed_at IS NULL) = (reviewed_by IS NULL)
        )
    """)
    op.execute("""
    CREATE TABLE src.published_file (
        id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        dataset_version_id uuid NOT NULL UNIQUE
            REFERENCES src.dataset_version(id) ON DELETE RESTRICT,
        facility_id        uuid NOT NULL REFERENCES ref.facility(id) ON DELETE RESTRICT,
        state_code         char(2) NOT NULL CHECK (state_code ~ '^[A-Z]{2}$'),
        price_source       text NOT NULL DEFAULT 'hospital_file'
            CHECK (price_source IN ('hospital_file', 'provider_submitted', 'provider_correction')),
        object_key         text NOT NULL UNIQUE,
        bytes              bigint NOT NULL CHECK (bytes > 0),
        sha256             char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
        rows               bigint NOT NULL CHECK (rows > 0),
        amount_sum         numeric,
        percentage_sum     numeric,
        published_at       timestamptz NOT NULL DEFAULT now(),
        retired_at         timestamptz,
        CHECK (retired_at IS NULL OR retired_at >= published_at)
    )""")
    op.execute("""
    CREATE UNIQUE INDEX published_file_one_current
    ON src.published_file (facility_id, price_source) WHERE retired_at IS NULL""")
    op.execute("""
    CREATE VIEW price.published_file AS
    SELECT facility_id, state_code, price_source, object_key, bytes, sha256, rows, published_at
    FROM src.published_file WHERE retired_at IS NULL""")
    api_role = os.environ.get("PS_API_ROLE", "ps_api")
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", api_role):
        raise ValueError(f"PS_API_ROLE is not a plain role name: {api_role!r}")
    op.execute(f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{api_role}') THEN
            EXECUTE 'GRANT SELECT ON price.published_file TO {api_role}';
        END IF;
    END $$""")


def downgrade() -> None:
    op.execute("DROP VIEW price.published_file")
    op.execute("DROP TABLE src.published_file")
    op.execute("""
    ALTER TABLE src.dataset_version
        DROP CONSTRAINT dataset_version_published_reviewed,
        DROP COLUMN review_note,
        DROP COLUMN reviewed_at,
        DROP COLUMN reviewed_by
    """)
