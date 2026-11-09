"""Offices from the national provider list, listing requests, wrong-price
reports, staff sign-in, email retries, and billing (listing fee, Sponsored).

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-08

- ref.facility.taxonomy_codes (+ ref.facility_npi): offices loaded from the NPPES
  file (organizations, by taxonomy), dataset 'nppes_offices' (D-052).
- prov.listing_request: a practice not in public records asks to be added;
  a person checks it before it becomes a facility.
- prov.price_report: anyone can report a wrong price; a person looks at it.
- prov.staff: who may use the review pages (per-person accounts with the
  authenticator app, replacing the shared password, ADM-02).
- prov.outbox.attempts: email retries.
- bill.*: plans, subscriptions, Sponsored spots, Stripe events (D-051). While
  the listing fee is not in force (bill.setting 'listing_fee_starts_on' unset
  or in the future) every provider's own content shows. Once in force, a
  provider's own prices, specials, packages, homepage and photos show only
  with an active or trialing listing subscription. Public-record listings,
  hospital price files and reviews never depend on payment.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATASETS_0016 = [
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
    "hrsa_health_center_sites",
]
DATASETS_0020 = [*DATASETS_0016, "nppes_offices"]


def _role(env: str, default: str) -> str:
    role = os.environ.get(env, default)
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", role):
        raise ValueError(f"{env} is not a plain role name: {role!r}")
    return role


def _datasets(conn_datasets: list[str]) -> None:
    quoted = ", ".join("'" + d + "'" for d in conn_datasets)
    op.execute(
        "ALTER TABLE src.reference_load DROP CONSTRAINT IF EXISTS reference_load_dataset_check"
    )
    op.execute(
        "ALTER TABLE src.reference_load ADD CONSTRAINT reference_load_dataset_check "
        f"CHECK (dataset IN ({quoted}))"
    )


GATED = (
    "published_listing",
    "published_offer",
    "published_package",
    "published_package_item",
    "published_profile",
    "published_media",
)


def upgrade() -> None:
    # ---------------------------------------------------------------- offices
    op.execute("ALTER TABLE ref.facility ADD COLUMN taxonomy_codes text[] NOT NULL DEFAULT '{}'")
    op.execute(
        "ALTER TABLE ref.facility_provider_type DROP CONSTRAINT facility_provider_type_source_check"
    )
    op.execute(
        "ALTER TABLE ref.facility_provider_type ADD CONSTRAINT facility_provider_type_source_check "
        "CHECK (source IN ('cms_facility_type', 'provider', 'reviewer', 'nppes_taxonomy'))"
    )
    _datasets(DATASETS_0020)

    op.execute("""
    CREATE TABLE prov.listing_request (
        id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        account_id    uuid NOT NULL REFERENCES prov.account(id) ON DELETE CASCADE,
        name          text NOT NULL CHECK (length(name) BETWEEN 3 AND 120),
        address_line1 text NOT NULL CHECK (length(address_line1) BETWEEN 3 AND 120),
        city          text NOT NULL CHECK (length(city) BETWEEN 2 AND 60),
        state_code    char(2) NOT NULL CHECK (state_code ~ '^[A-Z]{2}$'),
        zip5          text NOT NULL CHECK (zip5 ~ '^[0-9]{5}$'),
        phone         text CHECK (phone IS NULL OR phone ~ '^[0-9+() .-]{7,25}$'),
        website       text CHECK (website IS NULL OR website ~ '^https?://'),
        provider_type text NOT NULL REFERENCES ref.provider_type(code),
        npi           text CHECK (npi IS NULL OR npi ~ '^[0-9]{10}$'),
        note          text CHECK (note IS NULL OR length(note) <= 500),
        status        text NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'approved', 'rejected')),
        facility_id   uuid REFERENCES ref.facility(id) ON DELETE SET NULL,
        reviewed_by   text,
        reviewed_at   timestamptz,
        review_note   text,
        created_at    timestamptz NOT NULL DEFAULT now(),
        CHECK (status <> 'approved' OR (facility_id IS NOT NULL AND reviewed_by IS NOT NULL))
    )""")

    # ---------------------------------------------------------- price reports
    op.execute("""
    CREATE TABLE prov.price_report (
        id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        facility_id  uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        service_key  text CHECK (service_key IS NULL OR length(service_key) <= 120),
        price_shown  text CHECK (price_shown IS NULL OR price_shown ~ '^[0-9]{1,9}(\\.[0-9]{1,15})?$'),
        problem      text NOT NULL CHECK (problem IN
                     ('price_different', 'not_offered', 'closed_or_moved', 'insurance_wrong',
                      'other')),
        details      text CHECK (details IS NULL OR length(details) <= 500),
        created_at   timestamptz NOT NULL DEFAULT now(),
        resolved_by  text,
        resolved_at  timestamptz,
        outcome      text CHECK (outcome IN ('fixed', 'no_change', 'sent_to_provider'))
    )""")
    op.execute(
        "CREATE INDEX price_report_open ON prov.price_report (created_at) WHERE resolved_at IS NULL"
    )

    # ------------------------------------------------------------------ staff
    op.execute("""
    CREATE TABLE prov.staff (
        account_id  uuid PRIMARY KEY REFERENCES prov.account(id) ON DELETE CASCADE,
        role        text NOT NULL CHECK (role IN ('reviewer', 'admin')),
        added_by    text NOT NULL,
        added_at    timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("ALTER TABLE prov.outbox ADD COLUMN attempts smallint NOT NULL DEFAULT 0")

    # ---------------------------------------------------------------- billing
    op.execute("CREATE SCHEMA IF NOT EXISTS bill")
    op.execute("""
    CREATE TABLE bill.setting (
        key    text PRIMARY KEY CHECK (key IN ('listing_fee_starts_on')),
        value  text NOT NULL,
        set_by text NOT NULL,
        set_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""
    CREATE TABLE bill.plan (
        code             text PRIMARY KEY CHECK (code ~ '^[a-z0-9_]{2,40}$'),
        name             text NOT NULL,
        kind             text NOT NULL CHECK (kind IN ('listing', 'sponsored')),
        provider_type    text REFERENCES ref.provider_type(code),  -- price differs by business
        amount           numeric NOT NULL CHECK (amount > 0),
        interval         text NOT NULL DEFAULT 'month' CHECK (interval IN ('month', 'year')),
        stripe_price_id  text,
        active           boolean NOT NULL DEFAULT true,
        approved_by      text NOT NULL,
        created_at       timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""
    CREATE TABLE bill.subscription (
        id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        facility_id            uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        account_id             uuid REFERENCES prov.account(id) ON DELETE SET NULL,
        plan_code              text NOT NULL REFERENCES bill.plan(code),
        status                 text NOT NULL CHECK (status IN
                               ('incomplete', 'trialing', 'active', 'past_due', 'canceled',
                                'unpaid', 'incomplete_expired', 'paused')),
        stripe_customer_id     text,
        stripe_subscription_id text UNIQUE,
        current_period_end     timestamptz,
        created_at             timestamptz NOT NULL DEFAULT now(),
        updated_at             timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX subscription_facility ON bill.subscription (facility_id, status)")
    op.execute("""
    CREATE TABLE bill.sponsored_slot (
        id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        subscription_id  uuid NOT NULL REFERENCES bill.subscription(id) ON DELETE CASCADE,
        facility_id      uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        service_key      text NOT NULL CHECK (service_key ~ '^(svc:[a-z0-9-]{1,80}|code:[A-Z_]{2,12}:[0-9A-Za-z.-]{1,12})$'),
        ring_miles       smallint NOT NULL CHECK (ring_miles IN (10, 25, 50)),
        created_at       timestamptz NOT NULL DEFAULT now(),
        UNIQUE (facility_id, service_key, ring_miles)
    )""")
    op.execute("""
    CREATE TABLE bill.stripe_event (
        id           text PRIMARY KEY,
        type         text NOT NULL,
        received_at  timestamptz NOT NULL DEFAULT now(),
        handled      boolean NOT NULL DEFAULT false
    )""")
    # Is a provider's own content shown? (true until the fee is in force)
    op.execute("""
    CREATE FUNCTION bill.listing_shown(f uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = bill, pg_temp AS $$
        SELECT NOT EXISTS (
                   SELECT 1 FROM bill.setting
                   WHERE key = 'listing_fee_starts_on' AND value::date <= current_date)
            OR EXISTS (
                   SELECT 1 FROM bill.subscription s JOIN bill.plan p ON p.code = s.plan_code
                   WHERE s.facility_id = f AND p.kind = 'listing'
                     AND s.status IN ('active', 'trialing'))
    $$""")
    # Sponsored facilities for one search (at most 2, never part of the results order)
    op.execute("""
    CREATE FUNCTION bill.sponsored_for(k text, lat numeric, lng numeric)
    RETURNS TABLE (facility_id uuid) LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path = bill, ref, public, pg_temp AS $$
        SELECT DISTINCT ss.facility_id
        FROM bill.sponsored_slot ss
        JOIN bill.subscription s ON s.id = ss.subscription_id
        JOIN ref.facility f ON f.id = ss.facility_id
        WHERE ss.service_key = k AND s.status IN ('active', 'trialing')
          AND f.geom IS NOT NULL AND f.status = 'active'
          AND ST_DWithin(f.geom,
                CAST(ST_SetSRID(ST_MakePoint(CAST(lng AS float8), CAST(lat AS float8)), 4326)
                     AS geography),
                ss.ring_miles * 1609.344)
          AND bill.listing_shown(ss.facility_id)
        LIMIT 2
    $$""")
    # gate the provider's own published content
    op.execute("""
    CREATE OR REPLACE VIEW prov.published_listing AS
    SELECT lp.id, lp.facility_id, p.slug AS service_slug, p.consumer_name AS service_name,
           p.unit, lp.code_system::text AS code_system, lp.code, lp.quantity,
           lp.regular_price, lp.reviewed_at
    FROM prov.listing_price lp LEFT JOIN ref.procedure p ON p.id = lp.procedure_id
    WHERE lp.status = 'published' AND bill.listing_shown(lp.facility_id)""")
    op.execute("""
    CREATE OR REPLACE VIEW prov.published_package AS
    SELECT id, facility_id, name, description, price, reviewed_at
    FROM prov.package WHERE status = 'published' AND bill.listing_shown(facility_id)""")
    op.execute("""
    CREATE OR REPLACE VIEW prov.published_profile AS
    SELECT facility_id, about, website_url, booking_url, phone, hours, languages,
           accessibility, insurance_note, social_urls, reviewed_at AS updated_at
    FROM prov.profile WHERE status = 'published' AND bill.listing_shown(facility_id)""")
    op.execute("""
    CREATE OR REPLACE VIEW prov.published_media AS
    SELECT id, facility_id, kind, object_key, content_type, width, height, alt_text
    FROM prov.media WHERE status = 'published' AND bill.listing_shown(facility_id)""")

    api_role = _role("PS_API_ROLE", "ps_api")
    portal_role = _role("PS_PORTAL_ROLE", "ps_portal")
    op.execute(f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{api_role}') THEN
            EXECUTE 'GRANT USAGE ON SCHEMA bill TO {api_role}';
            EXECUTE 'GRANT EXECUTE ON FUNCTION bill.listing_shown(uuid),
                     bill.sponsored_for(text, numeric, numeric) TO {api_role}';
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{portal_role}') THEN
            EXECUTE 'GRANT USAGE ON SCHEMA bill TO {portal_role}';
            EXECUTE 'GRANT SELECT, INSERT, UPDATE ON prov.listing_request, prov.price_report,
                     bill.subscription, bill.sponsored_slot, bill.stripe_event TO {portal_role}';
            EXECUTE 'GRANT DELETE ON bill.sponsored_slot TO {portal_role}';
            EXECUTE 'GRANT SELECT ON prov.staff, bill.plan, bill.setting TO {portal_role}';
            EXECUTE 'GRANT EXECUTE ON FUNCTION bill.listing_shown(uuid),
                     bill.sponsored_for(text, numeric, numeric) TO {portal_role}';
            EXECUTE 'GRANT SELECT ON ref.provider_type, ref.facility_provider_type
                     TO {portal_role}';
        END IF;
    END $$""")


def downgrade() -> None:
    for v, body in (
        (
            "published_listing",
            """SELECT lp.id, lp.facility_id, p.slug AS service_slug,
            p.consumer_name AS service_name, p.unit, lp.code_system::text AS code_system, lp.code,
            lp.quantity, lp.regular_price, lp.reviewed_at FROM prov.listing_price lp
            LEFT JOIN ref.procedure p ON p.id = lp.procedure_id WHERE lp.status = 'published'""",
        ),
        (
            "published_package",
            """SELECT id, facility_id, name, description, price, reviewed_at
            FROM prov.package WHERE status = 'published'""",
        ),
        (
            "published_profile",
            """SELECT facility_id, about, website_url, booking_url, phone,
            hours, languages, accessibility, insurance_note, social_urls, reviewed_at AS updated_at
            FROM prov.profile WHERE status = 'published'""",
        ),
        (
            "published_media",
            """SELECT id, facility_id, kind, object_key, content_type, width,
            height, alt_text FROM prov.media WHERE status = 'published'""",
        ),
    ):
        op.execute(f"CREATE OR REPLACE VIEW prov.{v} AS {body}")
    op.execute("DROP SCHEMA IF EXISTS bill CASCADE")
    op.execute("ALTER TABLE prov.outbox DROP COLUMN IF EXISTS attempts")
    op.execute("DROP TABLE IF EXISTS prov.staff")
    op.execute("DROP TABLE IF EXISTS prov.price_report")
    op.execute("DROP TABLE IF EXISTS prov.listing_request")
    op.execute("DELETE FROM ref.facility_provider_type WHERE source = 'nppes_taxonomy'")
    op.execute(
        "ALTER TABLE ref.facility_provider_type DROP CONSTRAINT facility_provider_type_source_check"
    )
    op.execute(
        "ALTER TABLE ref.facility_provider_type ADD CONSTRAINT facility_provider_type_source_check "
        "CHECK (source IN ('cms_facility_type', 'provider', 'reviewer'))"
    )
    op.execute("DELETE FROM src.reference_load WHERE dataset = 'nppes_offices'")
    _datasets(DATASETS_0016)
    op.execute("ALTER TABLE ref.facility DROP COLUMN taxonomy_codes")
