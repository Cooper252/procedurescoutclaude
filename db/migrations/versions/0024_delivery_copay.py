"""Provider prices: in person or online, and what insured patients pay.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-11

Cooper (2026-11-11) asked for in-person AND telehealth pricing and copays:
- delivery: 'in_person', 'online' or 'both'. The same service can have one
  price in person and another online, so delivery joins the "listed once" rules.
- copay_kind: NULL (not said), 'standard' ("with insurance, your plan's usual
  copay applies") or 'amount' with copay_amount (the copay the practice
  usually charges insured patients). A copay is never shown as a cash price.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIEW = """
    CREATE OR REPLACE VIEW prov.published_listing AS
    SELECT lp.id, lp.facility_id, p.slug AS service_slug, p.consumer_name AS service_name,
           p.unit, lp.code_system::text AS code_system, lp.code, lp.quantity,
           lp.regular_price, lp.reviewed_at{extra}
    FROM prov.listing_price lp LEFT JOIN ref.procedure p ON p.id = lp.procedure_id
    WHERE lp.status = 'published' AND bill.listing_shown(lp.facility_id)"""


def upgrade() -> None:
    op.execute("""
    ALTER TABLE prov.listing_price
        ADD COLUMN delivery text NOT NULL DEFAULT 'in_person'
            CHECK (delivery IN ('in_person', 'online', 'both')),
        ADD COLUMN copay_kind text CHECK (copay_kind IN ('standard', 'amount')),
        ADD COLUMN copay_amount numeric CHECK (copay_amount > 0),
        ADD CONSTRAINT listing_copay_pair CHECK (
            (copay_kind = 'amount') = (copay_amount IS NOT NULL))""")
    op.execute("DROP INDEX prov.listing_price_service_once")
    op.execute("DROP INDEX prov.listing_price_code_once")
    op.execute(
        "CREATE UNIQUE INDEX listing_price_service_once ON prov.listing_price "
        "(facility_id, procedure_id, quantity, delivery) WHERE procedure_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX listing_price_code_once ON prov.listing_price "
        "(facility_id, code_system, code, quantity, delivery) WHERE code IS NOT NULL"
    )
    # new columns go at the end, so the view keeps its grants
    op.execute(VIEW.format(extra=", lp.delivery, lp.copay_kind, lp.copay_amount"))


def downgrade() -> None:
    op.execute("DROP VIEW prov.published_listing")
    op.execute(VIEW.format(extra=""))
    op.execute("DROP INDEX prov.listing_price_service_once")
    op.execute("DROP INDEX prov.listing_price_code_once")
    op.execute(
        "CREATE UNIQUE INDEX listing_price_service_once ON prov.listing_price "
        "(facility_id, procedure_id, quantity) WHERE procedure_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX listing_price_code_once ON prov.listing_price "
        "(facility_id, code_system, code, quantity) WHERE code IS NOT NULL"
    )
    op.execute("""
    ALTER TABLE prov.listing_price DROP CONSTRAINT listing_copay_pair,
        DROP COLUMN copay_amount, DROP COLUMN copay_kind, DROP COLUMN delivery""")
