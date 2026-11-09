"""Provider prices, specials and packages: entered in the portal, reviewed, shown.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-08

- A live provider price stays live while a change waits for review
  (prov.listing_price.proposed_price); approving swaps it in.
- Review notes and reviewer fields for specials and packages.
- prov.published_listing / published_offer / published_package(+_item): what the
  public API may read (published rows only, no private columns).
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIEWS = (
    "prov.published_listing, prov.published_offer, prov.published_package, "
    "prov.published_package_item"
)


def _role(env: str, default: str) -> str:
    role = os.environ.get(env, default)
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", role):
        raise ValueError(f"{env} is not a plain role name: {role!r}")
    return role


def upgrade() -> None:
    op.execute("""
    ALTER TABLE prov.listing_price
        ADD COLUMN proposed_price numeric CHECK (proposed_price > 0),
        ADD COLUMN proposed_at    timestamptz,
        ADD COLUMN review_note    text CHECK (review_note IS NULL OR length(review_note) <= 500),
        ADD CONSTRAINT listing_proposed_only_when_live
            CHECK (proposed_price IS NULL OR status = 'published')""")
    op.execute("""
    ALTER TABLE prov.offer
        ADD COLUMN reviewed_by text,
        ADD COLUMN reviewed_at timestamptz,
        ADD COLUMN review_note text CHECK (review_note IS NULL OR length(review_note) <= 500),
        ADD CONSTRAINT offer_published_reviewed
            CHECK (status <> 'published' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))""")
    op.execute("""
    ALTER TABLE prov.package
        ADD COLUMN description text CHECK (description IS NULL OR length(description) <= 500),
        ADD COLUMN review_note text CHECK (review_note IS NULL OR length(review_note) <= 500)""")

    # a withdrawn special no longer has to be lower than the regular price
    op.execute("""
    CREATE OR REPLACE FUNCTION prov.check_offer() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE regular numeric;
    BEGIN
        IF NEW.status = 'withdrawn' THEN
            RETURN NEW;
        END IF;
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
    CREATE VIEW prov.published_listing AS
    SELECT lp.id, lp.facility_id, p.slug AS service_slug, p.consumer_name AS service_name,
           p.unit, lp.code_system::text AS code_system, lp.code, lp.quantity,
           lp.regular_price, lp.reviewed_at
    FROM prov.listing_price lp LEFT JOIN ref.procedure p ON p.id = lp.procedure_id
    WHERE lp.status = 'published'""")
    op.execute("""
    CREATE VIEW prov.published_offer AS
    SELECT o.id, o.listing_price_id, o.kind, o.who, o.offer_price, o.percent_off,
           o.amount_off, o.starts_on, o.ends_on, o.terms
    FROM prov.offer o JOIN prov.listing_price lp ON lp.id = o.listing_price_id
    WHERE o.status = 'published' AND lp.status = 'published'""")
    op.execute("""
    CREATE VIEW prov.published_package AS
    SELECT id, facility_id, name, description, price, reviewed_at
    FROM prov.package WHERE status = 'published'""")
    op.execute("""
    CREATE VIEW prov.published_package_item AS
    SELECT i.package_id, p.slug AS service_slug, p.consumer_name AS service_name,
           i.code_system::text AS code_system, i.code, i.quantity
    FROM prov.package_item i
    JOIN prov.package k ON k.id = i.package_id AND k.status = 'published'
    LEFT JOIN ref.procedure p ON p.id = i.procedure_id""")

    api_role = _role("PS_API_ROLE", "ps_api")
    portal_role = _role("PS_PORTAL_ROLE", "ps_portal")
    op.execute(f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{api_role}') THEN
            EXECUTE 'GRANT SELECT ON {VIEWS} TO {api_role}';
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{portal_role}') THEN
            EXECUTE 'GRANT SELECT ON {VIEWS} TO {portal_role}';
            EXECUTE 'GRANT DELETE ON prov.package_item TO {portal_role}';
        END IF;
    END $$""")


def downgrade() -> None:
    op.execute("""
    CREATE OR REPLACE FUNCTION prov.check_offer() RETURNS trigger LANGUAGE plpgsql AS $$
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
    for v in VIEWS.split(", "):
        op.execute(f"DROP VIEW IF EXISTS {v}")
    op.execute("ALTER TABLE prov.package DROP COLUMN description, DROP COLUMN review_note")
    op.execute(
        "ALTER TABLE prov.offer DROP CONSTRAINT offer_published_reviewed, "
        "DROP COLUMN reviewed_by, DROP COLUMN reviewed_at, DROP COLUMN review_note"
    )
    op.execute(
        "ALTER TABLE prov.listing_price DROP CONSTRAINT listing_proposed_only_when_live, "
        "DROP COLUMN proposed_price, DROP COLUMN proposed_at, DROP COLUMN review_note"
    )
