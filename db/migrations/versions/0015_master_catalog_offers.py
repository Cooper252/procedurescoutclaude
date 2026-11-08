"""One standard service list for every provider type, and provider specials.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-08

Providers pick services from ref.procedure (they never type their own names),
so "teeth cleaning", "full teeth cleaning" and "cleaning with X-rays" cannot
become three different things. Each service says what it includes and which
kinds of provider offer it. New units cover dental, eye and med-spa pricing.

prov.listing_price is a provider's own regular price for one standard service
and prov.offer a special on it (new-patient price, percent off, dollars off).
Specials are always shown as specials and never replace the regular price in
comparisons (D-042). The API role gets no access until the provider portal
and its review step exist.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_UNITS = (
    "per_service",
    "per_unit",
    "per_area",
    "per_syringe",
    "per_session",
    "per_visit",
    "per_day",
    "per_month",
)
UNITS = (
    *OLD_UNITS,
    "per_tooth",
    "per_quadrant",
    "per_arch",
    "per_eye",
    "per_vial",
    "per_injection",
)


def _units_check(units: Sequence[str]) -> str:
    quoted = ", ".join(f"'{u}'" for u in units)
    return f"CHECK (unit IN ({quoted}))"


def upgrade() -> None:
    op.execute("ALTER TABLE ref.procedure DROP CONSTRAINT procedure_unit_check")
    op.execute(
        f"ALTER TABLE ref.procedure ADD CONSTRAINT procedure_unit_check {_units_check(UNITS)}"
    )
    op.execute("""
    ALTER TABLE ref.procedure
        ADD COLUMN includes text CHECK (includes IS NULL OR length(includes) <= 600)""")
    op.execute("""
    CREATE TABLE ref.procedure_provider_type (
        procedure_id  uuid NOT NULL REFERENCES ref.procedure(id) ON DELETE CASCADE,
        provider_type text NOT NULL REFERENCES ref.provider_type(code) ON DELETE CASCADE,
        PRIMARY KEY (procedure_id, provider_type)
    )""")

    op.execute("CREATE SCHEMA IF NOT EXISTS prov")
    op.execute("""
    CREATE TABLE prov.listing_price (
        id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        facility_id   uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        procedure_id  uuid NOT NULL REFERENCES ref.procedure(id) ON DELETE RESTRICT,
        regular_price numeric NOT NULL CHECK (regular_price > 0),
        status        text NOT NULL DEFAULT 'draft'
                      CHECK (status IN ('draft', 'pending_review', 'published', 'withdrawn')),
        submitted_by  text,
        reviewed_by   text,
        reviewed_at   timestamptz,
        created_at    timestamptz NOT NULL DEFAULT now(),
        updated_at    timestamptz NOT NULL DEFAULT now(),
        UNIQUE (facility_id, procedure_id),
        CHECK (status <> 'published' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
    )""")
    op.execute("""
    CREATE TABLE prov.offer (
        id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        listing_price_id uuid NOT NULL REFERENCES prov.listing_price(id) ON DELETE CASCADE,
        kind             text NOT NULL
                         CHECK (kind IN ('special_price', 'percent_off', 'amount_off')),
        who              text NOT NULL CHECK (who IN ('new_patients', 'everyone')),
        offer_price      numeric CHECK (offer_price > 0),
        percent_off      numeric CHECK (percent_off > 0 AND percent_off < 100),
        amount_off       numeric CHECK (amount_off > 0),
        starts_on        date NOT NULL,
        ends_on          date,
        terms            text CHECK (terms IS NULL OR length(terms) <= 300),
        status           text NOT NULL DEFAULT 'draft'
                         CHECK (status IN ('draft', 'pending_review', 'published', 'withdrawn')),
        created_at       timestamptz NOT NULL DEFAULT now(),
        CHECK (ends_on IS NULL OR ends_on >= starts_on),
        CHECK ((kind = 'special_price') = (offer_price IS NOT NULL)),
        CHECK ((kind = 'percent_off') = (percent_off IS NOT NULL)),
        CHECK ((kind = 'amount_off') = (amount_off IS NOT NULL))
    )""")
    # an offer must actually be lower than the regular price it is attached to
    op.execute("""
    CREATE FUNCTION prov.check_offer() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE regular numeric;
    BEGIN
        SELECT regular_price INTO regular FROM prov.listing_price WHERE id = NEW.listing_price_id;
        IF NEW.kind = 'special_price' AND NEW.offer_price >= regular THEN
            RAISE EXCEPTION 'special price must be lower than the regular price';
        END IF;
        IF NEW.kind = 'amount_off' AND NEW.amount_off >= regular THEN
            RAISE EXCEPTION 'amount off must be less than the regular price';
        END IF;
        RETURN NEW;
    END $$""")
    op.execute("""
    CREATE TRIGGER offer_lower_than_regular BEFORE INSERT OR UPDATE ON prov.offer
    FOR EACH ROW EXECUTE FUNCTION prov.check_offer()""")
    # only approved standard services can be priced by providers
    op.execute("""
    CREATE FUNCTION prov.check_listing_service() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM ref.procedure
                       WHERE id = NEW.procedure_id AND review_state = 'approved') THEN
            RAISE EXCEPTION 'providers can only price approved services from the standard list';
        END IF;
        RETURN NEW;
    END $$""")
    op.execute("""
    CREATE TRIGGER listing_uses_standard_service BEFORE INSERT OR UPDATE ON prov.listing_price
    FOR EACH ROW EXECUTE FUNCTION prov.check_listing_service()""")

    api_role = os.environ.get("PS_API_ROLE", "ps_api")
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", api_role):
        raise ValueError(f"PS_API_ROLE is not a plain role name: {api_role!r}")
    op.execute(f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{api_role}') THEN
            EXECUTE 'GRANT SELECT ON ref.procedure_provider_type TO {api_role}';
        END IF;
    END $$""")


def downgrade() -> None:
    op.execute("DROP SCHEMA prov CASCADE")
    op.execute("DROP TABLE ref.procedure_provider_type")
    op.execute("ALTER TABLE ref.procedure DROP COLUMN includes")
    op.execute("ALTER TABLE ref.procedure DROP CONSTRAINT procedure_unit_check")
    op.execute(
        f"ALTER TABLE ref.procedure ADD CONSTRAINT procedure_unit_check {_units_check(OLD_UNITS)}"
    )
