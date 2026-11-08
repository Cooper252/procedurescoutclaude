"""Every published billing code is searchable; providers price by code and build packages.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-08

ref.code_index lists every code that appears in published hospital prices,
with the description hospitals most often publish for it (shown labeled as
the hospitals' wording, D-002) and how many places publish it. Searching by
any of these codes needs no approval, so the standard service list only has
to cover friendly names, not every procedure (D-045).

Providers can price an approved standard service OR an official billing code
(prov.listing_price.code_system/code, which must exist in ref.code), sell a
number of sessions for one price (quantity), and build their own packages
from those pieces (prov.package, prov.package_item) without new approvals.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PIECE_CHECK = """
    CHECK ((procedure_id IS NULL) <> (code IS NULL)),
    CHECK ((code IS NULL) = (code_system IS NULL))"""


def upgrade() -> None:
    op.execute("""
    CREATE TABLE ref.code_index (
        system               ref.code_system NOT NULL,
        code                 text NOT NULL,
        hospital_description text,
        facilities           integer NOT NULL CHECK (facilities > 0),
        prices               bigint NOT NULL CHECK (prices > 0),
        updated_at           timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (system, code)
    )""")
    op.execute(
        "CREATE INDEX code_index_description_idx ON ref.code_index "
        "USING gin (to_tsvector('english', coalesce(hospital_description, '')))"
    )

    # provider prices: an approved service OR an official code; sessions per price
    op.execute("ALTER TABLE prov.listing_price ALTER COLUMN procedure_id DROP NOT NULL")
    op.execute("""
    ALTER TABLE prov.listing_price
        ADD COLUMN code_system ref.code_system,
        ADD COLUMN code text,
        ADD COLUMN quantity integer NOT NULL DEFAULT 1 CHECK (quantity BETWEEN 1 AND 100),
        ADD CONSTRAINT listing_price_piece_check CHECK ((procedure_id IS NULL) <> (code IS NULL)),
        ADD CONSTRAINT listing_price_code_pair_check CHECK ((code IS NULL) = (code_system IS NULL))""")
    op.execute(
        "ALTER TABLE prov.listing_price DROP CONSTRAINT listing_price_facility_id_procedure_id_key"
    )
    op.execute(
        "CREATE UNIQUE INDEX listing_price_service_once ON prov.listing_price "
        "(facility_id, procedure_id, quantity) WHERE procedure_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX listing_price_code_once ON prov.listing_price "
        "(facility_id, code_system, code, quantity) WHERE code IS NOT NULL"
    )
    op.execute("""
    CREATE OR REPLACE FUNCTION prov.check_listing_service() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.procedure_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM ref.procedure
            WHERE id = NEW.procedure_id AND review_state = 'approved') THEN
            RAISE EXCEPTION 'providers can only price approved services from the standard list';
        END IF;
        IF NEW.code IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM ref.code WHERE system = NEW.code_system AND code = NEW.code) THEN
            RAISE EXCEPTION 'unknown billing code';
        END IF;
        RETURN NEW;
    END $$""")

    op.execute("""
    CREATE TABLE prov.package (
        id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        facility_id uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        name        text NOT NULL CHECK (length(name) BETWEEN 3 AND 80),
        price       numeric NOT NULL CHECK (price > 0),
        status      text NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'pending_review', 'published', 'withdrawn')),
        reviewed_by text,
        reviewed_at timestamptz,
        created_at  timestamptz NOT NULL DEFAULT now(),
        CHECK (status <> 'published' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
    )""")
    op.execute(f"""
    CREATE TABLE prov.package_item (
        id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        package_id   uuid NOT NULL REFERENCES prov.package(id) ON DELETE CASCADE,
        procedure_id uuid REFERENCES ref.procedure(id) ON DELETE RESTRICT,
        code_system  ref.code_system,
        code         text,
        quantity     integer NOT NULL DEFAULT 1 CHECK (quantity BETWEEN 1 AND 100),
        {PIECE_CHECK.strip()}
    )""")
    op.execute("""
    CREATE TRIGGER package_item_uses_standard_piece BEFORE INSERT OR UPDATE ON prov.package_item
    FOR EACH ROW EXECUTE FUNCTION prov.check_listing_service()""")

    api_role = os.environ.get("PS_API_ROLE", "ps_api")
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", api_role):
        raise ValueError(f"PS_API_ROLE is not a plain role name: {api_role!r}")
    op.execute(f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{api_role}') THEN
            EXECUTE 'GRANT SELECT ON ref.code_index TO {api_role}';
        END IF;
    END $$""")


def downgrade() -> None:
    op.execute("DROP TABLE prov.package_item")
    op.execute("DROP TABLE prov.package")
    op.execute("DROP INDEX prov.listing_price_service_once")
    op.execute("DROP INDEX prov.listing_price_code_once")
    op.execute("DELETE FROM prov.listing_price WHERE procedure_id IS NULL")
    op.execute("""
    ALTER TABLE prov.listing_price
        DROP CONSTRAINT listing_price_piece_check,
        DROP CONSTRAINT listing_price_code_pair_check,
        DROP COLUMN code_system, DROP COLUMN code, DROP COLUMN quantity,
        ALTER COLUMN procedure_id SET NOT NULL,
        ADD CONSTRAINT listing_price_facility_id_procedure_id_key UNIQUE (facility_id, procedure_id)""")
    op.execute("""
    CREATE OR REPLACE FUNCTION prov.check_listing_service() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM ref.procedure
                       WHERE id = NEW.procedure_id AND review_state = 'approved') THEN
            RAISE EXCEPTION 'providers can only price approved services from the standard list';
        END IF;
        RETURN NEW;
    END $$""")
    op.execute("DROP TABLE ref.code_index")
