"""Provider accounts, provider homepages, reviews and privacy-safe counts.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-08

See docs/PROVIDER_PAGES_SPEC.md and D-050.

- prov.account / login_token / session: sign-in by one-time email link, plus an
  authenticator app code (TOTP) before anything public can change. Only
  SHA-256 hashes of tokens are stored.
- prov.membership: who may speak for a facility. Active only once verified
  (work email on the facility's reviewed website domain, or a person checked it).
- prov.profile / prov.media: the provider's homepage (about, links, hours, logo,
  photos). Every change is reviewed before it shows; one published version.
- prov.review (+ token, reply, report): reviews from people who confirmed a visit
  by a link from us (email) or from the provider (invite). Providers cannot
  remove reviews; a person decides on reports. Removed reviews are counted.
- prov.outbox: emails waiting to be sent. Nothing sends them until an email
  service is chosen (Q26).
- stats.*: daily counts only. No IP addresses, devices, accounts or exact
  locations are stored; searches are counted on a 0.1-degree grid (about 7 miles).

Roles: the public API role reads only the published_* views. A new portal role
(PS_PORTAL_ROLE, default ps_portal) may write to prov and stats tables only.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_URL = r"'^https?://[^\s/?#]+[^\s]*$'"

PORTAL_TABLES = [
    "prov.account",
    "prov.login_token",
    "prov.session",
    "prov.membership",
    "prov.profile",
    "prov.media",
    "prov.review",
    "prov.review_token",
    "prov.review_reply",
    "prov.review_report",
    "prov.outbox",
    "stats.facility_daily",
    "stats.search_daily",
    "stats.facility_service_daily",
    "prov.listing_price",
    "prov.offer",
    "prov.package",
    "prov.package_item",
]


def _role(env: str, default: str) -> str:
    role = os.environ.get(env, default)
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", role):
        raise ValueError(f"{env} is not a plain role name: {role!r}")
    return role


def upgrade() -> None:
    op.execute("""
    CREATE TABLE prov.account (
        id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        email            text NOT NULL UNIQUE
                         CHECK (email = lower(email) AND email ~ '^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$'),
        display_name     text CHECK (display_name IS NULL OR length(display_name) <= 80),
        totp_secret      text,
        totp_enabled_at  timestamptz,
        created_at       timestamptz NOT NULL DEFAULT now(),
        last_sign_in_at  timestamptz,
        disabled_at      timestamptz,
        CHECK (totp_enabled_at IS NULL OR totp_secret IS NOT NULL)
    )""")
    op.execute("""
    CREATE TABLE prov.login_token (
        token_hash  bytea PRIMARY KEY,
        account_id  uuid NOT NULL REFERENCES prov.account(id) ON DELETE CASCADE,
        expires_at  timestamptz NOT NULL,
        used_at     timestamptz,
        created_at  timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""
    CREATE TABLE prov.session (
        token_hash    bytea PRIMARY KEY,
        account_id    uuid NOT NULL REFERENCES prov.account(id) ON DELETE CASCADE,
        mfa_passed_at timestamptz,
        mfa_failures  smallint NOT NULL DEFAULT 0,
        created_at    timestamptz NOT NULL DEFAULT now(),
        last_seen_at  timestamptz NOT NULL DEFAULT now(),
        expires_at    timestamptz NOT NULL
    )""")
    op.execute("""
    CREATE TABLE prov.membership (
        account_id    uuid NOT NULL REFERENCES prov.account(id) ON DELETE CASCADE,
        facility_id   uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        role          text NOT NULL CHECK (role IN ('owner', 'editor', 'viewer')),
        status        text NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'active', 'rejected', 'removed')),
        note          text CHECK (note IS NULL OR length(note) <= 500),
        verified_via  text CHECK (verified_via IN ('email_domain', 'manual', 'invited')),
        verified_by   text,
        verified_at   timestamptz,
        created_at    timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (account_id, facility_id),
        CHECK (status <> 'active' OR (verified_via IS NOT NULL AND verified_by IS NOT NULL
                                      AND verified_at IS NOT NULL))
    )""")
    op.execute(f"""
    CREATE TABLE prov.profile (
        id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        facility_id    uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        status         text NOT NULL DEFAULT 'draft'
                       CHECK (status IN ('draft', 'pending_review', 'published',
                                         'rejected', 'superseded')),
        about          text CHECK (about IS NULL OR length(about) <= 2000),
        website_url    text CHECK (website_url IS NULL OR (website_url ~ {_URL}
                                                          AND length(website_url) <= 300)),
        booking_url    text CHECK (booking_url IS NULL OR (booking_url ~ {_URL}
                                                          AND length(booking_url) <= 300)),
        phone          text CHECK (phone IS NULL OR phone ~ '^[0-9+() .-]{{7,25}}$'),
        hours          jsonb CHECK (hours IS NULL OR jsonb_typeof(hours) = 'object'),
        languages      text[] NOT NULL DEFAULT '{{}}',
        accessibility  text[] NOT NULL DEFAULT '{{}}',
        insurance_note text CHECK (insurance_note IS NULL OR length(insurance_note) <= 500),
        social_urls    text[] NOT NULL DEFAULT '{{}}',
        submitted_by   uuid REFERENCES prov.account(id) ON DELETE SET NULL,
        submitted_at   timestamptz,
        reviewed_by    text,
        reviewed_at    timestamptz,
        review_note    text,
        created_at     timestamptz NOT NULL DEFAULT now(),
        updated_at     timestamptz NOT NULL DEFAULT now(),
        CHECK (cardinality(social_urls) <= 6),
        CHECK (status <> 'published' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
    )""")
    op.execute(
        "CREATE UNIQUE INDEX profile_one_published ON prov.profile (facility_id) "
        "WHERE status = 'published'"
    )
    op.execute(
        "CREATE UNIQUE INDEX profile_one_open ON prov.profile (facility_id) "
        "WHERE status IN ('draft', 'pending_review')"
    )
    op.execute("""
    CREATE TABLE prov.media (
        id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        facility_id   uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        kind          text NOT NULL CHECK (kind IN ('logo', 'photo')),
        object_key    text NOT NULL UNIQUE CHECK (object_key ~ '^media/[0-9a-f-]{36}/[0-9a-f-]{36}\\.(png|jpg|webp)$'),
        content_type  text NOT NULL CHECK (content_type IN ('image/png', 'image/jpeg', 'image/webp')),
        bytes         integer NOT NULL CHECK (bytes > 0 AND bytes <= 2097152),
        sha256        text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
        width         integer CHECK (width > 0),
        height        integer CHECK (height > 0),
        alt_text      text CHECK (alt_text IS NULL OR length(alt_text) <= 200),
        status        text NOT NULL DEFAULT 'pending_review'
                      CHECK (status IN ('pending_review', 'published', 'rejected', 'removed')),
        uploaded_by   uuid REFERENCES prov.account(id) ON DELETE SET NULL,
        reviewed_by   text,
        reviewed_at   timestamptz,
        created_at    timestamptz NOT NULL DEFAULT now(),
        CHECK (status <> 'published' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
    )""")
    op.execute(
        "CREATE UNIQUE INDEX media_one_logo ON prov.media (facility_id) "
        "WHERE kind = 'logo' AND status = 'published'"
    )
    op.execute("""
    CREATE TABLE prov.review_token (
        token_hash   bytea PRIMARY KEY,
        facility_id  uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        kind         text NOT NULL CHECK (kind IN ('email', 'provider_invite')),
        reviewer_hash bytea NOT NULL,
        created_by   uuid REFERENCES prov.account(id) ON DELETE SET NULL,
        expires_at   timestamptz NOT NULL,
        used_at      timestamptz,
        created_at   timestamptz NOT NULL DEFAULT now(),
        CHECK ((kind = 'provider_invite') = (created_by IS NOT NULL))
    )""")
    op.execute("""
    CREATE TABLE prov.review (
        id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        facility_id    uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        rating         smallint NOT NULL CHECK (rating BETWEEN 1 AND 5),
        title          text CHECK (title IS NULL OR length(title) <= 120),
        body           text NOT NULL CHECK (length(body) BETWEEN 20 AND 3000),
        price_matched  boolean,
        display_name   text NOT NULL CHECK (length(display_name) BETWEEN 1 AND 40),
        verification   text NOT NULL CHECK (verification IN ('email', 'provider_invite')),
        reviewer_hash  bytea NOT NULL,
        status         text NOT NULL DEFAULT 'pending_moderation'
                       CHECK (status IN ('pending_moderation', 'published', 'removed')),
        removal_reason text CHECK (removal_reason IN
                       ('off_topic', 'personal_information', 'hateful', 'spam',
                        'conflict_of_interest', 'not_a_patient', 'other')),
        moderated_by   text,
        moderated_at   timestamptz,
        created_at     timestamptz NOT NULL DEFAULT now(),
        published_at   timestamptz,
        UNIQUE (facility_id, reviewer_hash),
        CHECK (status <> 'published' OR (moderated_by IS NOT NULL AND published_at IS NOT NULL)),
        CHECK ((status = 'removed') = (removal_reason IS NOT NULL))
    )""")
    op.execute("""
    CREATE TABLE prov.review_reply (
        review_id    uuid PRIMARY KEY REFERENCES prov.review(id) ON DELETE CASCADE,
        body         text NOT NULL CHECK (length(body) BETWEEN 2 AND 1500),
        account_id   uuid REFERENCES prov.account(id) ON DELETE SET NULL,
        status       text NOT NULL DEFAULT 'pending_review'
                     CHECK (status IN ('pending_review', 'published', 'rejected')),
        reviewed_by  text,
        reviewed_at  timestamptz,
        created_at   timestamptz NOT NULL DEFAULT now(),
        CHECK (status <> 'published' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
    )""")
    op.execute("""
    CREATE TABLE prov.review_report (
        id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        review_id    uuid NOT NULL REFERENCES prov.review(id) ON DELETE CASCADE,
        reason       text NOT NULL CHECK (length(reason) BETWEEN 3 AND 500),
        account_id   uuid REFERENCES prov.account(id) ON DELETE SET NULL,
        created_at   timestamptz NOT NULL DEFAULT now(),
        resolved_by  text,
        resolved_at  timestamptz,
        outcome      text CHECK (outcome IN ('kept', 'removed'))
    )""")
    op.execute("""
    CREATE TABLE prov.outbox (
        id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        to_email    text NOT NULL,
        purpose     text NOT NULL CHECK (purpose IN ('sign_in', 'review_confirm', 'notice')),
        subject     text NOT NULL,
        body        text NOT NULL,
        created_at  timestamptz NOT NULL DEFAULT now(),
        sent_at     timestamptz,
        error       text
    )""")

    op.execute("CREATE SCHEMA IF NOT EXISTS stats")
    op.execute("""
    CREATE TABLE stats.facility_daily (
        day           date NOT NULL,
        facility_id   uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        metric        text NOT NULL CHECK (metric IN
                      ('page_view', 'search_impression', 'website_click', 'phone_click',
                       'directions_click', 'booking_click')),
        count         bigint NOT NULL CHECK (count >= 0),
        position_sum  bigint NOT NULL DEFAULT 0 CHECK (position_sum >= 0),
        PRIMARY KEY (day, facility_id, metric)
    )""")
    op.execute("""
    CREATE TABLE stats.search_daily (
        day          date NOT NULL,
        service_key  text NOT NULL CHECK (service_key ~ '^(svc:[a-z0-9-]{1,80}|code:[A-Z_]{2,12}:[0-9A-Za-z.-]{1,12})$'),
        place_key    text NOT NULL CHECK (place_key ~ '^grid:-?[0-9]{1,2}\\.[0-9],-?[0-9]{1,3}\\.[0-9]$'),
        geom         geography(Point, 4326) NOT NULL,
        count        bigint NOT NULL CHECK (count >= 0),
        PRIMARY KEY (day, service_key, place_key)
    )""")
    op.execute("""
    CREATE TABLE stats.facility_service_daily (
        day          date NOT NULL,
        facility_id  uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        service_key  text NOT NULL,
        impressions  bigint NOT NULL CHECK (impressions >= 0),
        PRIMARY KEY (day, facility_id, service_key)
    )""")
    op.execute("CREATE INDEX search_daily_geom_gix ON stats.search_daily USING gist (geom)")
    op.execute("CREATE INDEX facility_daily_facility ON stats.facility_daily (facility_id, day)")

    # What the public API may read: published rows only, without private columns.
    op.execute("""
    CREATE VIEW prov.published_profile AS
    SELECT facility_id, about, website_url, booking_url, phone, hours, languages,
           accessibility, insurance_note, social_urls, reviewed_at AS updated_at
    FROM prov.profile WHERE status = 'published'""")
    op.execute("""
    CREATE VIEW prov.published_media AS
    SELECT id, facility_id, kind, object_key, content_type, width, height, alt_text
    FROM prov.media WHERE status = 'published'""")
    op.execute("""
    CREATE VIEW prov.published_review AS
    SELECT r.id, r.facility_id, r.rating, r.title, r.body, r.price_matched, r.display_name,
           r.verification, r.published_at,
           CASE WHEN rr.status = 'published' THEN rr.body END AS reply_body,
           CASE WHEN rr.status = 'published' THEN rr.reviewed_at END AS reply_at
    FROM prov.review r LEFT JOIN prov.review_reply rr ON rr.review_id = r.id
    WHERE r.status = 'published'""")
    op.execute("""
    CREATE VIEW prov.review_counts AS
    SELECT facility_id,
           count(*) FILTER (WHERE status = 'published') AS published,
           count(*) FILTER (WHERE status = 'removed') AS removed
    FROM prov.review GROUP BY facility_id""")
    op.execute("""
    CREATE VIEW prov.claimed_facility AS
    SELECT DISTINCT facility_id FROM prov.membership WHERE status = 'active'""")

    api_role = _role("PS_API_ROLE", "ps_api")
    portal_role = _role("PS_PORTAL_ROLE", "ps_portal")
    views = (
        "prov.published_profile, prov.published_media, prov.published_review, "
        "prov.review_counts, prov.claimed_facility"
    )
    tables = ", ".join(PORTAL_TABLES)
    op.execute(f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{api_role}') THEN
            EXECUTE 'GRANT USAGE ON SCHEMA prov TO {api_role}';
            EXECUTE 'GRANT SELECT ON {views} TO {api_role}';
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{portal_role}') THEN
            EXECUTE 'GRANT USAGE ON SCHEMA prov, stats, ref TO {portal_role}';
            EXECUTE 'GRANT SELECT, INSERT, UPDATE ON {tables} TO {portal_role}';
            EXECUTE 'GRANT DELETE ON prov.session, prov.login_token TO {portal_role}';
            EXECUTE 'GRANT SELECT ON {views} TO {portal_role}';
            EXECUTE 'GRANT SELECT ON ref.facility, ref.procedure, ref.code, ref.zcta TO {portal_role}';
        END IF;
    END $$""")


def downgrade() -> None:
    for v in (
        "claimed_facility",
        "review_counts",
        "published_review",
        "published_media",
        "published_profile",
    ):
        op.execute(f"DROP VIEW IF EXISTS prov.{v}")
    op.execute("DROP SCHEMA IF EXISTS stats CASCADE")
    for t in (
        "outbox",
        "review_report",
        "review_reply",
        "review",
        "review_token",
        "media",
        "profile",
        "membership",
        "session",
        "login_token",
        "account",
    ):
        op.execute(f"DROP TABLE IF EXISTS prov.{t}")
